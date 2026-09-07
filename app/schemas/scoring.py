from datetime import datetime
from pydantic import BaseModel, model_validator


class DeductionEventCreate(BaseModel):
    round_id: int
    student_id: int
    deduction_type_id: int
    question_number: int = 1
    amount: float | None = None   # Required only when DeductionType.points_deducted is NULL
    note: str | None = None

    @model_validator(mode="after")
    def amount_check(self) -> "DeductionEventCreate":
        if self.amount is not None and self.amount < 0:
            raise ValueError("amount must be positive (deductions are stored as positive values)")
        return self


class DeductionEventRead(BaseModel):
    id: int
    round_id: int
    student_id: int
    judge_id: int
    deduction_type_id: int
    question_number: int = 1
    amount: float
    logged_at: datetime
    note: str | None
    consistency_flagged: bool
    model_config = {"from_attributes": True}


class RoundQuestionCreate(BaseModel):
    round_id: int
    student_id: int
    question_number: int
    envelope_number: str | None = None
    surah_name: str | None = None
    ayah_from: int | None = None
    ayah_to: int | None = None


class RoundQuestionRead(BaseModel):
    id: int
    round_id: int
    student_id: int
    question_number: int
    envelope_number: str | None
    surah_name: str | None
    ayah_from: int | None
    ayah_to: int | None
    created_at: datetime
    model_config = {"from_attributes": True}


class QuestionScoreBreakdown(BaseModel):
    question_number: int
    surah_name: str = ""
    ayah_from: int | None = None
    ayah_to: int | None = None
    envelope_number: str | None = None
    tanbeeh_count: int = 0
    fath_count: int = 0
    lahn_count: int = 0
    tajweed_count: int = 0
    hifdh_deductions: float = 0.0
    tajweed_deductions: float = 0.0
    saut_deductions: float = 0.0
    tafsir_deductions: float = 0.0
    total_deductions: float = 0.0
    question_allotment: float = 25.0
    question_score: float = 25.0
    tanbeeh_limit_reached: bool = False  # Rule 5: >= 3 tanbeeh


class JudgeScoreSummary(BaseModel):
    """What a judge sees for their own submissions (others hidden until all submit)."""
    student_id: int
    round_id: int
    judge_id: int
    rubric_mode: str = "OFFICIAL_70_30"
    hifdh_score: float = 70.0
    tajweed_score: float = 30.0
    saut_score: float = 0.0
    tafsir_score: float = 0.0
    max_hifdh: float = 70.0
    max_tajweed: float = 30.0
    max_saut: float = 0.0
    max_tafsir: float = 0.0
    per_criterion_score: dict[str, float] = {}  # criterion name_en -> score
    total_score: float = 100.0
    per_question: list[QuestionScoreBreakdown] = []
    all_judges_submitted: bool
    panel_score: float | None = None       # Only present when all_judges_submitted=True


class OfficialSheetRead(BaseModel):
    """Data payload for rendering the official 2026 Kenya Quran Competition evaluation sheet."""
    round_id: int
    student_id: int
    student_name: str
    nationality: str
    age: int | None
    institution_name: str
    branch_name_en: str
    branch_name_ar: str
    branch_number: int  # 30, 20, 10, 5
    venue_ar: str = "مسجد الجامع نيروبي"
    venue_en: str = "Jamia Mosque Nairobi"
    date_str: str
    judge_name: str
    judge_id: int
    rubric_mode: str = "OFFICIAL_70_30"
    questions: list[QuestionScoreBreakdown]
    total_hifdh_deduction: float
    total_tajweed_deduction: float
    total_saut_deduction: float = 0.0
    total_tafsir_deduction: float = 0.0
    final_hifdh_score: float
    final_tajweed_score: float
    final_saut_score: float = 0.0
    final_tafsir_score: float = 0.0
    max_hifdh: float = 70.0
    max_tajweed: float = 30.0
    max_saut: float = 0.0
    max_tafsir: float = 0.0
    final_score: float
    all_judges_submitted: bool
    panel_score: float | None = None


class RubricModeUpdate(BaseModel):
    rubric_mode: str


class RubricModeResponse(BaseModel):
    rubric_mode: str

