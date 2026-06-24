"""
harmonise_helpers.py
Helper functions for the data harmonisation pipeline.

Covers:
- Entity config and registry I/O
- LLM-based field filling and schema validation
- Entity resolution (exact → LLM → create)
- Attribute and scope controlled-vocabulary resolution
- Candidate collection from unmapped entities
- Audit report generation
- Reset / clean-up of all derived (non-source) data files
"""

import csv
import json
import re
import shutil
from pathlib import Path

import ollama
import yaml

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
MODEL = "qwen3:14b"

# ---------------------------------------------------------------------------
# Global controlled-vocabulary context for all LLM calls.
# Set this from the notebook before running harmonisation, e.g.:
#   hh.GLOBAL_CV_CONTEXT = build_cv_context(df_nomenclature, df_carrier)
# ---------------------------------------------------------------------------
GLOBAL_CV_CONTEXT = ""

# ---------------------------------------------------------------------------
# Entity configuration
# ---------------------------------------------------------------------------
ENTITY_CONFIG = {
    "technology": {
        "path": "../motel-db/secondary/technology.csv",
        "id_field": "tech_id", "prefix": "TECH", "name_field": "technology_name",
        "cols": ["tech_id", "technology_name", "technology_type", "technology_category", "technology_description"],
        "schema_key": "technology.yaml",
    },
    "process": {
        "path": "../motel-db/secondary/process.csv",
        "id_field": "process_id", "prefix": "PROC", "name_field": "process_name",
        "cols": ["process_id", "process_name", "process_type", "process_category", "process_description"],
        "schema_key": "process.yaml",
    },
    "source": {
        "path": "../motel-db/secondary/source.csv",
        "id_field": "source_id", "prefix": "SRC", "name_field": "source_name",
        "cols": ["source_id", "source_name", "source_description", "source_type"],
        "schema_key": "source.yaml",
    },
    "carrier": {
        "path": "../motel-db/controlled_vocabulary/carrier.csv",
        "id_field": "carrier_id", "prefix": "CAR", "name_field": "carrier_name",
        "cols": ["carrier_id", "carrier_name", "carrier_description", "carrier_type", "carrier_category"],
        "schema_key": "carrier.yaml",
    },
}

SCOPE_CONFIG = {
    "geographic_scope": "../motel-db/controlled_vocabulary/geographic_scope.csv",
    "temporal_scope":   "../motel-db/controlled_vocabulary/temporal_scope.csv",
    "capacity_scope":   "../motel-db/controlled_vocabulary/capacity_scope.csv",
    "system_boundary":  "../motel-db/controlled_vocabulary/system_boundary.csv",
}

ATTR_PATH = "../motel-db/controlled_vocabulary/attribute.csv"
# All properties from attribute.yaml (required + optional)
ATTR_COLS = ["attribute_id", "attribute_name", "attribute_description", "unit", "data_format", "ontology_iri", "note"]

LE_PATH = "../motel-db/linked_entity/linked_entity.yaml"
# linked_entity uses YAML (not CSV) because its schema is deeply nested —
# sources, balancing, and values are arrays/objects that don't flatten cleanly into columns.

MAPPING_DIR = Path("../motel-db/mapping")

SUPPLEMENTARY_PATHS = [
    Path("../motel-db/supplementary/contributor.csv"),
    Path("../motel-db/supplementary/review.csv"),
]

# Flat-schema files: path -> schema filename.
# These schemas have only scalar top-level properties so columns can be derived
# directly from schema["properties"].keys(). linked_entity is excluded (nested schema).
FLAT_FILE_SCHEMA_MAP = {
    # Controlled vocabulary
    ATTR_PATH: "attribute.yaml",
    **{p: f"{st}.yaml" for st, p in SCOPE_CONFIG.items()},
    # Entity registries
    **{cfg["path"]: cfg["schema_key"] for cfg in ENTITY_CONFIG.values()},
}

# ---------------------------------------------------------------------------
# Schema loader
# ---------------------------------------------------------------------------
def load_all_schemas(base_dir="../schema/"):
    """Recursively load all YAML schema files into a {filename: schema} dict."""
    schemas = {}
    for p in Path(base_dir).rglob("*.yaml"):
        with open(p, encoding="utf-8") as f:
            schemas[p.name] = yaml.safe_load(f)
    return schemas

# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------
def load_registry(entity_type):
    """
    Load all rows from the CSV registry for the given entity type.

    Args:
        entity_type (str): Key in ENTITY_CONFIG (e.g. "technology").

    Returns:
        list[dict]: Rows as dicts; empty list if the file does not exist.
    """
    path = ENTITY_CONFIG[entity_type]["path"]
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_row(entity_type, row):
    """
    Append one row to the CSV for the given entity type, creating the file if needed.

    Args:
        entity_type (str): Key in ENTITY_CONFIG.
        row (dict): Values keyed by column name.
    """
    cfg = ENTITY_CONFIG[entity_type]
    Path(cfg["path"]).parent.mkdir(parents=True, exist_ok=True)
    file_exists = Path(cfg["path"]).exists()
    with open(cfg["path"], "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cfg["cols"])
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in cfg["cols"]})


def load_attr_registry():
    """
    Load the attribute registry as a {attribute_name: attribute_id} dict.

    Returns:
        dict[str, str]: Empty dict if the file does not exist.
    """
    if not Path(ATTR_PATH).exists():
        return {}
    with open(ATTR_PATH, encoding="utf-8") as f:
        return {r["attribute_name"]: r["attribute_id"] for r in csv.DictReader(f)}

# ---------------------------------------------------------------------------
# LLM field filling and schema validation
# ---------------------------------------------------------------------------
def llm_fill_fields(row, schema, extra_context=""):
    """
    Fill missing required fields in `row` using the LLM and the schema definition.

    Only fields that are empty in `row` and listed in `schema["required"]` are
    sent to the LLM. Existing non-empty values are never overwritten.

    Args:
        row (dict): Current field values for the entity being created.
        schema (dict): JSON Schema with "required" and "properties".
        extra_context (str): Additional free-text context (e.g. attribute notes)
            to help the LLM infer values.

    Returns:
        dict: The row with missing required fields populated where possible.
    """
    required = schema.get("required", [])
    missing = [f for f in required if not str(row.get(f, "")).strip()]
    if not missing:
        return row

    props = schema.get("properties", {})
    field_hints = {f: props[f].get("description", "") for f in missing if f in props}
    enum_hints  = {f: props[f]["enum"] for f in missing if f in props and "enum" in props[f]}

    prompt = (
        f"You are filling in missing fields for a new database row.\n\n"
        f"Known values:\n{json.dumps({k: v for k, v in row.items() if v}, indent=2)}\n\n"
        + (f"Additional context:\n{extra_context}\n\n" if extra_context else "")
        + f"Missing required fields to fill:\n{json.dumps(field_hints, indent=2)}\n\n"
        + (f"Allowed values for enum fields:\n{json.dumps(enum_hints, indent=2)}\n\n" if enum_hints else "")
        + f"Reply ONLY with a JSON object containing the missing fields: {missing}"
    )
    system_msg = "You are a data entry assistant. Output only valid JSON, no markdown or extra text."
    if GLOBAL_CV_CONTEXT:
        system_msg += f"\n\n{GLOBAL_CV_CONTEXT}"

    resp = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": prompt},
        ],
        options={"temperature": 0.0},
    )
    raw = re.sub(r"```(?:json)?|```", "", resp["message"]["content"]).strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    filled = json.loads(raw)
    for f in missing:
        if f in filled and filled[f] and not str(row.get(f, "")).strip():
            row[f] = filled[f]
    return row


def validate_row(row, schema, label=""):
    """
    Print a warning for any schema-required field still empty after filling.

    Args:
        row (dict): The entity row to validate.
        schema (dict): JSON Schema with a "required" list.
        label (str): Human-readable identifier shown in the warning.
    """
    required = schema.get("required", [])
    missing = [f for f in required if not str(row.get(f, "")).strip()]
    if missing:
        print(f"  [WARN] {label} — missing required fields after fill: {missing}")

