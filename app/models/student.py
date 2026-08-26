import enum
from datetime import date, datetime, timezone
from sqlmodel import Field, SQLModel, Column, UniqueConstraint
import sqlalchemy as sa


class StudentReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class Student(SQLModel, table=True):
    """
    UNIQUE CONSTRAINT: (institution_id, category_id)
    Enforces one student per category per institution.

    DUPLICATE CHECK (cross-competition):
    - national_id (birth cert number) — unique across all institutions
    - guardian_phone — unique across all institutions
    These are enforced at the CRUD layer with explicit queries, not only DB constraints,
    to provide meaningful error messages.

    SOFT DELETE: is_deleted + deletion_reason + archived_at
    Editing deletion_reason does NOT re-trigger notifications (CRUD enforces this).
    """
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("institution_id", "category_id", name="uq_student_institution_category"),
    )

    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key="institutions.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)

    # Full name: UTF-8, no Latin-only regex — must accept Arabic script
    full_name: str
    dob: date
    gender: Gender = Field(sa_column=Column(sa.Enum(Gender), nullable=False))

    # Cross-competition duplicate fields (unique enforced at CRUD layer + DB index)
    national_id: str = Field(index=True, unique=True)  # national_id / birth cert number
    guardian_phone: str = Field(index=True, unique=True)

    # S3 keys (private — accessed via presigned URLs only)
    photo: str | None = Field(default=None, description="S3 object key")
    id_document: str | None = Field(default=None, description="S3 object key (private, presigned)")

    review_status: StudentReviewStatus = Field(
        default=StudentReviewStatus.PENDING_REVIEW,
        sa_column=Column(sa.Enum(StudentReviewStatus), nullable=False, index=True),
    )
    rejection_reason: str | None = Field(default=None)

    # Backup student feature
    is_backup: bool = Field(default=False)

    # Soft delete
    is_deleted: bool = Field(default=False, index=True)
    deletion_reason: str | None = Field(default=None)
    archived_at: datetime | None = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )

    # Regret email tracking
    regret_email_sent: bool = Field(default=False)
    regret_email_sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
