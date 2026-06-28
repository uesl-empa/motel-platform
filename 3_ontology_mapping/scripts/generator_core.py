"""
Core TTL generator for motel-db -> MOTEL ontology export.

This module contains the real generation logic used by both:
- `gen_ttl.py` for command-line generation
- `ttl_creation_from_motel_db.ipynb` for notebook-based generation

What this file does:
- reads motel-db source files (`linked_entity.yaml` and supporting CSV tables)
- converts technology records into ontology individuals
- creates technology attributes from mapped motel-db values
- creates input/output flow nodes from each technology's `balancing` section
- creates dedicated `EmbeddedCarbon` nodes from motel-db embedded-carbon records
- returns the generated TTL text, plus simple stats and warnings

Important design note:
- this file is the single source of truth for motel-db TTL creation
- the notebook should call the functions here, not reimplement generation logic
- `gen_ttl.py` is only a thin wrapper around this module

Main public functions:
- `build_ttl_output(...)`: build TTL in memory and return metadata
- `write_ttl_output(...)`: build TTL and write it to the target `.ttl` file
"""

import csv
import re
import yaml
from collections import Counter
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_MOTEL_DB_PATH = REPO_ROOT / "motel-db"
DEFAULT_OUTPUT_TTL = REPO_ROOT / "3_ontology_mapping" / "output_ttl" / "cls_atr_motel.ttl"

# Base web path used when this file creates new MOTEL item IDs.
PROJECT_BASE = "https://digicities.info/proj/MOTEL"

# Standard unit IDs used when we want to attach a known unit to a value.
_QUDT = {
    "year": "http://qudt.org/vocab/unit/YR",
    "degC": "http://qudt.org/vocab/unit/DEG_C",
    "pct": "http://qudt.org/vocab/unit/PERCENT",
    "kW": "http://qudt.org/vocab/unit/KiloW",
    "MW": "http://qudt.org/vocab/unit/MegaW",
}
_USD = "http://qudt.org/vocab/currency/USD"
_EUR = "http://qudt.org/vocab/currency/EUR"

# Map simple unit labels from motel-db to standard unit IDs.
# This is used for regular technology values like lifetime, temperature, and size.
ATTRIBUTE_QUDT_BY_UNIT_LABEL = {
    "YR": _QUDT["year"],
    "dimensionless": None,
    "%": _QUDT["pct"],
    "°C": _QUDT["degC"],
    "kW": _QUDT["kW"],
    "MW": _QUDT["MW"],
}

# Separate unit lookup for input/output flows.
# Flow units come from a different part of motel-db, so they need their own mapping table.
FLOW_UNIT_BY_LABEL = {
    "kwh": ("http://qudt.org/vocab/unit/KiloW-HR", "KiloW-HR"),
    "kwhr": ("http://qudt.org/vocab/unit/KiloW-HR", "KiloW-HR"),
    "kg": ("http://qudt.org/vocab/unit/KiloGM", "KiloGM"),
    "t": ("http://qudt.org/vocab/unit/TON_Metric", "TON_Metric"),
    "ton": ("http://qudt.org/vocab/unit/TON_Metric", "TON_Metric"),
    "tonne": ("http://qudt.org/vocab/unit/TON_Metric", "TON_Metric"),
}

