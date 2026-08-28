"""
WebSocket connection registry and broadcast helpers.

Channels:
  - leaderboard/{category_id}  : public live leaderboard per category
  - admin/live-scoring          : staff-only real-time scoring feed
"""

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # category_id -> set of active WebSocket connections
        self._leaderboard: dict[int, set[WebSocket]] = defaultdict(set)
        # all admin live-scoring connections
        self._admin: set[WebSocket] = set()

    # ------------------------------------------------------------------
    # Leaderboard channel (public)
    # ------------------------------------------------------------------

    async def connect_leaderboard(self, ws: WebSocket, category_id: int) -> None:
        await ws.accept()
        self._leaderboard[category_id].add(ws)

    def disconnect_leaderboard(self, ws: WebSocket, category_id: int) -> None:
        self._leaderboard[category_id].discard(ws)

    async def broadcast_leaderboard(self, category_id: int, payload: dict) -> None:
        """Fan-out a leaderboard update to all subscribers of a category."""
        message = json.dumps(payload)
        dead: set[WebSocket] = set()
        for ws in list(self._leaderboard.get(category_id, [])):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._leaderboard[category_id].discard(ws)

    # ------------------------------------------------------------------
    # Admin live-scoring channel (staff only)
    # ------------------------------------------------------------------

    async def connect_admin(self, ws: WebSocket) -> None:
        await ws.accept()
        self._admin.add(ws)

    def disconnect_admin(self, ws: WebSocket) -> None:
        self._admin.discard(ws)

    async def broadcast_admin(self, payload: dict) -> None:
        """Fan-out a scoring event to all admin live-scoring subscribers."""
        message = json.dumps(payload)
        dead: set[WebSocket] = set()
        for ws in list(self._admin):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._admin.discard(ws)

    async def broadcast_active_student(self, round_id: int, student_id: int | None) -> None:
        """Notify all admin subscribers that the active student for a round has changed."""
        payload = {
            "type": "ACTIVE_STUDENT_CHANGED",
            "round_id": round_id,
            "student_id": student_id,
        }
        await self.broadcast_admin(payload)


# Singleton — imported wherever needed
ws_manager = ConnectionManager()
