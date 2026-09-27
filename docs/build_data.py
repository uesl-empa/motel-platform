"""
Build the data files behind the MOTEL data explorer (docs/explorer.html).

Reads the published database in motel-db/ and writes, under docs/data/:

- motel-data.js     the explorer's data as `window.MOTEL_DATA = {...}`, loaded
                    with a <script> tag so explorer.html also works when opened
                    straight from disk
- motel-data.json   the same data as plain JSON, for download
- motel-values.csv  one row per value with its technology, attribute, unit,
                    year, scope, and sources: the long table most modelling
                    tools load directly

Standard library plus PyYAML only, so the Deploy Docs workflow can run it
before publishing. The output is generated, not committed (docs/data/ is
ignored by git).

Usage:
    python docs/build_data.py
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "motel-db"
OUT = Path(__file__).resolve().parent / "data"

SCOPE_TYPES = ("geographic_scope", "temporal_scope", "capacity_scope", "system_boundary")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_yaml_list(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or []


def clean(value):
    """Blank CSV cells become None so the JSON stays small and explicit."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def pick(row: dict, *fields: str) -> dict:
    return {field: clean(row.get(field)) for field in fields}


def load_scopes() -> tuple[dict, dict]:
    """
    Return the scope vocabularies and a map from raw staged values to tokens.

    Some published linked entities still carry the raw staged value (for
    example "ECA") instead of its token (GEO_ECA). The scope mapping tables
    record which token each raw value resolved to, so the explorer can show
    the right label for both until the records are repaired.
    """
    vocab, aliases = {}, {}
    for scope_type in SCOPE_TYPES:
        rows = read_csv(DB / "controlled_vocabulary" / f"{scope_type}.csv")
        vocab[scope_type] = {
            row[scope_type].strip(): clean(row.get(f"{scope_type}_description"))
            for row in rows
            if clean(row.get(scope_type))
        }
        aliases[scope_type] = {
            row["original_value"].strip(): row["scope_token"].strip()
            for row in read_csv(DB / "mapping" / f"{scope_type}_map.csv")
            if clean(row.get("original_value")) and clean(row.get("scope_token"))
        }
    return vocab, aliases


def resolve_scope(scope: dict, vocab: dict, aliases: dict) -> dict:
    resolved = {}
    for scope_type in SCOPE_TYPES:
        value = clean((scope or {}).get(scope_type))
        if value and value not in vocab[scope_type]:
            value = aliases[scope_type].get(value, value)
        resolved[scope_type] = value
    return resolved


