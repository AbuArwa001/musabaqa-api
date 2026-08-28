import enum
from datetime import datetime
from sqlmodel import Field, SQLModel, Column, UniqueConstraint
import sqlalchemy as sa


class RoundType(str, enum.Enum):
    PRELIMINARY = "PRELIMINARY"
    FINAL = "FINAL"


class RoundStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class JudgeRole(str, enum.Enum):
    REGULAR = "REGULAR"
    GUEST_NEUTRAL = "GUEST_NEUTRAL"


class Round(SQLModel, table=True):
    __tablename__ = "rounds"

    id: int | None = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    round_type: RoundType = Field(sa_column=Column(sa.Enum(RoundType), nullable=False))
    status: RoundStatus = Field(
        default=RoundStatus.PENDING,
        sa_column=Column(sa.Enum(RoundStatus), nullable=False, index=True),
    )
    scheduled_at: datetime = Field(sa_column=Column(sa.DateTime(timezone=True), nullable=False))
    active_student_id: int | None = Field(default=None, foreign_key="students.id")


class RoundJudgeAssignment(SQLModel, table=True):
    """
    Judge panel composition.

    Validation rules (enforced before a round can move to ACTIVE):
      PRELIMINARY: exactly 3 REGULAR judges, 0 GUEST_NEUTRAL
      FINAL:       exactly 3 REGULAR + 1 GUEST_NEUTRAL = 4 total

    A round with the wrong composition is REJECTED at start-round time,
    never after scoring begins.
    """
    __tablename__ = "round_judge_assignments"
    __table_args__ = (
        UniqueConstraint("round_id", "admin_user_id", name="uq_judge_round"),
    )

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="rounds.id", index=True)
    admin_user_id: int = Field(foreign_key="admin_users.id", index=True)
    judge_role: JudgeRole = Field(sa_column=Column(sa.Enum(JudgeRole), nullable=False))
