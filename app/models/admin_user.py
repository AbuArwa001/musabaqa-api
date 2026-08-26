import enum
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class AdminRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    JUDGE = "JUDGE"
    MODERATOR = "MODERATOR"


class JudgeRole(str, enum.Enum):
    REGULAR = "REGULAR"
    GUEST_NEUTRAL = "GUEST_NEUTRAL"


class PreferredLanguage(str, enum.Enum):
    EN = "EN"
    AR = "AR"


class AdminUser(SQLModel, table=True):
    __tablename__ = "admin_users"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: AdminRole = Field(sa_column=Column(sa.Enum(AdminRole), nullable=False))
    judge_role: JudgeRole | None = Field(
        default=None,
        sa_column=Column(sa.Enum(JudgeRole), nullable=True),
    )
    preferred_language: PreferredLanguage = Field(
        default=PreferredLanguage.EN,
        sa_column=Column(sa.Enum(PreferredLanguage), nullable=False),
    )
    active: bool = Field(default=True)
