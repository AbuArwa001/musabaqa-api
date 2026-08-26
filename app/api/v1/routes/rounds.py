from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud import rounds as crud
from app.models.admin_user import AdminRole
from app.models.round import RoundStatus
from app.schemas.round import (
    RoundCreate, RoundRead, RoundUpdate,
    JudgeAssignmentCreate, JudgeAssignmentRead,
)

router = APIRouter(prefix="/rounds", tags=["Rounds"])


@router.post("/", response_model=RoundRead, status_code=201)
async def create_round(
    data: RoundCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    r = await crud.create_round(db, data)
    await db.commit()
    return r


@router.get("/", response_model=list[RoundRead])
async def list_rounds(
    category_id: int | None = None,
    status: RoundStatus | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    return await crud.list_rounds(db, category_id=category_id, status=status)


@router.get("/{round_id}", response_model=RoundRead)
async def get_round(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    return await crud.get_round(db, round_id)


@router.patch("/{round_id}", response_model=RoundRead)
async def update_round(
    round_id: int,
    data: RoundUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    r = await crud.update_round(db, round_id, data)
    await db.commit()
    return r


@router.post("/{round_id}/judges", response_model=JudgeAssignmentRead, status_code=201)
async def assign_judge(
    round_id: int,
    data: JudgeAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    assignment = await crud.assign_judge(db, round_id, data)
    await db.commit()
    return assignment


@router.get("/{round_id}/judges", response_model=list[JudgeAssignmentRead])
async def get_judges(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    return await crud.get_round_assignments(db, round_id)


@router.post("/{round_id}/start", response_model=RoundRead)
async def start_round(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """
    Validates judge panel composition before transitioning to ACTIVE.
    PRELIMINARY: 3 REGULAR, 0 GUEST_NEUTRAL
    FINAL: 3 REGULAR + 1 GUEST_NEUTRAL
    Returns 422 if composition is wrong.
    """
    r = await crud.start_round(db, round_id)
    await db.commit()
    return r


@router.post("/{round_id}/complete", response_model=RoundRead)
async def complete_round(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    r = await crud.complete_round(db, round_id)
    await db.commit()
    return r
