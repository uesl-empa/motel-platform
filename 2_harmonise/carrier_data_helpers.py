"""
Harmonisation logic for the carrier-bound track of the MOTEL workflow.

MOTEL's main track records data that belongs to a piece of hardware: an
``unmapped_entity`` staging record becomes a ``linked_entity`` anchored to a
``tech_id``. Energy prices and carbon intensities do not belong to hardware —
they belong to the energy carrier itself, and the same price applies to every
technology that consumes that carrier in the same region and year.

This module adds the symmetric carrier-bound track:

    unmapped_entity_carrier.yaml  ->  linked_entity_carrier.yaml
    (schema/unmapped_entity_carrier.yaml)  (schema/linked_entity_carrier.yaml)

anchored to a ``carrier_id`` instead of a ``tech_id``. Everything else is shared
with the technology track: the same carrier, source, attribute, and scope
registries, the same staging status lifecycle, and the same run log.

Two resolution modes are available:

- ``use_llm=True`` (default) reuses the Step 2 LLM resolvers from
  ``harmonise_helpers``, so free-text carrier and source labels are matched
  semantically. Requires a reachable Ollama service.
- ``use_llm=False`` resolves by exact (case- and whitespace-insensitive) name
  against the existing registries and creates deterministic new entries
  otherwise. Carrier data usually arrives from statistical agencies with
  already-clean labels, so this mode is often enough — and it lets the pipeline
  run in CI without a model.
"""

import csv
import datetime
import json
import re
import time
from pathlib import Path

import yaml

