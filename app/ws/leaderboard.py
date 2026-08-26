"""
Public WebSocket: /ws/leaderboard/{category_id}

Sends the current leaderboard snapshot on connect,
then receives live broadcasts whenever scores are updated.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import AsyncSessionLocal
from app.core.websocket_manager import ws_manager
from app.models.results import RoundResult
from app.models.round import Round
from app.models.student import Student
from app.models.institution import Institution
from app.models.region import Region
from app.schemas.results import LeaderboardEntry, LeaderboardPayload

router = APIRouter()


async def _snapshot(category_id: int) -> dict:
    """Build current leaderboard snapshot for a category."""
    async with AsyncSessionLocal() as db:
        # Find the most recent active/completed round for this category
        rounds = (await db.execute(
            select(Round).where(Round.category_id == category_id)
            .order_by(Round.scheduled_at.desc())
        )).scalars().all()

        if not rounds:
            return LeaderboardPayload(
                category_id=category_id, round_id=0, entries=[],
                broadcast_at=datetime.now(timezone.utc)
            ).model_dump(mode="json")

        round_ = rounds[0]
        results = (await db.execute(
            select(RoundResult).where(RoundResult.round_id == round_.id)
            .order_by(RoundResult.rank.asc().nulls_last(), RoundResult.final_score.desc())
        )).scalars().all()

        student_ids = [r.student_id for r in results]
        students = {s.id: s for s in (await db.execute(
            select(Student).where(Student.id.in_(student_ids))
        )).scalars().all()}
        institution_ids = list({s.institution_id for s in students.values()})
        institutions = {i.id: i for i in (await db.execute(
            select(Institution).where(Institution.id.in_(institution_ids))
        )).scalars().all()}
        region_ids = list({i.region_id for i in institutions.values() if i.region_id})
        regions = {r.id: r for r in (await db.execute(
            select(Region).where(Region.id.in_(region_ids))
        )).scalars().all()}

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

        return LeaderboardPayload(
            category_id=category_id,
            round_id=round_.id,
            entries=entries,
            broadcast_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")


@router.websocket("/ws/leaderboard/{category_id}")
async def leaderboard_ws(ws: WebSocket, category_id: int):
    await ws_manager.connect_leaderboard(ws, category_id)
    try:
        # Send snapshot on connect
        snapshot = await _snapshot(category_id)
        await ws.send_json(snapshot)
        # Hold connection open — updates are pushed by broadcasting from the ranking engine
        while True:
            await ws.receive_text()  # Keep-alive ping/pong
    except WebSocketDisconnect:
        ws_manager.disconnect_leaderboard(ws, category_id)
