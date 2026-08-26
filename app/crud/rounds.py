"""
Round CRUD — enforces judge panel composition before ACTIVE transition.

PRELIMINARY: exactly 3 REGULAR judges, 0 GUEST_NEUTRAL
FINAL:       exactly 3 REGULAR + 1 GUEST_NEUTRAL = 4 total

Validation happens here, not at the frontend layer.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.round import Round, RoundJudgeAssignment, RoundType, RoundStatus, JudgeRole
from app.models.admin_user import AdminUser, AdminRole
from app.schemas.round import RoundCreate, RoundUpdate, JudgeAssignmentCreate


async def get_round(db: AsyncSession, round_id: int) -> Round:
    r = await db.get(Round, round_id)
    if not r:
        raise HTTPException(404, "Round not found")
    return r


async def list_rounds(
    db: AsyncSession,
    category_id: int | None = None,
    status: RoundStatus | None = None,
) -> list[Round]:
    q = select(Round)
    if category_id:
        q = q.where(Round.category_id == category_id)
    if status:
        q = q.where(Round.status == status)
    return (await db.execute(q)).scalars().all()


async def create_round(db: AsyncSession, data: RoundCreate) -> Round:
    r = Round(**data.model_dump())
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return r


async def update_round(db: AsyncSession, round_id: int, data: RoundUpdate) -> Round:
    r = await get_round(db, round_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return r


async def assign_judge(
    db: AsyncSession, round_id: int, data: JudgeAssignmentCreate
) -> RoundJudgeAssignment:
    # Validate assigned user is a JUDGE
    user = await db.get(AdminUser, data.admin_user_id)
    if not user or user.role != AdminRole.JUDGE:
        raise HTTPException(422, "Assigned user must have role=JUDGE")

    assignment = RoundJudgeAssignment(round_id=round_id, **data.model_dump())
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


async def get_round_assignments(
    db: AsyncSession, round_id: int
) -> list[RoundJudgeAssignment]:
    result = await db.execute(
        select(RoundJudgeAssignment).where(RoundJudgeAssignment.round_id == round_id)
    )
    return result.scalars().all()


def _validate_panel(round_type: RoundType, assignments: list[RoundJudgeAssignment]) -> None:
    """
    Enforce panel composition rules:
      PRELIMINARY: exactly 3 REGULAR, 0 GUEST_NEUTRAL
      FINAL:       exactly 3 REGULAR + 1 GUEST_NEUTRAL
    Raises HTTPException if invalid.
    """
    regulars = [a for a in assignments if a.judge_role == JudgeRole.REGULAR]
    guests = [a for a in assignments if a.judge_role == JudgeRole.GUEST_NEUTRAL]

    if round_type == RoundType.PRELIMINARY:
        if len(regulars) != 3 or len(guests) != 0:
            raise HTTPException(
                422,
                f"PRELIMINARY round requires exactly 3 REGULAR judges and 0 GUEST_NEUTRAL. "
                f"Currently: {len(regulars)} REGULAR, {len(guests)} GUEST_NEUTRAL."
            )
    elif round_type == RoundType.FINAL:
        if len(regulars) != 3 or len(guests) != 1:
            raise HTTPException(
                422,
                f"FINAL round requires exactly 3 REGULAR + 1 GUEST_NEUTRAL (4 total). "
                f"Currently: {len(regulars)} REGULAR, {len(guests)} GUEST_NEUTRAL."
            )


async def start_round(db: AsyncSession, round_id: int) -> Round:
    """Validate panel composition, then set status=ACTIVE."""
    r = await get_round(db, round_id)
    if r.status != RoundStatus.PENDING:
        raise HTTPException(409, f"Round is already {r.status.value}")

    assignments = await get_round_assignments(db, round_id)
    _validate_panel(r.round_type, assignments)

    r.status = RoundStatus.ACTIVE
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return r


async def complete_round(db: AsyncSession, round_id: int) -> Round:
    r = await get_round(db, round_id)
    if r.status != RoundStatus.ACTIVE:
        raise HTTPException(409, "Only ACTIVE rounds can be completed")
    r.status = RoundStatus.COMPLETED
    db.add(r)
    await db.flush()
    await db.refresh(r)
    return r
