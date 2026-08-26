from sqlmodel import Field, SQLModel


class County(SQLModel, table=True):
    __tablename__ = "counties"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    active: bool = Field(default=True)
