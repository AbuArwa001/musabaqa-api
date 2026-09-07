import pytest
from datetime import datetime, timezone
from sqlmodel import select

from app.models.category import Category, CategoryGroup, ScoringCriteria, DeductionType
from app.models.round import Round, RoundType, RoundStatus, RoundJudgeAssignment
from app.models.student import Student, StudentReviewStatus, Gender
from app.models.admin_user import AdminUser, AdminRole
from app.models.institution import Institution, InstitutionType, InstitutionStatus
from app.schemas.scoring import DeductionEventCreate, RoundQuestionCreate
from app.crud.scoring import (
    submit_deduction, delete_deduction, upsert_round_question,
    get_judge_score_summary, get_official_sheet_data
)

@pytest.mark.asyncio
async def test_official_rubric_scoring_and_rules(db):
    # Setup Category (Juz 30 - 4 questions)
    category = Category(
        name_en="Juz' 30 (Complete)", name_ar="الجزء الثلاثون",
        max_age=25, category_group=CategoryGroup.JUZ_30, display_order=4
    )
    db.add(category)
    await db.flush()

    # Criteria: 70 Hifdh, 30 Tajweed
    crit_mem = ScoringCriteria(category_group=CategoryGroup.JUZ_30, name_en="Memorization", name_ar="الحفظ", max_points=70.0)
    crit_taj = ScoringCriteria(category_group=CategoryGroup.JUZ_30, name_en="Tajweed", name_ar="التجويد وحسن الصوت والأداء", max_points=30.0)
    db.add_all([crit_mem, crit_taj])
    await db.flush()

    # Deductions: Tanbeeh (1.0), Al-Fath (2.0), Al-Lahn (2.0), Tajweed (0.5)
    dt_tanbeeh = DeductionType(scoring_criteria_id=crit_mem.id, name_en="Tanbeeh (Warning)", name_ar="التنبيه", points_deducted=1.0)
    dt_fath = DeductionType(scoring_criteria_id=crit_mem.id, name_en="Al-Fath (Prompting)", name_ar="الفتح", points_deducted=2.0)
    dt_lahn = DeductionType(scoring_criteria_id=crit_mem.id, name_en="Al-Lahn (Vocalization Error)", name_ar="اللحن", points_deducted=2.0)
    dt_tajweed = DeductionType(scoring_criteria_id=crit_taj.id, name_en="Tajweed Error", name_ar="خطأ في التجويد", points_deducted=0.5)
    db.add_all([dt_tanbeeh, dt_fath, dt_lahn, dt_tajweed])
    await db.flush()

    # Judge
    judge = AdminUser(name="Sheikh Ahmad", email="ahmad@judge.test", password_hash="hash", role=AdminRole.JUDGE)
    db.add(judge)
    await db.flush()

    # Student & Institution
    inst = Institution(name="Markaz Anwaar", type=InstitutionType.MADRASA, contact_person="Dir", phone="+254700000000", email="anwaar@madrasa.test", password_hash="hash", status=InstitutionStatus.APPROVED)
    db.add(inst)
    await db.flush()

    student = Student(
        full_name="Musab Abdullah", national_id="KE-1001", guardian_phone="+254700000000",
        dob=datetime(2009, 1, 1).date(), gender=Gender.MALE,
        institution_id=inst.id, category_id=category.id,
        review_status=StudentReviewStatus.APPROVED,
    )
    db.add(student)
    await db.flush()

    # Round & Assignment
    round_ = Round(
        category_id=category.id, round_type=RoundType.PRELIMINARY, status=RoundStatus.ACTIVE,
        scheduled_at=datetime.now(timezone.utc)
    )
    db.add(round_)
    await db.flush()

    from app.models.round import JudgeRole
    db.add(RoundJudgeAssignment(round_id=round_.id, admin_user_id=judge.id, judge_role=JudgeRole.REGULAR))
    await db.flush()

    # Question 1: Save Envelope & Surah metadata
    await upsert_round_question(db, RoundQuestionCreate(
        round_id=round_.id, student_id=student.id, question_number=1,
        envelope_number="Envelope #14", surah_name="البقرة", ayah_from=1, ayah_to=25
    ))

    # Log 1 Tanbeeh in Q1 (-1.0)
    e1 = await submit_deduction(db, judge_id=judge.id, data=DeductionEventCreate(
        round_id=round_.id, student_id=student.id, deduction_type_id=dt_tanbeeh.id,
        question_number=1, amount=1.0
    ))
    assert e1.amount == 1.0
    assert e1.question_number == 1

    # Log 1 Tajweed error in Q1 (-0.5)
    await submit_deduction(db, judge_id=judge.id, data=DeductionEventCreate(
        round_id=round_.id, student_id=student.id, deduction_type_id=dt_tajweed.id,
        question_number=1, amount=0.5
    ))

    summary = await get_judge_score_summary(db, round_.id, student.id, judge.id)
    assert summary.hifdh_score == 69.0  # 70 - 1
    assert summary.tajweed_score == 29.5  # 30 - 0.5
    assert summary.total_score == 98.5
    assert summary.per_question[0].tanbeeh_count == 1
    assert summary.per_question[0].tajweed_count == 1
    assert summary.per_question[0].tanbeeh_limit_reached is False
    assert summary.per_question[0].surah_name == "البقرة"
    assert summary.per_question[0].envelope_number == "Envelope #14"

    # Test Rule 5: Log 2 more Tanbeeh in Q1 to reach 3
    await submit_deduction(db, judge_id=judge.id, data=DeductionEventCreate(
        round_id=round_.id, student_id=student.id, deduction_type_id=dt_tanbeeh.id,
        question_number=1, amount=1.0
    ))
    e3 = await submit_deduction(db, judge_id=judge.id, data=DeductionEventCreate(
        round_id=round_.id, student_id=student.id, deduction_type_id=dt_tanbeeh.id,
        question_number=1, amount=1.0
    ))
    
    summary_rule5 = await get_judge_score_summary(db, round_.id, student.id, judge.id)
    assert summary_rule5.per_question[0].tanbeeh_count == 3
    assert summary_rule5.per_question[0].tanbeeh_limit_reached is True

    # Test Undo: delete e3
    await delete_deduction(db, judge_id=judge.id, deduction_id=e3.id)
    summary_undone = await get_judge_score_summary(db, round_.id, student.id, judge.id)
    assert summary_undone.per_question[0].tanbeeh_count == 2
    assert summary_undone.per_question[0].tanbeeh_limit_reached is False

    # Test Official Sheet Data
    sheet = await get_official_sheet_data(db, round_.id, student.id, judge.id)
    assert sheet.student_name == "Musab Abdullah"
    assert sheet.institution_name == "Markaz Anwaar"
    assert sheet.branch_number == 30
    assert len(sheet.questions) == 4
    assert sheet.final_hifdh_score == 68.0  # 70 - 2
    assert sheet.final_tajweed_score == 29.5  # 30 - 0.5
    assert sheet.final_score == 97.5
