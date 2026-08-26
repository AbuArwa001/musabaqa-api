from pydantic import BaseModel, EmailStr
from app.models.admin_user import AdminRole, JudgeRole, PreferredLanguage


class AdminUserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: AdminRole
    judge_role: JudgeRole | None = None
    preferred_language: PreferredLanguage = PreferredLanguage.EN


class AdminUserRead(BaseModel):
    id: int
    name: str
    email: str
    role: AdminRole
    judge_role: JudgeRole | None
    preferred_language: PreferredLanguage
    active: bool
    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    name: str | None = None
    role: AdminRole | None = None
    judge_role: JudgeRole | None = None
    preferred_language: PreferredLanguage | None = None
    active: bool | None = None
