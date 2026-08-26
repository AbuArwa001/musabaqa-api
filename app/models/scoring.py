from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class DeductionEvent(SQLModel, table=True):
    """
    A single judge's deduction entry for a student in a round.

    amount:
      - If deduction_type.points_deducted IS NOT NULL → copy that fixed value here
      - If deduction_type.points_deducted IS NULL (Saut/Tafsir) → judge-entered value required
    """
    __tablename__ = "deduction_events"

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="rounds.id", index=True)
    student_id: int = Field(foreign_key="students.id", index=True)
    judge_id: int = Field(foreign_key="admin_users.id", index=True)
    deduction_type_id: int = Field(foreign_key="deduction_types.id", index=True)
    amount: float = Field(description="Actual deduction applied (always positive)")
    logged_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    note: str | None = Field(default=None)

    # Consistency flag: set if this judge's total deviates >10 pts from panel avg
    consistency_flagged: bool = Field(default=False)
