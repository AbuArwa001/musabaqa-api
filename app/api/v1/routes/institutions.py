import secrets
from fastapi import APIRouter, Depends, Request, UploadFile, File, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from app.api.deps import get_db, get_current_institution, require_role
from app.crud import institutions as crud
from app.models.admin_user import AdminRole
from app.models.institution import Institution, InstitutionStatus, InstitutionType
from app.models.student import Student
from app.schemas.institution import (
    InstitutionCreate, InstitutionRead, InstitutionUpdate,
    InstitutionApprove, InstitutionReject,
    InstitutionDirectoryItem, InstitutionAdminIntakeCreate,
)
from app.services import notifications
from app.services.s3 import (
    generate_presigned_url, upload_bytes, institution_document_upload_key
)
from app.core.security import obscure_phone, obscure_email, hash_password
from app.models.audit import AuditLog, AuditAction

router = APIRouter(prefix="/institutions", tags=["Institutions"])


@router.get("/directory", response_model=list[InstitutionDirectoryItem])
async def list_institution_directory(
    county_id: int | None = None,
    region_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Public directory of pre-listed and approved institutions for Option 2 (Express Intake)
    and Option 3 (Fast-track Portal Login). Contact details are partially masked for privacy.
    """
    query = select(Institution).where(Institution.status != InstitutionStatus.REJECTED)
    if county_id:
        query = query.where(Institution.county_id == county_id)
    if region_id:
        query = query.where(Institution.region_id == region_id)
    query = query.order_by(Institution.name.asc())

    institutions = (await db.execute(query)).scalars().all()

    # Pre-fetch student counts
    inst_ids = [i.id for i in institutions]
    counts_map = {}
    if inst_ids:
        counts_query = (
            select(Student.institution_id, func.count(Student.id))
            .where(Student.institution_id.in_(inst_ids), Student.is_deleted == False)
            .group_by(Student.institution_id)
        )
        counts_res = await db.execute(counts_query)
        counts_map = {row[0]: row[1] for row in counts_res.all()}

    items = []
    for inst in institutions:
        active_count = counts_map.get(inst.id, 0)
        items.append(
            InstitutionDirectoryItem(
                id=inst.id,
                name=inst.name,
                type=inst.type,
                contact_person=inst.contact_person,
                region_id=inst.region_id,
                county_id=inst.county_id,
                status=inst.status,
                obscured_phone=obscure_phone(inst.phone),
                obscured_email=obscure_email(inst.email),
                active_students_count=active_count,
                available_spots=max(0, 4 - active_count),
            )
        )
    return items


@router.post("/admin-intake", response_model=InstitutionRead, status_code=201)
async def admin_intake_institution(
    data: InstitutionAdminIntakeCreate,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """
    Allows desk officers to quickly input institutions from the 50-Madaris Intake Roster.
    Automatically creates the institution with status APPROVED and generates initial security credentials.
    """
    existing = await crud.get_institution_by_email(db, str(data.email))
    if existing:
        raise HTTPException(status_code=409, detail="An institution with this email is already registered.")

    temp_password = secrets.token_urlsafe(12)
    new_inst = Institution(
        name=data.name.strip(),
        type=data.type,
        contact_person=data.contact_person.strip(),
        phone=data.phone.strip(),
        email=str(data.email).strip().lower(),
        password_hash=hash_password(temp_password),
        county_id=data.county_id,
        region_id=data.region_id,
        preferred_language=data.preferred_language,
        status=InstitutionStatus.APPROVED,
    )
    db.add(new_inst)
    await db.commit()
    await db.refresh(new_inst)

    return _with_presigned_inst(new_inst)



def _with_presigned_inst(inst) -> dict:
    """Replace raw S3 keys with presigned URLs before returning to client."""
    d = inst.__dict__.copy()
    for field in ["document_url", "teacher_photo_url", "classroom_photo_url", "students_photo_url", "video_url"]:
        if d.get(field):
            d[field] = generate_presigned_url(d[field])
    return d


from app.models.region import Region
from app.models.county import County


@router.post("/register", response_model=InstitutionRead, status_code=201)
async def register_institution(data: InstitutionCreate, db: AsyncSession = Depends(get_db)):
    inst = await crud.create_institution(db, data)
    await db.commit()

    # Look up location names for premium email receipt
    region_name = None
    county_name = None
    try:
        if inst.region_id:
            reg = await db.get(Region, inst.region_id)
            if reg:
                region_name = reg.name_ar if inst.preferred_language == "AR" else reg.name_en
        if inst.county_id:
            cty = await db.get(County, inst.county_id)
            if cty:
                county_name = cty.name
    except Exception:
        pass

    # Dispatch ultra-premium review email via Resend
    try:
        await notifications.send_institution_registration_review_email(
            inst,
            region_name=region_name,
            county_name=county_name,
        )
    except Exception as exc:
        pass

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
    s3_key = institution_document_upload_key(inst.name, file.filename or "verification_doc.pdf", media_type="document")
    upload_bytes(s3_key, contents, file.content_type or "application/pdf")
    inst.document_url = s3_key
    db.add(inst)
    await db.commit()

    presigned = generate_presigned_url(s3_key)
    return {"s3_key": s3_key, "url": presigned}


@router.post("/{institution_id}/media", status_code=200)
async def upload_institution_media(
    institution_id: int,
    media_type: str = Query(..., description="Type of media: document, teacher, classroom, students, video"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Uploads verification media (Teacher photo, Classroom photo, Students photo, Video) to AWS S3.
    Saves as: institutions/<institution_name>/<media_type>_<filename>.[jpg/pdf/png/mp4]
    """
    valid_types = ["document", "teacher", "classroom", "students", "video"]
    if media_type not in valid_types:
        raise HTTPException(400, f"Invalid media_type. Must be one of: {', '.join(valid_types)}")

    inst = await crud.get_institution(db, institution_id)
    contents = await file.read()
    s3_key = institution_document_upload_key(inst.name, file.filename or f"{media_type}.jpg", media_type=media_type)
    content_type = file.content_type or ("video/mp4" if media_type == "video" else "image/jpeg")
    upload_bytes(s3_key, contents, content_type)

    if media_type == "document":
        inst.document_url = s3_key
    elif media_type == "teacher":
        inst.teacher_photo_url = s3_key
    elif media_type == "classroom":
        inst.classroom_photo_url = s3_key
    elif media_type == "students":
        inst.students_photo_url = s3_key
    elif media_type == "video":
        inst.video_url = s3_key

    db.add(inst)
    await db.commit()

    presigned = generate_presigned_url(s3_key)
    return {"media_type": media_type, "s3_key": s3_key, "url": presigned}


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
