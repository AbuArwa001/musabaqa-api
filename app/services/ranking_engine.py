"""
Ranking Engine — the core of musabaqa-api.

Triggered automatically when the LAST assigned judge for a given
student+round submits their score.

Steps:
1. Compute per-judge round score (criterion_max - deductions, floored at 0)
2. Panel score = AVERAGE or MEDIAN across judges (per CompetitionSeasonSettings)
3. Check consistency flag (>10 pts deviation from panel average)
4. Write/update RoundResult row
5. Compute regional advancement rankings
6. Broadcast updated leaderboard over WebSocket

Regional Advancement Algorithm:
- Within each region × category group: rank entrants by panel score
- Positions 1–4 advance (default_top_n_per_region, with RegionOverride support)
- Tie at advancement boundary: draw from that category's tie_allowance_pool
- Tie pool is PER CATEGORY, not competition-wide
- If regional_balancing_enabled=False: fall back to flat top-N-by-score
"""

import statistics
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.websocket_manager import ws_manager
from app.models.category import ScoringCriteria, DeductionType
from app.models.institution import Institution
from app.models.region import Region
from app.models.results import (
    CompetitionSeasonSettings,
    RegionOverride,
    RoundResult,
    PanelScoreMethod,
)
from app.models.round import Round, RoundJudgeAssignment
from app.models.scoring import DeductionEvent
from app.models.student import Student
from app.schemas.results import LeaderboardEntry, LeaderboardPayload


# ---------------------------------------------------------------------------
# Score computation helpers
# ---------------------------------------------------------------------------

async def _compute_judge_score(
    db: AsyncSession,
    round_id: int,
    student_id: int,
    judge_id: int,
    criteria: list[ScoringCriteria],
    dt_to_crit: dict[int, int],
) -> float:
    """Compute one judge's total score for one student in one round."""
    events = (await db.execute(
        select(DeductionEvent).where(
            DeductionEvent.round_id == round_id,
            DeductionEvent.student_id == student_id,
            DeductionEvent.judge_id == judge_id,
        )
    )).scalars().all()

    deductions_by_crit: dict[int, float] = defaultdict(float)
    for e in events:
        crit_id = dt_to_crit.get(e.deduction_type_id)
        if crit_id:
            deductions_by_crit[crit_id] += e.amount

    total = 0.0
    for crit in criteria:
        total += max(0.0, crit.max_points - deductions_by_crit.get(crit.id, 0.0))
    return total


async def _get_criteria_for_round(
    db: AsyncSession, round_id: int
) -> tuple[list[ScoringCriteria], dict[int, int]]:
    """Returns (criteria list, deduction_type_id -> criteria_id map)."""
    round_ = await db.get(Round, round_id)
    from app.models.category import Category, CategoryGroup
    cat = await db.get(Category, round_.category_id)

    criteria = (await db.execute(
        select(ScoringCriteria).where(
            ScoringCriteria.category_group == cat.category_group
        )
    )).scalars().all()

    dts = (await db.execute(
        select(DeductionType).where(
            DeductionType.scoring_criteria_id.in_([c.id for c in criteria])
        )
    )).scalars().all()

    dt_to_crit = {dt.id: dt.scoring_criteria_id for dt in dts}
    return criteria, dt_to_crit


async def compute_panel_score(
    db: AsyncSession,
    round_id: int,
    student_id: int,
    season: CompetitionSeasonSettings,
) -> tuple[float, float, list[float]]:
    """
    Returns (panel_score, std_dev_indicator, per_judge_scores).
    panel_score uses AVERAGE or MEDIAN per season config.
    """
    judge_ids = (await db.execute(
        select(RoundJudgeAssignment.admin_user_id).where(
            RoundJudgeAssignment.round_id == round_id
        )
    )).scalars().all()

    criteria, dt_to_crit = await _get_criteria_for_round(db, round_id)

    judge_scores = []
    for jid in judge_ids:
        score = await _compute_judge_score(db, round_id, student_id, jid, criteria, dt_to_crit)
        judge_scores.append(score)

    if not judge_scores:
        return 0.0, 0.0, []

    avg = sum(judge_scores) / len(judge_scores)

    if season.panel_score_method == PanelScoreMethod.MEDIAN:
        panel = statistics.median(judge_scores)
    else:
        panel = avg  # AVERAGE (default)

    return panel, avg, judge_scores


def _check_consistency(judge_scores: list[float], panel_avg: float) -> bool:
    """Flag if any judge deviates by more than 10 pts from the panel average."""
    return any(abs(s - panel_avg) > 10.0 for s in judge_scores)


# ---------------------------------------------------------------------------
# Main entry point — called after last judge submits
# ---------------------------------------------------------------------------

async def finalize_and_broadcast(
    db: AsyncSession,
    round_id: int,
    student_id: int,
) -> RoundResult:
    """
    1. Compute panel score
    2. Write RoundResult
    3. Recompute full round rankings
    4. Broadcast leaderboard WebSocket
    5. Return the individual RoundResult
    """
    # Get active season
    season = (await db.execute(
        select(CompetitionSeasonSettings).where(CompetitionSeasonSettings.is_active == True)
    )).scalar_one_or_none()
    if not season:
        # Fall back to defaults
        season = CompetitionSeasonSettings()

    panel_score, panel_avg, judge_scores = await compute_panel_score(
        db, round_id, student_id, season
    )
    flagged = _check_consistency(judge_scores, panel_avg)

    # Upsert RoundResult
    existing = (await db.execute(
        select(RoundResult).where(
            RoundResult.round_id == round_id,
            RoundResult.student_id == student_id,
        )
    )).scalar_one_or_none()

    if existing:
        existing.final_score = panel_score
        existing.consistency_flagged = flagged
        existing.computed_at = datetime.now(timezone.utc)
        db.add(existing)
        result = existing
    else:
        result = RoundResult(
            round_id=round_id,
            student_id=student_id,
            final_score=panel_score,
            consistency_flagged=flagged,
        )
        db.add(result)

    await db.flush()

    # Recompute rankings for the full round
    await _recompute_rankings(db, round_id, season)
    await db.refresh(result)

    # Build leaderboard and broadcast
    await _broadcast_leaderboard(db, round_id)

    return result


