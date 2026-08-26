from datetime import datetime
from pydantic import BaseModel, model_validator


class DeductionEventCreate(BaseModel):
    round_id: int
    student_id: int
    deduction_type_id: int
    amount: float | None = None   # Required only when DeductionType.points_deducted is NULL
    note: str | None = None

    @model_validator(mode="after")
    def amount_check(self) -> "DeductionEventCreate":
        # Full validation (fixed vs judge-entered) is done in the CRUD layer
        # where DeductionType can be fetched; schema just ensures non-negative
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount must be positive (deductions are stored as positive values)")
        return self


class DeductionEventRead(BaseModel):
    id: int
    round_id: int
    student_id: int
    judge_id: int
    deduction_type_id: int
    amount: float
    logged_at: datetime
    note: str | None
    consistency_flagged: bool
    model_config = {"from_attributes": True}


class JudgeScoreSummary(BaseModel):
    """What a judge sees for their own submissions (others hidden until all submit)."""
    student_id: int
    round_id: int
    judge_id: int
    per_criterion_score: dict[str, float]  # criterion name_en -> score
    total_score: float
    all_judges_submitted: bool
    panel_score: float | None = None       # Only present when all_judges_submitted=True
