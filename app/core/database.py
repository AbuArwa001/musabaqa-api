"""Async SQLAlchemy 2.0 engine + session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db_and_tables() -> None:
    """Create all tables (used in tests and startup) and ensure schema migrations."""
    import app.models  # noqa: F401
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

        # 1. Add rubric_mode to competition_season_settings if missing
        try:
            await conn.execute(text(
                "ALTER TABLE competition_season_settings ADD COLUMN IF NOT EXISTS rubric_mode VARCHAR DEFAULT 'OFFICIAL_70_30';"
            ))
        except Exception:
            try:
                await conn.execute(text(
                    "ALTER TABLE competition_season_settings ADD COLUMN rubric_mode VARCHAR DEFAULT 'OFFICIAL_70_30';"
                ))
            except Exception:
                pass

        # 2. Add question_number to deduction_events if missing
        try:
            await conn.execute(text(
                "ALTER TABLE deduction_events ADD COLUMN IF NOT EXISTS question_number INTEGER DEFAULT 1;"
            ))
        except Exception:
            try:
                await conn.execute(text(
                    "ALTER TABLE deduction_events ADD COLUMN question_number INTEGER DEFAULT 1;"
                ))
            except Exception:
                pass

        # 3. Ensure null rubric_mode rows default to OFFICIAL_70_30
        try:
            await conn.execute(text(
                "UPDATE competition_season_settings SET rubric_mode = 'OFFICIAL_70_30' WHERE rubric_mode IS NULL;"
            ))
        except Exception:
            pass


async def get_session() -> AsyncSession:
    """Dependency-injectable async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