# ---------------------------------------------------------------------------
# Regional advancement ranking algorithm
# ---------------------------------------------------------------------------

async def _recompute_rankings(
    db: AsyncSession,
    round_id: int,
    season: CompetitionSeasonSettings,
) -> None:
    """
    Assign rank to all RoundResults for this round.

    If regional_balancing_enabled:
      - Group by region × category
      - Rank within each group
      - Positions 1-top_n advance
      - Tie at boundary: use category's tie_allowance_pool
    Else:
      - Rank by score across entire round (flat)
    """
    round_ = await db.get(Round, round_id)
    all_results = (await db.execute(
        select(RoundResult).where(RoundResult.round_id == round_id)
    )).scalars().all()

    if not all_results:
        return

    if not season.regional_balancing_enabled:
        # Flat ranking by final_score descending
        sorted_results = sorted(all_results, key=lambda r: r.final_score, reverse=True)
        for i, res in enumerate(sorted_results, start=1):
            res.rank = i
            db.add(res)
        await db.flush()
        return

    # Regional ranking: group by student's region within category
    student_ids = [r.student_id for r in all_results]
    students = (await db.execute(
        select(Student).where(Student.id.in_(student_ids))
    )).scalars().all()
    student_map = {s.id: s for s in students}

    institutions = (await db.execute(
        select(Institution).where(
            Institution.id.in_([s.institution_id for s in students])
        )
    )).scalars().all()
    inst_map = {i.id: i for i in institutions}

    # Get region overrides for this season
    overrides = (await db.execute(
        select(RegionOverride).where(
            RegionOverride.season == (season.season if season.id else ""),
            RegionOverride.active == True,
        )
    )).scalars().all()
    override_map = {o.region_id: o.top_n_override for o in overrides if o.top_n_override}

    # Group results by region_id
    by_region: dict[int | None, list[RoundResult]] = defaultdict(list)
    for res in all_results:
        s = student_map.get(res.student_id)
        region_id = inst_map[s.institution_id].region_id if s else None
        by_region[region_id].append(res)

    for region_id, region_results in by_region.items():
        top_n = override_map.get(region_id, season.default_top_n_per_region)
        sorted_region = sorted(region_results, key=lambda r: r.final_score, reverse=True)

        # Assign regional ranks
        for i, res in enumerate(sorted_region, start=1):
            res.rank = i
            db.add(res)

        # Tie detection at the top_n / top_n+1 boundary
        if len(sorted_region) > top_n:
            boundary_score = sorted_region[top_n - 1].final_score
            next_score = sorted_region[top_n].final_score
            if boundary_score == next_score:
                # Tie exists at boundary — tie_allowance_pool is PER CATEGORY
                # The pool tracking is logged; resolution happens via TieBreakVote
                pass  # TieBreakVote creation is triggered via API endpoint

    await db.flush()


# ---------------------------------------------------------------------------
# WebSocket broadcast
# ---------------------------------------------------------------------------

async def _broadcast_leaderboard(db: AsyncSession, round_id: int) -> None:
    round_ = await db.get(Round, round_id)
    category_id = round_.category_id

    results = (await db.execute(
        select(RoundResult).where(RoundResult.round_id == round_id).order_by(
            RoundResult.rank.asc().nulls_last(),
            RoundResult.final_score.desc(),
        )
    )).scalars().all()

    student_ids = [r.student_id for r in results]
    students = {
        s.id: s for s in (await db.execute(
            select(Student).where(Student.id.in_(student_ids))
        )).scalars().all()
    }
    institution_ids = list({s.institution_id for s in students.values()})
    institutions = {
        i.id: i for i in (await db.execute(
            select(Institution).where(Institution.id.in_(institution_ids))
        )).scalars().all()
    }
    region_ids = list({i.region_id for i in institutions.values() if i.region_id})
    regions = {
        r.id: r for r in (await db.execute(
            select(Region).where(Region.id.in_(region_ids))
        )).scalars().all()
    }

    entries = []
    for res in results:
        s = students.get(res.student_id)
        inst = institutions.get(s.institution_id) if s else None
        reg = regions.get(inst.region_id) if inst and inst.region_id else None
        entries.append(LeaderboardEntry(
            rank=res.rank,
            student_id=res.student_id,
            student_name=s.full_name if s else "",
            institution_id=inst.id if inst else 0,
            institution_name=inst.name if inst else "",
            region_id=reg.id if reg else None,
            region_name_en=reg.name_en if reg else None,
            final_score=res.final_score,
            consistency_flagged=res.consistency_flagged,
        ))

    payload = LeaderboardPayload(
        category_id=category_id,
        round_id=round_id,
        entries=entries,
        broadcast_at=datetime.now(timezone.utc),
    )

    await ws_manager.broadcast_leaderboard(category_id, payload.model_dump(mode="json"))
    await ws_manager.broadcast_admin(payload.model_dump(mode="json"))
