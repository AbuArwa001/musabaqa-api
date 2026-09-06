from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
import urllib.parse


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://musabaqa:musabaqa_secret@localhost:5432/musabaqa_db"

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def clean_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]

        parsed = urllib.parse.urlparse(v)
        if parsed.scheme.startswith("postgresql"):
            qs = urllib.parse.parse_qs(parsed.query)
            if "sslmode" in qs:
                ssl_val = qs.pop("sslmode")[0]
                qs["ssl"] = [ssl_val]
            qs.pop("channel_binding", None)
            new_query = urllib.parse.urlencode(qs, doseq=True)
            v = urllib.parse.urlunparse(parsed._replace(query=new_query))
        return v

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "supersecretkey_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # AWS S3 + CloudFront
    S3_BUCKET: str = "musabaqa-bucket"
    S3_REGION: str = "us-east-1"
    CLOUDFRONT_DOMAIN: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    PRESIGNED_URL_TTL_SECONDS: int = 300  # 5 minutes

    # Notifications
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@musabaqa.jmc.or.ke"
    KNOCK_API_KEY: str = ""
    AT_API_KEY: str = ""
    AT_USERNAME: str = "sandbox"
    AT_SENDER_ID: str = "MUSABAQA"

    # App
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    API_V1_PREFIX: str = "/api/v1"


settings = Settings()