import harmonise_helpers as hh
from harmonise_helpers import (
    ATTR_COLS,
    ATTR_PATH,
    ENTITY_CONFIG,
    HARMONISATION_VERSION,
    LCD_PATH,
    MAPPING_DIR,
    SCOPE_CONFIG,
    _has_value,
    append_row,
    ensure_attr,
    ensure_scope,
    get_scope_description_context,
    get_scope_note_context,
    get_scope_value,
    load_all_schemas,
    load_pending_unmapped,
    load_registry,
    log_harmonisation_event,
    mark_unmapped_entities_mapped,
    resolve_entity,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Only carrier and source are resolved here. Technology and process are
# deliberately absent: a carrier data record describes a commodity, not an asset.
CARRIER_DATA_ENTITY_TYPES = ["carrier", "source"]

LCD_PREFIX = "LCD"
CARRIER_DATA_ID_FIELD = "linked_carrier_data_id"

# Token prefixes used when a scope value has to be created without the LLM.
SCOPE_TOKEN_PREFIX = {
    "geographic_scope": "GEO",
    "temporal_scope": "TIME",
    "capacity_scope": "CAP",
    "system_boundary": "BOUND",
}

# Allowed data_category values, mirroring the enum in schema/linked_entity_carrier.yaml.
DATA_CATEGORIES = [
    "price",
    "emission_intensity",
    "availability",
    "resource_potential",
    "demand",
    "other",
]

CARRIER_DATA_PROVENANCE_FILE = "unmapped_to_linked_carrier_data.csv"
CARRIER_DATA_ATTRIBUTE_MAP_FILE = "carrier_data_attribute_map.csv"

# Deterministic mode reads the unit from a note written as "Unit: EUR/kWh" or
# "Unit EUR/kWh". Only the first token is taken, matching the single-token unit
# convention used throughout the attribute controlled vocabulary.
_UNIT_IN_NOTES = re.compile(r"\bunits?\s*[:=]?\s+(\S+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Small shared utilities
# ---------------------------------------------------------------------------
def _norm(value):
    """Normalise a label for case- and whitespace-insensitive comparison."""
    return " ".join(str(value or "").split()).strip().lower()


def _slug(value, max_length=40):
    """
    Build an uppercase token fragment from a free-text scope value.

    Long values are cut back to the last complete word inside ``max_length`` so
    tokens stay readable instead of ending mid-word.
    """
    cleaned = re.sub(r"[^0-9A-Za-z]+", "_", str(value or "").strip()).strip("_").upper()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
        if "_" in cleaned:
            cleaned = cleaned.rsplit("_", 1)[0]
    return cleaned.strip("_") or "UNSPECIFIED"


def _unit_from_notes(notes):
    """Pull a unit out of an attribute note such as 'Unit: EUR/kWh'."""
    match = _UNIT_IN_NOTES.search(str(notes or ""))
    return match.group(1).strip().rstrip(".,;:|") if match else ""


def _next_free_id(prefix, taken, width=5):
    """Build the next unused sequential ID so appends never reuse an existing key."""
    number = len(taken) + 1
    while f"{prefix}_{number:0{width}d}" in taken:
        number += 1
    return f"{prefix}_{number:0{width}d}"


def _infer_value_type(value, time_index):
    """Classify a staged value so downstream solvers know how to read it."""
    if isinstance(value, (list, tuple)):
        return "timeseries" if time_index else "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "numeric"
    return "text"


def load_pending_carrier_data(path):
    """
    Load a carrier data staging file and select records that still need harmonisation.

    Thin alias over the shared staging loader so callers read the intent from the
    call site; the staging status lifecycle is identical for both tracks.
    """
    return load_pending_unmapped(path)


# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------
def collect_carrier_data_candidates(carrier_data_records):
    """
    Extract unique carrier and source candidates from staged carrier data records.

    Args:
        carrier_data_records (list[dict]): Records following unmapped_entity_carrier.yaml.

    Returns:
        dict[str, dict]: {entity_type: {name: candidate_dict}}
    """
    candidates = {entity_type: {} for entity_type in CARRIER_DATA_ENTITY_TYPES}

    for record in carrier_data_records:
        carrier_name = record.get("carrier_name")
        if carrier_name:
            carrier = record.get("carrier", {}) or {}
            existing = candidates["carrier"].setdefault(carrier_name, {})
            proposed = {
                "carrier_name": carrier_name,
                "carrier_description": carrier.get("carrier_description"),
                "carrier_type": carrier.get("carrier_type"),
                "carrier_category": carrier.get("carrier_category"),
                "note": carrier.get("carrier_notes"),
            }
            for field, value in proposed.items():
                if _has_value(value) and not _has_value(existing.get(field)):
                    existing[field] = value

        for source in record.get("sources", []) or []:
            source_name = source.get("source_name")
            if not source_name:
                continue
            existing = candidates["source"].setdefault(source_name, {})
            proposed = {
                "source_name": source_name,
                "source_description": source.get("source_description"),
                "source_type": source.get("source_type"),
                "link": source.get("link"),
                "access_date": source.get("access_date"),
                "confidence_level": source.get("confidence_level"),
                "assessment_method": source.get("assessment_method"),
                "reference_year": source.get("reference_year"),
                "note": " | ".join(
                    str(value).strip()
                    for value in [
                        source.get("note"),
                        source.get("source_notes"),
                        source.get("source_locator"),
                    ]
                    if _has_value(value)
                ),
            }
            for field, value in proposed.items():
                if _has_value(value) and not _has_value(existing.get(field)):
                    existing[field] = value

    return candidates


# ---------------------------------------------------------------------------
# Deterministic (no-LLM) resolvers
# ---------------------------------------------------------------------------
def _resolve_entity_exact(entity_type, candidate, registry):
    """
    Resolve a candidate against a registry by exact name, creating a row if absent.

    This is the ``use_llm=False`` counterpart of ``harmonise_helpers.resolve_entity``.

    Returns:
        tuple[str, str]: (resolved_id, status) with status "exact" or "created".
    """
    cfg = ENTITY_CONFIG[entity_type]
    id_field, name_field = cfg["id_field"], cfg["name_field"]
    candidate_name = _norm(candidate.get(name_field))

    for row in registry:
        if _norm(row.get(name_field)) == candidate_name:
            return row[id_field], "exact"

    new_id = _next_free_id(cfg["prefix"], {str(row.get(id_field, "")) for row in registry})
    new_row = {id_field: new_id}
    for key in cfg["cols"]:
        if key != id_field and _has_value(candidate.get(key)):
            new_row[key] = candidate[key]
    append_row(entity_type, new_row)
    registry.append(new_row)
    return new_id, "created"


def _ensure_attr_exact(name, registry, notes="", applies_to="carrier"):
    """
    Resolve an attribute by exact name, creating a registry row if absent.

    This is the ``use_llm=False`` counterpart of ``harmonise_helpers.ensure_attr``.
    The canonical name is taken as given, and the unit is read from the staging
    note when it is written as ``Unit: <unit>``.

    Args:
        name (str): Attribute name from the staging record.
        registry (dict[str, str]): In-memory {name: id} mapping; mutated on creation.
        notes (str): Raw attribute_notes string from the staging record.
        applies_to (str): Subject class recorded on newly created rows.

    Returns:
        tuple[str, str, str]: (attribute_id, canonical_name, status).
    """
    canonical_name = " ".join(str(name).split()).strip()
    for existing_name, existing_id in registry.items():
        if _norm(existing_name) == _norm(canonical_name):
            return existing_id, existing_name, "existing"

    new_id = _next_free_id("ATTR", set(registry.values()))
    new_row = {
        "attribute_id": new_id,
        "attribute_name": canonical_name,
        "attribute_description": str(notes or "").strip(),
        "unit": _unit_from_notes(notes),
        "data_format": "float",
        "applies_to": applies_to,
    }
    registry[canonical_name] = new_id
    Path(ATTR_PATH).parent.mkdir(parents=True, exist_ok=True)
    file_exists = Path(ATTR_PATH).exists()
    with open(ATTR_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ATTR_COLS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({key: new_row.get(key, "") for key in ATTR_COLS})
    return new_id, canonical_name, "created"


def _ensure_scope_exact(scope_type, value, description_seed="", extra_context=""):
    """
    Resolve a scope value against its CSV by token or description, creating it if absent.

    This is the ``use_llm=False`` counterpart of ``harmonise_helpers.ensure_scope``.
    Staging records that already carry a canonical token (``GEO_CHE``) match it
    directly; free-text values are matched against existing descriptions and
    otherwise become ``<PREFIX>_<SLUG>``.

    Returns:
        tuple[str | None, str | None]: (scope_token, status) or (None, None) when empty.
    """
    if not _has_value(value):
        return None, None

    raw_value = str(value).strip()
    path = Path(SCOPE_CONFIG[scope_type])
    description_field = f"{scope_type}_description"
    seeded_description = description_seed or raw_value

    existing_rows = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            existing_rows = list(csv.DictReader(f))

    for row in existing_rows:
        token = str(row.get(scope_type, "")).strip()
        if _norm(token) == _norm(raw_value):
            return token, "existing"
        if _norm(row.get(description_field)) == _norm(raw_value):
            return token, "existing"

    prefix = SCOPE_TOKEN_PREFIX[scope_type]
    token = raw_value if raw_value.upper().startswith(f"{prefix}_") else f"{prefix}_{_slug(raw_value)}"
    if any(_norm(row.get(scope_type)) == _norm(token) for row in existing_rows):
        return token, "existing"

    cols = [scope_type, description_field, "note"]
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            scope_type: token,
            description_field: seeded_description,
            "note": extra_context or "",
        })
    return token, "created"


# ---------------------------------------------------------------------------
# Step 1 — resolve carrier and source
# ---------------------------------------------------------------------------
def resolve_carrier_data_entities_step(
    candidates,
    all_schemas,
    use_llm=True,
    harmonisation_log=None,
):
    """
    Resolve carrier and source candidates against the shared MOTEL registries.

    Args:
        candidates (dict): Output of ``collect_carrier_data_candidates``.
        all_schemas (dict): Loaded schema definitions keyed by filename.
        use_llm (bool): Use the LLM resolvers from Step 2 when True.
        harmonisation_log (Path | None): Run log to append events to.

    Returns:
        dict: {"resolved_ids": {...}, "resolution_status": {...}, "counts": {...}}
    """
    step_started = time.perf_counter()
    registries = {et: load_registry(et) for et in CARRIER_DATA_ENTITY_TYPES}
    resolved_ids = {et: {} for et in CARRIER_DATA_ENTITY_TYPES}
    resolution_status = {et: {} for et in CARRIER_DATA_ENTITY_TYPES}
    counts_by_type = {}
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)

    for entity_type in CARRIER_DATA_ENTITY_TYPES:
        entity_candidates = candidates.get(entity_type, {})
        print(f"\nResolving {entity_type} ({len(entity_candidates)} unique values)...")
        registry = registries[entity_type]
        counts = {"exact": 0, "llm": 0, "created": 0}

        for name, candidate in entity_candidates.items():
            if use_llm:
                resolved_id, status = resolve_entity(
                    entity_type, candidate, registry, all_schemas
                )
            else:
                resolved_id, status = _resolve_entity_exact(
                    entity_type, candidate, registry
                )
            resolved_ids[entity_type][name] = resolved_id
            resolution_status[entity_type][name] = status
            counts[status] += 1
            marker = "+" if status == "created" else "="
            print(f"  {marker} {entity_type}: {name!r} -> {resolved_id}  [{status}]")

        counts_by_type[entity_type] = counts
        print(
            f"{entity_type} — total: {sum(counts.values())}  |  "
            f"exact: {counts['exact']}  |  llm: {counts['llm']}  |  created: {counts['created']}"
        )

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "carrier_data_step_1",
            "entities_resolved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            use_llm=use_llm,
            counts_by_type=counts_by_type,
        )

    return {
        "resolved_ids": resolved_ids,
        "resolution_status": resolution_status,
        "counts_by_type": counts_by_type,
    }


