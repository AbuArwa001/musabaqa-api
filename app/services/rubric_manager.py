"""
Rubric Manager Service — Handles dynamic switching between:
1. OFFICIAL_70_30 (70 Memorization / 30 Tajweed)
2. TRADITIONAL_TIERED (50/30/20 for Juz 10-20, 45/25/10/20 for Juz 30)
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from fastapi import HTTPException

from app.models.category import CategoryGroup, ScoringCriteria, DeductionType, ScoringMethod
from app.models.results import CompetitionSeasonSettings
from app.models.scoring import DeductionEvent
from app.core.websocket_manager import ws_manager


RUBRIC_CONFIGS = {
    "OFFICIAL_70_30": {
        CategoryGroup.JUZ_10_15_20: [
            {
                "name_en": "Memorization",
                "name_ar": "الحفظ",
                "max_points": 70.0,
                "deductions": [
                    {"name_en": "Tanbeeh (Warning)", "name_ar": "التنبيه", "points_deducted": 1.0},
                    {"name_en": "Al-Fath (Prompting)", "name_ar": "الفتح", "points_deducted": 2.0},
                    {"name_en": "Al-Lahn (Vocalization Error)", "name_ar": "اللحن", "points_deducted": 2.0},
                ],
            },
            {
                "name_en": "Tajweed",
                "name_ar": "التجويد وحسن الصوت والأداء",
                "max_points": 30.0,
                "deductions": [
                    {"name_en": "Tajweed Error", "name_ar": "خطأ في التجويد", "points_deducted": 0.5},
                ],
            },
        ],
        CategoryGroup.JUZ_30: [
            {
                "name_en": "Memorization",
                "name_ar": "الحفظ",
                "max_points": 70.0,
                "deductions": [
                    {"name_en": "Tanbeeh (Warning)", "name_ar": "التنبيه", "points_deducted": 1.0},
                    {"name_en": "Al-Fath (Prompting)", "name_ar": "الفتح", "points_deducted": 2.0},
                    {"name_en": "Al-Lahn (Vocalization Error)", "name_ar": "اللحن", "points_deducted": 2.0},
                ],
            },
            {
                "name_en": "Tajweed",
                "name_ar": "التجويد وحسن الصوت والأداء",
                "max_points": 30.0,
                "deductions": [
                    {"name_en": "Tajweed Error", "name_ar": "خطأ في التجويد", "points_deducted": 0.5},
                ],
            },
        ],
    },
    "TRADITIONAL_TIERED": {
        CategoryGroup.JUZ_10_15_20: [
            {
                "name_en": "Memorization",
                "name_ar": "الحفظ",
                "max_points": 50.0,
                "deductions": [
                    {"name_en": "Tanbeeh (Warning)", "name_ar": "التنبيه", "points_deducted": 1.0},
                    {"name_en": "Al-Fath (Prompting)", "name_ar": "الفتح", "points_deducted": 2.0},
                    {"name_en": "Al-Lahn (Vocalization Error)", "name_ar": "اللحن", "points_deducted": 2.0},
                ],
            },
            {
                "name_en": "Tajweed",
                "name_ar": "التجويد",
                "max_points": 30.0,
                "deductions": [
                    {"name_en": "Tajweed Error", "name_ar": "خطأ في التجويد", "points_deducted": 0.5},
                ],
            },
            {
                "name_en": "Saut",
                "name_ar": "حسن الصوت والأداء",
                "max_points": 20.0,
                "deductions": [
                    {"name_en": "Saut Deduction", "name_ar": "خصم الصوت والأداء", "points_deducted": None},
                ],
            },
        ],
        CategoryGroup.JUZ_30: [
            {
                "name_en": "Memorization",
                "name_ar": "الحفظ",
                "max_points": 45.0,
                "deductions": [
                    {"name_en": "Tanbeeh (Warning)", "name_ar": "التنبيه", "points_deducted": 1.0},
                    {"name_en": "Al-Fath (Prompting)", "name_ar": "الفتح", "points_deducted": 2.0},
                    {"name_en": "Al-Lahn (Vocalization Error)", "name_ar": "اللحن", "points_deducted": 2.0},
                ],
            },
            {
                "name_en": "Tajweed",
                "name_ar": "التجويد",
                "max_points": 25.0,
                "deductions": [
                    {"name_en": "Tajweed Error", "name_ar": "خطأ في التجويد", "points_deducted": 0.5},
                ],
            },
            {
                "name_en": "Tafsir",
                "name_ar": "التفسير",
                "max_points": 10.0,
                "deductions": [
                    {"name_en": "Tafsir Deduction", "name_ar": "خصم التفسير", "points_deducted": None},
                ],
            },
            {
                "name_en": "Saut",
                "name_ar": "حسن الصوت والأداء",
                "max_points": 20.0,
                "deductions": [
                    {"name_en": "Saut Deduction", "name_ar": "خصم الصوت والأداء", "points_deducted": None},
                ],
            },
        ],
    },
}


async def get_current_rubric_mode(db: AsyncSession) -> str:
    """Returns the currently active rubric mode, defaulting to OFFICIAL_70_30."""
    try:
        result = await db.execute(
            select(CompetitionSeasonSettings).where(CompetitionSeasonSettings.is_active == True)
        )
        season = result.scalar_one_or_none()
        if not season:
            # Fallback to any season setting
            result = await db.execute(select(CompetitionSeasonSettings).limit(1))
            season = result.scalar_one_or_none()
        
        if season and getattr(season, "rubric_mode", None):
            return season.rubric_mode
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Could not query rubric_mode from season settings: %s", exc)
    return "OFFICIAL_70_30"


async def set_rubric_mode(db: AsyncSession, mode: str) -> str:
    """
    Switches the active competition rubric mode and updates criteria and deduction types.
    Broadcasts the change via WebSocket to all judges and admins.
    """
    if mode not in RUBRIC_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid rubric mode '{mode}'. Must be one of: {list(RUBRIC_CONFIGS.keys())}"
        )

    # 1. Update season settings
    result = await db.execute(
        select(CompetitionSeasonSettings).where(CompetitionSeasonSettings.is_active == True)
    )
    season = result.scalar_one_or_none()
    if not season:
        result = await db.execute(select(CompetitionSeasonSettings).limit(1))
        season = result.scalar_one_or_none()

    if season:
        season.rubric_mode = mode
    else:
        season = CompetitionSeasonSettings(
            season="2026",
            is_active=True,
            rubric_mode=mode,
        )
        db.add(season)
    await db.flush()

    # 2. Synchronize Criteria and Deduction Types
    config = RUBRIC_CONFIGS[mode]

    for cat_group, criteria_list in config.items():
        desired_crit_names = {c["name_en"] for c in criteria_list}

        # Fetch existing criteria for this group
        existing_criteria = (await db.execute(
            select(ScoringCriteria).where(ScoringCriteria.category_group == cat_group)
        )).scalars().all()
        crit_map = {c.name_en: c for c in existing_criteria}

        # Handle criteria in the target config
        for c_spec in criteria_list:
            crit = crit_map.get(c_spec["name_en"])
            if not crit:
                crit = ScoringCriteria(
                    category_group=cat_group,
                    name_en=c_spec["name_en"],
                    name_ar=c_spec["name_ar"],
                    max_points=c_spec["max_points"],
                    scoring_method=ScoringMethod.DEDUCTION_BASED,
                )
                db.add(crit)
                await db.flush()
                await db.refresh(crit)
            else:
                crit.max_points = c_spec["max_points"]
                crit.name_ar = c_spec["name_ar"]
                await db.flush()

            # Synchronize deduction types for this criterion
            existing_dts = (await db.execute(
                select(DeductionType).where(DeductionType.scoring_criteria_id == crit.id)
            )).scalars().all()
            dt_map = {dt.name_en: dt for dt in existing_dts}
            desired_dt_names = {d["name_en"] for d in c_spec["deductions"]}

            for dt_spec in c_spec["deductions"]:
                dt = dt_map.get(dt_spec["name_en"])
                if not dt:
                    dt = DeductionType(
                        scoring_criteria_id=crit.id,
                        name_en=dt_spec["name_en"],
                        name_ar=dt_spec["name_ar"],
                        points_deducted=dt_spec["points_deducted"],
                    )
                    db.add(dt)
                    await db.flush()
                else:
                    dt.points_deducted = dt_spec["points_deducted"]
                    dt.name_ar = dt_spec["name_ar"]
                    await db.flush()

            # Clean up obsolete deduction types for this criterion if unreferenced
            for dt in existing_dts:
                if dt.name_en not in desired_dt_names:
                    events_count = (await db.execute(
                        select(DeductionEvent).where(DeductionEvent.deduction_type_id == dt.id).limit(1)
                    )).first()
                    if not events_count:
                        await db.delete(dt)
                        await db.flush()

        # Handle criteria not in desired config (e.g. Tafsir or Saut when switching to 70/30)
        for crit in existing_criteria:
            if crit.name_en not in desired_crit_names:
                # Check if referenced by any deduction events
                dt_ids = (await db.execute(
                    select(DeductionType.id).where(DeductionType.scoring_criteria_id == crit.id)
                )).scalars().all()

                referenced = False
                if dt_ids:
                    events_count = (await db.execute(
                        select(DeductionEvent).where(DeductionEvent.deduction_type_id.in_(dt_ids)).limit(1)
                    )).first()
                    if events_count:
                        referenced = True

                if not referenced:
                    for dt_id in dt_ids:
                        dt = await db.get(DeductionType, dt_id)
                        if dt:
                            await db.delete(dt)
                    await db.delete(crit)
                    await db.flush()
                else:
                    # If previously used in historical rounds, keep with 0 max_points so data remains intact
                    crit.max_points = 0.0
                    await db.flush()

    await db.commit()

    # 3. Broadcast real-time event to all connected judges and admins
    await ws_manager.broadcast_admin({
        "type": "RUBRIC_MODE_CHANGED",
        "rubric_mode": mode,
    })

    return mode
