import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.schemas.results import RoundResultRead
from app.workers.tasks import generate_bulk_dossiers_task

router = APIRouter(prefix="/archive", tags=["Archive"])


@router.post("/dossiers/bulk", status_code=202)
async def start_bulk_dossiers(
    student_ids: list[int],
    lang: str = "EN",
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Start bulk dossier generation. Returns a job_id to poll for progress."""
    job_id = str(uuid.uuid4())
    generate_bulk_dossiers_task.delay(job_id, student_ids, lang)
    return {"job_id": job_id, "status": "QUEUED", "total": len(student_ids)}


@router.get("/dossiers/jobs/{job_id}")
async def get_dossier_job_status(
    job_id: str,
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Poll bulk dossier job status."""
    import json, redis
    from app.core.config import settings
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    raw = r.get(f"job:{job_id}")
    if not raw:
        raise HTTPException(404, "Job not found or expired")
    return json.loads(raw)
