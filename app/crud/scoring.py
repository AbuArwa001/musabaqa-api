"""
Scoring CRUD — deduction submission, question tracking, undo, and official sheet generation.
"""

from collections import defaultdict
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.models.category import DeductionType, ScoringCriteria, Category
from app.models.round import RoundJudgeAssignment, Round
from app.models.scoring import DeductionEvent, RoundQuestion
from app.models.student import Student
from app.models.institution import Institution
from app.models.admin_user import AdminUser, AdminRole
from app.schemas.scoring import (
    DeductionEventCreate,
    JudgeScoreSummary,
    QuestionScoreBreakdown,
    RoundQuestionCreate,
    OfficialSheetRead,
)


async def submit_deduction(
    db: AsyncSession, judge_id: int, data: DeductionEventCreate
) -> DeductionEvent:
    # Validate judge is assigned to this round
    assignment = (await db.execute(
        select(RoundJudgeAssignment).where(
            RoundJudgeAssignment.round_id == data.round_id,
            RoundJudgeAssignment.admin_user_id == judge_id,
        )
    )).scalar_one_or_none()
    if not assignment:
        raise HTTPException(403, "You are not assigned to this round")

    # Validate round is ACTIVE
    round_ = await db.get(Round, data.round_id)
    if not round_ or round_.status.value != "ACTIVE":
        raise HTTPException(409, "Round is not in ACTIVE status")

    # Resolve deduction type and amount
    dt = await db.get(DeductionType, data.deduction_type_id)
    if not dt:
        raise HTTPException(404, "DeductionType not found")

    if dt.points_deducted is not None:
        amount = dt.points_deducted
    else:
        if data.amount is None:
            raise HTTPException(
                422,
                f"DeductionType '{dt.name_en}' requires a judge-entered amount (points_deducted is null)"
            )
        amount = data.amount

    event = DeductionEvent(
        round_id=data.round_id,
        student_id=data.student_id,
        judge_id=judge_id,
        deduction_type_id=data.deduction_type_id,
        question_number=data.question_number or 1,
        amount=amount,
        note=data.note,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


async def delete_deduction(
    db: AsyncSession, judge_id: int, deduction_id: int
) -> DeductionEvent:
    """Allows a judge to undo/revert their own deduction event."""
    event = await db.get(DeductionEvent, deduction_id)
    if not event:
        raise HTTPException(404, "Deduction not found")

    user = await db.get(AdminUser, judge_id)
    is_privileged = user and user.role in (AdminRole.SUPERADMIN, AdminRole.MODERATOR)
    if event.judge_id != judge_id and not is_privileged:
        raise HTTPException(403, "Cannot delete another judge's deduction")

    await db.delete(event)
    await db.flush()
    return event


async def upsert_round_question(
    db: AsyncSession, data: RoundQuestionCreate
) -> RoundQuestion:
    """Saves or updates Surah, Ayah range, or envelope number for a contestant question."""
    existing = (await db.execute(
        select(RoundQuestion).where(
            RoundQuestion.round_id == data.round_id,
            RoundQuestion.student_id == data.student_id,
            RoundQuestion.question_number == data.question_number,
        )
    )).scalar_one_or_none()

    if existing:
        if data.envelope_number is not None:
            existing.envelope_number = data.envelope_number
        if data.surah_name is not None:
            existing.surah_name = data.surah_name
        if data.ayah_from is not None:
            existing.ayah_from = data.ayah_from
        if data.ayah_to is not None:
            existing.ayah_to = data.ayah_to
        db.add(existing)
        await db.flush()
        await db.refresh(existing)
        return existing

    rq = RoundQuestion(
        round_id=data.round_id,
        student_id=data.student_id,
        question_number=data.question_number,
        envelope_number=data.envelope_number,
        surah_name=data.surah_name,
        ayah_from=data.ayah_from,
        ayah_to=data.ayah_to,
    )
    db.add(rq)
    await db.flush()
    await db.refresh(rq)
    return rq


async def get_round_questions(
    db: AsyncSession, round_id: int, student_id: int
) -> list[RoundQuestion]:
    result = await db.execute(
        select(RoundQuestion)
        .where(
            RoundQuestion.round_id == round_id,
            RoundQuestion.student_id == student_id,
        )
        .order_by(RoundQuestion.question_number)
    )
    return result.scalars().all()


async def get_all_assigned_judge_ids(db: AsyncSession, round_id: int) -> list[int]:
    result = await db.execute(
        select(RoundJudgeAssignment.admin_user_id).where(
            RoundJudgeAssignment.round_id == round_id
        )
    )
    return result.scalars().all()


async def get_judges_who_submitted(
    db: AsyncSession, round_id: int, student_id: int
) -> list[int]:
    result = await db.execute(
        select(DeductionEvent.judge_id)
        .where(
            DeductionEvent.round_id == round_id,
            DeductionEvent.student_id == student_id,
        )
        .distinct()
    )
    return result.scalars().all()


async def all_judges_submitted(
    db: AsyncSession, round_id: int, student_id: int
) -> bool:
    assigned = set(await get_all_assigned_judge_ids(db, round_id))
    submitted = set(await get_judges_who_submitted(db, round_id, student_id))
    return assigned == submitted and len(assigned) > 0


async def get_judge_deductions_for_student(
    db: AsyncSession, round_id: int, student_id: int, judge_id: int
) -> list[DeductionEvent]:
    result = await db.execute(
        select(DeductionEvent).where(
            DeductionEvent.round_id == round_id,
            DeductionEvent.student_id == student_id,
            DeductionEvent.judge_id == judge_id,
        )
    )
    return result.scalars().all()


def _get_branch_info(category_name: str) -> tuple[int, int]:
    """Returns (branch_number, num_questions)."""
    lower = category_name.lower()
    if "30" in lower:
        return 30, 4
    elif "20" in lower:
        return 20, 4
    elif "10" in lower or "15" in lower:
        return 10, 3
    elif "5" in lower:
        return 5, 3
    return 30, 4


async def get_judge_score_summary(
    db: AsyncSession, round_id: int, student_id: int, requesting_judge_id: int
) -> JudgeScoreSummary:
    from app.services.rubric_manager import get_current_rubric_mode
    rubric_mode = await get_current_rubric_mode(db)

    all_submitted = await all_judges_submitted(db, round_id, student_id)
    events = await get_judge_deductions_for_student(db, round_id, student_id, requesting_judge_id)

    student = await db.get(Student, student_id)
    category = await db.get(Category, student.category_id) if student else None
    cat_name = category.name_en if category else "30"
    branch_num, num_questions = _get_branch_info(cat_name)

    # Determine max points based on rubric_mode and category
    if rubric_mode == "TRADITIONAL_TIERED":
        if "30" in cat_name:
            max_hifdh, max_tajweed, max_tafsir, max_saut = 45.0, 25.0, 10.0, 20.0
        else:
            max_hifdh, max_tajweed, max_tafsir, max_saut = 50.0, 30.0, 0.0, 20.0
    else:
        max_hifdh, max_tajweed, max_tafsir, max_saut = 70.0, 30.0, 0.0, 0.0

    # Fetch deduction types to classify them
    dt_rows = (await db.execute(select(DeductionType, ScoringCriteria).join(
        ScoringCriteria, DeductionType.scoring_criteria_id == ScoringCriteria.id
    ))).all()
    dt_map = {dt.id: (dt, crit) for dt, crit in dt_rows}

    # Fetch stored question info
    q_records = await get_round_questions(db, round_id, student_id)
    q_map = {q.question_number: q for q in q_records}

    question_allotment = round(100.0 / num_questions, 2)

    per_question: list[QuestionScoreBreakdown] = []
    total_hifdh_deductions = 0.0
    total_tajweed_deductions = 0.0
    total_saut_deductions = 0.0
    total_tafsir_deductions = 0.0

    for q_idx in range(1, num_questions + 1):
        q_meta = q_map.get(q_idx)
        q_events = [e for e in events if getattr(e, "question_number", 1) == q_idx]

        tanbeeh_cnt = 0
        fath_cnt = 0
        lahn_cnt = 0
        tajweed_cnt = 0
        h_deduct = 0.0
        t_deduct = 0.0
        s_deduct = 0.0
        tf_deduct = 0.0

        for e in q_events:
            dt_tuple = dt_map.get(e.deduction_type_id)
            dt_name_en = dt_tuple[0].name_en.lower() if dt_tuple else ""
            dt_name_ar = dt_tuple[0].name_ar if dt_tuple else ""
            crit_name = dt_tuple[1].name_en.lower() if dt_tuple else ""

            if "tanbeeh" in dt_name_en or "تنبيه" in dt_name_ar or (crit_name == "memorization" and e.amount == 1.0):
                tanbeeh_cnt += 1
                h_deduct += e.amount
            elif "fath" in dt_name_en or "الفتح" in dt_name_ar or "فتح" in dt_name_ar:
                fath_cnt += 1
                h_deduct += e.amount
            elif "lahn" in dt_name_en or "اللحن" in dt_name_ar or "لحن" in dt_name_ar:
                lahn_cnt += 1
                h_deduct += e.amount
            elif "tafsir" in crit_name or "تفسير" in dt_name_ar or "tafsir" in dt_name_en:
                tf_deduct += e.amount
            elif "saut" in crit_name or "voice" in crit_name or "صوت" in dt_name_ar or "saut" in dt_name_en:
                s_deduct += e.amount
            elif "tajweed" in crit_name or "تجويد" in dt_name_ar or "tajweed" in dt_name_en or e.amount == 0.5:
                tajweed_cnt += 1
                t_deduct += e.amount
            else:
                if "memorization" in crit_name:
                    h_deduct += e.amount
                elif "saut" in crit_name:
                    s_deduct += e.amount
                elif "tafsir" in crit_name:
                    tf_deduct += e.amount
                else:
                    t_deduct += e.amount

        total_q_deduct = h_deduct + t_deduct + s_deduct + tf_deduct
        total_hifdh_deductions += h_deduct
        total_tajweed_deductions += t_deduct
        total_saut_deductions += s_deduct
        total_tafsir_deductions += tf_deduct

        q_score = max(0.0, round(question_allotment - total_q_deduct, 2))

        per_question.append(QuestionScoreBreakdown(
            question_number=q_idx,
            surah_name=q_meta.surah_name if q_meta and q_meta.surah_name else "",
            ayah_from=q_meta.ayah_from if q_meta else None,
            ayah_to=q_meta.ayah_to if q_meta else None,
            envelope_number=q_meta.envelope_number if q_meta else None,
            tanbeeh_count=tanbeeh_cnt,
            fath_count=fath_cnt,
            lahn_count=lahn_cnt,
            tajweed_count=tajweed_cnt,
            hifdh_deductions=round(h_deduct, 2),
            tajweed_deductions=round(t_deduct, 2),
            saut_deductions=round(s_deduct, 2),
            tafsir_deductions=round(tf_deduct, 2),
            total_deductions=round(total_q_deduct, 2),
            question_allotment=question_allotment,
            question_score=q_score,
            tanbeeh_limit_reached=(tanbeeh_cnt >= 3),
        ))

    hifdh_score = max(0.0, round(max_hifdh - total_hifdh_deductions, 2))
    tajweed_score = max(0.0, round(max_tajweed - total_tajweed_deductions, 2))
    saut_score = max(0.0, round(max_saut - total_saut_deductions, 2)) if max_saut > 0 else 0.0
    tafsir_score = max(0.0, round(max_tafsir - total_tafsir_deductions, 2)) if max_tafsir > 0 else 0.0
    total = round(hifdh_score + tajweed_score + saut_score + tafsir_score, 2)

    user = await db.get(AdminUser, requesting_judge_id)
    is_moderator = user and user.role in (AdminRole.SUPERADMIN, AdminRole.MODERATOR)

    panel_score = None
    if all_submitted or is_moderator:
        all_judge_ids = await get_all_assigned_judge_ids(db, round_id)
        judge_totals = []
        for jid in all_judge_ids:
            j_events = await get_judge_deductions_for_student(db, round_id, student_id, jid)
            j_h_deduct = 0.0
            j_t_deduct = 0.0
            j_s_deduct = 0.0
            j_tf_deduct = 0.0
            for e in j_events:
                dt_tuple = dt_map.get(e.deduction_type_id)
                crit_name = dt_tuple[1].name_en.lower() if dt_tuple else ""
                dt_name_en = dt_tuple[0].name_en.lower() if dt_tuple else ""
                if "tanbeeh" in dt_name_en or "fath" in dt_name_en or "lahn" in dt_name_en or "memorization" in crit_name:
                    j_h_deduct += e.amount
                elif "tafsir" in crit_name:
                    j_tf_deduct += e.amount
                elif "saut" in crit_name or "voice" in crit_name:
                    j_s_deduct += e.amount
                elif "tajweed" in crit_name or e.amount == 0.5:
                    j_t_deduct += e.amount
                else:
                    j_h_deduct += e.amount
            j_score = (
                max(0.0, max_hifdh - j_h_deduct) +
                max(0.0, max_tajweed - j_t_deduct) +
                (max(0.0, max_saut - j_s_deduct) if max_saut > 0 else 0.0) +
                (max(0.0, max_tafsir - j_tf_deduct) if max_tafsir > 0 else 0.0)
            )
            judge_totals.append(round(j_score, 2))
        panel_score = round(sum(judge_totals) / len(judge_totals), 2) if judge_totals else None

        if is_moderator and panel_score is not None:
            total = panel_score

    per_crit = {
        "Memorization": hifdh_score,
        "Tajweed": tajweed_score,
    }
    if max_saut > 0:
        per_crit["Saut"] = saut_score
    if max_tafsir > 0:
        per_crit["Tafsir"] = tafsir_score

    return JudgeScoreSummary(
        student_id=student_id,
        round_id=round_id,
        judge_id=requesting_judge_id,
        rubric_mode=rubric_mode,
        hifdh_score=hifdh_score,
        tajweed_score=tajweed_score,
        saut_score=saut_score,
        tafsir_score=tafsir_score,
        max_hifdh=max_hifdh,
        max_tajweed=max_tajweed,
        max_saut=max_saut,
        max_tafsir=max_tafsir,
        per_criterion_score=per_crit,
        total_score=total,
        per_question=per_question,
        all_judges_submitted=all_submitted,
        panel_score=panel_score,
    )


async def get_official_sheet_data(
    db: AsyncSession, round_id: int, student_id: int, requesting_judge_id: int
) -> OfficialSheetRead:
    summary = await get_judge_score_summary(db, round_id, student_id, requesting_judge_id)
    student = await db.get(Student, student_id)
    institution = await db.get(Institution, student.institution_id) if student and student.institution_id else None
    category = await db.get(Category, student.category_id) if student and student.category_id else None
    judge = await db.get(AdminUser, requesting_judge_id)

    cat_name = category.name_en if category else "30"
    branch_num, _ = _get_branch_info(cat_name)

    total_h_deduct = sum(q.hifdh_deductions for q in summary.per_question)
    total_t_deduct = sum(q.tajweed_deductions for q in summary.per_question)
    total_s_deduct = sum(q.saut_deductions for q in summary.per_question)
    total_tf_deduct = sum(q.tafsir_deductions for q in summary.per_question)

    return OfficialSheetRead(
        round_id=round_id,
        student_id=student_id,
        student_name=student.full_name if student else "Unknown",
        nationality=getattr(student, "nationality", "كينية") or "كينية",
        age=student.age if hasattr(student, "age") else 17,
        institution_name=institution.name if institution else "—",
        branch_name_en=category.name_en if category else "Juz 30",
        branch_name_ar=category.name_ar if category else "الجزء الثلاثون",
        branch_number=branch_num,
        venue_ar="مسجد الجامع نيروبي",
        venue_en="Jamia Mosque Nairobi",
        date_str=datetime.now(timezone.utc).strftime("%Y/%m/%d"),
        judge_name=judge.name if judge else "المحكّم",
        judge_id=requesting_judge_id,
        rubric_mode=summary.rubric_mode,
        questions=summary.per_question,
        total_hifdh_deduction=total_h_deduct,
        total_tajweed_deduction=total_t_deduct,
        total_saut_deduction=total_s_deduct,
        total_tafsir_deduction=total_tf_deduct,
        final_hifdh_score=summary.hifdh_score,
        final_tajweed_score=summary.tajweed_score,
        final_saut_score=summary.saut_score,
        final_tafsir_score=summary.tafsir_score,
        max_hifdh=summary.max_hifdh,
        max_tajweed=summary.max_tajweed,
        max_saut=summary.max_saut,
        max_tafsir=summary.max_tafsir,
        final_score=summary.total_score,
        all_judges_submitted=summary.all_judges_submitted,
        panel_score=summary.panel_score,
    )

