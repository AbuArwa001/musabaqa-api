from datetime import date, datetime
from typing import Any
from pydantic import BaseModel
from app.models.competition import CompetitionStatus, HostOrganization


class GalleryItem(BaseModel):
    id: str | None = None
    url: str
    title: str = ""
    caption: str = ""
    stage: str = "General"  # e.g. "Preliminary", "Semifinals", "Grand Finale", "Award Ceremony"
    date: str | None = None


class WinnerPodiumEntry(BaseModel):
    rank: int  # 1, 2, 3
    student_id: int | None = None
    student_name: str
    institution_name: str = ""
    location: str = ""
    score: float = 0.0
    photo_url: str | None = None
    award_notes: str | None = None


class CategoryWinnersPodium(BaseModel):
    category_id: int
    category_name_en: str
    category_name_ar: str = ""
    rank_1: WinnerPodiumEntry | None = None
    rank_2: WinnerPodiumEntry | None = None
    rank_3: WinnerPodiumEntry | None = None
    honorable_mentions: list[WinnerPodiumEntry] = []


class CompetitionCreate(BaseModel):
    title_en: str
    title_ar: str = ""
    edition_label: str = ""
    year: int = 2026
    host_org: HostOrganization = HostOrganization.JAMIA_MOSQUE
    host_org_name_en: str = "Jamia Mosque Committee · Nairobi"
    host_org_name_ar: str = "لجنة مسجد جامعة نيروبي"
    status: CompetitionStatus = CompetitionStatus.DRAFT
    is_current: bool = False
    scope: str = "COUNTY_REGIONAL"
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: date | None = None
    grand_finale_date: date | None = None
    venue_en: str | None = "Jamia Mosque Multi-Purpose Hall, Nairobi, Kenya"
    venue_ar: str | None = "قاعة مسجد الجامعة متعددة الأغراض، نيروبي، كينيا"
    banner_url: str | None = None
    theme_image_url: str | None = None
    logo_url: str | None = None
    description_en: str | None = None
    description_ar: str | None = None
    config_json: dict[str, Any] | None = None
    gallery: list[dict[str, Any]] = []
    winners: list[dict[str, Any]] = []


class CompetitionUpdate(BaseModel):
    title_en: str | None = None
    title_ar: str | None = None
    edition_label: str | None = None
    year: int | None = None
    host_org: HostOrganization | None = None
    host_org_name_en: str | None = None
    host_org_name_ar: str | None = None
    status: CompetitionStatus | None = None
    is_current: bool | None = None
    scope: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    registration_deadline: date | None = None
    grand_finale_date: date | None = None
    venue_en: str | None = None
    venue_ar: str | None = None
    banner_url: str | None = None
    theme_image_url: str | None = None
    logo_url: str | None = None
    description_en: str | None = None
    description_ar: str | None = None
    config_json: dict[str, Any] | None = None
    gallery: list[dict[str, Any]] | None = None
    winners: list[dict[str, Any]] | None = None


class CompetitionRead(BaseModel):
    id: int
    title_en: str
    title_ar: str
    edition_label: str
    year: int
    host_org: HostOrganization
    host_org_name_en: str
    host_org_name_ar: str
    status: CompetitionStatus
    is_current: bool
    scope: str
    start_date: date | None
    end_date: date | None
    registration_deadline: date | None
    grand_finale_date: date | None
    venue_en: str | None
    venue_ar: str | None
    banner_url: str | None
    theme_image_url: str | None
    logo_url: str | None
    description_en: str | None
    description_ar: str | None
    config_json: dict[str, Any] | None
    gallery: list[dict[str, Any]]
    winners: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class EventReplicationResponse(BaseModel):
    success: bool
    competition_id: int
    title: str
    location: str
    start_at: str | None
    end_at: str | None
    image_url: str | None
    description_html: str
    gallery_count: int
    winners_count: int
    payload_ready_for_jamia_events: dict[str, Any]
