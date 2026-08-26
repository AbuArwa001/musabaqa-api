from pydantic import BaseModel


class CountyCreate(BaseModel):
    name: str
    active: bool = True


class CountyRead(BaseModel):
    id: int
    name: str
    active: bool
    model_config = {"from_attributes": True}


class CountyUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