# Main mapping from cleaned-up motel-db attribute names to Digicities attribute types.
# Each entry says:
# - which Digicities attribute name to use
# - what kind of attribute it is
# - what data type to store for the value
ATTR_CONFIG = {
    "trl": {"class": "TRL", "category": "SimpleValueAttribute", "dtype": "int"},
    "tech_maturity": {"class": "tech_maturity", "category": "CategoricalAttribute", "dtype": "text"},
    "technical_efficiency": {"class": "technical_efficiency", "category": "PhysicalAttribute", "dtype": "decimal"},
    "theoretical_efficiency": {"class": "theoretical_efficiency", "category": "PhysicalAttribute", "dtype": "decimal"},
    "operating_temperature_c": {"class": "operating_temperature_c", "category": "PhysicalAttribute", "dtype": "decimal"},
    "lifetime_yr": {"class": "Lifetime", "category": "PhysicalAttribute", "dtype": "decimal"},
    "capex_one_time": {"class": "CAPEX", "category": "SimpleCostAttribute", "dtype": "decimal"},
    "capex_per_capacity": {"class": "CAPEXPerCapacity", "category": "UnitBasedCostAttribute", "dtype": "decimal"},
    "opex_one_time": {"class": "OPEX", "category": "SimpleCostAttribute", "dtype": "decimal"},
    "opex_fix_pct_of_capex": {"class": "opex_fix_pct_of_capex", "category": "PhysicalAttribute", "dtype": "decimal"},
    "opex_per_capacity_yr": {"class": "OPEX_power", "category": "UnitBasedCostAttribute", "dtype": "decimal"},
    "opex_per_energy": {"class": "OPEX_energy", "category": "UnitBasedCostAttribute", "dtype": "decimal"},
    "min_installation_size": {"class": "min_installation_size", "category": "PhysicalAttribute", "dtype": "decimal"},
    "uncertainty_rating": {"class": "uncertainty_rating", "category": "CategoricalAttribute", "dtype": "text"},
    "discount_rate_pct": {"class": "InterestRate", "category": "PhysicalAttribute", "dtype": "decimal"},
    "reference_unit_size": {"class": "reference_unit_size", "category": "PhysicalAttribute", "dtype": "decimal"},
}

# Different source spellings that should all be treated as the same attribute name.
# This step only cleans up names before we look them up in ATTR_CONFIG.
ATTRIBUTE_NAME_ALIASES = {
    "technology readiness level": "trl",
    "technology maturity": "tech_maturity",
    "technical efficiency": "technical_efficiency",
    "theoretical efficiency": "theoretical_efficiency",
    "operating temperature": "operating_temperature_c",
    "economiclifetime": "lifetime_yr",
    "economic lifetime": "lifetime_yr",
    "capital expenditure one time": "capex_one_time",
    "capital expenditure per capacity": "capex_per_capacity",
    "one-time operational expenditure": "opex_one_time",
    "opex one-time": "opex_one_time",
    "fixed operational expenditure percentage of capital expenditure": "opex_fix_pct_of_capex",
    "annual opex per capacity": "opex_per_capacity_yr",
    "annual operational expenditure per installed capacity": "opex_per_capacity_yr",
    "operational expenditure per capacity": "opex_per_capacity_yr",
    "operating expenditure per energy": "opex_per_energy",
    "operational expenditure per energy": "opex_per_energy",
    "minimum installation size": "min_installation_size",
    "uncertainty rating": "uncertainty_rating",
    "discount rate": "discount_rate_pct",
    "reference unit size": "reference_unit_size",
}

# Carrier types that should be exported as `EnergyCarrier`.
# Everything else is treated as `Material`.
ENERGY_CARRIER_TYPES = {"electricity", "fuel", "heat"}

# Special marker used to tell apart embedded-carbon rows from normal technology rows.
# This is due to the web app design (the embedded carbon of a tech is shown in a seperated table)
EMBEDDED_CARBON_ATTR_ID = "ATTR_00028"
EMBEDDED_CARBON_ATTR_NAME = "embedded carbon"

# Prefix block for the generated TTL.
# `dici_onto` is the main Digicities vocabulary.
# The other prefixes are used for units, sources, text types, and related helper terms.
PREFIXES = """@prefix dici_onto: <https://digicities.info/ontology#> .
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix cur: <http://qudt.org/vocab/currency/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix schema: <https://schema.org/> .
"""


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a motel-db CSV file into a list of rows."""
    with open(path, encoding="utf-8") as file:
        return list(csv.DictReader(file))


def u(iri: str) -> str:
    """Wrap a full ID in Turtle format."""
    return f"<{iri}>"


def esc(value: object) -> str:
    """Make text safe to write inside a Turtle string."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def cn(value: object) -> str:
    """Turn free text into a simple safe name."""
    return re.sub(r"[^A-Za-z0-9_]", "_", str(value)).strip("_")


