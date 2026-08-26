from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.security import hash_password
from app.models.institution import Institution, InstitutionStatus
from app.schemas.institution import InstitutionCreate, InstitutionUpdate


async def get_institution(db: AsyncSession, institution_id: int) -> Institution:
    inst = await db.get(Institution, institution_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    return inst


async def get_institution_by_email(db: AsyncSession, email: str) -> Institution | None:
    result = await db.execute(select(Institution).where(Institution.email == email))
    return result.scalar_one_or_none()


async def list_institutions(
    db: AsyncSession,
    status: InstitutionStatus | None = None,
    region_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Institution]:
    q = select(Institution)
    if status:
        q = q.where(Institution.status == status)
    if region_id:
        q = q.where(Institution.region_id == region_id)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


async def create_institution(db: AsyncSession, data: InstitutionCreate) -> Institution:
    existing = await get_institution_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    inst = Institution(
        **data.model_dump(exclude={"password"}),
        password_hash=hash_password(data.password),
    )
    db.add(inst)
    await db.flush()
    await db.refresh(inst)
    return inst


async def update_institution(
    db: AsyncSession, institution_id: int, data: InstitutionUpdate
) -> Institution:
    inst = await get_institution(db, institution_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(inst, field, value)
    db.add(inst)
    await db.flush()
    await db.refresh(inst)
    return inst


async def approve_institution(db: AsyncSession, institution_id: int) -> Institution:
    inst = await get_institution(db, institution_id)
    inst.status = InstitutionStatus.APPROVED
    inst.rejection_reason = None
    db.add(inst)
    await db.flush()
    await db.refresh(inst)
    return inst


async def reject_institution(
    db: AsyncSession, institution_id: int, reason: str
) -> Institution:
    inst = await get_institution(db, institution_id)
    inst.status = InstitutionStatus.REJECTED
    inst.rejection_reason = reason
    db.add(inst)
    await db.flush()
    await db.refresh(inst)
    return inst
