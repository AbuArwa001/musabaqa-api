import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.core.config import settings
from app.core.security import (
    create_institution_token, create_staff_token, verify_password,
    obscure_phone, obscure_email, normalize_ke_phone,
)
from app.crud.institutions import get_institution_by_email
from app.models.admin_user import AdminRole, AdminUser
from app.models.institution import Institution, InstitutionStatus
from app.models.otp import InstitutionOTP, OTPChannel
from app.models.student import Student
from app.schemas.auth import (
    TokenResponse, InstitutionLoginRequest, StaffLoginRequest,
    RequestOTPRequest, RequestOTPResponse, VerifyOTPRequest, VerifyOTPResponse,
)
from app.services.notifications import _send_at_sms, _send_resend_email

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


@router.post("/institution/request-otp", response_model=RequestOTPResponse)
async def request_institution_otp(
    data: RequestOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Dispatches a 6-digit OTP to the institution's contact (SMS or Email).
    For Option 3 (Fast-track portal login), validates the user's input against the stored contact.
    """
    institution = await db.get(Institution, data.institution_id)
    if not institution or institution.status == InstitutionStatus.REJECTED:
        raise HTTPException(status_code=404, detail="Madrasa or institution not found or not active.")

    channel_clean = data.channel.upper()
    if channel_clean not in ["SMS", "EMAIL"]:
        channel_clean = "SMS"

    # If verify_value is provided (Option 3 identity verification), validate it matches phone or email
    if data.verify_value and data.verify_value.strip():
        val = data.verify_value.strip().lower()
        matched = False

        # 1. Email check
        if val == institution.email.strip().lower():
            matched = True

        # 2. Phone check (compare normalized Kenyan phone numbers)
        if normalize_ke_phone(val) == normalize_ke_phone(institution.phone):
            matched = True

        if not matched:
            raise HTTPException(
                status_code=400,
                detail="The provided phone number or email does not match our roster records for this institution.",
            )

    destination = institution.email if channel_clean == "EMAIL" else institution.phone
    if not destination or not destination.strip():
        raise HTTPException(
            status_code=400,
            detail=f"No {channel_clean} destination on file for this institution.",
        )

    # Invalidate existing active OTPs for this institution
    existing_otps = (
        await db.execute(
            select(InstitutionOTP).where(
                InstitutionOTP.institution_id == institution.id,
                InstitutionOTP.is_used == False,
            )
        )
    ).scalars().all()
    for o in existing_otps:
        o.is_used = True

    # Generate 6-digit code
    code = f"{secrets.randbelow(900000) + 100000}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    otp_record = InstitutionOTP(
        institution_id=institution.id,
        code=code,
        channel=OTPChannel.EMAIL if channel_clean == "EMAIL" else OTPChannel.SMS,
        destination=destination,
        expires_at=expires_at,
        is_used=False,
    )
    db.add(otp_record)
    await db.commit()

    # Send message
    msg = f"Jamia Mosque Musabaqa 2026: Your verification code is {code}. Valid for 10 minutes. Do not share."
    try:
        if channel_clean == "EMAIL":
            await _send_resend_email(
                to=destination,
                subject="Jamia Musabaqa 2026 — Verification Code",
                body_text=msg,
            )
        else:
            await _send_at_sms(destination, msg)
    except Exception:
        pass

    masked_dest = obscure_email(destination) if channel_clean == "EMAIL" else obscure_phone(destination)

    return RequestOTPResponse(
        success=True,
        channel=channel_clean,
        destination_masked=masked_dest,
        message=f"Verification code sent via {channel_clean} to {masked_dest}",
        test_otp=code if settings.ENVIRONMENT != "production" else None,
    )


@router.post("/institution/verify-otp", response_model=VerifyOTPResponse)
async def verify_institution_otp(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Validates the 6-digit OTP code and issues a standard institution JWT session.
    """
    institution = await db.get(Institution, data.institution_id)
    if not institution or institution.status == InstitutionStatus.REJECTED:
        raise HTTPException(status_code=404, detail="Institution not found.")

    otp_record = (
        await db.execute(
            select(InstitutionOTP)
            .where(
                InstitutionOTP.institution_id == data.institution_id,
                InstitutionOTP.is_used == False,
            )
            .order_by(InstitutionOTP.created_at.desc())
        )
    ).scalars().first()

    if not otp_record:
        raise HTTPException(
            status_code=400,
            detail="No active verification code found. Please request a new code.",
        )

    now = datetime.now(timezone.utc)
    exp = otp_record.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        otp_record.is_used = True
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please request a new code.",
        )

    if otp_record.attempts >= 5:
        otp_record.is_used = True
        await db.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many incorrect attempts. Please request a new code.",
        )

    if otp_record.code != data.code.strip():
        otp_record.attempts += 1
        await db.commit()
        remaining = 5 - otp_record.attempts
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verification code. {remaining} attempt(s) remaining.",
        )

    # Validated! Mark as used
    otp_record.is_used = True
    await db.commit()

    # Get student statistics
    students = (
        await db.execute(
            select(Student).where(
                Student.institution_id == institution.id,
                Student.is_deleted == False,
            )
        )
    ).scalars().all()

    registered_cats = [s.category_id for s in students]
    token = create_institution_token(institution.id)

    return VerifyOTPResponse(
        access_token=token,
        token_type="bearer",
        scope="institution",
        institution_id=institution.id,
        institution_name=institution.name,
        active_students_count=len(students),
        max_students_allowed=4,
        registered_categories=registered_cats,
    )



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
    user: AdminUser = Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    """Refreshes staff session JWT and returns a newly extended token."""
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