def safe_uri(value: object) -> str:
    """Turn free text into a safe URL-like path part."""
    return re.sub(r"[^A-Za-z0-9_.~:@!$&'()*+,;=/?#-]", "_", str(value))


def normalize_scope_value(value: object) -> str:
    """Remove code-like prefixes such as `GEO_` or `YEAR_` from scope values."""
    return re.sub(r"^[A-Z]+_", "", str(value or "").strip())


def normalize_attribute_name(name: object) -> str:
    """Clean up a source attribute name so we can match it in ATTR_CONFIG."""
    text = str(name or "").strip()
    if not text:
        return ""
    if text in ATTR_CONFIG:
        return text
    lowered = text.lower()
    if lowered in ATTRIBUTE_NAME_ALIASES:
        return ATTRIBUTE_NAME_ALIASES[lowered]
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    if collapsed in ATTRIBUTE_NAME_ALIASES:
        return ATTRIBUTE_NAME_ALIASES[collapsed]
    return cn(text).lower()


def normalize_attribute_unit_label(unit: object) -> str | None:
    """Clean up a unit label before we map it to a standard unit or currency."""
    text = str(unit or "").strip()
    if not text or text in {"—", "-", "nan"}:
        return None

    lowered = text.lower()
    if lowered == "years":
        return "YR"
    if lowered == "ratio":
        return "dimensionless"
    return text


def infer_currency_from_unit_label(unit_label: str | None) -> str | None:
    """Guess the currency from a unit label such as `EUR/kW` or `USD/kWh`."""
    if not unit_label:
        return None
    upper = unit_label.upper()
    if "EUR" in upper:
        return _EUR
    if "USD" in upper:
        return _USD
    return None


def infer_qudt_unit_from_unit_label(unit_label: str | None) -> str | None:
    """Look up the standard unit ID for a cleaned unit label."""
    if not unit_label:
        return None
    return ATTRIBUTE_QUDT_BY_UNIT_LABEL.get(unit_label)


