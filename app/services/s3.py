"""S3 + CloudFront helpers for file uploads and presigned URL generation."""

import os
import re
import logging
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

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


def make_s3_folder_key(full_name: str, national_id: str | None = None) -> str:
    """
    Build the registrant folder name from full name + ID number.
    Format: <FirstInitial>_<Lastname>_<NationalID>
    e.g. "Muzamil Mohamed Isack", "32145678" -> "M_Isack_32145678"
    """
    name = (full_name or "Unknown").strip()
    parts = name.split()

    if len(parts) >= 2:
        first_initial = parts[0][0].upper()
        last_name = parts[-1]
    elif len(parts) == 1:
        first_initial = parts[0][0].upper()
        last_name = parts[0]
    else:
        first_initial = "X"
        last_name = "unknown"

    last_name = re.sub(r"[^\w\-]", "", last_name, flags=re.UNICODE) or "unknown"
    clean_id = re.sub(r"[^\w]", "", str(national_id or ""), flags=re.UNICODE) or "noid"

    return f"{first_initial}_{last_name}_{clean_id}"


def passport_photo_upload_key(full_name: str, national_id: str | None, filename: str) -> str:
    """Returns: <folder>/passport/<safe_filename>.<ext>"""
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    folder = make_s3_folder_key(full_name, national_id)
    orig_base = os.path.splitext(os.path.basename(filename))[0]
    safe_name = re.sub(r"[^\w\-.]", "_", orig_base)
    return f"{folder}/passport/{safe_name}{ext}"


def id_document_upload_key(full_name: str, national_id: str | None, filename: str) -> str:
    """Returns: <folder>/id/<safe_filename>.<ext>"""
    ext = os.path.splitext(filename)[1].lower() or ".pdf"
    folder = make_s3_folder_key(full_name, national_id)
    orig_base = os.path.splitext(os.path.basename(filename))[0]
    safe_name = re.sub(r"[^\w\-.]", "_", orig_base)
    return f"{folder}/id/{safe_name}{ext}"


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload raw bytes to S3, return the key."""
    if not settings.AWS_ACCESS_KEY_ID or not settings.S3_BUCKET:
        logger.warning("AWS not configured — storing key reference for %s", key)
        return key
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("Successfully uploaded object to S3: %s", key)
        return key
    except Exception as exc:
        logger.error("Failed to upload object to S3 (%s): %s", key, exc)
        return key


def get_s3_object_bytes(s3_key: str) -> bytes | None:
    """Download bytes for an S3 key."""
    if not s3_key or not settings.AWS_ACCESS_KEY_ID or not settings.S3_BUCKET:
        return None
    try:
        s3 = get_s3_client()
        resp = s3.get_object(Bucket=settings.S3_BUCKET, Key=s3_key)
        return resp["Body"].read()
    except ClientError as exc:
        logger.error("Error reading S3 object %s: %s", s3_key, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error reading S3 object %s: %s", s3_key, exc)
        return None


def generate_presigned_url(s3_key: str, expires_in: int | None = None) -> str:
    """Generate a presigned GET URL for a private S3 object."""
    if not s3_key:
        return ""
    if not settings.AWS_ACCESS_KEY_ID or not settings.S3_BUCKET:
        return f"https://s3.amazonaws.com/mock/{s3_key}"
    try:
        s3 = get_s3_client()
        ttl = expires_in or settings.PRESIGNED_URL_TTL_SECONDS
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
            ExpiresIn=ttl,
        )
    except Exception as exc:
        logger.error("Presigned URL generation error for %s: %s", s3_key, exc)
        return ""