# ---------------------------------------------------------------------------
# Entity resolver
# ---------------------------------------------------------------------------
def resolve_entity(entity_type, candidate, registry, all_schemas):
    """
    Resolve a candidate entity against the registry: exact match → LLM match → create.

    On creation, missing required fields are filled via the schema and LLM, then
    the row is validated before being written to the CSV.

    Args:
        entity_type (str): Key in ENTITY_CONFIG.
        candidate (dict): Candidate entity fields.
        registry (list[dict]): In-memory registry rows; mutated when a new row is created.
        all_schemas (dict): Loaded schema definitions keyed by filename.

    Returns:
        tuple[str, str]: (resolved_id, status) where status is "exact", "llm", or "created".
    """
    cfg = ENTITY_CONFIG[entity_type]
    id_field, name_field = cfg["id_field"], cfg["name_field"]
    candidate_name = str(candidate.get(name_field, "")).strip().lower()

    for row in registry:
        if str(row.get(name_field, "")).strip().lower() == candidate_name:
            return row[id_field], "exact"

    if registry:
        prompt = (
            f"Registry:\n{json.dumps(registry, indent=2)}\n\n"
            f"Candidate:\n{json.dumps(candidate, indent=2)}\n\n"
            f"Does the candidate semantically match any registry row?\n"
            f'Reply ONLY with JSON: {{"match": true, "id": "<existing_id>"}} or {{"match": false}}'
        )
        resp = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a data entity resolver. Output only valid JSON, no markdown or extra text."},
                {"role": "user",   "content": prompt},
            ],
            options={"temperature": 0.0},
        )
        raw = re.sub(r"```(?:json)?|```", "", resp["message"]["content"]).strip()
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        decision = json.loads(raw)
        if decision.get("match"):
            return decision["id"], "llm"

    new_id  = f"{cfg['prefix']}_{len(registry) + 1:05d}"
    new_row = {id_field: new_id, **candidate}
    schema  = all_schemas.get(cfg.get("schema_key"), {})
    if schema:
        new_row = llm_fill_fields(new_row, schema)
        validate_row(new_row, schema, label=f"{entity_type}:{candidate.get(name_field)}")
    append_row(entity_type, new_row)
    registry.append(new_row)
    print(f"  + {entity_type}: {new_id}  ({candidate.get(name_field)})")
    return new_id, "created"

# ---------------------------------------------------------------------------
# Attribute and scope helpers
# ---------------------------------------------------------------------------
def ensure_attr(name, registry, notes="", attr_schema=None):
    """
    Return the attribute ID for the given name, creating a new registry entry if needed.

    All schema-required fields start empty so llm_fill_fields can extract them
    from the notes string (which contains column header, unit/format, allowed
    values, and description from the source YAML).

    Args:
        name (str): Attribute name to look up or create.
        registry (dict[str, str]): In-memory {name: id} mapping; mutated on creation.
        notes (str): Raw notes string from the unmapped entity YAML attribute entry.
        attr_schema (dict | None): JSON Schema for the attribute entity.

    Returns:
        tuple[str, str]: (attribute_id, status) where status is "existing" or "created".
    """
    if name in registry:
        return registry[name], "existing"

    new_id  = f"ATTR_{len(registry) + 1:05d}"
    new_row = {
        "attribute_id":          new_id,
        "attribute_name":        name,
        "attribute_description": "",
        "unit":                  "",
        "data_format":           "",
    }
    if attr_schema:
        new_row = llm_fill_fields(new_row, attr_schema, extra_context=notes)
        validate_row(new_row, attr_schema, label=f"attribute:{name}")

    registry[name] = new_id
    Path(ATTR_PATH).parent.mkdir(parents=True, exist_ok=True)
    file_exists = Path(ATTR_PATH).exists()
    with open(ATTR_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ATTR_COLS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: new_row.get(k, "") for k in ATTR_COLS})
    return new_id, "created"


def ensure_scope(scope_type, value):
    """
    Ensure a scope token exists in the corresponding controlled-vocabulary CSV.

    Args:
        scope_type (str): Key in SCOPE_CONFIG (e.g. "geographic_scope").
        value (str | None): Scope token to look up or register.

    Returns:
        tuple[str | None, str | None]: (scope_token, status) where status is
            "existing", "created", or None if value was empty.
    """
    if not value:
        return None, None
    token = str(value).strip()
    path  = SCOPE_CONFIG[scope_type]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    existing_tokens = set()
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            existing_tokens = {r.get(scope_type, "").strip() for r in csv.DictReader(f)}
    if token in existing_tokens:
        return token, "existing"
    desc_field = f"{scope_type}_description"
    cols       = [scope_type, desc_field, "note"]
    file_exists = Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        if not file_exists:
            writer.writeheader()
        writer.writerow({scope_type: token, desc_field: token, "note": ""})
    return token, "created"

