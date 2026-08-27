"""Counties and regions management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, require_role
from app.models.admin_user import AdminRole
from app.models.county import County
from app.models.region import Region
from app.schemas.county import CountyCreate, CountyRead, CountyUpdate
from app.schemas.region import RegionCreate, RegionRead, RegionUpdate

router = APIRouter(tags=["Geography"])


@router.get("/counties", response_model=list[CountyRead])
async def list_counties(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(County))).scalars().all()


@router.post("/counties", response_model=CountyRead, status_code=201)
async def create_county(
    data: CountyCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    c = County(**data.model_dump())
    db.add(c)
    await db.flush()
    await db.refresh(c)
    await db.commit()
    return c


@router.patch("/counties/{county_id}", response_model=CountyRead)
async def update_county(
    county_id: int,
    data: CountyUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    c = await db.get(County, county_id)
    if not c:
        raise HTTPException(404, "County not found")
    for f, v in data.model_dump(exclude_unset=True).items():
        setattr(c, f, v)
    db.add(c)
    await db.flush()
    await db.refresh(c)
    await db.commit()
    return c


@router.delete("/counties/{county_id}", status_code=204)
async def delete_county(
    county_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    c = await db.get(County, county_id)
    if not c:
        raise HTTPException(404, "County not found")
    await db.delete(c)
    await db.commit()


@router.get("/regions", response_model=list[RegionRead])
async def list_regions(county_id: int | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Region)
    if county_id:
        q = q.where(Region.county_id == county_id)
    return (await db.execute(q)).scalars().all()


@router.post("/regions", response_model=RegionRead, status_code=201)
async def create_region(
    data: RegionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    r = Region(**data.model_dump())
    db.add(r)
    await db.flush()
    await db.refresh(r)
    await db.commit()
    return r


@router.patch("/regions/{region_id}", response_model=RegionRead)
async def update_region(
    region_id: int,
    data: RegionUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    r = await db.get(Region, region_id)
    if not r:
        raise HTTPException(404, "Region not found")
    for f, v in data.model_dump(exclude_unset=True).items():
        setattr(r, f, v)
    db.add(r)
    await db.flush()
    await db.refresh(r)
    await db.commit()
    return r


@router.delete("/regions/{region_id}", status_code=204)
async def delete_region(
    region_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_role(AdminRole.SUPERADMIN)),
):
    r = await db.get(Region, region_id)
    if not r:
        raise HTTPException(404, "Region not found")
    await db.delete(r)
    await db.commit()

