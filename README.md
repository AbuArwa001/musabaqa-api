# musabaqa-api

**Jamia Mosque Nairobi — Quran Memorization Competition Backend**

FastAPI + SQLModel (PostgreSQL) backend with native WebSocket leaderboard broadcasting, Celery background jobs, WeasyPrint RTL-safe Arabic/English PDF generation, and Africa's Talking SMS lifecycle notifications.

---

## Quick Start (Docker)

```bash
cp .env.example .env
# Edit .env with your real keys (Resend, Knock, Africa's Talking, S3)

docker compose up --build
```

API: http://localhost:8000/api/v1/docs
WebSocket leaderboard: ws://localhost:8000/ws/leaderboard/{category_id}
Admin live-scoring: ws://localhost:8000/ws/admin/live-scoring?token=<staff_jwt>

---

## Quick Start (Local, without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start Postgres and Redis locally, then:
cp .env.example .env  # set DATABASE_URL and REDIS_URL

alembic upgrade head
python -m seed.seed
uvicorn app.main:app --reload
```

---

## Default Credentials (from seed data)

| Role       | Email                       | Password       |
|------------|-----------------------------|----------------|
| SUPERADMIN | admin@jmc.or.ke             | Admin@2025!    |
| JUDGE      | judge1@jmc.or.ke            | Judge@2025!    |
| JUDGE      | judge2@jmc.or.ke            | Judge@2025!    |
| JUDGE      | judge3@jmc.or.ke            | Judge@2025!    |
| Institution| nuuralislam@example.com     | Inst@2025!     |

---

## Running Tests

```bash
pip install aiosqlite  # SQLite async driver for tests
pytest tests/ -v --asyncio-mode=auto
```

---

## Architecture Notes

### Two JWT Scopes
- `scope: institution` — institutions login, register students
- `scope: staff` — judges/moderators/superadmin; judge tokens carry `assigned_round_ids` + `assigned_category_ids` claims

### Ranking Engine
Triggered automatically on last-judge submission. Regional advancement algorithm:
- Groups students by `region × category`
- Advances top-`N` per region (default 4, configurable via `RegionOverride`)
- Tie at boundary uses per-category `tie_allowance_pool` (NOT shared)
- Falls back to flat ranking if `regional_balancing_enabled=False`

### SMS Lifecycle Triggers (Africa's Talking)
1. **Student approved** after registration → SMS to institution guardian phone
2. **Student advances Preliminary → Finals** → SMS
3. **Student confirmed in Finals** → SMS

### Bilingual Support
- All category/region names stored as `name_en` + `name_ar` pairs
- Notification templates (email, SMS, in-app) are selected based on `preferred_language` (EN/AR)
- WeasyPrint PDFs generated from separate `certificate_en.html` / `certificate_ar.html` templates
- Arabic templates use `direction: rtl; unicode-bidi: embed` with Amiri/Noto Arabic fonts

### Score Visibility Rule
Judges CANNOT see other judges' scores for the same student+round until ALL assigned judges for that round have submitted. Enforced server-side in `GET /scoring/rounds/{round_id}/students/{student_id}/my-score`.

---

## Project Structure

```
app/
├── core/         config.py, security.py, websocket_manager.py, database.py
├── models/       SQLModel tables
├── schemas/      Pydantic request/response models
├── crud/         Async DB query functions
├── services/     ranking_engine, certificate, dossier, reporting, notifications, s3
├── api/
│   ├── deps.py   Auth dependencies
│   └── v1/routes/  All REST endpoints
├── ws/           WebSocket endpoints
├── workers/      Celery app + tasks
└── main.py
alembic/          Migrations
seed/             Demo data
templates/        WeasyPrint HTML templates (EN + AR)
tests/            pytest suite
```

---

## Key Assumptions

| Assumption | Value | Notes |
|------------|-------|-------|
| `panel_score_method` | AVERAGE | Spec said "not explicitly confirmed" — overridable per season |
| Institution WS | Single public `/ws/leaderboard/{category_id}` | Filter client-side |
| Task queue | Celery + Redis | Confirmed by user |
| PDF engine | WeasyPrint | Best RTL Arabic support |