# ---------------------------------------------------------------------------
# Step 2 — resolve attributes and scope tokens
# ---------------------------------------------------------------------------
def resolve_carrier_data_vocabulary_step(
    all_schemas,
    carrier_data_records,
    use_llm=True,
    harmonisation_log=None,
):
    """
    Resolve attribute names and scope values used by staged carrier data records.

    The attribute registry is shared with the technology track and is appended to,
    never rebuilt, so carrier metrics and technology metrics live in one vocabulary
    and are told apart by the ``applies_to`` column.

    Returns:
        dict: attribute and scope lookups plus per-status counts.
    """
    step_started = time.perf_counter()
    attr_schema = all_schemas.get("attribute.yaml", {})

    attr_registry = {}
    if Path(ATTR_PATH).exists():
        with open(ATTR_PATH, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("attribute_name"):
                    attr_registry[row["attribute_name"]] = row["attribute_id"]

    attr_ids, attr_names, attr_status, attr_units = {}, {}, {}, {}
    scope_ids = {}
    attr_counts = {"existing": 0, "created": 0}
    scope_counts = {"existing": 0, "created": 0}

    unique_attributes = []
    seen_attribute_names = set()
    for record in carrier_data_records:
        for attribute in record.get("attributes", []) or []:
            name = attribute.get("attribute_name")
            if name and name not in seen_attribute_names:
                unique_attributes.append((name, attribute))
                seen_attribute_names.add(name)

    print(f"Resolving carrier attributes ({len(unique_attributes)} unique values)...")
    for index, (name, attribute) in enumerate(unique_attributes, start=1):
        notes = attribute.get("attribute_notes") or attribute.get("notes", "")
        print(f"  [{index}/{len(unique_attributes)}] resolving attribute: {name!r}")
        if use_llm:
            attribute_id, canonical_name, status = ensure_attr(
                name,
                registry=attr_registry,
                notes=notes,
                attr_schema=attr_schema,
                applies_to="carrier",
            )
        else:
            attribute_id, canonical_name, status = _ensure_attr_exact(
                name, registry=attr_registry, notes=notes, applies_to="carrier"
            )
        attr_ids[name] = attribute_id
        attr_names[name] = canonical_name
        attr_status[name] = status
        attr_counts[status] += 1
        if status == "created":
            print(f"  + attribute: {name!r} -> {canonical_name!r}  [{attribute_id}]")

    attr_units = _load_attribute_units()

    unique_scopes = []
    seen_scope_keys = set()
    for record in carrier_data_records:
        scope = record.get("scope", {}) or {}
        for scope_type in SCOPE_CONFIG:
            value = get_scope_value(scope, scope_type)
            description = get_scope_description_context(scope, scope_type)
            context = get_scope_note_context(scope, scope_type)
            key = (scope_type, value, description, context)
            if value and key not in seen_scope_keys:
                unique_scopes.append(key)
                seen_scope_keys.add(key)

    print(f"Resolving scope tokens ({len(unique_scopes)} unique values)...")
    for index, (scope_type, value, description, context) in enumerate(unique_scopes, start=1):
        print(f"  [{index}/{len(unique_scopes)}] resolving {scope_type}: {value!r}")
        if use_llm:
            token, status = ensure_scope(
                scope_type,
                value,
                scope_schema=all_schemas.get(f"{scope_type}.yaml", {}),
                description_seed=description,
                extra_context=context,
            )
        else:
            token, status = _ensure_scope_exact(
                scope_type,
                value,
                description_seed=description,
                extra_context=context,
            )
        scope_ids[(scope_type, value)] = token
        if status:
            scope_counts[status] += 1
            if status == "created":
                print(f"  + {scope_type}: {value!r} -> {token!r}")

    print(
        f"Attributes   — total: {sum(attr_counts.values())}  |  "
        f"existing: {attr_counts['existing']}  |  created: {attr_counts['created']}"
    )
    print(
        f"Scope tokens — total: {sum(scope_counts.values())}  |  "
        f"existing: {scope_counts['existing']}  |  created: {scope_counts['created']}"
    )

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "carrier_data_step_2",
            "controlled_vocabulary_resolved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            use_llm=use_llm,
            attribute_counts=attr_counts,
            scope_counts=scope_counts,
            attribute_path=str(Path(ATTR_PATH).resolve()),
        )

    return {
        "attr_ids": attr_ids,
        "attr_names": attr_names,
        "attr_status": attr_status,
        "attr_units": attr_units,
        "scope_ids": scope_ids,
        "attr_counts": attr_counts,
        "scope_counts": scope_counts,
    }


