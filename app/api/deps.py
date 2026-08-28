"""
FastAPI dependency injection.

Two separate auth flows:
  - get_current_institution: validates institution-scoped JWT
  - get_current_staff: validates staff-scoped JWT
  - require_role(*roles): role-based access control for staff endpoints
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_token
from app.models.admin_user import AdminRole, AdminUser
from app.models.institution import Institution

# Two separate OAuth2 schemes — institutions and staff never share a token
institution_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/institution/login")
staff_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/staff/login")


async def get_db() -> AsyncSession:
    async for session in get_session():
        yield session


async def get_current_institution(
    token: str = Depends(institution_oauth2),
    db: AsyncSession = Depends(get_db),
) -> Institution:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired institution token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("scope") != "institution":
            raise credentials_exc
        institution_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise credentials_exc

    inst = await db.get(Institution, institution_id)
    if not inst:
        raise credentials_exc
    return inst


async def get_current_staff(
    token: str = Depends(staff_oauth2),
    db: AsyncSession = Depends(get_db),
) -> tuple[AdminUser, dict]:
    """Returns (admin_user, token_payload). Payload carries role + assignment claims."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired staff token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("scope") != "staff":
            raise credentials_exc
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise credentials_exc

    user = await db.get(AdminUser, user_id)
    if not user or not user.active:
        raise credentials_exc
    return user, payload


def require_role(*roles: AdminRole):
    """Dependency factory — restricts endpoint to specified admin roles."""
    async def _check(
        staff_data: tuple[AdminUser, dict] = Depends(get_current_staff)
    ) -> AdminUser:
        user, _ = staff_data
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {[r.value for r in roles]}",
            )
        return user
    return _check


from fastapi import Request

async def get_current_actor(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> tuple[str, AdminUser | Institution]:
    """
    Returns ('staff', AdminUser) or ('institution', Institution).
    Validates JWT token from the Authorization header.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header.split(" ", 1)[1]
    try:
        payload = decode_token(token)
        scope = payload.get("scope")
        sub = int(payload.get("sub"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    if scope == "staff":
        user = await db.get(AdminUser, sub)
        if not user or not user.active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Staff inactive or not found")
        return "staff", user
    elif scope == "institution":
        inst = await db.get(Institution, sub)
        if not inst:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Institution not found")
        return "institution", inst
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token scope")

