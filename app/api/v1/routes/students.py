import os
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, Query, Request, UploadFile, File, Response, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_current_institution, require_role, get_current_actor
from app.crud import students as crud
from app.models.admin_user import AdminRole
from app.models.student import Student, StudentReviewStatus
from app.models.institution import Institution
from app.models.category import Category
from app.models.audit import AuditLog, AuditAction, RegretEmailLog
from app.schemas.student import (
    StudentCreate, StudentRead, StudentUpdate, StudentApprove, StudentReject,
    StudentReassignCategory, StudentSoftDelete, StudentUpdateDeletionReason,
    BulkSoftDelete, BulkStudentIds,
)
from app.services import notifications
from app.services.s3 import (
    generate_presigned_url, upload_bytes, passport_photo_upload_key, id_document_upload_key
)
from app.services.dossier import generate_single_student_pdf
from app.services.reporting import generate_comprehensive_analytics_workbook

router = APIRouter(prefix="/students", tags=["Students"])


def _with_presigned(student) -> dict:
    """Replace raw S3 keys with presigned URLs before returning to client."""
    d = student.__dict__.copy()
    if d.get("photo"):
        d["photo"] = generate_presigned_url(d["photo"])
    if d.get("id_document"):
        d["id_document"] = generate_presigned_url(d["id_document"])
    return d


# ─── 1. Core CRUD ─────────────────────────────────────────────────────────────

@router.post("/", response_model=StudentRead, status_code=201)
async def create_student(
    data: StudentCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    inst=Depends(get_current_institution),
):
    # Institutions can only register for themselves
    data.institution_id = inst.id
    student = await crud.create_student(db, data)
    cat = await db.get(Category, student.category_id)
    
    db.add(AuditLog(actor_id=None, action=AuditAction.CREATE, module="students",
                    target_record_id=student.id, ip_address=request.client.host, payload={}))
    await db.commit()

    # Trigger registration confirmation email
    try:
        await notifications.send_registration_confirmation_email(student, inst, cat)
    except Exception:
        pass

    return _with_presigned(student)


@router.get("/", response_model=list[StudentRead])
async def list_students(
    institution_id: int | None = None,
    category_id: int | None = None,
    review_status: StudentReviewStatus | None = None,
    regret_sent: bool | None = None,
    is_deleted: bool = False,
    skip: int = 0,
    limit: int = 100,
    sort: str = Query(default="created_at:asc", description="Up to 3 tiers: field:dir,field:dir"),
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR, AdminRole.JUDGE)),
):
    sort_tiers = []
    for tier in sort.split(",")[:3]:
        parts = tier.strip().split(":")
        if len(parts) == 2:
            sort_tiers.append((parts[0], parts[1]))
    students = await crud.list_students(
        db, institution_id=institution_id, category_id=category_id,
        review_status=review_status, regret_sent=regret_sent,
        is_deleted=is_deleted, skip=skip, limit=limit, sort_tiers=sort_tiers,
    )
    return [_with_presigned(s) for s in students]


# ─── 2. Analytics Export (.xlsx) ──────────────────────────────────────────────