def _load_attribute_units():
    """Return {attribute_id: canonical unit} from the attribute controlled vocabulary."""
    if not Path(ATTR_PATH).exists():
        return {}
    with open(ATTR_PATH, encoding="utf-8-sig", newline="") as f:
        return {
            row["attribute_id"]: (row.get("unit") or "").strip()
            for row in csv.DictReader(f)
            if row.get("attribute_id")
        }


# ---------------------------------------------------------------------------
# Step 3 — build and save linked carrier data
# ---------------------------------------------------------------------------
def build_and_save_linked_carrier_data(
    pending_records,
    pending_indices,
    all_records,
    unmapped_path,
    resolved_ids,
    attr_ids,
    attr_names,
    attr_units,
    scope_ids,
    linked_carrier_data_path=LCD_PATH,
    harmonisation_log=None,
):
    """
    Build linked carrier data records, save them, and mark the staging records mapped.

    Mirrors ``harmonise_helpers.build_and_save_linked_entities`` for the
    carrier-bound track: existing records are preserved and new IDs continue the
    ``LCD_#####`` sequence.

    Returns:
        dict: {"linked_carrier_data": [...], "existing_records": [...], "today": str}
    """
    step_started = time.perf_counter()
    today = str(datetime.date.today())
    lcd_path = Path(linked_carrier_data_path)

    if lcd_path.exists():
        with open(lcd_path, "r", encoding="utf-8") as f:
            existing_records = yaml.safe_load(f) or []
    else:
        existing_records = []

    existing_numbers = [
        int(str(record[CARRIER_DATA_ID_FIELD]).split("_")[-1])
        for record in existing_records
        if str(record.get(CARRIER_DATA_ID_FIELD, "")).startswith(f"{LCD_PREFIX}_")
    ]
    next_number = max(existing_numbers, default=0) + 1

    linked_carrier_data = []
    for offset, record in enumerate(pending_records):
        scope = record.get("scope", {}) or {}
        carrier_name = record.get("carrier_name")

        values = []
        for attribute in record.get("attributes", []) or []:
            attribute_name = attribute.get("attribute_name")
            if not attribute_name:
                continue
            attribute_id = attr_ids.get(attribute_name, "")
            value = attribute.get("value")
            time_index = attribute.get("time_index")
            entry = {
                "attribute_id": attribute_id,
                "attribute_name": attr_names.get(attribute_name, attribute_name),
                "value": value,
                "value_type": _infer_value_type(value, time_index),
                "unit": attr_units.get(attribute_id, ""),
            }
            if time_index:
                entry["time_index"] = time_index
            if _has_value(attribute.get("uncertainty_notes")):
                entry["uncertainty"] = {
                    "uncertainty_assumption": attribute["uncertainty_notes"],
                }
            if _has_value(attribute.get("attribute_notes")):
                entry["note"] = attribute["attribute_notes"]
            values.append(entry)

        linked_carrier_data.append({
            CARRIER_DATA_ID_FIELD: f"{LCD_PREFIX}_{next_number + offset:05d}",
            "version": {
                "version_number": HARMONISATION_VERSION,
                "date_created": today,
            },
            "carrier_id": resolved_ids.get("carrier", {}).get(carrier_name, ""),
            "data_category": record.get("data_category", "other"),
            "scope": {
                scope_type: (
                    scope_ids.get((scope_type, get_scope_value(scope, scope_type)))
                    or scope.get(scope_type)
                    or ""
                )
                for scope_type in SCOPE_CONFIG
            } | {"scenario": scope.get("scenario", "")},
            "sources": [
                {
                    "source_id": resolved_ids.get("source", {}).get(source["source_name"], ""),
                    "linked_attributes": [
                        attr_ids.get(attribute_name) or f"[unregistered: {attribute_name}]"
                        for attribute_name in source.get("linked_attribute", [])
                    ],
                }
                for source in record.get("sources", []) or []
                if source.get("source_name")
            ],
            "values": values,
            "date_created": today,
        })

    all_linked = existing_records + linked_carrier_data
    lcd_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = lcd_path.with_suffix(lcd_path.suffix + ".tmp")
    with open(temporary_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(all_linked, f, allow_unicode=True, sort_keys=False)
    temporary_path.replace(lcd_path)

    mark_unmapped_entities_mapped(
        unmapped_path,
        all_records,
        pending_indices,
        linked_carrier_data,
        today,
        id_field=CARRIER_DATA_ID_FIELD,
    )

    print(f"Saved {len(linked_carrier_data)} new carrier data records -> {lcd_path}")
    for record in linked_carrier_data:
        print(
            f"  {record[CARRIER_DATA_ID_FIELD]}  "
            f"carrier={record['carrier_id']}  "
            f"category={record['data_category']}  "
            f"scope={record['scope']}"
        )

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "carrier_data_step_3",
            "linked_carrier_data_saved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            created_count=len(linked_carrier_data),
            preserved_count=len(existing_records),
            output_path=str(lcd_path.resolve()),
            linked_carrier_data_ids=[r[CARRIER_DATA_ID_FIELD] for r in linked_carrier_data],
        )

    return {
        "linked_carrier_data": linked_carrier_data,
        "existing_records": existing_records,
        "today": today,
    }


