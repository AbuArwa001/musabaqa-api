from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.audit import AuditLog

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("/")
async def list_audit_logs(
    module: str | None = None,
    actor_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    q = select(AuditLog).order_by(AuditLog.timestamp.desc())
    if module:
        q = q.where(AuditLog.module == module)
    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    q = q.offset(skip).limit(limit)
    return (await db.execute(q)).scalars().all()
