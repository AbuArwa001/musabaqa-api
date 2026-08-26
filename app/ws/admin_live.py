"""
Staff-only WebSocket: /ws/admin/live-scoring

Requires a valid staff JWT in the 'token' query parameter.
Receives all scoring events in real time as the ranking engine broadcasts them.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import JWTError

from app.core.security import decode_token
from app.core.websocket_manager import ws_manager

router = APIRouter()


@router.websocket("/ws/admin/live-scoring")
async def admin_live_ws(ws: WebSocket, token: str = Query(...)):
    # Validate JWT before accepting connection
    try:
        payload = decode_token(token)
        if payload.get("scope") != "staff":
            await ws.close(code=4001, reason="Invalid token scope")
            return
    except JWTError:
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    await ws_manager.connect_admin(ws)
    try:
        while True:
            await ws.receive_text()  # Keep-alive
    except WebSocketDisconnect:
        ws_manager.disconnect_admin(ws)
