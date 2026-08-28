from datetime import datetime
from pydantic import BaseModel
from app.models.round import RoundType, RoundStatus, JudgeRole


class RoundCreate(BaseModel):
    category_id: int
    round_type: RoundType
    scheduled_at: datetime


class RoundRead(BaseModel):
    id: int
    category_id: int
    round_type: RoundType
    status: RoundStatus
    scheduled_at: datetime
    active_student_id: int | None = None
    model_config = {"from_attributes": True}


class RoundUpdate(BaseModel):
    scheduled_at: datetime | None = None


class JudgeAssignmentCreate(BaseModel):
    admin_user_id: int
    judge_role: JudgeRole


class JudgeAssignmentRead(BaseModel):
    id: int
    round_id: int
    admin_user_id: int
    judge_role: JudgeRole
    model_config = {"from_attributes": True}
