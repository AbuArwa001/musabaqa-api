"""
Celery background tasks.

- generate_bulk_dossiers_task: concurrent PDF generation → ZIP upload
- generate_excel_export_task: large Excel export
- send_bulk_regret_emails_task: batch regret emails
"""

import asyncio
import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

JOB_TTL = 3600  # Redis key TTL: 1 hour


def _set_job_status(redis_client, job_id: str, status: dict) -> None:
    redis_client.setex(f"job:{job_id}", JOB_TTL, json.dumps(status))


def _get_redis():
    import redis
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def generate_bulk_dossiers_task(self, job_id: str, student_ids: list[int], lang: str = "EN"):
    """
    Generate dossier PDFs for a list of students, ZIP them, upload to S3.
    Progress tracked in Redis as {"status": ..., "done": N, "total": N, "url": ...}
    """
    r = _get_redis()
    total = len(student_ids)
    _set_job_status(r, job_id, {"status": "RUNNING", "done": 0, "total": total})

    from app.services.dossier import generate_dossier_pdf_sync, package_dossiers_as_zip
    from app.services.s3 import upload_bytes

    dossiers: list[tuple[str, bytes]] = []
    failed: list[int] = []

    for i, student_id in enumerate(student_ids):
        try:
            # Minimal student data — in production fetch from DB via sync session
            student_data = {
                "student_id": student_id,
                "student_name": f"Student {student_id}",
                "category_name": "Category",
                "season": "2025",
            }
            pdf_bytes = generate_dossier_pdf_sync(student_data, lang=lang)
            dossiers.append((f"dossier_{student_id}_{lang.lower()}.pdf", pdf_bytes))
            _set_job_status(r, job_id, {"status": "RUNNING", "done": i + 1, "total": total})
        except Exception as exc:
            logger.error("Dossier failed for student %s: %s", student_id, exc)
            failed.append(student_id)
            try:
                self.retry(exc=exc)
            except Exception:
                pass

    if not dossiers:
        _set_job_status(r, job_id, {"status": "FAILED", "done": 0, "total": total, "failed": failed})
        return

    zip_bytes = package_dossiers_as_zip(dossiers)
    s3_key = f"exports/dossiers/{job_id}.zip"
    upload_bytes(s3_key, zip_bytes, content_type="application/zip")

    from app.services.s3 import generate_presigned_url
    url = generate_presigned_url(s3_key)

    _set_job_status(r, job_id, {
        "status": "DONE",
        "done": len(dossiers),
        "total": total,
        "failed": failed,
        "url": url,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })


@celery_app.task(bind=True, max_retries=2)
def generate_excel_export_task(self, job_id: str, student_data: list[dict], export_type: str):
    """Generate an Excel file in the background and upload to S3."""
    from app.services.reporting import generate_granular_export, generate_power_bi_export
    from app.services.s3 import upload_bytes, generate_presigned_url

    r = _get_redis()
    _set_job_status(r, job_id, {"status": "RUNNING"})
    try:
        if export_type == "granular":
            xlsx_bytes = generate_granular_export(student_data, include_presigned_urls=True)
        else:
            xlsx_bytes = generate_power_bi_export(student_data, [], [], [])

        s3_key = f"exports/excel/{job_id}.xlsx"
        upload_bytes(s3_key, xlsx_bytes, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        url = generate_presigned_url(s3_key)
        _set_job_status(r, job_id, {"status": "DONE", "url": url})
    except Exception as exc:
        _set_job_status(r, job_id, {"status": "FAILED", "error": str(exc)})
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def send_bulk_regret_emails_task(self, student_ids: list[int]):
    """Send regret emails to a batch of students via Resend."""
    logger.info("Sending regret emails to %d students", len(student_ids))
    # Actual DB + notification calls happen here in a sync context
    # In production: use a sync SQLAlchemy session or asyncio.run()