def build() -> dict:
    technologies = [
        {
            "id": row["tech_id"],
            **pick(row, "technology_name", "technology_description", "technology_variant",
                   "main_process", "main_operation_unit"),
        }
        for row in read_csv(DB / "secondary" / "technology.csv")
    ]
    processes = [
        {"id": row["process_id"], **pick(row, "process_name", "process_description",
                                          "process_type", "process_category", "main_sector")}
        for row in read_csv(DB / "secondary" / "process.csv")
    ]
    sources = [
        {"id": row["source_id"], **pick(row, "source_name", "source_description", "source_type",
                                         "link", "reference_year", "confidence_level",
                                         "assessment_method")}
        for row in read_csv(DB / "secondary" / "source.csv")
    ]
    carriers = [
        {"id": row["carrier_id"], **pick(row, "carrier_name", "carrier_description",
                                          "carrier_type", "carrier_category")}
        for row in read_csv(DB / "controlled_vocabulary" / "carrier.csv")
    ]
    attributes = [
        {"id": row["attribute_id"], **pick(row, "attribute_name", "attribute_description",
                                            "unit", "data_format", "applies_to")}
        for row in read_csv(DB / "controlled_vocabulary" / "attribute.csv")
    ]
    scope_vocab, scope_aliases = load_scopes()

    records = []
    for entity in read_yaml_list(DB / "linked_entity" / "linked_entity.yaml"):
        balancing = entity.get("balancing") or {}
        records.append({
            "id": entity.get("linked_entity_id"),
            "tech_id": entity.get("tech_id"),
            "process_id": clean(entity.get("process_id")),
            "scope": resolve_scope(entity.get("scope"), scope_vocab, scope_aliases),
            "sources": [
                {
                    "source_id": source.get("source_id"),
                    "attributes": [
                        attribute_id for attribute_id in source.get("linked_attributes") or []
                        if not str(attribute_id).startswith("[unregistered")
                    ],
                }
                for source in entity.get("sources") or []
            ],
            "inputs": [
                pick(flow, "carrier_id", "unit") | {"share": flow.get("share")}
                for flow in balancing.get("inputs") or []
            ],
            "outputs": [
                pick(flow, "carrier_id", "unit") | {"share": flow.get("share")}
                for flow in balancing.get("outputs") or []
            ],
            "values": [
                {
                    "attribute_id": value.get("attribute_id"),
                    "value": value.get("value"),
                    "time_index": clean(value.get("time_index")),
                }
                for value in entity.get("values") or []
                if value.get("attribute_id")
            ],
            "date_created": clean(entity.get("date_created")),
        })

    carrier_records = []
    for record in read_yaml_list(DB / "linked_carrier_data" / "linked_carrier_data.yaml"):
        carrier_records.append({
            "id": record.get("linked_carrier_data_id"),
            "carrier_id": record.get("carrier_id"),
            "data_category": record.get("data_category"),
            "scope": resolve_scope(record.get("scope"), scope_vocab, scope_aliases)
            | {"scenario": clean((record.get("scope") or {}).get("scenario"))},
            "sources": [
                {"source_id": source.get("source_id"),
                 "attributes": source.get("linked_attributes") or []}
                for source in record.get("sources") or []
            ],
            "values": [
                {
                    "attribute_id": value.get("attribute_id"),
                    "value": value.get("value"),
                    "unit": clean(value.get("unit")),
                    "time_index": clean(value.get("time_index")),
                }
                for value in record.get("values") or []
                if value.get("attribute_id")
            ],
        })

    return {
        "generated": datetime.date.today().isoformat(),
        "technologies": technologies,
        "processes": processes,
        "sources": sources,
        "carriers": carriers,
        "attributes": attributes,
        "scopes": scope_vocab,
        "records": records,
        "carrier_records": carrier_records,
    }


def write_values_csv(data: dict, path: Path) -> int:
    """Write the long table: one row per value of the technology track."""
    technologies = {t["id"]: t for t in data["technologies"]}
    processes = {p["id"]: p for p in data["processes"]}
    attributes = {a["id"]: a for a in data["attributes"]}
    source_names = {s["id"]: s["source_name"] for s in data["sources"]}
    columns = [
        "linked_entity_id", "tech_id", "technology_name", "process_id", "process_name",
        "attribute_id", "attribute_name", "value", "unit", "time_index",
        *SCOPE_TYPES, "source_ids", "source_names",
    ]
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in data["records"]:
            technology = technologies.get(record["tech_id"], {})
            process_id = record["process_id"] or technology.get("main_process")
            for value in record["values"]:
                attribute = attributes.get(value["attribute_id"], {})
                value_sources = [
                    source["source_id"] for source in record["sources"]
                    if value["attribute_id"] in source["attributes"]
                ]
                writer.writerow({
                    "linked_entity_id": record["id"],
                    "tech_id": record["tech_id"],
                    "technology_name": technology.get("technology_name"),
                    "process_id": process_id,
                    "process_name": processes.get(process_id, {}).get("process_name"),
                    "attribute_id": value["attribute_id"],
                    "attribute_name": attribute.get("attribute_name"),
                    "value": value["value"],
                    "unit": attribute.get("unit"),
                    "time_index": value["time_index"],
                    **record["scope"],
                    "source_ids": ";".join(value_sources),
                    "source_names": ";".join(source_names.get(s) or s for s in value_sources),
                })
                rows += 1
    return rows


def main() -> int:
    data = build()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    (OUT / "motel-data.json").write_text(payload, encoding="utf-8")
    (OUT / "motel-data.js").write_text(f"window.MOTEL_DATA = {payload};\n", encoding="utf-8")
    rows = write_values_csv(data, OUT / "motel-values.csv")
    print(
        f"Wrote {OUT.relative_to(ROOT)}: {len(data['technologies'])} technologies, "
        f"{len(data['records'])} records, {rows} values, "
        f"{len(data['carrier_records'])} carrier records ({len(payload) / 1024:.0f} KiB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
