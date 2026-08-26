import uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.student import Student
from app.models.category import Category
from app.models.region import Region
from app.models.round import Round
from app.services.reporting import (
    generate_print_ready_report,
    generate_power_bi_export,
    generate_granular_export,
)
from app.services.s3 import generate_presigned_url

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/print-ready")
async def print_ready_report(
    group_by: str | None = Query(default=None, description="'region' or 'category'"),
    columns: str = Query(
        default="category,region,institution,age,registration_date,phone,review_status",
        description="Comma-separated column names",
    ),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN, AdminRole.MODERATOR)),
):
    col_list = [c.strip() for c in columns.split(",")]
    students_raw = (await db.execute(select(Student))).scalars().all()

    # Build flat dicts for the reporter
    rows = []
    for s in students_raw:
        rows.append({
            "category": str(s.category_id),
            "institution": str(s.institution_id),
            "age": str(s.dob),
            "registration_date": str(s.created_at.date()),
            "phone": s.guardian_phone,
            "review_status": s.review_status.value,
        })

    xlsx = generate_print_ready_report(rows, col_list, group_by=group_by)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=print_ready_report.xlsx"},
    )


@router.get("/power-bi")
async def power_bi_export(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    students = (await db.execute(select(Student))).scalars().all()
    regions = (await db.execute(select(Region))).scalars().all()
    categories = (await db.execute(select(Category))).scalars().all()
    rounds = (await db.execute(select(Round))).scalars().all()

    def to_dict(obj) -> dict:
        return {c.name: getattr(obj, c.name) for c in obj.__class__.__table__.columns}

    xlsx = generate_power_bi_export(
        [to_dict(s) for s in students],
        [to_dict(r) for r in regions],
        [to_dict(c) for c in categories],
        [to_dict(r) for r in rounds],
    )
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=power_bi_export.xlsx"},
    )


@router.get("/granular")
async def granular_export(
    include_presigned_urls: bool = False,
    include_photos: bool = False,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    students = (await db.execute(select(Student))).scalars().all()
    rows = []
    for s in students:
        row = {c.name: str(getattr(s, c.name, "")) for c in s.__class__.__table__.columns}
        if include_presigned_urls:
            row["photo_url"] = generate_presigned_url(s.photo) if s.photo else ""
            row["id_document_url"] = generate_presigned_url(s.id_document) if s.id_document else ""
        rows.append(row)

    xlsx = generate_granular_export(rows, include_presigned_urls, include_photos)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=granular_export.xlsx"},
    )
