"""
Tests for cross-competition duplicate detection and student caps.

Covers:
1. Cross-institution national_id collision rejected
2. Cross-institution guardian_phone collision rejected
3. UNIQUE (institution_id, category_id) enforced
4. Max 4 active students per institution
"""

import pytest
from datetime import date
from fastapi import HTTPException

from app.models.category import Category, CategoryGroup
from app.models.county import County
from app.models.institution import Institution, InstitutionType, InstitutionStatus, PreferredLanguage
from app.models.region import Region
from app.models.student import StudentReviewStatus, Gender
from app.core.security import hash_password
from app.crud.students import create_student, _check_duplicates
from app.schemas.student import StudentCreate


async def _make_env(db):
    county = County(name="DupTestCounty", active=True)
    db.add(county)
    await db.flush()
    region = Region(name_en="DupRegion", name_ar="منطقة", county_id=county.id)
    db.add(region)
    await db.flush()
    cat1 = Category(name_en="Cat1", name_ar="ف١", min_age=7, max_age=18,
                    category_group=CategoryGroup.JUZ_10_15_20, display_order=1)
    cat2 = Category(name_en="Cat2", name_ar="ف٢", min_age=7, max_age=18,
                    category_group=CategoryGroup.JUZ_10_15_20, display_order=2)
    cat3 = Category(name_en="Cat3", name_ar="ف٣", min_age=7, max_age=18,
                    category_group=CategoryGroup.JUZ_10_15_20, display_order=3)
    cat4 = Category(name_en="Cat4", name_ar="ف٤", min_age=7, max_age=18,
                    category_group=CategoryGroup.JUZ_10_15_20, display_order=4)
    cat5 = Category(name_en="Cat5", name_ar="ف٥", min_age=7, max_age=18,
                    category_group=CategoryGroup.JUZ_10_15_20, display_order=5)
    db.add_all([cat1, cat2, cat3, cat4, cat5])
    await db.flush()

    inst1 = Institution(
        name="Inst One", type=InstitutionType.MADRASA, contact_person="A",
        phone="+10", email="inst1@dup.com", password_hash=hash_password("x"),
        region_id=region.id, status=InstitutionStatus.APPROVED,
        preferred_language=PreferredLanguage.EN,
    )
    inst2 = Institution(
        name="Inst Two", type=InstitutionType.MADRASA, contact_person="B",
        phone="+20", email="inst2@dup.com", password_hash=hash_password("x"),
        region_id=region.id, status=InstitutionStatus.APPROVED,
        preferred_language=PreferredLanguage.EN,
    )
    db.add_all([inst1, inst2])
    await db.flush()
    return inst1, inst2, [cat1, cat2, cat3, cat4, cat5]


def _make_create_data(institution_id, category_id, national_id, phone, name="Test Student"):
    return StudentCreate(
        institution_id=institution_id,
        category_id=category_id,
        full_name=name,
        dob=date(2012, 6, 15),
        gender=Gender.MALE,
        national_id=national_id,
        guardian_phone=phone,
    )


@pytest.mark.asyncio
async def test_cross_institution_national_id_rejected(db):
    """Same national_id at two different institutions → rejected."""
    inst1, inst2, cats = await _make_env(db)

    # Create student at inst1
    await create_student(db, _make_create_data(inst1.id, cats[0].id, "NID-CLASH-001", "+2541000001"))
    await db.flush()

    # Attempt same national_id at inst2
    with pytest.raises(HTTPException) as exc_info:
        await create_student(db, _make_create_data(inst2.id, cats[0].id, "NID-CLASH-001", "+2541000002"))
    assert exc_info.value.status_code == 409
    assert "national_id" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cross_institution_guardian_phone_rejected(db):
    """Same guardian_phone at two different institutions → rejected."""
    inst1, inst2, cats = await _make_env(db)

    await create_student(db, _make_create_data(inst1.id, cats[0].id, "NID-PHONE-001", "+2542000001"))
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await create_student(db, _make_create_data(inst2.id, cats[0].id, "NID-PHONE-002", "+2542000001"))
    assert exc_info.value.status_code == 409
    assert "guardian_phone" in exc_info.value.detail


@pytest.mark.asyncio
async def test_unique_institution_category_constraint(db):
    """Same institution + same category = rejected (one student per category per institution)."""
    inst1, inst2, cats = await _make_env(db)

    await create_student(db, _make_create_data(inst1.id, cats[0].id, "NID-UNQ-001", "+2543000001"))
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await create_student(db, _make_create_data(inst1.id, cats[0].id, "NID-UNQ-002", "+2543000002"))
    assert exc_info.value.status_code == 409
    assert "category" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_max_4_active_students_per_institution(db):
    """Exactly 4 active students allowed per institution; the 5th is rejected."""
    inst1, inst2, cats = await _make_env(db)

    # Add 4 students to inst1 (in 4 different categories)
    for i in range(4):
        await create_student(db, _make_create_data(
            inst1.id, cats[i].id, f"NID-CAP-{i:03d}", f"+2544{i:06d}"
        ))
        await db.flush()

    # 5th student should be rejected
    with pytest.raises(HTTPException) as exc_info:
        await create_student(db, _make_create_data(
            inst1.id, cats[4].id, "NID-CAP-004", "+2544000004"
        ))
    assert exc_info.value.status_code == 409
    assert "4" in exc_info.value.detail  # "already has 4 active students"


@pytest.mark.asyncio
async def test_same_institution_different_categories_allowed(db):
    """Same institution, different categories = allowed (up to the cap)."""
    inst1, inst2, cats = await _make_env(db)

    for i in range(4):
        result = await create_student(db, _make_create_data(
            inst1.id, cats[i].id, f"NID-DIFF-{i:03d}", f"+2545{i:06d}"
        ))
        await db.flush()
        assert result.id is not None
