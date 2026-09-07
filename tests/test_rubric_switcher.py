import pytest
from datetime import datetime, timezone
from sqlmodel import select

from app.models.category import Category, CategoryGroup, ScoringCriteria, DeductionType
from app.models.round import Round, RoundType, RoundStatus, RoundJudgeAssignment, JudgeRole
from app.models.student import Student, StudentReviewStatus, Gender
from app.models.admin_user import AdminUser, AdminRole
from app.models.institution import Institution, InstitutionType, InstitutionStatus
from app.models.results import CompetitionSeasonSettings
from app.schemas.scoring import DeductionEventCreate
from app.crud.scoring import submit_deduction, get_judge_score_summary, get_official_sheet_data
from app.services.rubric_manager import get_current_rubric_mode, set_rubric_mode


@pytest.mark.asyncio
async def test_rubric_switching_and_calculations(db):
    # 1. Check initial mode
    mode = await get_current_rubric_mode(db)
    assert mode == "OFFICIAL_70_30"

    # 2. Switch to TRADITIONAL_TIERED
    new_mode = await set_rubric_mode(db, "TRADITIONAL_TIERED")
    assert new_mode == "TRADITIONAL_TIERED"
    assert await get_current_rubric_mode(db) == "TRADITIONAL_TIERED"

    # Verify criteria created for JUZ_30 (45 Hifdh, 25 Tajweed, 10 Tafsir, 20 Saut)
    crits_30 = (await db.execute(
        select(ScoringCriteria).where(ScoringCriteria.category_group == CategoryGroup.JUZ_30)
    )).scalars().all()
    crit_dict = {c.name_en: c.max_points for c in crits_30}
    assert crit_dict.get("Memorization") == 45.0
    assert crit_dict.get("Tajweed") == 25.0
    assert crit_dict.get("Tafsir") == 10.0
    assert crit_dict.get("Saut") == 20.0

    # Verify criteria for JUZ_10_15_20 (50 Hifdh, 30 Tajweed, 20 Saut)
    crits_20 = (await db.execute(
        select(ScoringCriteria).where(ScoringCriteria.category_group == CategoryGroup.JUZ_10_15_20)
    )).scalars().all()
    crit_dict_20 = {c.name_en: c.max_points for c in crits_20}
    assert crit_dict_20.get("Memorization") == 50.0
    assert crit_dict_20.get("Tajweed") == 30.0
    assert crit_dict_20.get("Saut") == 20.0

    # 3. Test scoring under TRADITIONAL_TIERED
    category = Category(
        name_en="Juz' 30 (Complete)", name_ar="الجزء الثلاثون",
        max_age=25, category_group=CategoryGroup.JUZ_30, display_order=4
    )
    db.add(category)
    await db.flush()

    inst = Institution(
        name="Markaz Test", type=InstitutionType.MADRASA, contact_person="Dir",
        phone="+254700000001", email="test@madrasa.test", password_hash="hash",
        status=InstitutionStatus.APPROVED
    )
    db.add(inst)
    await db.flush()

    student = Student(
        full_name="Ibrahim Ali", national_id="KE-2001", guardian_phone="+254700000001",
        dob=datetime(2008, 5, 5).date(), gender=Gender.MALE,
        institution_id=inst.id, category_id=category.id,
        review_status=StudentReviewStatus.APPROVED,
    )
    db.add(student)
    await db.flush()

    judge = AdminUser(name="Sheikh Omar", email="omar@judge.test", password_hash="hash", role=AdminRole.JUDGE)
    db.add(judge)
    await db.flush()

    round_ = Round(
        category_id=category.id, round_type=RoundType.PRELIMINARY, status=RoundStatus.ACTIVE,
        scheduled_at=datetime.now(timezone.utc)
    )
    db.add(round_)
    await db.flush()

    db.add(RoundJudgeAssignment(round_id=round_.id, admin_user_id=judge.id, judge_role=JudgeRole.REGULAR))
    await db.flush()

    # Find deduction types for Juz 30
    dts = (await db.execute(
        select(DeductionType, ScoringCriteria).join(
            ScoringCriteria, DeductionType.scoring_criteria_id == ScoringCriteria.id
        ).where(ScoringCriteria.category_group == CategoryGroup.JUZ_30)
    )).all()
    dt_map = {dt.name_en: dt for dt, crit in dts}

    # Submit deductions:
    # 1 Tanbeeh (-1.0)
    await submit_deduction(db, judge.id, DeductionEventCreate(
        round_id=round_.id, student_id=student.id,
        deduction_type_id=dt_map["Tanbeeh (Warning)"].id,
        question_number=1,
    ))
    # 1 Tajweed error (-0.5)
    await submit_deduction(db, judge.id, DeductionEventCreate(
        round_id=round_.id, student_id=student.id,
        deduction_type_id=dt_map["Tajweed Error"].id,
        question_number=1,
    ))
    # Tafsir deduction (-2.0 judge entered)
    await submit_deduction(db, judge.id, DeductionEventCreate(
        round_id=round_.id, student_id=student.id,
        deduction_type_id=dt_map["Tafsir Deduction"].id,
        question_number=1,
        amount=2.0,
    ))
    # Saut deduction (-1.5 judge entered)
    await submit_deduction(db, judge.id, DeductionEventCreate(
        round_id=round_.id, student_id=student.id,
        deduction_type_id=dt_map["Saut Deduction"].id,
        question_number=1,
        amount=1.5,
    ))

    # Verify score summary
    summary = await get_judge_score_summary(db, round_.id, student.id, judge.id)
    assert summary.rubric_mode == "TRADITIONAL_TIERED"
    assert summary.max_hifdh == 45.0
    assert summary.max_tajweed == 25.0
    assert summary.max_tafsir == 10.0
    assert summary.max_saut == 20.0
    assert summary.hifdh_score == 44.0      # 45 - 1.0
    assert summary.tajweed_score == 24.5    # 25 - 0.5
    assert summary.tafsir_score == 8.0      # 10 - 2.0
    assert summary.saut_score == 18.5       # 20 - 1.5
    assert summary.total_score == 95.0      # 44 + 24.5 + 8.0 + 18.5 = 95.0

    # 4. Switch back to OFFICIAL_70_30
    restored_mode = await set_rubric_mode(db, "OFFICIAL_70_30")
    assert restored_mode == "OFFICIAL_70_30"
    assert await get_current_rubric_mode(db) == "OFFICIAL_70_30"

    crits_30_restored = (await db.execute(
        select(ScoringCriteria).where(ScoringCriteria.category_group == CategoryGroup.JUZ_30)
    )).scalars().all()
    restored_dict = {c.name_en: c.max_points for c in crits_30_restored if c.max_points > 0}
    assert restored_dict.get("Memorization") == 70.0
    assert restored_dict.get("Tajweed") == 30.0
