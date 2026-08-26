"""
Certificate PDF generation via WeasyPrint.

RTL Arabic is rendered correctly via:
  - direction: rtl; unicode-bidi: embed on Arabic templates
  - Amiri / Noto Arabic fonts (installed in Docker)
  - Separate EN/AR HTML templates
"""

import io
import logging
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "certificates"


def _get_template(lang: str) -> str:
    filename = "certificate_ar.html" if lang == "AR" else "certificate_en.html"
    return (TEMPLATE_DIR / filename).read_text(encoding="utf-8")


async def generate_certificate_pdf(
    student_name: str,
    category_name: str,
    rank: int,
    final_score: float,
    season: str,
    lang: str = "EN",
) -> bytes:
    """Generate a certificate PDF and return raw bytes."""
    try:
        from weasyprint import HTML, CSS

        template_html = _get_template(lang)
        rendered = template_html.format(
            student_name=student_name,
            category_name=category_name,
            rank=rank,
            final_score=f"{final_score:.2f}",
            season=season,
        )
        pdf_bytes = HTML(string=rendered).write_pdf()
        return pdf_bytes
    except Exception as exc:
        logger.error("WeasyPrint certificate error: %s", exc)
        raise


async def generate_and_upload_certificate(
    student,
    category,
    round_result,
    season: str,
    lang: str = "EN",
) -> str:
    """Generate PDF, upload to S3, return presigned URL."""
    import boto3
    from botocore.config import Config

    lang_key = "AR" if lang == "AR" else "EN"
    pdf_bytes = await generate_certificate_pdf(
        student_name=student.full_name,
        category_name=category.name_ar if lang_key == "AR" else category.name_en,
        rank=round_result.rank or 0,
        final_score=round_result.final_score,
        season=season,
        lang=lang_key,
    )

    s3_key = f"certificates/{season}/{student.id}_certificate_{lang_key.lower()}.pdf"

    if not settings.AWS_ACCESS_KEY_ID:
        logger.warning("AWS not configured — returning mock presigned URL")
        return f"https://s3.example.com/{s3_key}"

    s3 = boto3.client(
        "s3",
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
    )
    s3.put_object(
        Bucket=settings.S3_BUCKET,
        Key=s3_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": s3_key},
        ExpiresIn=settings.PRESIGNED_URL_TTL_SECONDS,
    )
    return url
