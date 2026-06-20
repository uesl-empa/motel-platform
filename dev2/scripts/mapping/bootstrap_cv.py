"""Bootstrap controlled-vocabulary CSVs from unmapped entities.

The five controlled-vocabulary tables (carrier, geographic_scope,
temporal_scope, capacity_scope, system_boundary) start empty. This module
scans the unmapped_entity YAML, collects every distinct scope description and
balancing carrier, mints a candidate id token for each, and writes schema-
correct rows into the CV CSVs for a human to curate (descriptions are filled;
the remaining columns are left blank).

It is additive and idempotent: existing rows (matched on description / name)
are preserved and never duplicated, so it can be re-run as new data arrives.

Usage:
    python scripts/mapping/bootstrap_cv.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

# --- paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]          # dev2/
UNMAPPED = ROOT / "motel-db" / "unmapped_entity" / "refuel.yaml"
CV_DIR = ROOT / "motel-db" / "controlled_vocabulary"

# Column layout per CV table, taken from motel_schema_rev2.yaml.
CV_COLUMNS = {
    "carrier": ["carrier_id", "carrier_name", "carrier_description",
                "carrier_type", "carrier_category", "carrier_reference",
                "carrier_note"],
    "geographic_scope": ["geographic_scope", "geographic_scope_description"],
    "temporal_scope": ["temporal_scope", "temporal_scope_description"],
    "capacity_scope": ["capacity_scope", "capacity_scope_description"],
    "system_boundary": ["system_boundary", "system_boundary_description"],
}

# Per-table id prefix and the column that carries the human description.
CV_META = {
    "carrier": ("CARRIER", "carrier_name", "carrier_id"),
    "geographic_scope": ("GEO", "geographic_scope_description", "geographic_scope"),
    "temporal_scope": ("TIME", "temporal_scope_description", "temporal_scope"),
    "capacity_scope": ("CAP", "capacity_scope_description", "capacity_scope"),
    "system_boundary": ("BOUND", "system_boundary_description", "system_boundary"),
}


def _slug(value: str) -> str:
    """Uppercase alphanumeric token usable in an id (e.g. 'Plant ready' -> PLANT_READY)."""
    token = re.sub(r"[^0-9A-Za-z]+", "_", str(value).strip()).strip("_").upper()
    return token or "UNSPECIFIED"


def _is_blank(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "nan", "none", "0", "na", "n/a"}


def collect_terms(entities: list[dict]) -> dict[str, list[str]]:
    """Return distinct raw descriptions/carriers per CV table (blanks dropped)."""
    found: dict[str, list[str]] = {k: [] for k in CV_COLUMNS}
    seen: dict[str, set] = {k: set() for k in CV_COLUMNS}

    def add(table: str, value) -> None:
        if _is_blank(value):
            return
        key = str(value).strip()
        if key not in seen[table]:
            seen[table].add(key)
            found[table].append(key)

    for ent in entities:
        scope = ent.get("scope", {}) or {}
        add("geographic_scope", scope.get("geographic_scope_description"))
        add("temporal_scope", scope.get("temporal_scope_description"))
        add("capacity_scope", scope.get("capacity_scope_description"))
        add("system_boundary", scope.get("system_boundary_description"))

        balancing = ent.get("balancing", {}) or {}
        for side in ("inputs", "outputs"):
            for item in balancing.get(side, []) or []:
                add("carrier", item.get("carrier_name"))

    return found


def _load_existing(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame(columns=columns)


def bootstrap(write: bool = True) -> dict[str, pd.DataFrame]:
    entities = yaml.safe_load(UNMAPPED.read_text(encoding="utf-8"))
    terms = collect_terms(entities)
    tables: dict[str, pd.DataFrame] = {}

    for table, columns in CV_COLUMNS.items():
        prefix, desc_col, id_col = CV_META[table]
        existing = _load_existing(CV_DIR / f"{table}.csv", columns)
        known_desc = set(existing[desc_col].astype(str)) if desc_col in existing else set()
        known_ids = set(existing[id_col].astype(str)) if id_col in existing else set()

        new_rows = []
        for term in terms[table]:
            if term in known_desc:
                continue
            candidate = f"{prefix}_{_slug(term)}"
            token, n = candidate, 2
            while token in known_ids:            # guarantee unique id
                token, n = f"{candidate}_{n}", n + 1
            known_ids.add(token)
            row = {c: "" for c in columns}
            row[id_col] = token
            row[desc_col] = term
            if table == "carrier":               # carrier_name == raw token too
                row["carrier_name"] = term
            new_rows.append(row)

        merged = pd.concat([existing, pd.DataFrame(new_rows, columns=columns)],
                           ignore_index=True)
        tables[table] = merged
        print(f"{table:18s}: {len(existing):3d} existing + {len(new_rows):3d} new "
              f"= {len(merged):3d} rows")

        if write:
            (CV_DIR / f"{table}.csv").write_text(
                merged.to_csv(index=False), encoding="utf-8")

    return tables


if __name__ == "__main__":
    bootstrap(write=True)
