from pydantic import BaseModel


class RegionCreate(BaseModel):
    name_en: str
    name_ar: str
    county_id: int
    active: bool = True


class RegionRead(BaseModel):
    id: int
    name_en: str
    name_ar: str
    county_id: int
    active: bool
    model_config = {"from_attributes": True}


class RegionUpdate(BaseModel):
    name_en: str | None = None
    name_ar: str | None = None
    active: bool | None = None
