import enum
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class AuditLog(SQLModel, table=True):
    """
    Immutable audit trail. Covers:
    - Every scoring action
    - All approval/rejection events
    - Category reassignments
    - Archival actions (soft-delete, restore, permanent-delete)
    - Config changes (season settings, category edits)
    - Regret emails
    """
    __tablename__ = "audit_logs"

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(default=None, description="admin_user_id or None for system")
    action: AuditAction = Field(sa_column=Column(sa.Enum(AuditAction), nullable=False, index=True))
    module: str = Field(index=True, description="e.g. 'scoring', 'students', 'institutions'")
    target_record_id: int | None = Field(default=None, index=True)
    ip_address: str | None = Field(default=None)
    payload: dict | None = Field(
        default=None,
        sa_column=Column(sa.JSON, nullable=True),
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False, index=True),
    )


class RegretEmailLog(SQLModel, table=True):
    """
    Tracks regret email delivery per student.
    Drives the Sent/Unsent filter on the admin dashboard.
    """
    __tablename__ = "regret_email_logs"

    id: int | None = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="students.id", index=True)
    sent_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    sent_by: int = Field(foreign_key="admin_users.id")
