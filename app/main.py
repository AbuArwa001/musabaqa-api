"""
musabaqa-api — Jamia Mosque Nairobi Quran Memorization Competition API

All routes versioned under /api/v1/ from day one.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import v1_router
from app.ws.leaderboard import router as leaderboard_ws_router
from app.ws.admin_live import router as admin_live_ws_router

app = FastAPI(
    title="Musabaqa API",
    description="Jamia Mosque Nairobi — Quran Memorization Competition Backend",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(v1_router)

# WebSocket routes
app.include_router(leaderboard_ws_router)
app.include_router(admin_live_ws_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "service": "musabaqa-api", "version": "1.0.0"}
