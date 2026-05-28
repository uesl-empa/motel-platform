from fastapi import APIRouter

from app.models.technology import Technology

router = APIRouter(prefix="/technologies", tags=["technologies"])

_SAMPLE_TECHNOLOGIES = [
    Technology(
        id="solar_pv_utility",
        name="Solar PV Utility-Scale",
        category="conversion",
        capex_chf_per_kw=920.0,
        lifetime_years=30,
        efficiency=0.2,
    ),
    Technology(
        id="li_ion_battery",
        name="Li-Ion Battery",
        category="storage",
        capex_chf_per_kw=450.0,
        lifetime_years=15,
        efficiency=0.9,
    ),
]


@router.get("", response_model=list[Technology])
def list_technologies() -> list[Technology]:
    return _SAMPLE_TECHNOLOGIES
