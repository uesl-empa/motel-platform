import os
from pathlib import Path


ROOT = Path.cwd().resolve().parent
# The public release by default; the full database when MOTEL_DATA points at a
# checkout of the private motel-data repository.
DB_DIR = (
    Path(os.environ["MOTEL_DATA"]).expanduser().resolve() / "motel-db"
    if os.environ.get("MOTEL_DATA", "").strip()
    else ROOT / "motel-db"
)
LINKED_ENTITY_PATH = DB_DIR / "linked_entity" / "linked_entity.yaml"
LINKED_CARRIER_DATA_PATH = DB_DIR / "linked_carrier_data" / "linked_carrier_data.yaml"
MAPPING_DIR = DB_DIR / "mapping"
VOCAB_DIR = DB_DIR / "controlled_vocabulary"


DEFAULT_TECHNOLOGY_KEYWORDS = ["hydrogen", "fuel cell"]
DEFAULT_ATTRIBUTE_OF_INTEREST = "Capital Expenditure Per Capacity"
DEFAULT_SOURCE_KEYWORDS = ["VSE", "ShareRef", "DanishEnergyAgency"]
DEFAULT_CARRIER_QUERY = "hydrogen"
DEFAULT_CARRIER_DATA_QUERY = "electricity"
DEFAULT_CARRIER_DATA_CATEGORY = "price"