# ---------------------------------------------------------------------------
# Candidate collection
# ---------------------------------------------------------------------------
def collect_candidates(unmapped_entities):
    """
    Extract unique entity candidates per type from a list of unmapped entities.

    Deduplication is by name so each unique name is resolved only once.

    Args:
        unmapped_entities (list[dict]): Unmapped entity dicts from the source YAML.

    Returns:
        dict[str, dict]: {entity_type: {name: candidate_dict}}
    """
    candidates = {et: {} for et in ENTITY_CONFIG}
    for e in unmapped_entities:
        t     = e.get("technology", {})
        tname = e.get("technology_name")
        if tname:
            candidates["technology"].setdefault(tname, {
                "technology_name":        tname,
                "technology_type":        t.get("technology_type"),
                "technology_category":    t.get("technology_category"),
                "technology_description": t.get("technology_description"),
            })
        pname = t.get("process_name")
        if pname:
            candidates["process"].setdefault(pname, {
                "process_name":     pname,
                "process_type":     t.get("process_type"),
                "process_category": t.get("process_category"),
            })
        for src in e.get("sources", []):
            sname = src.get("source_name")
            if sname:
                candidates["source"].setdefault(sname, {
                    "source_name":        sname,
                    "source_description": src.get("source_description"),
                })
        for item in e.get("balancing", {}).get("inputs", []) + e.get("balancing", {}).get("outputs", []):
            cname = item.get("carrier_name")
            if cname:
                candidates["carrier"].setdefault(cname, {"carrier_name": cname})
    return candidates

# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------
def generate_audit(ue, attr_ids, indices=None):
    """
    Build a per-entity audit report by joining the provenance map, entity lookup
    maps, and the original unmapped entity YAML data.

    Args:
        ue (list[dict]): The working slice of unmapped entities.
        attr_ids (dict[str, str]): {attribute_name: attribute_id} resolved in Step 3.
        indices (list[int] | None): Indices to audit; None audits all.

    Returns:
        list[dict]: One report dict per audited entity.
    """
    map_a_path = MAPPING_DIR / "unmapped_to_linked.csv"
    with open(map_a_path, encoding="utf-8") as f:
        map_a = {int(r["unmapped_index"]): r for r in csv.DictReader(f)}

    c_maps = {}
    for et, cfg in ENTITY_CONFIG.items():
        path = MAPPING_DIR / f"{et}_map.csv"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                c_maps[et] = {r[cfg["name_field"]]: r for r in csv.DictReader(f)}

    scope_c = {}
    for scope_type in SCOPE_CONFIG:
        path = MAPPING_DIR / f"{scope_type}_map.csv"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                scope_c[scope_type] = {r["original_value"]: r["scope_token"] for r in csv.DictReader(f)}

    targets = indices if indices is not None else list(map_a.keys())
    report  = []
    for idx in targets:
        entity = ue[idx]
        a      = map_a.get(idx, {})
        t      = entity.get("technology", {})
        report.append({
            "unmapped_index":   idx,
            "technology_name":  entity.get("technology_name"),
            "linked_entity_id": a.get("linked_entity_id"),
            "resolution": {
                "technology": c_maps.get("technology", {}).get(entity.get("technology_name"), {}),
                "process":    c_maps.get("process", {}).get(t.get("process_name"), {}),
                "sources":    [c_maps.get("source", {}).get(s["source_name"], {}) for s in entity.get("sources", [])],
                "carriers": {
                    "inputs":  [c_maps.get("carrier", {}).get(x["carrier_name"], {}) for x in entity.get("balancing", {}).get("inputs", [])],
                    "outputs": [c_maps.get("carrier", {}).get(x["carrier_name"], {}) for x in entity.get("balancing", {}).get("outputs", [])],
                },
                "scope": {st: scope_c.get(st, {}).get(entity.get("scope", {}).get(f"{st}_description")) for st in SCOPE_CONFIG},
            },
            "unresolved_attributes": [
                a["attribute_name"] for a in entity.get("attributes", [])
                if not attr_ids.get(a["attribute_name"])
            ],
        })
    return report

