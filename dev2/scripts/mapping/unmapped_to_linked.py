"""Map unmapped entities to linked entities (one linked_entity per source).

Design (per dev2/record_mapping.ipynb): a linked_entity is anchored to a
single source. Each unmapped_entity carries a `sources` list where every
source declares the raw reFuel attributes it backs (`linked_attribute`). We
therefore EXPLODE one entity into N linked records -- one per source -- and
each record's `values` array holds only the attributes that source supports.

Foreign keys are resolved against:
  - secondary/technologies.csv      (tech_id)
  - secondary/sources.csv           (source_id)
  - mapping/refuel/map_tech.csv     (raw reFuel tech name -> MOTEL name)
  - mapping/refuel/map_attr.csv     (raw reFuel attr name -> ATTR_* id)
  - controlled_vocabulary/*.csv     (scope + carrier ids; run bootstrap_cv first)

Anything that cannot be resolved is recorded in an `unresolved` report rather
than silently dropped.

Usage:
    python scripts/mapping/unmapped_to_linked.py
"""

from __future__ import annotations

import datetime
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]                 # dev2/
UNMAPPED = ROOT / "motel-db" / "unmapped_entity" / "refuel.yaml"
SECONDARY = ROOT / "motel-db" / "secondary"
MAPPING = ROOT / "motel-db" / "mapping" / "refuel"
CV_DIR = ROOT / "motel-db" / "controlled_vocabulary"
OUT_DIR = ROOT / "motel-db" / "linked_entity"

VERSION = "2.0.0"

# linked_attribute tokens that are balancing shares, not real attributes
NON_ATTRIBUTE_TOKENS = {"ratios_in", "ratios_out"}


# --- resolvers ---------------------------------------------------------------

def _norm_tech(name: str) -> str:
    """reFuel display name 'NH3 CCGT El' -> map_tech key 'NH3_CCGT_El'."""
    return re.sub(r"\s+", "_", str(name).strip())


def build_resolvers() -> dict:
    tech = pd.read_csv(SECONDARY / "technologies.csv")
    src = pd.read_csv(SECONDARY / "sources.csv")
    map_tech = pd.read_csv(MAPPING / "map_tech.csv")
    map_attr = pd.read_csv(MAPPING / "map_attr.csv")

    # raw reFuel tech (underscored) -> MOTEL technology_name -> tech_id
    prev2motel = dict(zip(map_tech["previous_technology_name"],
                          map_tech["new_technology_name"]))
    name2techid = dict(zip(tech["technology_name"], tech["tech_id"]))

    def tech_id(raw_name):
        motel = prev2motel.get(_norm_tech(raw_name))
        return name2techid.get(motel) if motel else None

    resolvers = {
        "tech_id": tech_id,
        "source_id": dict(zip(src["source_name"], src["source_id"])),
        # raw reFuel attribute name -> ATTR_* id  /  -> cleaned name
        "attr_raw2id": dict(zip(map_attr["Raw Attribute"],
                                map_attr["Assigned Target attribute_id"])),
        "attr_raw2cleaned": dict(zip(map_attr["Raw Attribute"],
                                     map_attr["Cleaned attribute_name"])),
        # cleaned attribute name -> ATTR_* id (entity carries cleaned names)
        "attr_cleaned2id": dict(zip(map_attr["Cleaned attribute_name"],
                                    map_attr["Assigned Target attribute_id"])),
        # valid ATTR ids
        "attr_ids": set(map_attr["Assigned Target attribute_id"].dropna()),
    }

    # controlled-vocabulary description -> id
    cv = {
        "geographic_scope": ("geographic_scope_description", "geographic_scope"),
        "temporal_scope": ("temporal_scope_description", "temporal_scope"),
        "capacity_scope": ("capacity_scope_description", "capacity_scope"),
        "system_boundary": ("system_boundary_description", "system_boundary"),
    }
    for table, (desc_col, id_col) in cv.items():
        df = pd.read_csv(CV_DIR / f"{table}.csv")
        resolvers[table] = {str(d): i for d, i in zip(df[desc_col], df[id_col])}

    carrier = pd.read_csv(CV_DIR / "carrier.csv")
    resolvers["carrier"] = dict(zip(carrier["carrier_name"], carrier["carrier_id"]))
    return resolvers


# --- value helpers -----------------------------------------------------------

