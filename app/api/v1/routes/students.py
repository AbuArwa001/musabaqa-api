from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_institution, require_role
from app.crud import students as crud
from app.models.admin_user import AdminRole
from app.models.student import StudentReviewStatus
from app.schemas.student import (
    StudentCreate, StudentRead, StudentUpdate, StudentApprove, StudentReject,
    StudentReassignCategory, StudentSoftDelete, StudentUpdateDeletionReason,
    BulkSoftDelete, BulkStudentIds,
)
from app.services import notifications
from app.services.s3 import generate_presigned_url
from app.models.audit import AuditLog, AuditAction

router = APIRouter(prefix="/students", tags=["Students"])


def _with_presigned(student) -> dict:
    """Replace raw S3 keys with presigned URLs before returning to client."""
    d = student.__dict__.copy()
    if d.get("photo"):
        d["photo"] = generate_presigned_url(d["photo"])
    if d.get("id_document"):
        d["id_document"] = generate_presigned_url(d["id_document"])
    return d


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
    db.add(AuditLog(actor_id=None, action=AuditAction.CREATE, module="students",
                    target_record_id=student.id, ip_address=request.client.host, payload={}))
    await db.commit()
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
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    s = await crud.update_student(db, student_id, data)
    await db.commit()
    return _with_presigned(s)


@router.post("/{student_id}/approve", response_model=StudentRead)
async def approve_student(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    from app.models.institution import Institution
    from app.models.category import Category
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
    from app.models.institution import Institution
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
    staff=Depends(require_role(AdminRole.SUPERADMIN)),
):
    student = await crud.reassign_category(db, student_id, data)
    db.add(AuditLog(actor_id=staff.id, action=AuditAction.UPDATE, module="students",
                    target_record_id=student_id, ip_address=request.client.host,
                    payload={"action": "reassign_category", "new_category_id": data.new_category_id}))
    await db.commit()
    return _with_presigned(student)


# ------ Soft delete / restore / permanent delete ------

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
    """Edit deletion_reason ONLY — does NOT re-trigger any notification."""
    student = await crud.update_deletion_reason(db, student_id, data)
    await db.commit()
    return _with_presigned(student)


# ------ Bulk operations ------

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


# ------ Regret emails ------

@router.post("/{student_id}/regret-email", status_code=200)
async def send_regret_email(
    student_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    staff=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    from app.models.institution import Institution
    from app.models.audit import RegretEmailLog
    from datetime import datetime, timezone
    student = await crud.get_student(db, student_id)
    inst = await db.get(Institution, student.institution_id)
    await notifications.send_regret_email(student, inst)
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
    from sqlmodel import select
    from app.models.student import Student
    unsent = (await db.execute(
        select(Student.id).where(
            Student.regret_email_sent == False,
            Student.is_deleted == False,
        )
    )).scalars().all()
    send_bulk_regret_emails_task.delay(list(unsent))
    return {"queued": len(unsent)}
