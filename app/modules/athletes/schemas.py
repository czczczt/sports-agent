from pydantic import BaseModel


class AthleteOut(BaseModel):
    id: int
    display_name: str
    birth_year: int | None


class AthletePage(BaseModel):
    items: list[AthleteOut]
    total: int
    limit: int
    offset: int