# ---------------------------------------------------------------------------
# Reset / clean-up
# ---------------------------------------------------------------------------
def backup_derived_data(backup_dir="../motel-db/_backup", confirm=True):
    """
    Copy all current derived data files into a timestamped backup folder.

    A subfolder named after the current date-time (YYYYMMDD_HHMMSS) is created
    inside `backup_dir`, and every derived file that exists is copied there,
    preserving its relative path under `motel-db/`. Safe to call before reset.

    Files backed up (if they exist):
    - controlled_vocabulary/attribute.csv
    - controlled_vocabulary/carrier.csv
    - controlled_vocabulary/geographic_scope.csv
    - controlled_vocabulary/temporal_scope.csv
    - controlled_vocabulary/capacity_scope.csv
    - controlled_vocabulary/system_boundary.csv
    - secondary/technology.csv
    - secondary/process.csv
    - secondary/source.csv
    - supplementary/contributor.csv
    - supplementary/review.csv
    - mapping/ (directory, all files)

    Entity folders (linked_entity/, unmapped_entity/) are intentionally excluded.

    Args:
        backup_dir (str): Root directory for all backups.
        confirm (bool): If True (default), prints a summary of what was copied.
    """
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_root = Path(backup_dir) / timestamp

    flat_paths = [Path(p) for p in FLAT_FILE_SCHEMA_MAP] + SUPPLEMENTARY_PATHS
    backed_up, skipped = [], []

    for src in flat_paths:
        if src.exists():
            dest = dest_root / src
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            backed_up.append(str(src))
        else:
            skipped.append(str(src))

    if MAPPING_DIR.exists():
        dest_map = dest_root / MAPPING_DIR
        shutil.copytree(MAPPING_DIR, dest_map)
        backed_up.append(str(MAPPING_DIR) + "/ (directory)")

    if confirm:
        print(f"=== Backup saved to {dest_root} ===")
        if backed_up:
            print("Copied:")
            for f in backed_up:
                print(f"  - {f}")
        if skipped:
            print("Skipped (not found):")
            for f in skipped:
                print(f"  - {f}")


def reset_derived_data(confirm=True, schema_dir="../schema/"):
    """
    Reset all derived (non-source) data files produced by the harmonisation pipeline.

    Each file is deleted and immediately recreated as an empty CSV whose column
    headers are derived from ALL properties defined in the corresponding schema
    (not just the required subset). For flat schemas (attribute, scope files) every
    top-level property becomes a column. For linked_entity, the schema is deeply
    nested so LE_COLS (the flat denormalized representation) is used instead.

    Files reset with schema-derived headers (all properties, not just required):
    - secondary/technology.csv              → all properties in technology.yaml
    - secondary/process.csv                 → all properties in process.yaml
    - secondary/source.csv                  → all properties in source.yaml
    - controlled_vocabulary/carrier.csv     → all properties in carrier.yaml
    - controlled_vocabulary/attribute.csv   → all properties in attribute.yaml
    - controlled_vocabulary/geographic_scope.csv → all properties in geographic_scope.yaml
    - controlled_vocabulary/temporal_scope.csv   → all properties in temporal_scope.yaml
    - controlled_vocabulary/capacity_scope.csv   → all properties in capacity_scope.yaml
    - controlled_vocabulary/system_boundary.csv  → all properties in system_boundary.yaml
    - linked_entity/linked_entity.yaml            → empty YAML list (schema is nested)

    The mapping/ directory is wiped (no header stubs — rebuilt by Step 5).

    Args:
        confirm (bool): If True (default), prints a summary of what was reset.
        schema_dir (str): Path to the schema directory used to derive column headers.
    """
    all_schemas = load_all_schemas(schema_dir)

    def schema_cols(schema_key):
        """Return all top-level property names from a flat schema, in definition order."""
        schema = all_schemas.get(schema_key, {})
        return list(schema.get("properties", {}).keys())

    # Flat CSV files: derive columns from every property in the schema
    reset_log = []
    for path_str, schema_key in FLAT_FILE_SCHEMA_MAP.items():
        path = Path(path_str)
        cols = schema_cols(schema_key)
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=cols).writeheader()
        status = "reset" if existed else "created"
        reset_log.append((path, cols, status))

    # linked_entity: YAML file — reset to an empty list
    le_path = Path(LE_PATH)
    existed = le_path.exists()
    le_path.parent.mkdir(parents=True, exist_ok=True)
    with open(le_path, "w", encoding="utf-8") as f:
        yaml.dump([], f)
    reset_log.append((le_path, ["(yaml — no columns)"], "reset" if existed else "created"))

    mapping_note = None
    if MAPPING_DIR.exists():
        shutil.rmtree(MAPPING_DIR)
        mapping_note = f"{MAPPING_DIR}/ removed (rebuilt by Step 5)"

    if confirm:
        print("=== Reset complete ===")
        for path, cols, status in reset_log:
            print(f"  [{status}] {path}")
            print(f"           columns: {', '.join(cols)}")
        if mapping_note:
            print(f"  [removed] {mapping_note}")
