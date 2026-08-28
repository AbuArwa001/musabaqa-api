import enum
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class InstitutionStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class InstitutionType(str, enum.Enum):
    MADRASA = "MADRASA"
    SCHOOL = "SCHOOL"
    MOSQUE = "MOSQUE"
    OTHER = "OTHER"


class PreferredLanguage(str, enum.Enum):
    EN = "EN"
    AR = "AR"


class Institution(SQLModel, table=True):
    __tablename__ = "institutions"

    id: int | None = Field(default=None, primary_key=True)
    name: str  # Accepts Arabic script (UTF-8)
    type: InstitutionType = Field(
        sa_column=Column(sa.Enum(InstitutionType), nullable=False)
    )
    contact_person: str
    phone: str
    email: str = Field(unique=True, index=True)
    password_hash: str

    # Geography: region_id for REGIONAL mode, county_id for NATIONAL mode
    region_id: int | None = Field(default=None, foreign_key="regions.id", index=True)
    county_id: int | None = Field(default=None, foreign_key="counties.id", index=True)

    status: InstitutionStatus = Field(
        default=InstitutionStatus.PENDING,
        sa_column=Column(sa.Enum(InstitutionStatus), nullable=False),
    )
    rejection_reason: str | None = Field(default=None)
    document_url: str | None = Field(default=None)
    teacher_photo_url: str | None = Field(default=None)
    classroom_photo_url: str | None = Field(default=None)
    students_photo_url: str | None = Field(default=None)
    video_url: str | None = Field(default=None)
    preferred_language: PreferredLanguage = Field(
        default=PreferredLanguage.EN,
        sa_column=Column(sa.Enum(PreferredLanguage), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
