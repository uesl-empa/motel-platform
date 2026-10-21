"""
Build the data files behind the MOTEL data explorer (docs/explorer.html).

Reads a MOTEL database and writes, under docs/data/:

- motel-data.js     the explorer's data as `window.MOTEL_DATA = {...}`, loaded
                    with a <script> tag so explorer.html also works when opened
                    straight from disk
- motel-data.json   the same data as plain JSON, for download
- motel-values.csv  one row per value with its technology, attribute, unit,
                    year, scope, and sources: the long table most modelling
                    tools load directly
- withheld-values.csv  the release's list of withheld values, when the database
                    is a public release built by tools/build_release.py

The Deploy Docs workflow builds the public release first and points --db at
it, so the published explorer carries only values whose sources permit
redistribution. Without --db it reads motel-db/ (or $MOTEL_DATA/motel-db),
which is for local use only.

Standard library plus PyYAML only, so the Deploy Docs workflow can run it
before publishing. The output is generated, not committed (docs/data/ is
ignored by git).

Usage:
    python docs/build_data.py
    python docs/build_data.py --db dist/motel-db
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# Full database when MOTEL_DATA points at a checkout of the private motel-data
# repository; the public release in this repository otherwise.
DB = (
    Path(os.environ["MOTEL_DATA"]).expanduser().resolve() / "motel-db"
    if os.environ.get("MOTEL_DATA", "").strip()
    else ROOT / "motel-db"
)
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


SCENARIO_NOTE = re.compile(r"climate scenario:\s*([^|]+)")


def value_note(value: dict) -> tuple[str | None, str | None]:
    """
    Return (scenario, note) for one value.

    Values from scenario-dependent sources (the reFuel LCA, for example) carry
    "climate scenario: ssp2_ndc | ..." in their note; the scenario is pulled
    out so the explorer can keep the scenarios apart, and the rest of the note
    is kept as it is.
    """
    note = clean(value.get("note"))
    if not note:
        return None, None
    match = SCENARIO_NOTE.search(note)
    if not match:
        return None, note
    rest = " | ".join(part.strip() for part in note.split("|")
                      if not SCENARIO_NOTE.search(part) and part.strip())
    return match.group(1).strip(), rest or None


def pick(row: dict, *fields: str) -> dict:
    return {field: clean(row.get(field)) for field in fields}


def load_scopes(db: Path) -> tuple[dict, dict]:
    """
    Return the scope vocabularies and a map from raw staged values to tokens.

    Some published linked entities still carry the raw staged value (for
    example "ECA") instead of its token (GEO_ECA). The scope mapping tables
    record which token each raw value resolved to, so the explorer can show
    the right label for both until the records are repaired.
    """
    vocab, aliases = {}, {}
    for scope_type in SCOPE_TYPES:
        rows = read_csv(db / "controlled_vocabulary" / f"{scope_type}.csv")
        vocab[scope_type] = {
            row[scope_type].strip(): clean(row.get(f"{scope_type}_description"))
            for row in rows
            if clean(row.get(scope_type))
        }
        aliases[scope_type] = {
            row["original_value"].strip(): row["scope_token"].strip()
            for row in read_csv(db / "mapping" / f"{scope_type}_map.csv")
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


def build(db: Path) -> dict:
    technologies = [
        {
            "id": row["tech_id"],
            **pick(row, "technology_name", "technology_description", "technology_variant",
                   "main_process", "main_operation_unit"),
        }
        for row in read_csv(db / "secondary" / "technology.csv")
    ]
    processes = [
        {"id": row["process_id"], **pick(row, "process_name", "process_description",
                                          "process_type", "process_category", "main_sector")}
        for row in read_csv(db / "secondary" / "process.csv")
    ]
    sources = [
        {"id": row["source_id"], **pick(row, "source_name", "source_description", "source_type",
                                         "link", "reference_year", "confidence_level",
                                         "assessment_method", "source_licence",
                                         "redistribution_permitted")}
        for row in read_csv(db / "secondary" / "source.csv")
    ]
    carriers = [
        {"id": row["carrier_id"], **pick(row, "carrier_name", "carrier_description",
                                          "carrier_type", "carrier_category")}
        for row in read_csv(db / "controlled_vocabulary" / "carrier.csv")
    ]
    attributes = [
        {"id": row["attribute_id"], **pick(row, "attribute_name", "attribute_description",
                                            "unit", "data_format", "applies_to")}
        for row in read_csv(db / "controlled_vocabulary" / "attribute.csv")
    ]
    scope_vocab, scope_aliases = load_scopes(db)

    records = []
    for entity in read_yaml_list(db / "linked_entity" / "linked_entity.yaml"):
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
                    **dict(zip(("scenario", "note"), value_note(value))),
                }
                for value in entity.get("values") or []
                if value.get("attribute_id")
            ],
            "date_created": clean(entity.get("date_created")),
        })

    carrier_records = []
    for record in read_yaml_list(db / "linked_carrier_data" / "linked_carrier_data.yaml"):
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
        "withheld": load_withheld(db),
    }


def load_withheld(db: Path) -> dict | None:
    """
    Summarise the values a public release withheld from the harmonised records.

    None when db is not a release, which the explorer reads as "nothing was
    filtered". Only the harmonised records are counted, since they are what the
    explorer shows; the staging and human-readable copies repeat the same values.
    """
    if not (db / "WITHHELD.csv").exists():
        return None
    rows = [
        row for row in read_csv(db / "WITHHELD.csv")
        if row.get("file", "").startswith(("linked_entity/", "linked_carrier_data/"))
    ]
    return {
        "values": sum(1 for row in rows if not row["item"].startswith("balancing.")),
        "balancing": sum(1 for row in rows if row["item"].startswith("balancing.")),
        "by_reason": dict(Counter(row["reason"] for row in rows)),
    }


def write_values_csv(data: dict, path: Path) -> int:
    """Write the long table: one row per value of the technology track."""
    technologies = {t["id"]: t for t in data["technologies"]}
    processes = {p["id"]: p for p in data["processes"]}
    attributes = {a["id"]: a for a in data["attributes"]}
    source_names = {s["id"]: s["source_name"] for s in data["sources"]}
    columns = [
        "linked_entity_id", "tech_id", "technology_name", "process_id", "process_name",
        "attribute_id", "attribute_name", "value", "unit", "time_index", "scenario",
        *SCOPE_TYPES, "source_ids", "source_names", "note",
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
                    "scenario": value.get("scenario"),
                    **record["scope"],
                    "source_ids": ";".join(value_sources),
                    "source_names": ";".join(source_names.get(s) or s for s in value_sources),
                    "note": value.get("note"),
                })
                rows += 1
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the data explorer's data files.")
    parser.add_argument("--db", default=str(DB),
                        help="database to read (default: $MOTEL_DATA/motel-db, else <repo>/motel-db; publish from "
                             "a release built by tools/build_release.py)")
    db = Path(parser.parse_args(argv).db).resolve()

    data = build(db)
    OUT.mkdir(parents=True, exist_ok=True)
    withheld_list = OUT / "withheld-values.csv"
    if (db / "WITHHELD.csv").exists():
        shutil.copyfile(db / "WITHHELD.csv", withheld_list)
    elif withheld_list.exists():
        withheld_list.unlink()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    (OUT / "motel-data.json").write_text(payload, encoding="utf-8")
    (OUT / "motel-data.js").write_text(f"window.MOTEL_DATA = {payload};\n", encoding="utf-8")
    rows = write_values_csv(data, OUT / "motel-values.csv")
    print(
        f"Wrote {OUT.relative_to(ROOT)}: {len(data['technologies'])} technologies, "
        f"{len(data['records'])} records, {rows} values, "
        f"{len(data['carrier_records'])} carrier records ({len(payload) / 1024:.0f} KiB)"
        + (f", {data['withheld']['values']} values withheld" if data["withheld"] else
           " — unfiltered motel-db, not for publishing")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
