"""S3 + CloudFront helpers for presigned URL generation."""

import logging
import boto3
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        config=Config(signature_version="s3v4"),
    )


def generate_presigned_url(s3_key: str) -> str:
    """Generate a 5-minute presigned GET URL for a private S3 object."""
    if not settings.AWS_ACCESS_KEY_ID:
        return f"https://s3.example.com/{s3_key}?presigned=mock"
    try:
        s3 = get_s3_client()
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
            ExpiresIn=settings.PRESIGNED_URL_TTL_SECONDS,
        )
    except Exception as exc:
        logger.error("Presigned URL error for %s: %s", s3_key, exc)
        return ""


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to S3, return the key."""
    if not settings.AWS_ACCESS_KEY_ID:
        logger.warning("AWS not configured — skipping upload for %s", key)
        return key
    s3 = get_s3_client()
    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key
