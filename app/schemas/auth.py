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
