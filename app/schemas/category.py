from pydantic import BaseModel
from app.models.category import CategoryGroup, ScoringMethod


class CategoryCreate(BaseModel):
    name_en: str
    name_ar: str
    min_age: int | None = None
    max_age: int
    category_group: CategoryGroup
    display_order: int = 0


class CategoryRead(BaseModel):
    id: int
    name_en: str
    name_ar: str
    min_age: int | None
    max_age: int
    category_group: CategoryGroup
    display_order: int
    model_config = {"from_attributes": True}


class CategoryUpdate(BaseModel):
    name_en: str | None = None
    name_ar: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    display_order: int | None = None


class ScoringCriteriaRead(BaseModel):
    id: int
    category_group: CategoryGroup
    name_en: str
    name_ar: str
    max_points: float
    scoring_method: ScoringMethod
    model_config = {"from_attributes": True}


class DeductionTypeRead(BaseModel):
    id: int
    scoring_criteria_id: int
    name_en: str
    name_ar: str
    points_deducted: float | None
    model_config = {"from_attributes": True}
