from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.core.security import create_institution_token, create_staff_token, verify_password
from app.crud.institutions import get_institution_by_email
from app.models.admin_user import AdminRole, AdminUser
from app.schemas.auth import TokenResponse, InstitutionLoginRequest, StaffLoginRequest
from sqlmodel import select

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/institution/login", response_model=TokenResponse)
async def institution_login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Institution login — returns a JWT with scope='institution'."""
    inst = await get_institution_by_email(db, form.username)
    if not inst or not verify_password(form.password, inst.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_institution_token(inst.id)
    return TokenResponse(access_token=token, scope="institution")


@router.post("/staff/login", response_model=TokenResponse)
async def staff_login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Staff login — returns JWT with scope='staff', role, and judge assignment claims."""
    result = await db.execute(
        select(AdminUser).where(AdminUser.email == form.username, AdminUser.active == True)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # For judges: embed their assigned round/category IDs in the token
    assigned_round_ids: list[int] = []
    assigned_category_ids: list[int] = []
    if user.role == AdminRole.JUDGE:
        from app.models.round import RoundJudgeAssignment, Round
        assignments = (await db.execute(
            select(RoundJudgeAssignment, Round).join(
                Round, Round.id == RoundJudgeAssignment.round_id
            ).where(RoundJudgeAssignment.admin_user_id == user.id)
        )).all()
        assigned_round_ids = [a.RoundJudgeAssignment.round_id for a in assignments]
        assigned_category_ids = list({a.Round.category_id for a in assignments})

    token = create_staff_token(
        user_id=user.id,
        role=user.role.value,
        judge_role=user.judge_role.value if user.judge_role else None,
        assigned_round_ids=assigned_round_ids,
        assigned_category_ids=assigned_category_ids,
    )
    return TokenResponse(access_token=token, scope="staff")


@router.post("/staff/refresh", response_model=TokenResponse)
async def staff_refresh(
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    """Refreshes staff session JWT and returns a newly extended token."""
    user = await db.get(AdminUser, staff.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account inactive or not found")

    assigned_round_ids: list[int] = []
    assigned_category_ids: list[int] = []
    if user.role == AdminRole.JUDGE:
        from app.models.round import RoundJudgeAssignment, Round
        assignments = (await db.execute(
            select(RoundJudgeAssignment, Round).join(
                Round, Round.id == RoundJudgeAssignment.round_id
            ).where(RoundJudgeAssignment.admin_user_id == user.id)
        )).all()
        assigned_round_ids = [a.RoundJudgeAssignment.round_id for a in assignments]
        assigned_category_ids = list({a.Round.category_id for a in assignments})

    token = create_staff_token(
        user_id=user.id,
        role=user.role.value,
        judge_role=user.judge_role.value if user.judge_role else None,
        assigned_round_ids=assigned_round_ids,
        assigned_category_ids=assigned_category_ids,
    )
    return TokenResponse(access_token=token, scope="staff")
