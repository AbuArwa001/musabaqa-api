"""
Scoring CRUD — deduction submission and score visibility gating.

Judge score visibility rule:
  A judge may NOT see other judges' scores for the same student+round
  until ALL assigned judges for that round have submitted at least one
  deduction or explicitly marked their scoring complete.
  Enforced server-side in get_judge_score_summary().
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.models.category import DeductionType, ScoringCriteria
from app.models.round import RoundJudgeAssignment, Round
from app.models.scoring import DeductionEvent
from app.schemas.scoring import DeductionEventCreate, JudgeScoreSummary


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
        # Fixed amount — ignore user-supplied amount
        amount = dt.points_deducted
    else:
        # Judge-entered amount is required
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
        amount=amount,
        note=data.note,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event


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


async def get_judge_score_summary(
    db: AsyncSession, round_id: int, student_id: int, requesting_judge_id: int
) -> JudgeScoreSummary:
    """
    Returns the requesting judge's own score.
    panel_score is ONLY included when all judges have submitted (enforced here).
    """
    all_submitted = await all_judges_submitted(db, round_id, student_id)
    events = await get_judge_deductions_for_student(db, round_id, student_id, requesting_judge_id)

    # Compute per-criterion score for requesting judge
    from collections import defaultdict
    criterion_deductions: dict[int, float] = defaultdict(float)
    for e in events:
        criterion_deductions[e.deduction_type_id] += e.amount

    # Fetch criteria maxes
    criteria_result = await db.execute(
        select(ScoringCriteria, DeductionType).join(
            DeductionType, DeductionType.scoring_criteria_id == ScoringCriteria.id
        )
    )
    # Group by criterion
    crit_max: dict[int, tuple[str, float]] = {}  # criteria_id -> (name_en, max_points)
    dt_to_crit: dict[int, int] = {}  # deduction_type_id -> scoring_criteria_id
    for crit, dt in criteria_result.all():
        crit_max[crit.id] = (crit.name_en, crit.max_points)
        dt_to_crit[dt.id] = crit.id

    per_criterion: dict[str, float] = {}
    total = 0.0
    for crit_id, (name_en, max_pts) in crit_max.items():
        total_deducted = sum(
            amount for dt_id, amount in criterion_deductions.items()
            if dt_to_crit.get(dt_id) == crit_id
        )
        score = max(0.0, max_pts - total_deducted)  # Floor at 0 per criterion
        per_criterion[name_en] = score
        total += score

    panel_score = None
    if all_submitted:
        # Compute panel average from all judges
        all_judge_ids = await get_all_assigned_judge_ids(db, round_id)
        judge_totals = []
        for jid in all_judge_ids:
            j_events = await get_judge_deductions_for_student(db, round_id, student_id, jid)
            j_deductions: dict[int, float] = defaultdict(float)
            for e in j_events:
                j_deductions[e.deduction_type_id] += e.amount
            j_total = 0.0
            for crit_id, (_, max_pts) in crit_max.items():
                deducted = sum(
                    amt for dt_id, amt in j_deductions.items()
                    if dt_to_crit.get(dt_id) == crit_id
                )
                j_total += max(0.0, max_pts - deducted)
            judge_totals.append(j_total)
        panel_score = sum(judge_totals) / len(judge_totals) if judge_totals else None

    return JudgeScoreSummary(
        student_id=student_id,
        round_id=round_id,
        judge_id=requesting_judge_id,
        per_criterion_score=per_criterion,
        total_score=total,
        all_judges_submitted=all_submitted,
        panel_score=panel_score,
    )
