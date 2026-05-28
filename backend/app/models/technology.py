from pydantic import BaseModel, Field


class Technology(BaseModel):
    id: str = Field(..., description="Unique technology identifier")
    name: str
    category: str
    capex_chf_per_kw: float
    lifetime_years: int
    efficiency: float
