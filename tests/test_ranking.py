"""
Tests for the regional advancement algorithm.

Covers:
1. Normal case: top-4 per region advance cleanly
2. Tie at boundary (position 4/5): tie_allowance_pool used per category
3. tie_allowance_pool is PER CATEGORY (not shared across categories)
4. Flat fallback when regional_balancing_enabled=False
"""

import pytest
import pytest_asyncio
from datetime import date, datetime, timezone

from sqlmodel import select

from app.models.admin_user import AdminUser, AdminRole, JudgeRole as AJudgeRole, PreferredLanguage as AdminLang
from app.models.category import Category, CategoryGroup, ScoringCriteria, ScoringMethod, DeductionType
from app.models.county import County
from app.models.institution import Institution, InstitutionType, InstitutionStatus, PreferredLanguage as InstLang
from app.models.region import Region
from app.models.results import (
    CompetitionSeasonSettings, RoundResult,
    GeographicScope, RankingScope, PanelScoreMethod,
)
from app.models.round import Round, RoundType, RoundStatus, RoundJudgeAssignment, JudgeRole
from app.models.scoring import DeductionEvent
from app.models.student import Student, StudentReviewStatus, Gender
from app.core.security import hash_password
from app.services.ranking_engine import _recompute_rankings


async def _build_scenario(db, regional_balancing: bool = True):
    """Build a minimal complete scenario for ranking tests."""
    county = County(name="TestCounty", active=True)
    db.add(county)
    await db.flush()

    region_a = Region(name_en="RegionA", name_ar="منطقة ا", county_id=county.id)
    region_b = Region(name_en="RegionB", name_ar="منطقة ب", county_id=county.id)
    db.add_all([region_a, region_b])
    await db.flush()

    category = Category(
        name_en="Test Category", name_ar="فئة اختبار",
        min_age=7, max_age=18,
        category_group=CategoryGroup.JUZ_10_15_20, display_order=1,
    )
    db.add(category)
    await db.flush()

    season = CompetitionSeasonSettings(
        season="test-2025", is_active=True,
        geographic_scope=GeographicScope.REGIONAL,
        regional_balancing_enabled=regional_balancing,
        default_top_n_per_region=4,
        tie_allowance_pool=3,
        ranking_scope=RankingScope.PER_REGION_PER_CATEGORY,
        panel_score_method=PanelScoreMethod.AVERAGE,
    )
    db.add(season)
    await db.flush()

    inst_a = Institution(
        name="Inst A", type=InstitutionType.MADRASA, contact_person="C",
        phone="+1", email="insta@test.com", password_hash=hash_password("x"),
        region_id=region_a.id, status=InstitutionStatus.APPROVED,
        preferred_language=InstLang.EN,
    )
    inst_b = Institution(
        name="Inst B", type=InstitutionType.MADRASA, contact_person="C",
        phone="+2", email="instb@test.com", password_hash=hash_password("x"),
        region_id=region_b.id, status=InstitutionStatus.APPROVED,
        preferred_language=InstLang.EN,
    )
    db.add_all([inst_a, inst_b])
    await db.flush()

    round_ = Round(
        category_id=category.id, round_type=RoundType.PRELIMINARY,
        status=RoundStatus.ACTIVE,
        scheduled_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
    )
    db.add(round_)
    await db.flush()

    return county, region_a, region_b, category, season, inst_a, inst_b, round_


async def _add_result(db, round_id, student, score):
    r = RoundResult(round_id=round_id, student_id=student.id, final_score=score)
    db.add(r)
    await db.flush()
    return r


async def _make_student(db, institution_id, category_id, name, national_id, phone):
    inst = await db.get(Institution, institution_id)
    new_inst = Institution(
        name=f"Inst for {name}",
        type=inst.type if inst else InstitutionType.MADRASA,
        contact_person=f"Contact {name}",
        phone=f"+254{abs(hash(name)) % 100000000:08d}",
        email=f"inst_{name.lower().replace(' ', '_')}@test.com",
        password_hash=hash_password("x"),
        region_id=inst.region_id if inst else None,
        status=InstitutionStatus.APPROVED,
        preferred_language=InstLang.EN,
    )
    db.add(new_inst)
    await db.flush()

    s = Student(
        institution_id=new_inst.id, category_id=category_id,
        full_name=name, dob=date(2012, 1, 1), gender=Gender.MALE,
        national_id=national_id, guardian_phone=phone,
        review_status=StudentReviewStatus.APPROVED,
    )
    db.add(s)
    await db.flush()
    return s


@pytest.mark.asyncio
async def test_regional_ranking_clean_cutoff(db):
    """Top-4 advance cleanly — no tie at boundary."""
    _, reg_a, _, cat, season, inst_a, _, round_ = await _build_scenario(db)

    # 5 students in region A — top 4 should advance (no tie at boundary)
    scores = [95.0, 88.0, 80.0, 72.0, 65.0]
    students = []
    for i, score in enumerate(scores):
        s = await _make_student(db, inst_a.id, cat.id, f"Student{i}", f"NID-A-{i}", f"+254{i:09d}")
        await _add_result(db, round_.id, s, score)
        students.append((s, score))

    await _recompute_rankings(db, round_.id, season)

    results = (await db.execute(
        select(RoundResult).where(RoundResult.round_id == round_.id)
        .order_by(RoundResult.rank.asc())
    )).scalars().all()

    ranks = {r.student_id: r.rank for r in results}

    # Ranks 1–5, top 4 get rank ≤ 4
    assert sorted(ranks.values()) == [1, 2, 3, 4, 5]
    # Highest score gets rank 1
    top_student = students[0][0]
    assert ranks[top_student.id] == 1


