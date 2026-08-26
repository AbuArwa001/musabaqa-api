from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.core.security import hash_password
from app.models.admin_user import AdminUser, AdminRole
from app.schemas.admin_user import AdminUserCreate, AdminUserRead, AdminUserUpdate

router = APIRouter(prefix="/admin-users", tags=["Admin Users"])


@router.post("/", response_model=AdminUserRead, status_code=201)
async def create_admin_user(
    data: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    existing = (await db.execute(select(AdminUser).where(AdminUser.email == data.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Email already in use")
    user = AdminUser(**data.model_dump(exclude={"password"}), password_hash=hash_password(data.password))
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()
    return user


@router.get("/", response_model=list[AdminUserRead])
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    return (await db.execute(select(AdminUser))).scalars().all()


@router.patch("/{user_id}", response_model=AdminUserRead)
async def update_admin_user(
    user_id: int,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    user = await db.get(AdminUser, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    await db.commit()
    return user
