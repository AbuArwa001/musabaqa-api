from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.results import RoundResult
from app.schemas.results import RoundResultRead

router = APIRouter(prefix="/results", tags=["Results"])


@router.get("/rounds/{round_id}", response_model=list[RoundResultRead])
async def get_round_results(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return (await db.execute(
        select(RoundResult).where(RoundResult.round_id == round_id)
        .order_by(RoundResult.rank.asc().nulls_last())
    )).scalars().all()


@router.get("/students/{student_id}", response_model=list[RoundResultRead])
async def get_student_results(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return (await db.execute(
        select(RoundResult).where(RoundResult.student_id == student_id)
    )).scalars().all()
