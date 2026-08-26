from datetime import date, datetime
from pydantic import BaseModel, field_validator
from app.models.student import StudentReviewStatus, Gender


class StudentCreate(BaseModel):
    institution_id: int
    category_id: int
    full_name: str          # UTF-8; Arabic script accepted — no Latin-only validation
    dob: date
    gender: Gender
    national_id: str
    guardian_phone: str
    photo: str | None = None
    id_document: str | None = None
    is_backup: bool = False

    @field_validator("full_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("full_name cannot be blank")
        return v


class StudentRead(BaseModel):
    id: int
    institution_id: int
    category_id: int
    full_name: str
    dob: date
    gender: Gender
    national_id: str
    guardian_phone: str
    photo: str | None          # returned as presigned URL by the API layer
    id_document: str | None    # always presigned URL, never raw S3 key
    review_status: StudentReviewStatus
    rejection_reason: str | None
    is_backup: bool
    is_deleted: bool
    deletion_reason: str | None
    archived_at: datetime | None
    regret_email_sent: bool
    regret_email_sent_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}


class StudentUpdate(BaseModel):
    full_name: str | None = None
    dob: date | None = None
    gender: Gender | None = None
    guardian_phone: str | None = None
    is_backup: bool | None = None


class StudentApprove(BaseModel):
    pass


class StudentReject(BaseModel):
    rejection_reason: str


class StudentReassignCategory(BaseModel):
    new_category_id: int
    age_exemption: bool = False
    age_exemption_reason: str | None = None


class StudentSoftDelete(BaseModel):
    deletion_reason: str


class StudentRestoreRequest(BaseModel):
    pass


class StudentUpdateDeletionReason(BaseModel):
    """Edit deletion_reason WITHOUT re-triggering notifications."""
    deletion_reason: str


class BulkStudentIds(BaseModel):
    student_ids: list[int]


class BulkSoftDelete(BaseModel):
    student_ids: list[int]
    deletion_reason: str


class RegretEmailBulkRequest(BaseModel):
    student_ids: list[int] | None = None  # None = all unsent
