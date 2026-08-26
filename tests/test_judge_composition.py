"""
Tests for judge panel composition validation.

PRELIMINARY: exactly 3 REGULAR judges, 0 GUEST_NEUTRAL
FINAL:       exactly 3 REGULAR + 1 GUEST_NEUTRAL

A round with wrong composition must be REJECTED at start-round time,
BEFORE scoring begins.
"""

import pytest
from datetime import datetime, timezone
from fastapi import HTTPException

from app.models.admin_user import AdminUser, AdminRole, JudgeRole as AJudgeRole, PreferredLanguage as AdminLang
from app.models.category import Category, CategoryGroup
from app.models.county import County
from app.models.region import Region
from app.models.round import Round, RoundType, RoundStatus, RoundJudgeAssignment, JudgeRole
from app.core.security import hash_password
from app.crud.rounds import start_round, assign_judge, _validate_panel
from app.schemas.round import JudgeAssignmentCreate


async def _make_judges(db, count_regular: int, count_guest: int) -> list[AdminUser]:
    judges = []
    for i in range(count_regular):
        j = AdminUser(
            name=f"Regular {i}", email=f"regular{i}@test.com",
            password_hash=hash_password("x"),
            role=AdminRole.JUDGE, judge_role=AJudgeRole.REGULAR,
            preferred_language=AdminLang.EN, active=True,
        )
        db.add(j)
        judges.append((j, JudgeRole.REGULAR))
    for i in range(count_guest):
        j = AdminUser(
            name=f"Guest {i}", email=f"guest{i}@test.com",
            password_hash=hash_password("x"),
            role=AdminRole.JUDGE, judge_role=AJudgeRole.GUEST_NEUTRAL,
            preferred_language=AdminLang.EN, active=True,
        )
        db.add(j)
        judges.append((j, JudgeRole.GUEST_NEUTRAL))
    await db.flush()
    return judges


async def _make_round(db, round_type: RoundType, category_id: int) -> Round:
    r = Round(
        category_id=category_id, round_type=round_type, status=RoundStatus.PENDING,
        scheduled_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )
    db.add(r)
    await db.flush()
    return r


async def _setup_category(db) -> Category:
    county = County(name="JudgeTestCounty", active=True)
    db.add(county)
    await db.flush()
    region = Region(name_en="JudgeRegion", name_ar="منطقة", county_id=county.id)
    db.add(region)
    await db.flush()
    cat = Category(name_en="JudgeCat", name_ar="فئة", min_age=7, max_age=18,
                   category_group=CategoryGroup.JUZ_10_15_20, display_order=1)
    db.add(cat)
    await db.flush()
    return cat


def _build_assignments(judge_tuples, round_id) -> list[RoundJudgeAssignment]:
    return [
        RoundJudgeAssignment(round_id=round_id, admin_user_id=j.id, judge_role=role)
        for j, role in judge_tuples
    ]


# ---------------------------------------------------------------------------
# PRELIMINARY round composition tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preliminary_3_regular_passes(db):
    """PRELIMINARY + 3 REGULAR = valid."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=3, count_guest=0)
    r = await _make_round(db, RoundType.PRELIMINARY, cat.id)
    assignments = _build_assignments(judges, r.id)
    # Should NOT raise
    _validate_panel(RoundType.PRELIMINARY, assignments)


@pytest.mark.asyncio
async def test_preliminary_2_regular_rejected(db):
    """PRELIMINARY + 2 REGULAR = invalid (needs exactly 3)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=2, count_guest=0)
    r = await _make_round(db, RoundType.PRELIMINARY, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.PRELIMINARY, assignments)
    assert exc.value.status_code == 422
    assert "3 REGULAR" in exc.value.detail


@pytest.mark.asyncio
async def test_preliminary_3_regular_plus_guest_rejected(db):
    """PRELIMINARY + 3 REGULAR + 1 GUEST_NEUTRAL = invalid (no guests in preliminary)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=3, count_guest=1)
    r = await _make_round(db, RoundType.PRELIMINARY, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.PRELIMINARY, assignments)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_preliminary_4_regular_rejected(db):
    """PRELIMINARY + 4 REGULAR = invalid (max 3 for preliminary)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=4, count_guest=0)
    r = await _make_round(db, RoundType.PRELIMINARY, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.PRELIMINARY, assignments)
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# FINAL round composition tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_final_3_regular_plus_1_guest_passes(db):
    """FINAL + 3 REGULAR + 1 GUEST_NEUTRAL = valid."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=3, count_guest=1)
    r = await _make_round(db, RoundType.FINAL, cat.id)
    assignments = _build_assignments(judges, r.id)
    # Should NOT raise
    _validate_panel(RoundType.FINAL, assignments)


@pytest.mark.asyncio
async def test_final_4_regular_no_guest_rejected(db):
    """FINAL + 4 REGULAR + 0 GUEST_NEUTRAL = invalid (must have exactly 1 GUEST_NEUTRAL)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=4, count_guest=0)
    r = await _make_round(db, RoundType.FINAL, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.FINAL, assignments)
    assert exc.value.status_code == 422
    assert "GUEST_NEUTRAL" in exc.value.detail


@pytest.mark.asyncio
async def test_final_2_regular_1_guest_rejected(db):
    """FINAL + 2 REGULAR + 1 GUEST_NEUTRAL = invalid (needs 3 REGULAR)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=2, count_guest=1)
    r = await _make_round(db, RoundType.FINAL, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.FINAL, assignments)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_final_3_regular_2_guests_rejected(db):
    """FINAL + 3 REGULAR + 2 GUEST_NEUTRAL = invalid (max 1 guest)."""
    cat = await _setup_category(db)
    judges = await _make_judges(db, count_regular=3, count_guest=2)
    r = await _make_round(db, RoundType.FINAL, cat.id)
    assignments = _build_assignments(judges, r.id)
    with pytest.raises(HTTPException) as exc:
        _validate_panel(RoundType.FINAL, assignments)
    assert exc.value.status_code == 422
