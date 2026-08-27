import enum
from datetime import date, datetime, timezone
from typing import Any
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class CompetitionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"          # Live & Active / جارية ومباشرة
    CONCLUDED = "CONCLUDED"    # Concluded & Archived / منتهية ومؤرشفة
    DRAFT = "DRAFT"            # Draft & Setup / مسودة للإعداد


class HostOrganization(str, enum.Enum):
    JAMIA_MOSQUE = "JAMIA_MOSQUE"                    # Jamia Mosque Committee · Nairobi
    RELIGIOUS_ATTACHE = "RELIGIOUS_ATTACHE"          # Saudi Religious Attaché · الملحقية الدينية بالسفارة السعودية
    JOINT_COLLABORATION = "JOINT_COLLABORATION"      # Joint National Collaboration
    CUSTOM = "CUSTOM"                                # Custom / Other Organizer


class Competition(SQLModel, table=True):
    """
    Competition edition model representing a specific annual or special Musabaqa event.
    Supports multi-host competitions (Jamia Mosque, Religious Attaché, Joint),
    theme banners, media galleries, winners podium archives, and Jamia events replication.
    """
    __tablename__ = "competitions"

    id: int | None = Field(default=None, primary_key=True)
    title_en: str = Field(index=True)
    title_ar: str = Field(default="")
    edition_label: str = Field(default="", description="e.g. '14th Annual Edition (2026)'")
    year: int = Field(default=2026, index=True)

    host_org: HostOrganization = Field(
        default=HostOrganization.JAMIA_MOSQUE,
        sa_column=Column(sa.Enum(HostOrganization), nullable=False),
    )
    host_org_name_en: str = Field(default="Jamia Mosque Committee · Nairobi")
    host_org_name_ar: str = Field(default="لجنة مسجد جامعة نيروبي")

    status: CompetitionStatus = Field(
        default=CompetitionStatus.ACTIVE,
        sa_column=Column(sa.Enum(CompetitionStatus), nullable=False, index=True),
    )
    is_current: bool = Field(default=False, index=True)
    scope: str = Field(default="COUNTY_REGIONAL", description="'NATIONAL' or 'COUNTY_REGIONAL'")

    # Event Dates & Venue
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    registration_deadline: date | None = Field(default=None)
    grand_finale_date: date | None = Field(default=None)
    venue_en: str | None = Field(default="Jamia Mosque Multi-Purpose Hall, Nairobi, Kenya")
    venue_ar: str | None = Field(default="قاعة مسجد الجامعة متعددة الأغراض، نيروبي، كينيا")

    # Branding & Media
    banner_url: str | None = Field(default=None, description="Wide promotional theme banner")
    theme_image_url: str | None = Field(default=None, description="Featured poster or theme picture")
    logo_url: str | None = Field(default=None, description="Competition or Host logo emblem")
    description_en: str | None = Field(default=None)
    description_ar: str | None = Field(default=None)

    # Detailed Configuration & Rules JSON (quotas, categories, age limits)
    config_json: dict[str, Any] | None = Field(default=None, sa_column=Column(sa.JSON, nullable=True))

    # Gallery Media Array: list of { id, url, title, caption, stage, date }
    gallery: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(sa.JSON, nullable=False))

    # Winners Podium Array: list of { category_id, category_name, rank_1: {...}, rank_2: {...}, rank_3: {...} }
    winners: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(sa.JSON, nullable=False))

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
