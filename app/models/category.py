import enum
from sqlmodel import Field, SQLModel, Column
import sqlalchemy as sa


class CategoryGroup(str, enum.Enum):
    JUZ_10_15_20 = "JUZ_10_15_20"
    JUZ_30 = "JUZ_30"


class ScoringMethod(str, enum.Enum):
    DEDUCTION_BASED = "DEDUCTION_BASED"
    DIRECT_SCORE = "DIRECT_SCORE"  # In schema but unused today; kept for future


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    name_en: str
    name_ar: str
    min_age: int | None = Field(default=None)  # Super-Admin-editable
    max_age: int
    category_group: CategoryGroup = Field(
        sa_column=Column(sa.Enum(CategoryGroup), nullable=False)
    )
    display_order: int = Field(default=0)


class ScoringCriteria(SQLModel, table=True):
    """
    Rubric A (JUZ_10_15_20): Memorization 50, Tajweed 30, Saut 20
    Rubric B (JUZ_30):        Memorization 45, Tajweed 25, Tafsir 10, Saut 20
    All seeded as DEDUCTION_BASED.
    """
    __tablename__ = "scoring_criteria"

    id: int | None = Field(default=None, primary_key=True)
    category_group: CategoryGroup = Field(
        sa_column=Column(sa.Enum(CategoryGroup), nullable=False, index=True)
    )
    name_en: str
    name_ar: str
    max_points: float
    scoring_method: ScoringMethod = Field(
        default=ScoringMethod.DEDUCTION_BASED,
        sa_column=Column(sa.Enum(ScoringMethod), nullable=False),
    )


class DeductionType(SQLModel, table=True):
    """
    Fixed-amount deductions have points_deducted set.
    Judge-entered deductions (Saut, Tafsir) have points_deducted=NULL.
    """
    __tablename__ = "deduction_types"

    id: int | None = Field(default=None, primary_key=True)
    scoring_criteria_id: int = Field(foreign_key="scoring_criteria.id", index=True)
    name_en: str
    name_ar: str
    points_deducted: float | None = Field(
        default=None,
        description="NULL = judge-entered amount per event; value = fixed deduction",
    )
