from pathlib import Path


ROOT = Path.cwd().resolve().parent
LINKED_ENTITY_PATH = ROOT / "motel-db" / "linked_entity" / "linked_entity.yaml"
MAPPING_DIR = ROOT / "motel-db" / "mapping"
VOCAB_DIR = ROOT / "motel-db" / "controlled_vocabulary"


DEFAULT_TECHNOLOGY_KEYWORDS = ["hydrogen", "fuel cell"]
DEFAULT_ATTRIBUTE_OF_INTEREST = "Capital Expenditure Per Capacity"
DEFAULT_SOURCE_KEYWORDS = ["VSE", "ShareRef", "DanishEnergyAgency"]
DEFAULT_CARRIER_QUERY = "hydrogen"
