from pydantic import BaseModel, EmailStr


class InstitutionLoginRequest(BaseModel):
    email: EmailStr
    password: str


class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scope: str


class RequestOTPRequest(BaseModel):
    institution_id: int
    channel: str = "SMS"  # "SMS" or "EMAIL"
    verify_value: str | None = None  # Phone or email for Option 3 proof of identity


class RequestOTPResponse(BaseModel):
    success: bool
    channel: str
    destination_masked: str
    message: str
    test_otp: str | None = None  # Returned in non-production for testing ease


class VerifyOTPRequest(BaseModel):
    institution_id: int
    code: str


class VerifyOTPResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    scope: str = "institution"
    institution_id: int
    institution_name: str
    active_students_count: int
    max_students_allowed: int = 4
    registered_categories: list[int] = []