def normalize_balancing_entries(entity: dict, direction: str) -> list[dict[str, object]]:
    """Turn the balancing data into one simple flow list format."""
    balancing = entity.get("balancing", {}) or {}
    candidate_keys = [direction, direction[:-1], f'ratios_{"in" if direction == "inputs" else "out"}']
    raw_entries: list[dict] = []
    for key in candidate_keys:
        value = balancing.get(key)
        if isinstance(value, list):
            raw_entries.extend(value)
        elif isinstance(value, dict):
            if "carrier_id" in value:
                raw_entries.append(value)
            else:
                for nested_key in ("flows", "entries", "items"):
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        raw_entries.extend(nested)

    normalized: list[dict[str, object]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        carrier_id = entry.get("carrier_id") or entry.get("carrierId")
        if not carrier_id:
            continue
        normalized.append(
            {
                "carrier_id": carrier_id,
                "share": entry.get("share", entry.get("value", entry.get("ratio"))),
                "unit": entry.get("unit", entry.get("share_unit", "")),
                "is_main": bool(entry.get("is_main", entry.get("main", entry.get("is_primary", False)))),
            }
        )
    return normalized


def classify_carrier(carrier_row: dict[str, str]) -> tuple[str, str]:
    """Decide which Digicities types to use for a carrier and its flow."""
    carrier_type = str((carrier_row or {}).get("carrier_type", "")).strip().lower()
    if carrier_type in ENERGY_CARRIER_TYPES:
        return ("EnergyCarrier", "EnergyCarrierFlow")
    return ("Material", "MaterialFlow")


def inst_uri(label: str) -> str:
    """Build the ID for one technology item in the MOTEL output."""
    return f"{PROJECT_BASE}/EnergyConverter/{label}"


def attr_uri(label: str, attribute_class: str) -> str:
    """Build the ID for one attribute attached to a technology item."""
    return f"{inst_uri(label)}/{attribute_class}"


def carrier_uri(name: str) -> str:
    """Build the ID for a carrier or material used by flows."""
    return f"{PROJECT_BASE}/{safe_uri('EnergyCarrier')}/{safe_uri(name)}"


def reference_uri(name: str) -> str:
    """Build the ID for a source or reference item."""
    return f"{PROJECT_BASE}/Reference/{safe_uri(name)}"


def location_uri(geo: str) -> str:
    """Build the ID for a location item."""
    return f"{PROJECT_BASE}/{safe_uri(geo)}"


def temporal_uri(year: str) -> str:
    """Build the ID for a time item."""
    return f"{PROJECT_BASE}/{safe_uri(year)}"


def embedded_carbon_uri(label: str) -> str:
    """Build the ID for an embedded-carbon item."""
    return f"{PROJECT_BASE}/EmbeddedCarbon/{safe_uri(label)}"


def tb(subject: str, po_pairs: list[tuple[str, str]]) -> str:
    """Build one Turtle text block from one subject and its fields."""
    if not po_pairs:
        return ""
    lines = [subject]
    for index, (pred, obj) in enumerate(po_pairs):
        sep = " ;" if index < len(po_pairs) - 1 else " ."
        lines.append(f"\t{pred} {obj}{sep}")
    return "\n".join(lines)


def fv(raw: object, dtype: str) -> str:
    """Format one motel-db value for the TTL output."""
    text = str(raw).strip()
    if dtype == "int":
        try:
            return f'"{int(float(text))}"^^xsd:integer'
        except ValueError:
            pass
    elif dtype == "decimal":
        try:
            return f'"{float(text)}"^^xsd:decimal'
        except ValueError:
            pass
    return f'"{esc(text)}"^^xsd:string'


def build_ttl_content(path_motel_db: Path) -> tuple[str, Counter, list[str]]:
    """Read motel-db files and build the main TTL text plus stats and warnings."""
    db = Path(path_motel_db)
    with open(db / "linked_entity" / "linked_entity.yaml", encoding="utf-8") as file:
        linked_entities = yaml.safe_load(file)

    technologies = read_csv(db / "secondary" / "technology.csv")
    sources = read_csv(db / "secondary" / "source.csv")
    carriers = read_csv(db / "controlled_vocabulary" / "carrier.csv")
    attributes = read_csv(db / "controlled_vocabulary" / "attribute.csv")
    unmapped_map = read_csv(db / "mapping" / "unmapped_to_linked.csv")

    tech_by_id = {t["tech_id"]: t for t in technologies}
    source_by_id = {s["source_id"]: s for s in sources}
    carrier_by_id = {c["carrier_id"]: c for c in carriers}
    attribute_by_id = {a["attribute_id"]: a for a in attributes}
    le_tech_name = {r["linked_entity_id"]: r["technology_name"] for r in unmapped_map}

    def is_embedded_carbon_entity(entity: dict) -> bool:
        """Check whether this row is for embedded carbon instead of a technology."""
        values = entity.get("values", []) or []
        if not values:
            return False
        return all(
            str(value_entry.get("attribute_id", "")).strip() == EMBEDDED_CARBON_ATTR_ID
            or str(value_entry.get("attribute_name", "")).strip().lower() == EMBEDDED_CARBON_ATTR_NAME
            for value_entry in values
        )

    tech_entities = [entity for entity in linked_entities if not is_embedded_carbon_entity(entity)]
    embedded_carbon_entities = [entity for entity in linked_entities if is_embedded_carbon_entity(entity)]

    scope_by_le = {e["linked_entity_id"]: e.get("scope", {}) for e in tech_entities}
    tid_by_le = {e["linked_entity_id"]: e["tech_id"] for e in tech_entities}

    def base_label(le_id: str) -> str:
        """Build a base name from the technology name and year."""
        tname = le_tech_name.get(le_id, tech_by_id.get(tid_by_le.get(le_id, ""), {}).get("technology_name", le_id))
        temporal = normalize_scope_value(scope_by_le.get(le_id, {}).get("temporal_scope", ""))
        return f"{tname}_{temporal}"

    key_counts = Counter(base_label(entity["linked_entity_id"]) for entity in tech_entities)
    le_instance_label = {}
    for entity in tech_entities:
        le_id = entity["linked_entity_id"]
        base = base_label(le_id)
        le_instance_label[le_id] = f"{base}_{le_id}" if key_counts[base] > 1 else base

    blocks = [PREFIXES, "# --- References ---"]
    stats = Counter()
    warnings: list[str] = []

    for src in source_by_id.values():
        name = src["source_name"]
        desc = src.get("source_description") or ""
        link = src.get("link") or ""
        adate = src.get("access_date") or ""
        po = [("a", "dici_onto:Reference"), ("rdfs:label", f'"{esc(name)}"')]
        if desc and desc.lower() not in ("nan", ""):
            po.append(("rdfs:comment", f'"{esc(desc)}"'))
        if link:
            po.append(("schema:url", f'"{esc(link)}"^^xsd:anyURI'))
        if adate:
            po.append(("dcterms:dateAccessed", f'"{adate}"^^xsd:date'))
        blocks.append(tb(u(reference_uri(name)), po))

    blocks.append("\n# --- Carrier instances ---")
    seen_carriers: set[str] = set()
    for entity in tech_entities:
        for direction in ("inputs", "outputs"):
            for flow in normalize_balancing_entries(entity, direction):
                carrier_id = str(flow["carrier_id"])
                if carrier_id in seen_carriers:
                    continue
                seen_carriers.add(carrier_id)
                carrier = carrier_by_id.get(carrier_id)
                if not carrier:
                    warnings.append(f"{entity['linked_entity_id']}: unknown carrier_id '{carrier_id}' in {direction}")
                    continue
                carrier_class, _ = classify_carrier(carrier)
                blocks.append(
                    tb(
                        u(carrier_uri(carrier["carrier_name"])),
                        [
                            ("a", f"dici_onto:{carrier_class}"),
                            ("rdfs:label", f'"{esc(carrier["carrier_name"])}"'),
                        ],
                    )
                )

    blocks.append("\n# --- Process class hierarchy ---")
    proc_cls = {}
    for entity in tech_entities:
        tech = tech_by_id.get(entity["tech_id"], {})
        variant = (tech.get("technology_variant") or "").strip()
        if variant:
            proc_cls[variant] = cn(variant)
    for variant, cname in sorted(proc_cls.items()):
        blocks.append(
            tb(
                f"dici_onto:{cname}",
                [
                    ("a", "owl:Class"),
                    ("rdfs:subClassOf", "dici_onto:EnergyConverter"),
                    ("rdfs:label", f'"{esc(variant)}"^^xsd:string'),
                ],
            )
        )

    blocks.append("\n# --- EnergyConverter instances ---")
    tech_instance_labels_by_key: dict[tuple[str, str], list[str]] = {}
    for entity in tech_entities:
        le_id = entity["linked_entity_id"]
        tech = tech_by_id.get(entity["tech_id"], {})
        label = le_instance_label[le_id]
        tname = le_tech_name.get(le_id, tech.get("technology_name", le_id))
        scope = entity.get("scope", {})
        temporal = normalize_scope_value(scope.get("temporal_scope", ""))
        geo = (scope.get("geographic_scope") or "").strip()
        variant = (tech.get("technology_variant") or "").strip()
        type_cls = cn(variant) if variant else "EnergyConverter"
        desc = (tech.get("main_process") or tech.get("technology_description") or "").strip()

        attr_sources: dict[str, list[str]] = {}
        for source_entry in entity.get("sources", []):
            source_id = source_entry.get("source_id", "")
            for attr_id in source_entry.get("linked_attribute_ids", []):
                # Skip placeholder IDs so we only write real source links.
                if not str(attr_id).startswith("[unregistered"):
                    attr_sources.setdefault(attr_id, []).append(source_id)

        valid_attrs = []
        for value_entry in entity.get("values", []):
            attr_name = normalize_attribute_name(value_entry.get("attribute_name", ""))
            raw = value_entry.get("value")
            attr_id = value_entry.get("attribute_id", "")
            if raw is None or str(raw).strip().lower() in ("na", "nan", ""):
                continue
            if attr_name not in ATTR_CONFIG:
                warnings.append(f"{le_id}: unmapped attribute '{value_entry.get('attribute_name', '')}'")
                continue
            valid_attrs.append((attr_id, attr_name, raw, ATTR_CONFIG[attr_name]))

        inputs = normalize_balancing_entries(entity, "inputs")
        outputs = normalize_balancing_entries(entity, "outputs")

        def flow_base_uri(flow_class: str) -> str:
            """Build the base ID path for one flow type."""
            return f"{PROJECT_BASE}/{flow_class}"

        def flow_uri(direction_abbr: str, carrier_name: str, flow_class: str) -> str:
            """Build the ID for one input or output flow of a technology."""
            return f"{flow_base_uri(flow_class)}/{label}_{direction_abbr}_{safe_uri(carrier_name)}"

        def cf_attr_uri(direction_abbr: str, carrier_name: str, flow_class: str) -> str:
            """Build the ID for the conversion-factor value on a flow."""
            return f"{flow_uri(direction_abbr, carrier_name, flow_class)}/ConversionFactor"

        def main_attr_uri(direction_abbr: str, carrier_name: str, is_input: bool, flow_class: str) -> str:
            """Build the ID for the main-input or main-output flag on a flow."""
            attr_cls = "IsMainInput" if is_input else "IsMainOutput"
            return f"{flow_uri(direction_abbr, carrier_name, flow_class)}/{attr_cls}"

        po = [("a", f"dici_onto:{type_cls}")]
        if temporal:
            po.append(("dici_onto:occursDuring", u(temporal_uri(temporal))))
        if geo:
            po.append(("dici_onto:locatedIn", u(location_uri(geo))))
        po.append(("rdfs:label", f'"{esc(tname)}"'))
        if desc:
            po.append(("rdfs:description", f'"{esc(desc)}"'))

        all_attrs = []
        if temporal:
            all_attrs.append(u(attr_uri(label, "Introduced")))
        for _, _, _, cfg in valid_attrs:
            all_attrs.append(u(attr_uri(label, cfg["class"])))
        if all_attrs:
            po.append(("dici_onto:hasAttribute", ", ".join(all_attrs)))

        blocks.append(tb(u(inst_uri(label)), po))
        if temporal:
            tech_instance_labels_by_key.setdefault((entity["tech_id"], temporal), []).append(label)

        if temporal:
            blocks.append(
                tb(
                    u(attr_uri(label, "Introduced")),
                    [
                        ("a", "dici_onto:Introduced"),
                        ("a", "dici_onto:EventAttribute"),
                        ("dici_onto:hasTemporalPrecision", "dici_onto:Year"),
                        ("dici_onto:hasAttributeValue", f'"{temporal}"^^xsd:gYear'),
                    ],
                )
            )

        for attr_id, _, raw, cfg in valid_attrs:
            attr_meta = attribute_by_id.get(attr_id, {})
            source_unit_label = normalize_attribute_unit_label(attr_meta.get("unit"))
            unit_label = source_unit_label
            # Add standard unit and currency IDs when we can recognize the unit label.
            currency = infer_currency_from_unit_label(unit_label)
            qudt_unit = infer_qudt_unit_from_unit_label(unit_label)
            po_attr = [
                ("a", f"dici_onto:{cfg['class']}"),
                ("a", f"dici_onto:{cfg['category']}"),
                ("dici_onto:hasAttributeValue", fv(raw, cfg.get("dtype", "decimal"))),
            ]
            if unit_label:
                po_attr.append(("dici_onto:hasUnitLabel", f'"{esc(unit_label)}"^^xsd:string'))
            if qudt_unit:
                po_attr.append(("qudt:unit", u(qudt_unit)))
            if currency:
                po_attr.append(("dici_onto:currency", u(currency)))
            for source_id in attr_sources.get(attr_id, []):
                source = source_by_id.get(source_id, {})
                source_name = source.get("source_name")
                if source_name:
                    po_attr.append(("prov:wasDerivedFrom", u(reference_uri(source_name))))
            blocks.append(tb(u(attr_uri(label, cfg["class"])), po_attr))

        for is_input, flow_list in ((True, inputs), (False, outputs)):
            direction_abbr = "in" if is_input else "out"
            conv_predicate = "feeds" if is_input else "fedBy"
            main_cls = "IsMainInput" if is_input else "IsMainOutput"
            for index, flow_entry in enumerate(flow_list):
                carrier = carrier_by_id.get(str(flow_entry.get("carrier_id", "")), {})
                if not carrier:
                    warnings.append(
                        f"{le_id}: unknown carrier_id '{flow_entry.get('carrier_id', '')}' while building flows"
                    )
                    continue
                carrier_name = carrier["carrier_name"]
                _, flow_class = classify_carrier(carrier)
                share = flow_entry.get("share")
                has_share = share is not None and str(share).strip().lower() not in ("nan", "")
                is_main = bool(flow_entry.get("is_main")) or index == 0
                flow_subject = flow_uri(direction_abbr, carrier_name, flow_class)
                conv_factor_subject = cf_attr_uri(direction_abbr, carrier_name, flow_class)
                main_subject = main_attr_uri(direction_abbr, carrier_name, is_input, flow_class)

                attr_links = []
                if has_share:
                    attr_links.append(u(conv_factor_subject))
                if is_main:
                    attr_links.append(u(main_subject))

                flow_po = [
                    ("a", f"dici_onto:{flow_class}"),
                    ("dici_onto:contains", u(carrier_uri(carrier_name))),
                    (f"dici_onto:{conv_predicate}", u(inst_uri(label))),
                ]
                if attr_links:
                    flow_po.append(("dici_onto:hasAttribute", ", ".join(attr_links)))
                blocks.append(tb(u(flow_subject), flow_po))
                stats["flows"] += 1

                if has_share:
                    unit_raw = str(flow_entry.get("unit", "") or "").strip()
                    # Flow units use a separate mapping because they are stored differently.
                    qudt_unit, unit_label = FLOW_UNIT_BY_LABEL.get(unit_raw.lower(), (None, unit_raw))
                    attr_po = [
                        ("a", "dici_onto:ConversionFactor"),
                        ("a", "dici_onto:PhysicalAttribute"),
                        ("dici_onto:hasAttributeValue", f'"{float(share)}"^^xsd:decimal'),
                    ]
                    if qudt_unit:
                        attr_po.append(("qudt:unit", u(qudt_unit)))
                    if unit_label:
                        attr_po.append(("dici_onto:hasUnitLabel", f'"{esc(unit_label)}"^^xsd:string'))
                    blocks.append(tb(u(conv_factor_subject), attr_po))

                if is_main:
                    blocks.append(
                        tb(
                            u(main_subject),
                            [
                                ("a", f"dici_onto:{main_cls}"),
                                ("a", "dici_onto:SimpleValueAttribute"),
                                ("dici_onto:hasAttributeValue", '"1.0"^^xsd:decimal'),
                            ],
                        )
                    )

    blocks.append("\n# --- Embedded carbon instances ---")

    for entity in embedded_carbon_entities:
        # Export embedded carbon as separate items linked to the matching technology and year.
        tech_id = entity["tech_id"]
        scope = entity.get("scope", {}) or {}
        geo = normalize_scope_value(scope.get("geographic_scope", ""))
        values_by_year: dict[str, list[object]] = {}
        for value_entry in entity.get("values", []) or []:
            raw_year = str(value_entry.get("time_index", "")).strip()
            raw_value = value_entry.get("value")
            if not raw_year or raw_value is None or str(raw_value).strip().lower() in ("", "na", "nan"):
                continue
            year = normalize_scope_value(raw_year)
            values_by_year.setdefault(year, []).append(raw_value)

        for year, year_values in sorted(values_by_year.items()):
            target_labels = tech_instance_labels_by_key.get((tech_id, year), [])
            if not target_labels:
                warnings.append(
                    f"{entity['linked_entity_id']}: no technology instance found for embedded carbon tech_id '{tech_id}' in year '{year}'"
                )
                continue
            if len(year_values) < 2:
                warnings.append(
                    f"{entity['linked_entity_id']}: expected two embedded carbon values for year '{year}', found {len(year_values)}"
                )
                continue

            ssp2_ndc = year_values[0]
            ssp2_pkbudg1000 = year_values[1]

            for target_label in target_labels:
                output_unit = "kgCO2eq/kg" if re.search(r"_(CO2|H2|NH3|CH4|MeOH|Syngas|C8|C12|Biochar)_", target_label) else "kgCO2eq/kW"
                ec_label = f"{target_label}_LCA"
                ec_subject = embedded_carbon_uri(ec_label)
                lca_unit_subject = f"{ec_subject}/LCA_unit"
                ndc_subject = f"{ec_subject}/ssp2_NDC"
                pk_subject = f"{ec_subject}/ssp2_PkBudg1000"

                ec_po = [("a", "dici_onto:EmbeddedCarbon")]
                if year:
                    ec_po.append(("dici_onto:occursDuring", u(temporal_uri(year))))
                if geo:
                    ec_po.append(("dici_onto:locatedIn", u(location_uri(geo))))
                ec_po.extend(
                    [
                        ("dici_onto:linksComponent", u(inst_uri(target_label))),
                        (
                            "dici_onto:hasAttribute",
                            ", ".join([u(lca_unit_subject), u(ndc_subject), u(pk_subject)]),
                        ),
                    ]
                )
                blocks.append(tb(u(ec_subject), ec_po))
                blocks.append(
                    tb(
                        u(ec_subject),
                        [
                            ("dici_onto:hasEmbeddedCarbonLCA_unitAttribute", u(lca_unit_subject)),
                            ("dici_onto:hasEmbeddedCarbonssp2_NDCAttribute", u(ndc_subject)),
                            ("dici_onto:hasEmbeddedCarbonssp2_PkBudg1000Attribute", u(pk_subject)),
                        ],
                    )
                )
                blocks.append(
                    tb(
                        u(lca_unit_subject),
                        [
                            ("a", "dici_onto:LCA_unit"),
                            ("a", "dici_onto:SimpleValueAttribute"),
                            ("dici_onto:hasAttributeValue", f'"{output_unit}"^^xsd:string'),
                        ],
                    )
                )
                blocks.append(
                    tb(
                        u(ndc_subject),
                        [
                            ("a", "dici_onto:ssp2_NDC"),
                            ("a", "dici_onto:PhysicalAttribute"),
                            ("qudt:value", fv(ssp2_ndc, "decimal")),
                        ],
                    )
                )
                blocks.append(
                    tb(
                        u(pk_subject),
                        [
                            ("a", "dici_onto:ssp2_PkBudg1000"),
                            ("a", "dici_onto:PhysicalAttribute"),
                            ("qudt:value", fv(ssp2_pkbudg1000, "decimal")),
                        ],
                    )
                )
                stats["embedded_carbon"] += 1

    return "\n\n".join(block for block in blocks if block), stats, warnings


def build_ttl_output(
    path_motel_db: Path | str = DEFAULT_MOTEL_DB_PATH,
    output_ttl: Path | str = DEFAULT_OUTPUT_TTL,
    generated_by: str = "gen_ttl.py",
) -> dict[str, object]:
    """Build the final TTL text plus metadata about when it was created."""
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    ttl_body, stats, warnings = build_ttl_content(Path(path_motel_db))
    ttl = f"# Generated at: {generated_at}\n# Generated by: {generated_by}\n\n{ttl_body}"
    return {
        "generated_at": generated_at,
        "ttl": ttl,
        "stats": stats,
        "warnings": warnings,
        "output_ttl": Path(output_ttl),
    }


def write_ttl_output(
    path_motel_db: Path | str = DEFAULT_MOTEL_DB_PATH,
    output_ttl: Path | str = DEFAULT_OUTPUT_TTL,
    generated_by: str = "gen_ttl.py",
) -> dict[str, object]:
    """Write the TTL output to disk and return the result."""
    result = build_ttl_output(path_motel_db=path_motel_db, output_ttl=output_ttl, generated_by=generated_by)
    output_path = Path(result["output_ttl"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(str(result["ttl"]), encoding="utf-8")
    return result
