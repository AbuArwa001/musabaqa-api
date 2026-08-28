from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.institution import InstitutionStatus, InstitutionType, PreferredLanguage


class InstitutionCreate(BaseModel):
    name: str
    type: InstitutionType
    contact_person: str
    phone: str
    email: EmailStr
    password: str
    region_id: int | None = None
    county_id: int | None = None
    document_url: str | None = None
    preferred_language: PreferredLanguage = PreferredLanguage.EN


class InstitutionRead(BaseModel):
    id: int
    name: str
    type: InstitutionType
    contact_person: str
    phone: str
    email: str
    region_id: int | None
    county_id: int | None
    document_url: str | None = None
    status: InstitutionStatus
    rejection_reason: str | None
    preferred_language: PreferredLanguage
    created_at: datetime
    model_config = {"from_attributes": True}


class InstitutionUpdate(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    document_url: str | None = None
    preferred_language: PreferredLanguage | None = None


class InstitutionApprove(BaseModel):
    pass  # No body needed


class InstitutionReject(BaseModel):
    rejection_reason: str
