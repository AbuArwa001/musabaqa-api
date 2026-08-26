from datetime import datetime
from pydantic import BaseModel


class RoundResultRead(BaseModel):
    id: int
    round_id: int
    student_id: int
    final_score: float
    rank: int | None
    computed_at: datetime
    consistency_flagged: bool
    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int | None
    student_id: int
    student_name: str
    institution_id: int
    institution_name: str
    region_id: int | None
    region_name_en: str | None
    final_score: float
    consistency_flagged: bool


class LeaderboardPayload(BaseModel):
    category_id: int
    round_id: int
    entries: list[LeaderboardEntry]
    broadcast_at: datetime