def _value_type(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "numeric"
    if isinstance(value, list):
        return "array"
    return "text"


def _build_value(attr_entry: dict, attribute_id: str) -> dict:
    """unmapped attribute item -> linked_entity values[] item."""
    value = attr_entry.get("value")
    item = {
        "attribute_id": attribute_id,
        "value": value,
        "value_type": _value_type(value),
        "unit": attr_entry.get("unit"),
    }
    notes = attr_entry.get("uncertainty_notes")
    if notes:
        item["uncertainty"] = {"uncertainty_type": "range", "other_value": str(notes)}
    if attr_entry.get("notes"):
        item["note"] = attr_entry["notes"]
    return item


def _map_carriers(items, resolver, unresolved) -> list:
    out = []
    for it in items or []:
        name = it.get("carrier_name")
        cid = resolver.get(name)
        if cid is None and name is not None:
            unresolved["carrier"][name] += 1
        out.append({"carrier_id": cid, "share": it.get("share"), "unit": it.get("unit")})
    return out


# --- main mapping ------------------------------------------------------------

def map_entities(entities: list[dict], resolvers: dict, today: str):
    records = []
    unresolved = {k: Counter() for k in
                  ("tech", "source", "attr", "carrier", "orphan_attr",
                   "geographic_scope", "temporal_scope", "capacity_scope",
                   "system_boundary", "no_sources")}
    seq = 0

    for ent in entities:
        tech_name = ent.get("technology_name")
        tech_id = resolvers["tech_id"](tech_name)
        if tech_id is None:
            unresolved["tech"][tech_name] += 1

        scope_raw = ent.get("scope", {}) or {}
        scope = {}
        for field, table in (("geographic_scope", "geographic_scope"),
                             ("temporal_scope", "temporal_scope"),
                             ("capacity_scope", "capacity_scope"),
                             ("system_boundary", "system_boundary")):
            desc = scope_raw.get(f"{field}_description")
            sid = resolvers[table].get(str(desc)) if desc is not None else None
            if sid is None and desc not in (None, 0, "0"):
                unresolved[table][str(desc)] += 1
            scope[field] = sid

        balancing_raw = ent.get("balancing", {}) or {}
        balancing = {
            "inputs": _map_carriers(balancing_raw.get("inputs"), resolvers["carrier"], unresolved),
            "main_input": resolvers["carrier"].get(balancing_raw.get("main_input")),
            "outputs": _map_carriers(balancing_raw.get("outputs"), resolvers["carrier"], unresolved),
            "main_output": resolvers["carrier"].get(balancing_raw.get("main_output")),
        }
        if balancing_raw.get("balance_assumption"):
            balancing["balance_assumption"] = balancing_raw["balance_assumption"]

        attrs = ent.get("attributes", []) or []
        # attribute_name (cleaned, ATTR id, or raw) -> attribute entry
        by_key = {a.get("attribute_name"): a for a in attrs}
        claimed_keys: set = set()

        sources = ent.get("sources", []) or []
        if not sources:
            unresolved["no_sources"][tech_name] += 1

        for source in sources:
            sname = source.get("source_name")
            source_id = resolvers["source_id"].get(sname)
            if source_id is None:
                unresolved["source"][sname] += 1

            # raw linked attribute names -> ATTR ids -> attribute entries
            value_items = []
            for raw in source.get("linked_attribute", []) or []:
                if raw in NON_ATTRIBUTE_TOKENS:
                    continue                       # balancing share, not an attribute
                attr_id = resolvers["attr_raw2id"].get(raw)
                if attr_id is None:
                    unresolved["attr"][raw] += 1
                    continue
                cleaned = resolvers["attr_raw2cleaned"].get(raw)
                # entity may key attributes by cleaned name, ATTR id, or raw name
                key = next((k for k in (cleaned, attr_id, raw) if k in by_key), None)
                if key is None:
                    continue                       # source claims an attr the entity lacks
                claimed_keys.add(key)
                value_items.append(_build_value(by_key[key], attr_id))

            seq += 1
            records.append({
                "linked_entity_id": f"REC_{seq:05d}",
                "version": {"version_number": VERSION,
                            "date_created": today, "date_modified": today},
                "tech_id": tech_id,
                "source_id": source_id,
                "scope": scope,
                "values": value_items,
                "balancing": balancing,
                "_provenance": {"technology_name": tech_name, "source_name": sname},
            })

        # Attributes claimed by no source -> one null-source record per entity,
        # flagged for later source assignment (keeps all values, attribution honest).
        orphan_values = []
        for key, entry in by_key.items():
            if key in claimed_keys:
                continue
            attr_id = resolvers["attr_cleaned2id"].get(key, key)
            unresolved["orphan_attr"][attr_id] += 1
            orphan_values.append(_build_value(entry, attr_id))

        if orphan_values:
            seq += 1
            records.append({
                "linked_entity_id": f"REC_{seq:05d}",
                "version": {"version_number": VERSION,
                            "date_created": today, "date_modified": today},
                "tech_id": tech_id,
                "source_id": None,                 # unsourced; assign later
                "scope": scope,
                "values": orphan_values,
                "balancing": balancing,
                "_provenance": {"technology_name": tech_name, "source_name": None},
                "_unsourced": True,
            })

    return records, unresolved


def run(write: bool = True):
    entities = yaml.safe_load(UNMAPPED.read_text(encoding="utf-8"))
    resolvers = build_resolvers()
    today = datetime.date.today().isoformat()
    records, unresolved = map_entities(entities, resolvers, today)

    print(f"entities in: {len(entities)}  ->  linked records out: {len(records)}")
    print("\nunresolved / flags (top items):")
    for kind, counter in unresolved.items():
        if counter:
            total = sum(counter.values())
            print(f"  {kind:18s}: {total:3d}  e.g. {dict(list(counter.most_common(5)))}")

    if write:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "refuel.yaml").write_text(
            yaml.dump(records, sort_keys=False, allow_unicode=True), encoding="utf-8")
        report = {k: dict(v) for k, v in unresolved.items() if v}
        (OUT_DIR / "refuel_unresolved.yaml").write_text(
            yaml.dump(report, sort_keys=False, allow_unicode=True), encoding="utf-8")
        print(f"\nwrote {OUT_DIR / 'refuel.yaml'}")
        print(f"wrote {OUT_DIR / 'refuel_unresolved.yaml'}")

    return records, unresolved


if __name__ == "__main__":
    run(write=True)