# ---------------------------------------------------------------------------
# Step 4 — provenance and lookup maps
# ---------------------------------------------------------------------------
def save_carrier_data_mapping_files_step(
    pending_records,
    pending_indices,
    linked_carrier_data,
    today,
    attr_ids,
    attr_names,
    attr_status,
    harmonisation_log=None,
):
    """
    Write the carrier data provenance map and attribute lookup map.

    These are separate files from the technology-track maps so a carrier data run
    never overwrites provenance produced by a technology run.
    """
    step_started = time.perf_counter()
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)

    provenance_path = MAPPING_DIR / CARRIER_DATA_PROVENANCE_FILE
    provenance_cols = [
        "unmapped_index", "carrier_name",
        CARRIER_DATA_ID_FIELD, "carrier_id", "data_category",
        "geographic_scope", "temporal_scope", "capacity_scope", "system_boundary",
        "scenario", "source_ids", "date_mapped",
    ]
    with open(provenance_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=provenance_cols)
        writer.writeheader()
        for source_index, record, linked in zip(pending_indices, pending_records, linked_carrier_data):
            scope = linked.get("scope", {})
            writer.writerow({
                "unmapped_index": source_index,
                "carrier_name": record.get("carrier_name", ""),
                CARRIER_DATA_ID_FIELD: linked[CARRIER_DATA_ID_FIELD],
                "carrier_id": linked["carrier_id"],
                "data_category": linked.get("data_category", ""),
                "geographic_scope": scope.get("geographic_scope", ""),
                "temporal_scope": scope.get("temporal_scope", ""),
                "capacity_scope": scope.get("capacity_scope", ""),
                "system_boundary": scope.get("system_boundary", ""),
                "scenario": scope.get("scenario", ""),
                "source_ids": json.dumps([s["source_id"] for s in linked.get("sources", [])]),
                "date_mapped": today,
            })
    print(f"Provenance map: saved {len(linked_carrier_data)} rows -> {provenance_path}")

    attribute_map_path = MAPPING_DIR / CARRIER_DATA_ATTRIBUTE_MAP_FILE
    with open(attribute_map_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["original_name", "attribute_name", "attribute_id", "status"]
        )
        writer.writeheader()
        for name, attribute_id in attr_ids.items():
            writer.writerow({
                "original_name": name,
                "attribute_name": attr_names.get(name, name),
                "attribute_id": attribute_id,
                "status": attr_status.get(name, "created"),
            })
    print(f"Entity lookup map: {CARRIER_DATA_ATTRIBUTE_MAP_FILE}  ({len(attr_ids)} rows)")

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "carrier_data_step_4",
            "mapping_files_saved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            provenance_rows=len(linked_carrier_data),
            provenance_path=str(provenance_path.resolve()),
            attribute_map_path=str(attribute_map_path.resolve()),
        )

    return {
        "provenance_path": provenance_path,
        "attribute_map_path": attribute_map_path,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_carrier_data_harmonisation(
    unmapped_carrier_data_path,
    schema_dir="../schema/",
    linked_carrier_data_path=LCD_PATH,
    use_llm=True,
    test_limit=None,
    set_all_unmapped_to_pending=False,
    harmonisation_log=None,
):
    """
    Run the full carrier data harmonisation for one staging file.

    Args:
        unmapped_carrier_data_path (str | Path): Staging YAML following
            ``schema/unmapped_entity_carrier.yaml``.
        schema_dir (str): Directory holding the MOTEL schemas.
        linked_carrier_data_path (str | Path): Output YAML to append to.
        use_llm (bool): Resolve names with the LLM (True) or by exact match (False).
        test_limit (int | None): Process only the first N pending records.
        set_all_unmapped_to_pending (bool): Reset every staging record to pending
            before running, for a clean re-run.
        harmonisation_log (Path | None): Existing run log to append events to.

    Returns:
        dict: Results of every step plus the records written.
    """
    run_started = time.perf_counter()
    unmapped_carrier_data_path = Path(unmapped_carrier_data_path)
    all_schemas = load_all_schemas(schema_dir)

    if set_all_unmapped_to_pending:
        all_records, _, _ = load_pending_carrier_data(unmapped_carrier_data_path)
        hh.mark_all_unmapped_entities_pending(unmapped_carrier_data_path, all_records)

    all_records, pending_records, pending_indices = load_pending_carrier_data(
        unmapped_carrier_data_path
    )
    if test_limit is not None:
        pending_records = pending_records[:test_limit]
        pending_indices = pending_indices[:test_limit]

    print(
        f"Carrier data harmonisation — staged: {len(all_records)}  |  "
        f"pending: {len(pending_records)}  |  use_llm: {use_llm}"
    )
    if not pending_records:
        print("Nothing to harmonise; all staged carrier data records are already mapped.")
        return {"linked_carrier_data": [], "pending_records": []}

    candidates = collect_carrier_data_candidates(pending_records)
    entity_result = resolve_carrier_data_entities_step(
        candidates, all_schemas, use_llm=use_llm, harmonisation_log=harmonisation_log
    )
    vocabulary_result = resolve_carrier_data_vocabulary_step(
        all_schemas, pending_records, use_llm=use_llm, harmonisation_log=harmonisation_log
    )
    build_result = build_and_save_linked_carrier_data(
        pending_records,
        pending_indices,
        all_records,
        unmapped_carrier_data_path,
        entity_result["resolved_ids"],
        vocabulary_result["attr_ids"],
        vocabulary_result["attr_names"],
        vocabulary_result["attr_units"],
        vocabulary_result["scope_ids"],
        linked_carrier_data_path=linked_carrier_data_path,
        harmonisation_log=harmonisation_log,
    )
    mapping_result = save_carrier_data_mapping_files_step(
        pending_records,
        pending_indices,
        build_result["linked_carrier_data"],
        build_result["today"],
        vocabulary_result["attr_ids"],
        vocabulary_result["attr_names"],
        vocabulary_result["attr_status"],
        harmonisation_log=harmonisation_log,
    )

    duration = round(time.perf_counter() - run_started, 3)
    print(f"\nCarrier data harmonisation finished in {duration}s")
    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "carrier_data_run",
            "finished",
            duration_seconds=duration,
            use_llm=use_llm,
            records_created=len(build_result["linked_carrier_data"]),
        )

    return {
        "pending_records": pending_records,
        "pending_indices": pending_indices,
        "entities": entity_result,
        "vocabulary": vocabulary_result,
        "linked_carrier_data": build_result["linked_carrier_data"],
        "mapping": mapping_result,
        "duration_seconds": duration,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_linked_carrier_data(
    linked_carrier_data_path=LCD_PATH,
    database_dir="../motel-db/",
):
    """
    Check saved carrier data records for missing required fields and broken foreign keys.

    MOTEL has no JSON Schema validator dependency, so this performs the same
    lightweight checks the rest of the workflow relies on: required fields present,
    and every ID actually resolvable in the registry it points at.

    Returns:
        list[str]: Human-readable problems; empty when the file is consistent.
    """
    database_dir = Path(database_dir)
    lcd_path = Path(linked_carrier_data_path)
    if not lcd_path.exists():
        return [f"{lcd_path} does not exist"]

    with open(lcd_path, encoding="utf-8") as f:
        records = yaml.safe_load(f) or []

    def load_ids(path, column):
        if not path.exists():
            return set()
        with path.open(encoding="utf-8-sig", newline="") as f:
            return {row[column].strip() for row in csv.DictReader(f) if row.get(column)}

    carrier_ids = load_ids(database_dir / "controlled_vocabulary" / "carrier.csv", "carrier_id")
    source_ids = load_ids(database_dir / "secondary" / "source.csv", "source_id")
    attribute_ids = load_ids(database_dir / "controlled_vocabulary" / "attribute.csv", "attribute_id")
    scope_tokens = {
        scope_type: load_ids(Path(path), scope_type)
        for scope_type, path in SCOPE_CONFIG.items()
    }

    problems = []
    seen_ids = set()
    for record in records:
        record_id = record.get(CARRIER_DATA_ID_FIELD, "<missing id>")
        if not record.get(CARRIER_DATA_ID_FIELD):
            problems.append("record without linked_carrier_data_id")
        elif record_id in seen_ids:
            problems.append(f"{record_id}: duplicate linked_carrier_data_id")
        seen_ids.add(record_id)

        carrier_id = record.get("carrier_id", "")
        if not carrier_id:
            problems.append(f"{record_id}: missing carrier_id")
        elif carrier_ids and carrier_id not in carrier_ids:
            problems.append(f"{record_id}: unknown carrier_id {carrier_id!r}")

        category = record.get("data_category")
        if category and category not in DATA_CATEGORIES:
            problems.append(f"{record_id}: data_category {category!r} is not in {DATA_CATEGORIES}")

        if not record.get("sources"):
            problems.append(f"{record_id}: no sources recorded")
        for source in record.get("sources", []) or []:
            source_id = source.get("source_id", "")
            if source_ids and source_id not in source_ids:
                problems.append(f"{record_id}: unknown source_id {source_id!r}")
            for attribute_id in source.get("linked_attributes", []) or []:
                if attribute_ids and attribute_id not in attribute_ids:
                    problems.append(
                        f"{record_id}: source {source_id} links unknown attribute {attribute_id!r}"
                    )

        for scope_type, tokens in scope_tokens.items():
            token = (record.get("scope", {}) or {}).get(scope_type, "")
            if token and tokens and token not in tokens:
                problems.append(f"{record_id}: unknown {scope_type} {token!r}")

        for entry in record.get("values", []) or []:
            attribute_id = entry.get("attribute_id", "")
            if not attribute_id:
                problems.append(f"{record_id}: value without attribute_id")
            elif attribute_ids and attribute_id not in attribute_ids:
                problems.append(f"{record_id}: unknown attribute_id {attribute_id!r}")
            value = entry.get("value")
            time_index = entry.get("time_index")
            if isinstance(value, list) and time_index and len(value) != len(time_index):
                problems.append(
                    f"{record_id}: attribute {attribute_id} has {len(value)} values "
                    f"but {len(time_index)} time_index entries"
                )

    return problems
