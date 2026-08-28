import re

with open("app/api/v1/routes/scoring.py", "r") as f:
    content = f.read()

new_endpoint = """
from pydantic import BaseModel

class DeductionTypeOut(BaseModel):
    id: int
    name_en: str
    name_ar: str
    points_deducted: float | None
    criteria_name: str

class CriteriaListOut(BaseModel):
    deduction_types: list[DeductionTypeOut]

@router.get("/rounds/{round_id}/deduction-types", response_model=CriteriaListOut)
async def get_round_deduction_types(
    round_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_staff),
):
    from sqlmodel import select
    from app.models.round import Round
    from app.models.category import Category, ScoringCriteria, DeductionType
    
    # 1. Get round
    round_ = await db.get(Round, round_id)
    if not round_:
        from fastapi import HTTPException
        raise HTTPException(404, "Round not found")
        
    # 2. Get category to find category_group
    category = await db.get(Category, round_.category_id)
    
    # 3. Fetch all deduction types for this category group
    results = await db.execute(
        select(DeductionType, ScoringCriteria).join(
            ScoringCriteria, DeductionType.scoring_criteria_id == ScoringCriteria.id
        ).where(
            ScoringCriteria.category_group == category.category_group
        )
    )
    
    out = []
    for dt, crit in results.all():
        out.append(DeductionTypeOut(
            id=dt.id,
            name_en=dt.name_en,
            name_ar=dt.name_ar,
            points_deducted=dt.points_deducted,
            criteria_name=crit.name_en
        ))
    return CriteriaListOut(deduction_types=out)
"""

content = content + new_endpoint

with open("app/api/v1/routes/scoring.py", "w") as f:
    f.write(content)
