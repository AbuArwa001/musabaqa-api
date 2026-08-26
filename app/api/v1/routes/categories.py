from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.category import Category, ScoringCriteria, DeductionType
from app.schemas.category import (
    CategoryCreate, CategoryRead, CategoryUpdate,
    ScoringCriteriaRead, DeductionTypeRead,
)

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("/", response_model=list[CategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Category).order_by(Category.display_order))).scalars().all()


@router.post("/", response_model=CategoryRead, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    cat = Category(**data.model_dump())
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    await db.commit()
    return cat


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    cat = await db.get(Category, category_id)
    if not cat:
        from fastapi import HTTPException
        raise HTTPException(404, "Category not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    db.add(cat)
    await db.flush()
    await db.refresh(cat)
    await db.commit()
    return cat


@router.get("/scoring-criteria", response_model=list[ScoringCriteriaRead])
async def list_scoring_criteria(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(ScoringCriteria))).scalars().all()


@router.get("/deduction-types", response_model=list[DeductionTypeRead])
async def list_deduction_types(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(DeductionType))).scalars().all()