@router.get("/export_analysis/", status_code=200)
@router.get("/export_analysis", status_code=200)
async def export_analysis(
    pivot: str = Query(default="timeline"),
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Generates multi-tab Excel analytics workbook with Jamia Mosque styling."""
    students = (await db.execute(select(Student).where(Student.is_deleted == False))).scalars().all()
    categories = (await db.execute(select(Category))).scalars().all()
    institutions = (await db.execute(select(Institution))).scalars().all()

    excel_bytes = generate_comprehensive_analytics_workbook(
        students=list(students),
        categories=list(categories),
        institutions=list(institutions),
        pivot=pivot,
    )

    filename = f"Musabaqa_Analytics_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─── 3. Duplicate Checking ───────────────────────────────────────────────────

@router.post("/check-duplicate", status_code=200)
async def check_duplicate(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Checks if national ID, birth certificate, phone, or name already exists."""
    national_id = str(data.get("national_id") or "").strip()
    phone = str(data.get("guardian_phone") or data.get("phone") or "").strip()
    full_name = str(data.get("full_name") or "").strip()

    matched_fields = []
    existing_id = None

    if national_id:
        match = (await db.execute(
            select(Student).where(Student.national_id == national_id, Student.is_deleted == False)
        )).scalars().first()
        if match:
            matched_fields.append("national_id")
            existing_id = match.id

    if phone and not existing_id:
        match = (await db.execute(
            select(Student).where(Student.guardian_phone == phone, Student.is_deleted == False)
        )).scalars().first()
        if match:
            matched_fields.append("guardian_phone")
            existing_id = match.id

    return {
        "exists": len(matched_fields) > 0,
        "matched_fields": matched_fields,
        "existing_student_id": existing_id,
    }


# ─── 4. Single Record Operations ──────────────────────────────────────────────

@router.get("/{student_id}", response_model=StudentRead)
async def get_student(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    return _with_presigned(await crud.get_student(db, student_id))


@router.patch("/{student_id}", response_model=StudentRead)
async def update_student(
    student_id: int,
    data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    actor_type, user_or_inst = actor
    student = await crud.get_student(db, student_id)
    if actor_type == "institution" and student.institution_id != user_or_inst.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden to this candidate record")

    s = await crud.update_student(db, student_id, data)
    await db.commit()
    return _with_presigned(s)


# ─── 5. Media & Presigned S3 URLs ─────────────────────────────────────────────

@router.get("/{student_id}/photo_url/", status_code=200)
@router.get("/{student_id}/photo_url", status_code=200)
async def get_student_photo_url(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    actor_type, user_or_inst = actor
    student = await crud.get_student(db, student_id)
    if actor_type == "institution" and student.institution_id != user_or_inst.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden to this candidate record")
    url = generate_presigned_url(student.photo) if student.photo else None
    return {"url": url}


@router.get("/{student_id}/doc_url/", status_code=200)
@router.get("/{student_id}/doc_url", status_code=200)
async def get_student_doc_url(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    actor_type, user_or_inst = actor
    student = await crud.get_student(db, student_id)
    if actor_type == "institution" and student.institution_id != user_or_inst.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden to this candidate record")
    url = generate_presigned_url(student.id_document) if student.id_document else None
    return {"url": url}


@router.post("/{student_id}/photo", status_code=200)
async def upload_student_photo(
    student_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    """Uploads candidate passport photo to S3 and updates student.photo."""
    actor_type, user_or_inst = actor
    student = await crud.get_student(db, student_id)
    if actor_type == "institution" and student.institution_id != user_or_inst.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden to this candidate record")

    contents = await file.read()
    s3_key = passport_photo_upload_key(student.full_name, student.national_id, file.filename or "photo.jpg")
    
    upload_bytes(s3_key, contents, file.content_type or "image/jpeg")
    student.photo = s3_key
    db.add(student)
    await db.commit()

    presigned = generate_presigned_url(s3_key)
    return {"s3_key": s3_key, "url": presigned}


@router.post("/{student_id}/id-document", status_code=200)
async def upload_student_id_document(
    student_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor=Depends(get_current_actor),
):
    """Uploads candidate identification document (PDF/Image) to S3."""
    actor_type, user_or_inst = actor
    student = await crud.get_student(db, student_id)
    if actor_type == "institution" and student.institution_id != user_or_inst.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden to this candidate record")

    contents = await file.read()
    s3_key = id_document_upload_key(student.full_name, student.national_id, file.filename or "doc.pdf")
    
    upload_bytes(s3_key, contents, file.content_type or "application/pdf")
    student.id_document = s3_key
    db.add(student)
    await db.commit()

    presigned = generate_presigned_url(s3_key)
    return {"s3_key": s3_key, "url": presigned}


# ─── 6. Official PDF Compilation & Merging ────────────────────────────────────

@router.get("/{student_id}/download_pdf/", status_code=200)
@router.get("/{student_id}/pdf", status_code=200)
async def download_student_pdf(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Generates official candidate dossier PDF and merges page 2 ID document."""
    student = await crud.get_student(db, student_id)
    inst = await db.get(Institution, student.institution_id)
    cat = await db.get(Category, student.category_id)

    pdf_bytes = generate_single_student_pdf(student, category=cat, institution=inst)
    safe_ascii_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", student.full_name or "").strip("_") or f"student_{student.id}"
    fallback_filename = f"REF-{student.id:05d}_{safe_ascii_name}_Dossier.pdf"
    encoded_filename = urllib.parse.quote(f"REF-{student.id:05d}_{student.full_name or 'student'}_Dossier.pdf")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{fallback_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        },
    )


# ─── 7. Workflow Actions (Review, Category Change, Archival) ──────────────────

@router.post("/{student_id}/approve", response_model=StudentRead)
async def approve_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.approve_student(db, student_id)
    inst = await db.get(Institution, student.institution_id)
    cat = await db.get(Category, student.category_id)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.UPDATE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "approve"}))
    await db.commit()
    await notifications.notify_student_approved(student, inst, cat)
    return _with_presigned(student)


@router.post("/{student_id}/reject", response_model=StudentRead)
async def reject_student(
    student_id: int,
    body: StudentReject,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.reject_student(db, student_id, body.rejection_reason)
    inst = await db.get(Institution, student.institution_id)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.UPDATE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "reject", "reason": body.rejection_reason}))
    await db.commit()
    await notifications.notify_student_rejected(student, inst)
    return _with_presigned(student)


@router.patch("/{student_id}/category", response_model=StudentRead)
async def reassign_category(
    student_id: int,
    data: StudentReassignCategory,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.get_student(db, student_id)
    old_cat = await db.get(Category, student.category_id)
    new_cat = await db.get(Category, data.new_category_id)
    inst = await db.get(Institution, student.institution_id)

    updated_student = await crud.reassign_category(db, student_id, data)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.UPDATE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "reassign_category", "new_category_id": data.new_category_id}))
    await db.commit()

    try:
        old_name = old_cat.name_en if old_cat else f"Category #{student.category_id}"
        new_name = new_cat.name_en if new_cat else f"Category #{data.new_category_id}"
        await notifications.send_category_change_email(updated_student, inst, old_name, new_name)
    except Exception:
        pass

    return _with_presigned(updated_student)


# ─── 8. Soft Delete, Restore, Permanent Delete ───────────────────────────────

@router.delete("/{student_id}", response_model=StudentRead)
async def soft_delete_student(
    student_id: int,
    body: StudentSoftDelete,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.soft_delete_student(db, student_id, body)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.DELETE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"reason": body.deletion_reason}))
    await db.commit()
    return _with_presigned(student)


@router.post("/{student_id}/restore", response_model=StudentRead)
async def restore_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.restore_student(db, student_id)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.UPDATE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "restore"}))
    await db.commit()
    return _with_presigned(student)


@router.delete("/{student_id}/permanent", status_code=204)
async def permanent_delete_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN)),
):
    await crud.permanent_delete_student(db, student_id)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.DELETE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "permanent_delete"}))
    await db.commit()


@router.patch("/{student_id}/deletion-reason", response_model=StudentRead)
async def update_deletion_reason(
    student_id: int,
    data: StudentUpdateDeletionReason,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.update_deletion_reason(db, student_id, data)
    await db.commit()
    return _with_presigned(student)


# ─── 9. Bulk Operations ───────────────────────────────────────────────────────

@router.delete("/bulk/soft-delete", response_model=list[StudentRead])
async def bulk_soft_delete(
    body: BulkSoftDelete,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    students = await crud.bulk_soft_delete(db, body.student_ids, body.deletion_reason)
    await db.commit()
    return [_with_presigned(s) for s in students]


@router.post("/bulk/restore", response_model=list[StudentRead])
async def bulk_restore(
    body: BulkStudentIds,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    students = await crud.bulk_restore(db, body.student_ids)
    await db.commit()
    return [_with_presigned(s) for s in students]


@router.delete("/bulk/permanent", status_code=200)
async def bulk_permanent_delete(
    body: BulkStudentIds,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN)),
):
    count = await crud.bulk_permanent_delete(db, body.student_ids)
    await db.commit()
    return {"deleted": count}


# ─── 10. Regret Emails ────────────────────────────────────────────────────────

@router.post("/{student_id}/regret-email", status_code=200)
async def send_regret_email_endpoint(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    student = await crud.get_student(db, student_id)
    inst = await db.get(Institution, student.institution_id)
    
    await notifications.send_regret_email(student, inst, reason=student.deletion_reason)
    
    student.regret_email_sent = True
    student.regret_email_sent_at = datetime.now(timezone.utc)
    db.add(student)
    db.add(RegretEmailLog(student_id=student_id, sent_by=staff.id))
    await db.commit()
    return {"sent": True}


@router.post("/bulk/regret-email", status_code=200)
async def bulk_regret_email(
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    """Send regret emails to all students where regret_email_sent=False."""
    from app.workers.tasks import send_bulk_regret_emails_task
    unsent = (await db.execute(
        select(Student.id).where(
            Student.regret_email_sent == False,
            Student.is_deleted == False,
        )
    )).scalars().all()
    send_bulk_regret_emails_task.delay(list(unsent))
    return {"queued": len(unsent)}
