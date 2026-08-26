"""
JWT security module for musabaqa-api.

Two separate scopes:
- "institution"  — for Institution accounts (login, submit students)
- "staff"        — for AdminUser accounts (SUPERADMIN / JUDGE / MODERATOR)
                   carries role + assigned_round_ids + assigned_category_ids
                   so the API can enforce judge assignment boundaries without
                   a DB query on every request.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def _build_token(payload: dict[str, Any], expire_delta: timedelta | None = None) -> str:
    data = payload.copy()
    expire = datetime.now(timezone.utc) + (
        expire_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    data["exp"] = expire
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_institution_token(institution_id: int) -> str:
    """JWT with scope='institution'."""
    return _build_token({"sub": str(institution_id), "scope": "institution"})


def create_staff_token(
    user_id: int,
    role: str,
    judge_role: str | None = None,
    assigned_round_ids: list[int] | None = None,
    assigned_category_ids: list[int] | None = None,
) -> str:
    """JWT with scope='staff', role claim, and judge assignment context."""
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "scope": "staff",
        "role": role,
    }
    if judge_role:
        payload["judge_role"] = judge_role
    if assigned_round_ids is not None:
        payload["assigned_round_ids"] = assigned_round_ids
    if assigned_category_ids is not None:
        payload["assigned_category_ids"] = assigned_category_ids
    return _build_token(payload)


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises JWTError on invalid/expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