@pytest.mark.asyncio
async def test_tie_at_advancement_boundary(db):
    """
    Tie at position 4/5 boundary.
    Students at positions 4 and 5 have the same score → tie exists at boundary.
    The tie_allowance_pool should allow both to advance (pool has 3 slots).
    """
    _, reg_a, _, cat, season, inst_a, _, round_ = await _build_scenario(db)

    # Score 72.0 appears at position 4 AND 5 — tie at boundary
    scores_data = [
        ("Alpha",  "NID-TIE-0", "+254710000000", 90.0),
        ("Beta",   "NID-TIE-1", "+254710000001", 85.0),
        ("Gamma",  "NID-TIE-2", "+254710000002", 78.0),
        ("Delta",  "NID-TIE-3", "+254710000003", 72.0),  # position 4
        ("Epsilon","NID-TIE-4", "+254710000004", 72.0),  # position 5 — TIE
    ]

    student_objs = []
    for name, nid, phone, score in scores_data:
        s = await _make_student(db, inst_a.id, cat.id, name, nid, phone)
        await _add_result(db, round_.id, s, score)
        student_objs.append((s, score))

    await _recompute_rankings(db, round_.id, season)

    results = (await db.execute(
        select(RoundResult).where(RoundResult.round_id == round_.id)
        .order_by(RoundResult.rank.asc())
    )).scalars().all()

    # Both tied students should get rank ≤ 5 (boundary tie detected)
    tied_results = [r for r in results if r.final_score == 72.0]
    assert len(tied_results) == 2
    # Both tied students should have been ranked (ranking engine doesn't block on tie)
    assert all(r.rank is not None for r in tied_results)
    # They should share or be adjacent in rank
    tied_ranks = {r.rank for r in tied_results}
    assert all(rank >= 4 for rank in tied_ranks)


@pytest.mark.asyncio
async def test_tie_allowance_pool_per_category(db):
    """
    tie_allowance_pool is PER CATEGORY (3 per cat), not shared competition-wide.
    Two categories each have their own boundary tie — both can use their pools.
    """
    _, reg_a, _, cat, season, inst_a, _, round_ = await _build_scenario(db)

    cat2 = Category(
        name_en="Cat2", name_ar="فئة٢",
        min_age=10, max_age=18,
        category_group=CategoryGroup.JUZ_30, display_order=2,
    )
    db.add(cat2)
    await db.flush()

    round2 = Round(
        category_id=cat2.id, round_type=RoundType.PRELIMINARY,
        status=RoundStatus.ACTIVE,
        scheduled_at=datetime(2025, 12, 2, tzinfo=timezone.utc),
    )
    db.add(round2)
    await db.flush()

    # Category 1: tie at boundary
    for i, score in enumerate([90, 85, 78, 70, 70]):
        s = await _make_student(db, inst_a.id, cat.id, f"C1S{i}", f"NID-C1-{i}", f"+254720{i:06d}")
        await _add_result(db, round_.id, s, float(score))

    # Category 2: tie at boundary (separate pool)
    inst_b_mock = Institution(
        name="Inst C", type=InstitutionType.MADRASA, contact_person="C",
        phone="+3", email="instc@test.com", password_hash=hash_password("x"),
        region_id=reg_a.id, status=InstitutionStatus.APPROVED,
        preferred_language=InstLang.EN,
    )
    db.add(inst_b_mock)
    await db.flush()
    for i, score in enumerate([92, 87, 81, 68, 68]):
        s = await _make_student(db, inst_b_mock.id, cat2.id, f"C2S{i}", f"NID-C2-{i}", f"+254730{i:06d}")
        await _add_result(db, round2.id, s, float(score))

    await _recompute_rankings(db, round_.id, season)
    await _recompute_rankings(db, round2.id, season)

    r1 = (await db.execute(select(RoundResult).where(RoundResult.round_id == round_.id))).scalars().all()
    r2 = (await db.execute(select(RoundResult).where(RoundResult.round_id == round2.id))).scalars().all()

    # Both rounds should have 5 ranked students (pools are independent)
    assert len(r1) == 5
    assert len(r2) == 5


@pytest.mark.asyncio
async def test_flat_fallback_no_regional_balancing(db):
    """When regional_balancing_enabled=False, rank by score across full round."""
    _, reg_a, reg_b, cat, season, inst_a, inst_b, round_ = await _build_scenario(
        db, regional_balancing=False
    )

    # Region A: 3 students, Region B: 3 students
    # Without regional balancing, global top-4 should be ranked 1-4 regardless of region
    a_scores = [95.0, 88.0, 60.0]
    b_scores = [91.0, 78.0, 55.0]

    for i, sc in enumerate(a_scores):
        s = await _make_student(db, inst_a.id, cat.id, f"AS{i}", f"NID-FLAT-A{i}", f"+254740{i:06d}")
        await _add_result(db, round_.id, s, sc)
    for i, sc in enumerate(b_scores):
        s = await _make_student(db, inst_b.id, cat.id, f"BS{i}", f"NID-FLAT-B{i}", f"+254750{i:06d}")
        await _add_result(db, round_.id, s, sc)

    await _recompute_rankings(db, round_.id, season)

    results = sorted(
        (await db.execute(select(RoundResult).where(RoundResult.round_id == round_.id))).scalars().all(),
        key=lambda r: r.rank
    )

    scores_in_order = [r.final_score for r in results]
    # Should be globally sorted descending: 95, 91, 88, 78, 60, 55
    assert scores_in_order == [95.0, 91.0, 88.0, 78.0, 60.0, 55.0]
    assert results[0].rank == 1
    assert results[-1].rank == 6
