from sqlmodel import Field, SQLModel


class Region(SQLModel, table=True):
    __tablename__ = "regions"

    id: int | None = Field(default=None, primary_key=True)
    name_en: str
    name_ar: str
    county_id: int = Field(foreign_key="counties.id", index=True)
    active: bool = Field(default=True)
