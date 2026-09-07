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


def obscure_phone(phone: str) -> str:
    """Masks phone number for secure preview: e.g. +254711000001 -> +25471 ••• •01."""
    if not phone:
        return "••••"
    cleaned = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if len(cleaned) <= 4:
        return "••••"
    prefix = cleaned[:6] if cleaned.startswith("+254") else (cleaned[:4] if cleaned.startswith("07") or cleaned.startswith("01") else cleaned[:2])
    suffix = cleaned[-2:]
    return f"{prefix} ••• •{suffix}"


def obscure_email(email: str) -> str:
    """Masks email address for secure preview: e.g. nuuralislam@example.com -> nuu••••••••@example.com."""
    if not email or "@" not in email:
        return "••••@••••"
    name, domain = email.split("@", 1)
    if len(name) <= 3:
        masked_name = name[0] + "••"
    else:
        masked_name = name[:3] + "•" * max(len(name) - 3, 3)
    return f"{masked_name}@{domain}"


def normalize_ke_phone(phone: str) -> str:
    """Extracts significant phone digits (handling +254 vs 07/01 prefixes in Kenya)."""
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("254") and len(digits) >= 12:
        return digits[3:]
    if (digits.startswith("07") or digits.startswith("01")) and len(digits) >= 10:
        return digits[1:]
    return digits[-9:] if len(digits) >= 9 else digits


