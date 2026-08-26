"""
Seed data for musabaqa-api.

Seeds:
- 2 Counties: Nairobi, Kajiado
- 7 Nairobi regions + 3 Kajiado regions (with EN/AR names)
- 4 Categories with EN/AR names and correct rubric weights
- ScoringCriteria (Rubric A + B) with DeductionTypes
- CompetitionSeasonSettings (active 2025 season)
- Sample AdminUsers: 1 SUPERADMIN, 2 JUDGES
- Sample Institutions: 1 APPROVED, 1 PENDING
- Sample Students: APPROVED, PENDING_REVIEW, REJECTED states
- Sample Round (PENDING)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import AsyncSessionLocal, create_db_and_tables
from app.core.security import hash_password
from app.models.county import County
from app.models.region import Region
from app.models.institution import Institution, InstitutionType, InstitutionStatus, PreferredLanguage as InstLang
from app.models.category import Category, CategoryGroup, ScoringCriteria, ScoringMethod, DeductionType
from app.models.student import Student, StudentReviewStatus, Gender
from app.models.round import Round, RoundType, RoundStatus, RoundJudgeAssignment, JudgeRole
from app.models.admin_user import AdminUser, AdminRole, JudgeRole as AJudgeRole, PreferredLanguage as AdminLang
from app.models.results import CompetitionSeasonSettings, GeographicScope, RankingScope, PanelScoreMethod

from datetime import datetime, date, timezone


async def seed(db: AsyncSession) -> None:
    # -----------------------------------------------------------------------
    # IDEMPOTENCY: skip if already seeded
    # -----------------------------------------------------------------------
    existing = (await db.execute(select(County))).scalars().first()
    if existing:
        print("[seed] Already seeded — skipping.")
        return

    print("[seed] Seeding database...")

    # -----------------------------------------------------------------------
    # Counties
    # -----------------------------------------------------------------------
    nairobi = County(name="Nairobi", active=True)
    kajiado = County(name="Kajiado", active=True)
    db.add_all([nairobi, kajiado])
    await db.flush()

    # -----------------------------------------------------------------------
    # Regions — Nairobi (7) + Kajiado (3)
    # Kajiado has its own structured region list, NOT a single flat toggle
    # -----------------------------------------------------------------------
    nairobi_regions = [
        Region(name_en="Eastleigh",  name_ar="ايستلي",    county_id=nairobi.id),
        Region(name_en="Kasarani",   name_ar="كساراني",   county_id=nairobi.id),
        Region(name_en="South B",    name_ar="ساوث بي",   county_id=nairobi.id),
        Region(name_en="Langata",    name_ar="لانغاتا",   county_id=nairobi.id),
        Region(name_en="Embakasi",   name_ar="امباكاسي",  county_id=nairobi.id),
        Region(name_en="Westlands",  name_ar="وستلاندس",  county_id=nairobi.id),
        Region(name_en="Pumwani",    name_ar="بومواني",   county_id=nairobi.id),
    ]
    kajiado_regions = [
        Region(name_en="Kajiado Town", name_ar="مدينة كاجيادو", county_id=kajiado.id),
        Region(name_en="Kitengela",    name_ar="كيتنغيلا",     county_id=kajiado.id),
        Region(name_en="Ngong",        name_ar="نغونغ",         county_id=kajiado.id),
    ]
    db.add_all(nairobi_regions + kajiado_regions)
    await db.flush()

    eastleigh = nairobi_regions[0]
    kasarani   = nairobi_regions[1]

    # -----------------------------------------------------------------------
    # Competition Season Settings (active 2025 season)
    # ASSUMPTION: panel_score_method = AVERAGE (flagged in spec)
    # -----------------------------------------------------------------------
    season = CompetitionSeasonSettings(
        season="2025",
        is_active=True,
        geographic_scope=GeographicScope.REGIONAL,
        regional_balancing_enabled=True,
        default_top_n_per_region=4,
        tie_allowance_pool=3,
        ranking_scope=RankingScope.PER_REGION_PER_CATEGORY,
        panel_score_method=PanelScoreMethod.AVERAGE,  # ASSUMPTION
    )
    db.add(season)
    await db.flush()

    # -----------------------------------------------------------------------
    # Categories (4)
    # -----------------------------------------------------------------------
    cat_juz10 = Category(
        name_en="Juz' 1–10",   name_ar="الأجزاء ١-١٠",
        min_age=7, max_age=12,
        category_group=CategoryGroup.JUZ_10_15_20, display_order=1,
    )
    cat_juz20 = Category(
        name_en="Juz' 11–20",  name_ar="الأجزاء ١١-٢٠",
        min_age=10, max_age=15,
        category_group=CategoryGroup.JUZ_10_15_20, display_order=2,
    )
    cat_juz29 = Category(
        name_en="Juz' 21–29",  name_ar="الأجزاء ٢١-٢٩",
        min_age=13, max_age=18,
        category_group=CategoryGroup.JUZ_10_15_20, display_order=3,
    )
    cat_juz30 = Category(
        name_en="Juz' 30 (Complete)", name_ar="الجزء الثلاثون (حفظ كامل)",
        min_age=None, max_age=99,
        category_group=CategoryGroup.JUZ_30, display_order=4,
    )
    db.add_all([cat_juz10, cat_juz20, cat_juz29, cat_juz30])
    await db.flush()

    # -----------------------------------------------------------------------
    # Scoring Criteria
    # Rubric A (JUZ_10_15_20): Memorization 50, Tajweed 30, Saut 20
    # Rubric B (JUZ_30):       Memorization 45, Tajweed 25, Tafsir 10, Saut 20
    # ALL seeded as DEDUCTION_BASED
    # -----------------------------------------------------------------------
    # Rubric A
    crit_a_mem  = ScoringCriteria(category_group=CategoryGroup.JUZ_10_15_20,
                                   name_en="Memorization", name_ar="الحفظ",
                                   max_points=50, scoring_method=ScoringMethod.DEDUCTION_BASED)
    crit_a_taj  = ScoringCriteria(category_group=CategoryGroup.JUZ_10_15_20,
                                   name_en="Tajweed", name_ar="التجويد",
                                   max_points=30, scoring_method=ScoringMethod.DEDUCTION_BASED)
    crit_a_saut = ScoringCriteria(category_group=CategoryGroup.JUZ_10_15_20,
                                   name_en="Saut", name_ar="الصوت",
                                   max_points=20, scoring_method=ScoringMethod.DEDUCTION_BASED)
    # Rubric B
    crit_b_mem  = ScoringCriteria(category_group=CategoryGroup.JUZ_30,
                                   name_en="Memorization", name_ar="الحفظ",
                                   max_points=45, scoring_method=ScoringMethod.DEDUCTION_BASED)
    crit_b_taj  = ScoringCriteria(category_group=CategoryGroup.JUZ_30,
                                   name_en="Tajweed", name_ar="التجويد",
                                   max_points=25, scoring_method=ScoringMethod.DEDUCTION_BASED)
    crit_b_taf  = ScoringCriteria(category_group=CategoryGroup.JUZ_30,
                                   name_en="Tafsir", name_ar="التفسير",
                                   max_points=10, scoring_method=ScoringMethod.DEDUCTION_BASED)
    crit_b_saut = ScoringCriteria(category_group=CategoryGroup.JUZ_30,
                                   name_en="Saut", name_ar="الصوت",
                                   max_points=20, scoring_method=ScoringMethod.DEDUCTION_BASED)
    db.add_all([crit_a_mem, crit_a_taj, crit_a_saut, crit_b_mem, crit_b_taj, crit_b_taf, crit_b_saut])
    await db.flush()

    # -----------------------------------------------------------------------
    # Deduction Types
    # Fixed amounts: Memorization + Tajweed
    # NULL amounts: Saut + Tafsir (judge-entered per event)
    # -----------------------------------------------------------------------
    db.add_all([
        # Rubric A — Memorization
        DeductionType(scoring_criteria_id=crit_a_mem.id,  name_en="Normal Error",    name_ar="خطأ عادي",       points_deducted=1.0),
        DeductionType(scoring_criteria_id=crit_a_mem.id,  name_en="Forgetfulness",   name_ar="نسيان",           points_deducted=2.0),
        DeductionType(scoring_criteria_id=crit_a_mem.id,  name_en="Prompted Error",  name_ar="خطأ بتلقين",      points_deducted=0.5),
        # Rubric A — Tajweed
        DeductionType(scoring_criteria_id=crit_a_taj.id,  name_en="Tajweed Error",   name_ar="خطأ تجويدي",      points_deducted=0.5),
        DeductionType(scoring_criteria_id=crit_a_taj.id,  name_en="Major Tajweed Error", name_ar="خطأ تجويدي كبير", points_deducted=1.0),
        # Rubric A — Saut (judge-entered, NULL fixed amount)
        DeductionType(scoring_criteria_id=crit_a_saut.id, name_en="Voice Deduction", name_ar="خصم صوت",         points_deducted=None),
        # Rubric B — Memorization
        DeductionType(scoring_criteria_id=crit_b_mem.id,  name_en="Normal Error",    name_ar="خطأ عادي",        points_deducted=1.0),
        DeductionType(scoring_criteria_id=crit_b_mem.id,  name_en="Forgetfulness",   name_ar="نسيان",            points_deducted=2.0),
        DeductionType(scoring_criteria_id=crit_b_mem.id,  name_en="Prompted Error",  name_ar="خطأ بتلقين",       points_deducted=0.5),
        # Rubric B — Tajweed
        DeductionType(scoring_criteria_id=crit_b_taj.id,  name_en="Tajweed Error",   name_ar="خطأ تجويدي",       points_deducted=0.5),
        DeductionType(scoring_criteria_id=crit_b_taj.id,  name_en="Major Tajweed Error", name_ar="خطأ تجويدي كبير",  points_deducted=1.0),
        # Rubric B — Tafsir (judge-entered, NULL fixed amount)
        DeductionType(scoring_criteria_id=crit_b_taf.id,  name_en="Tafsir Deduction", name_ar="خصم تفسير",       points_deducted=None),
        # Rubric B — Saut (judge-entered, NULL fixed amount)
        DeductionType(scoring_criteria_id=crit_b_saut.id, name_en="Voice Deduction",  name_ar="خصم صوت",         points_deducted=None),
    ])
    await db.flush()

    # -----------------------------------------------------------------------
    # Admin Users
    # -----------------------------------------------------------------------
    superadmin = AdminUser(
        name="JMC Super Admin", email="admin@jmc.or.ke",
        password_hash=hash_password("Admin@2025!"),
        role=AdminRole.SUPERADMIN, preferred_language=AdminLang.EN, active=True,
    )
    judge1 = AdminUser(
        name="Sheikh Abdul Rahman", email="judge1@jmc.or.ke",
        password_hash=hash_password("Judge@2025!"),
        role=AdminRole.JUDGE, judge_role=AJudgeRole.REGULAR,
        preferred_language=AdminLang.AR, active=True,
    )
    judge2 = AdminUser(
        name="Sheikh Khalid Omar", email="judge2@jmc.or.ke",
        password_hash=hash_password("Judge@2025!"),
        role=AdminRole.JUDGE, judge_role=AJudgeRole.REGULAR,
        preferred_language=AdminLang.AR, active=True,
    )
    judge3 = AdminUser(
        name="Sheikh Ali Hassan", email="judge3@jmc.or.ke",
        password_hash=hash_password("Judge@2025!"),
        role=AdminRole.JUDGE, judge_role=AJudgeRole.REGULAR,
        preferred_language=AdminLang.AR, active=True,
    )
    db.add_all([superadmin, judge1, judge2, judge3])
    await db.flush()

    # -----------------------------------------------------------------------
    # Institutions
    # -----------------------------------------------------------------------
    inst_approved = Institution(
        name="Madrasa Nuur Al-Islam", type=InstitutionType.MADRASA,
        contact_person="Ustadh Ibrahim", phone="+254700000001",
        email="nuuralislam@example.com", password_hash=hash_password("Inst@2025!"),
        region_id=eastleigh.id, status=InstitutionStatus.APPROVED,
        preferred_language=InstLang.AR,
    )
    inst_pending = Institution(
        name="Al-Furqan Islamic School", type=InstitutionType.SCHOOL,
        contact_person="Ustadha Fatima", phone="+254700000002",
        email="alfurqan@example.com", password_hash=hash_password("Inst@2025!"),
        region_id=kasarani.id, status=InstitutionStatus.PENDING,
        preferred_language=InstLang.EN,
    )
    db.add_all([inst_approved, inst_pending])
    await db.flush()

    # -----------------------------------------------------------------------
    # Students
    # -----------------------------------------------------------------------
    students = [
        Student(
            institution_id=inst_approved.id, category_id=cat_juz10.id,
            full_name="أحمد محمد عبدالله",  # Arabic name — UTF-8
            dob=date(2013, 3, 15), gender=Gender.MALE,
            national_id="KE20130001", guardian_phone="+254711000001",
            review_status=StudentReviewStatus.APPROVED,
        ),
        Student(
            institution_id=inst_approved.id, category_id=cat_juz30.id,
            full_name="فاطمة عمر حسن",
            dob=date(2008, 7, 22), gender=Gender.FEMALE,
            national_id="KE20080001", guardian_phone="+254711000002",
            review_status=StudentReviewStatus.PENDING_REVIEW,
        ),
        Student(
            institution_id=inst_pending.id, category_id=cat_juz20.id,
            full_name="Yusuf Ibrahim Ali",
            dob=date(2011, 11, 1), gender=Gender.MALE,
            national_id="KE20110001", guardian_phone="+254711000003",
            review_status=StudentReviewStatus.PENDING_REVIEW,
        ),
        Student(
            institution_id=inst_pending.id, category_id=cat_juz29.id,
            full_name="Zainab Ahmed Waweru",
            dob=date(2009, 5, 10), gender=Gender.FEMALE,
            national_id="KE20090001", guardian_phone="+254711000004",
            review_status=StudentReviewStatus.REJECTED,
            rejection_reason="Age document not provided",
        ),
    ]
    db.add_all(students)
    await db.flush()

    # -----------------------------------------------------------------------
    # Sample Round (PENDING)
    # -----------------------------------------------------------------------
    sample_round = Round(
        category_id=cat_juz10.id,
        round_type=RoundType.PRELIMINARY,
        status=RoundStatus.PENDING,
        scheduled_at=datetime(2025, 12, 1, 9, 0, tzinfo=timezone.utc),
    )
    db.add(sample_round)
    await db.flush()

    # Judge assignments (3 REGULAR for PRELIMINARY)
    for judge in [judge1, judge2, judge3]:
        db.add(RoundJudgeAssignment(
            round_id=sample_round.id,
            admin_user_id=judge.id,
            judge_role=JudgeRole.REGULAR,
        ))

    await db.commit()
    print("[seed] ✅ Seeding complete.")
    print(f"[seed]   Super Admin: admin@jmc.or.ke / Admin@2025!")
    print(f"[seed]   Judge 1:    judge1@jmc.or.ke / Judge@2025!")
    print(f"[seed]   Institution: nuuralislam@example.com / Inst@2025!")


async def main():
    await create_db_and_tables()
    async with AsyncSessionLocal() as db:
        await seed(db)


if __name__ == "__main__":
    asyncio.run(main())
