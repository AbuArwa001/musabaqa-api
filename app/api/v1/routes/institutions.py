from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
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
from app.services.s3 import (
    generate_presigned_url, upload_bytes, institution_document_upload_key
)
from app.models.audit import AuditLog, AuditAction

router = APIRouter(prefix="/institutions", tags=["Institutions"])


def _with_presigned_inst(inst) -> dict:
    """Replace raw S3 key with presigned URL before returning to client."""
    d = inst.__dict__.copy()
    if d.get("document_url"):
        d["document_url"] = generate_presigned_url(d["document_url"])
    return d


@router.post("/register", response_model=InstitutionRead, status_code=201)
async def register_institution(data: InstitutionCreate, db: AsyncSession = Depends(get_db)):
    inst = await crud.create_institution(db, data)
    await db.commit()
    return _with_presigned_inst(inst)


@router.get("/me", response_model=InstitutionRead)
async def get_my_institution(inst=Depends(get_current_institution)):
    return _with_presigned_inst(inst)


@router.get("/{institution_id}", response_model=InstitutionRead)
async def get_institution(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    inst = await crud.get_institution(db, institution_id)
    return _with_presigned_inst(inst)


@router.get("/", response_model=list[InstitutionRead])
async def list_institutions(
    status: InstitutionStatus | None = None,
    region_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    insts = await crud.list_institutions(db, status=status, region_id=region_id, skip=skip, limit=limit)
    return [_with_presigned_inst(i) for i in insts]


@router.patch("/{institution_id}", response_model=InstitutionRead)
async def update_institution(
    institution_id: int,
    data: InstitutionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    inst = await crud.update_institution(db, institution_id, data)
    await db.commit()
    return _with_presigned_inst(inst)


@router.post("/{institution_id}/document", status_code=200)
async def upload_institution_document(
    institution_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Uploads official verification/registration document for institution to S3.
    Saves as: institutions/<institution_name>/<filename>.[jpg/pdf/png]
    """
    inst = await crud.get_institution(db, institution_id)
    contents = await file.read()
    s3_key = institution_document_upload_key(inst.name, file.filename or "verification_doc.pdf")
    upload_bytes(s3_key, contents, file.content_type or "application/pdf")
    inst.document_url = s3_key
    db.add(inst)
    await db.commit()

    presigned = generate_presigned_url(s3_key)
    return {"s3_key": s3_key, "url": presigned}


@router.get("/{institution_id}/document_url", status_code=200)
async def get_institution_document_url(
    institution_id: int,
    db: AsyncSession = Depends(get_db),
):
    inst = await crud.get_institution(db, institution_id)
    url = generate_presigned_url(inst.document_url) if inst.document_url else None
    return {"url": url}


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
    return _with_presigned_inst(inst)


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
    return _with_presigned_inst(inst)
