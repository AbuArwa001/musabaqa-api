from datetime import datetime, timezone
import enum
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class OTPChannel(str, enum.Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"


class InstitutionOTP(SQLModel, table=True):
    """
    One-time passcode (OTP) for fast-track institution login and express student intake.
    """
    __tablename__ = "institution_otps"

    id: int | None = Field(default=None, primary_key=True)
    institution_id: int = Field(foreign_key="institutions.id", index=True)
    code: str = Field(index=True)
    channel: OTPChannel = Field(
        sa_column=Column(sa.Enum(OTPChannel), nullable=False)
    )
    destination: str  # Phone number or email where OTP was sent
    attempts: int = Field(default=0)
    is_used: bool = Field(default=False, index=True)
    expires_at: datetime = Field(
        sa_column=Column(sa.DateTime(timezone=True), nullable=False, index=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
