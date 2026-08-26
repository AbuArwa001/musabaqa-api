"""
Student CRUD with full business rule enforcement:
- Cross-competition duplicate detection (national_id, guardian_phone)
- Max 4 active students per institution
- UNIQUE (institution_id, category_id) constraint feedback
- Soft delete / restore / permanent delete
- Category reassignment with age re-validation
- Editing deletion_reason does NOT notify (flag passed through)
- Multi-tier sort (up to 3 tiers)
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func
from sqlmodel import select

from app.models.student import Student, StudentReviewStatus
from app.models.category import Category
from app.schemas.student import (
    StudentCreate, StudentUpdate, StudentReassignCategory,
    StudentSoftDelete, StudentUpdateDeletionReason,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SortField = Literal[
    "full_name", "dob", "created_at", "review_status", "is_deleted", "is_backup"
]
SortTier = tuple[SortField, Literal["asc", "desc"]]


async def _check_duplicates(
    db: AsyncSession, national_id: str, guardian_phone: str, exclude_id: int | None = None
) -> None:
    """Enforce cross-competition uniqueness for national_id and guardian_phone."""
    q_nid = select(Student).where(Student.national_id == national_id)
    q_phone = select(Student).where(Student.guardian_phone == guardian_phone)
    if exclude_id:
        q_nid = q_nid.where(Student.id != exclude_id)
        q_phone = q_phone.where(Student.id != exclude_id)
    if (await db.execute(q_nid)).scalar_one_or_none():
        raise HTTPException(409, "national_id already registered in this competition")
    if (await db.execute(q_phone)).scalar_one_or_none():
        raise HTTPException(409, "guardian_phone already registered in this competition")


async def _check_institution_cap(
    db: AsyncSession, institution_id: int, exclude_id: int | None = None
) -> None:
    """Max 4 active (non-deleted) students per institution."""
    q = (
        select(func.count())
        .select_from(Student)
        .where(Student.institution_id == institution_id, Student.is_deleted == False)
    )
    if exclude_id:
        q = q.where(Student.id != exclude_id)
    count = (await db.execute(q)).scalar_one()
    if count >= 4:
        raise HTTPException(409, "Institution already has 4 active students (maximum)")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def get_student(db: AsyncSession, student_id: int) -> Student:
    s = await db.get(Student, student_id)
    if not s:
        raise HTTPException(404, "Student not found")
    return s


async def list_students(
    db: AsyncSession,
    institution_id: int | None = None,
    category_id: int | None = None,
    review_status: StudentReviewStatus | None = None,
    regret_sent: bool | None = None,
    is_deleted: bool = False,
    skip: int = 0,
    limit: int = 100,
    sort_tiers: list[SortTier] | None = None,
) -> list[Student]:
    q = select(Student).where(Student.is_deleted == is_deleted)
    if institution_id:
        q = q.where(Student.institution_id == institution_id)
    if category_id:
        q = q.where(Student.category_id == category_id)
    if review_status:
        q = q.where(Student.review_status == review_status)
    if regret_sent is not None:
        q = q.where(Student.regret_email_sent == regret_sent)

    # Multi-tier sort (up to 3 tiers)
    from sqlalchemy import asc, desc
    col_map = {
        "full_name": Student.full_name,
        "dob": Student.dob,
        "created_at": Student.created_at,
        "review_status": Student.review_status,
        "is_deleted": Student.is_deleted,
        "is_backup": Student.is_backup,
    }
    if sort_tiers:
        for field, direction in sort_tiers[:3]:
            col = col_map.get(field)
            if col is not None:
                q = q.order_by(asc(col) if direction == "asc" else desc(col))
    else:
        q = q.order_by(Student.created_at.asc())

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_student(db: AsyncSession, data: StudentCreate) -> Student:
    await _check_duplicates(db, data.national_id, data.guardian_phone)
    await _check_institution_cap(db, data.institution_id)

    # Check UNIQUE (institution_id, category_id)
    existing = (await db.execute(
        select(Student).where(
            Student.institution_id == data.institution_id,
            Student.category_id == data.category_id,
            Student.is_deleted == False,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "This institution already has a student in that category")

    student = Student(**data.model_dump())
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def update_student(
    db: AsyncSession, student_id: int, data: StudentUpdate
) -> Student:
    student = await get_student(db, student_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(student, field, value)
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


async def approve_student(db: AsyncSession, student_id: int) -> Student:
    student = await get_student(db, student_id)
    student.review_status = StudentReviewStatus.APPROVED
    student.rejection_reason = None
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


async def reject_student(db: AsyncSession, student_id: int, reason: str) -> Student:
    student = await get_student(db, student_id)
    student.review_status = StudentReviewStatus.REJECTED
    student.rejection_reason = reason
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# Category reassignment (re-validates age, supports exemption)
# ---------------------------------------------------------------------------

async def reassign_category(
    db: AsyncSession, student_id: int, data: StudentReassignCategory
) -> Student:
    student = await get_student(db, student_id)
    new_cat = await db.get(Category, data.new_category_id)
    if not new_cat:
        raise HTTPException(404, "Target category not found")

    # Age validation against new category
    from datetime import date
    today = date.today()
    age = today.year - student.dob.year - (
        (today.month, today.day) < (student.dob.month, student.dob.day)
    )
    age_ok = True
    if new_cat.min_age and age < new_cat.min_age:
        age_ok = False
    if age > new_cat.max_age:
        age_ok = False

    if not age_ok and not data.age_exemption:
        raise HTTPException(
            422,
            f"Student age {age} is outside the target category range "
            f"({new_cat.min_age}-{new_cat.max_age}). "
            "Set age_exemption=true with an age_exemption_reason to override."
        )
    if not age_ok and data.age_exemption and not data.age_exemption_reason:
        raise HTTPException(422, "age_exemption_reason is required when granting an exemption")

    # Check UNIQUE constraint in new category
    conflict = (await db.execute(
        select(Student).where(
            Student.institution_id == student.institution_id,
            Student.category_id == data.new_category_id,
            Student.is_deleted == False,
            Student.id != student_id,
        )
    )).scalar_one_or_none()
    if conflict:
        raise HTTPException(409, "Institution already has a student in the target category")

    student.category_id = data.new_category_id
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# Soft delete / restore / permanent delete
# ---------------------------------------------------------------------------

async def soft_delete_student(
    db: AsyncSession, student_id: int, data: StudentSoftDelete
) -> Student:
    student = await get_student(db, student_id)
    if student.is_deleted:
        raise HTTPException(409, "Student is already soft-deleted")
    student.is_deleted = True
    student.deletion_reason = data.deletion_reason
    student.archived_at = datetime.now(timezone.utc)
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student  # Caller is responsible for NOT firing notifications


async def restore_student(db: AsyncSession, student_id: int) -> Student:
    student = await get_student(db, student_id)
    if not student.is_deleted:
        raise HTTPException(409, "Student is not deleted")
    student.is_deleted = False
    student.deletion_reason = None
    student.archived_at = None
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


async def permanent_delete_student(db: AsyncSession, student_id: int) -> None:
    """Irreversible. SUPERADMIN only (enforced at route layer)."""
    student = await get_student(db, student_id)
    await db.delete(student)
    await db.flush()


async def update_deletion_reason(
    db: AsyncSession, student_id: int, data: StudentUpdateDeletionReason
) -> Student:
    """
    Edit deletion_reason ONLY — does NOT change is_deleted, archived_at,
    and MUST NOT trigger any notification (enforced here and at route layer).
    """
    student = await get_student(db, student_id)
    if not student.is_deleted:
        raise HTTPException(409, "Student is not in a deleted state")
    student.deletion_reason = data.deletion_reason
    db.add(student)
    await db.flush()
    await db.refresh(student)
    return student


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------

async def bulk_soft_delete(
    db: AsyncSession, student_ids: list[int], deletion_reason: str
) -> list[Student]:
    results = []
    for sid in student_ids:
        try:
            s = await soft_delete_student(
                db, sid, StudentSoftDelete(deletion_reason=deletion_reason)
            )
            results.append(s)
        except HTTPException:
            pass  # Skip already-deleted or missing; partial success allowed
    return results


async def bulk_restore(db: AsyncSession, student_ids: list[int]) -> list[Student]:
    results = []
    for sid in student_ids:
        try:
            results.append(await restore_student(db, sid))
        except HTTPException:
            pass
    return results


async def bulk_permanent_delete(db: AsyncSession, student_ids: list[int]) -> int:
    count = 0
    for sid in student_ids:
        try:
            await permanent_delete_student(db, sid)
            count += 1
        except HTTPException:
            pass
    return count
