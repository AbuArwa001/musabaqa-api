from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_institution, require_role
from app.crud import institutions as crud
from app.models.admin_user import AdminRole
from app.models.institution import InstitutionStatus
from app.schemas.institution import (
    InstitutionCreate, InstitutionRead, InstitutionUpdate,
    InstitutionApprove, InstitutionReject,
)
from app.services import notifications
from app.models.audit import AuditLog, AuditAction

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.post("/register", response_model=InstitutionRead, status_code=201)
async def register_institution(data: InstitutionCreate, db: AsyncSession = Depends(get_db)):
    inst = await crud.create_institution(db, data)
    await db.commit()
    return inst


@router.get("/me", response_model=InstitutionRead)
async def get_my_institution(inst=Depends(get_current_institution)):
    return inst


@router.get("/{institution_id}", response_model=InstitutionRead)
async def get_institution(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return await crud.get_institution(db, institution_id)


@router.get("/", response_model=list[InstitutionRead])
async def list_institutions(
    status: InstitutionStatus | None = None,
    region_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return await crud.list_institutions(db, status=status, region_id=region_id, skip=skip, limit=limit)


@router.patch("/{institution_id}", response_model=InstitutionRead)
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    inst = await crud.update_institution(db, institution_id, data)
    await db.commit()
    return inst


@router.post("/{institution_id}/approve", response_model=InstitutionRead)
async def approve_institution(
    institution_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    inst = await crud.approve_institution(db, institution_id)
    db.add(AuditLog(
        actor_id=staff.id, action=AuditAction.UPDATE, module="institutions",
        target_record_id=institution_id, ip_address=request.client.host,
        payload={"action": "approve"},
    ))
    await db.commit()
    await notifications.notify_institution_approved(inst)
    return inst


@router.post("/{institution_id}/reject", response_model=InstitutionRead)
async def reject_institution(
    institution_id: int,
    body: InstitutionReject,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    inst = await crud.reject_institution(db, institution_id, body.rejection_reason)
    db.add(AuditLog(
        actor_id=staff.id, action=AuditAction.UPDATE, module="institutions",
        target_record_id=institution_id, ip_address=request.client.host,
        payload={"action": "reject", "reason": body.rejection_reason},
    ))
    await db.commit()
    await notifications.notify_institution_rejected(inst)
    return inst
