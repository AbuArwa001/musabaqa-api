import enum
from datetime import datetime, timezone
from typing import List
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class GeographicScope(str, enum.Enum):
    REGIONAL = "REGIONAL"
    NATIONAL = "NATIONAL"


class RankingScope(str, enum.Enum):
    PER_REGION_PER_CATEGORY = "PER_REGION_PER_CATEGORY"
    PER_REGION_COMBINED = "PER_REGION_COMBINED"


class PanelScoreMethod(str, enum.Enum):
    AVERAGE = "AVERAGE"   # Default — confirmed assumption
    MEDIAN = "MEDIAN"


class CompetitionSeasonSettings(SQLModel, table=True):
    """
    One active row per season.

    ASSUMPTION: panel_score_method defaults to AVERAGE.
    The spec did not explicitly confirm this — it is flagged here.
    Override per-season via the admin API.
    """
    __tablename__ = "competition_season_settings"

    id: int | None = Field(default=None, primary_key=True)
    season: str = Field(index=True, unique=True, description="e.g. '2025', '2026'")
    is_active: bool = Field(default=False, index=True)

    geographic_scope: GeographicScope = Field(
        default=GeographicScope.REGIONAL,
        sa_column=Column(sa.Enum(GeographicScope), nullable=False),
    )
    regional_balancing_enabled: bool = Field(default=True)
    default_top_n_per_region: int = Field(default=4)
    tie_allowance_pool: int = Field(
        default=3,
        description="Per-category allowance; NOT a single competition-wide pool",
    )
    ranking_scope: RankingScope = Field(
        default=RankingScope.PER_REGION_PER_CATEGORY,
        sa_column=Column(sa.Enum(RankingScope), nullable=False),
    )
    panel_score_method: PanelScoreMethod = Field(
        default=PanelScoreMethod.AVERAGE,
        sa_column=Column(sa.Enum(PanelScoreMethod), nullable=False),
    )


class RegionOverride(SQLModel, table=True):
    """Per-region exception to the season default top_n."""
    __tablename__ = "region_overrides"

    id: int | None = Field(default=None, primary_key=True)
    region_id: int = Field(foreign_key="regions.id", index=True)
    season: str = Field(index=True)
    top_n_override: int | None = Field(default=None)
    active: bool = Field(default=True)


class RoundResult(SQLModel, table=True):
    """
    Written automatically by the ranking engine.
    NEVER directly editable by a user.
    """
    __tablename__ = "round_results"

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="rounds.id", index=True)
    student_id: int = Field(foreign_key="students.id", index=True)
    final_score: float
    rank: int | None = Field(default=None)
    computed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    consistency_flagged: bool = Field(default=False)


class TieBreakVote(SQLModel, table=True):
    """
    Recorded when a tie exists at the advancement boundary for a region+category.
    resolved_at and resolution are set once all votes are in.
    """
    __tablename__ = "tie_break_votes"

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="rounds.id", index=True)
    # Stored as a JSON array of student IDs (cross-dialect compatible)
    tied_student_ids: List[int] = Field(
        default_factory=list,
        sa_column=Column(sa.JSON, nullable=False)
    )
    judge_id: int = Field(foreign_key="admin_users.id", index=True)
    vote: int = Field(description="student_id this judge votes for")
    voted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(sa.DateTime(timezone=True), nullable=False),
    )
    resolved_at: datetime | None = Field(
        default=None,
        sa_column=Column(sa.DateTime(timezone=True), nullable=True),
    )
    resolution: int | None = Field(
        default=None, description="Winning student_id once all votes tallied"
    )
