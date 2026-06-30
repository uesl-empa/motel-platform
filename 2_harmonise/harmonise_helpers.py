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
import datetime
import json
import re
import shutil
import time
from pathlib import Path

import ollama
import yaml

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
MODEL = "qwen3:14b"
HARMONISATION_VERSION = "1.0.0"
LOG_DIR = Path("../motel-db/log")
DEFAULT_UNMAPPED_PATH = Path("../motel-db/unmapped_entity/unmapped_entities_refuel.yaml")
SCHEMA_DIR = Path("../schema")


def find_project_root(start: Path | None = None) -> Path:
    """Find the repository root from any path inside motel-platform."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "motel-db").is_dir() and (candidate / "schema").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate the repository root. Start the notebook from inside motel-platform."
    )


def get_harmonisation_paths(project_root: Path | None = None) -> dict[str, Path]:
    """Return the main repository paths used by the harmonisation workflow."""
    root = (project_root or find_project_root()).resolve()
    return {
        "project_root": root,
        "schema_dir": root / "schema",
        "database_dir": root / "motel-db",
        "unmapped_path": root / "motel-db" / "unmapped_entity" / "unmapped_entities_refuel.yaml",
        "linked_entity_path": root / "motel-db" / "linked_entity" / "linked_entity.yaml",
        "mapping_dir": root / "motel-db" / "mapping",
        "notebook_path": root / "2_harmonise" / "2_data_harmonisation.ipynb",
    }


def load_all_csv_data(directory="../motel-db/"):
    """Recursively load CSV files under motel-db for notebook inspection."""
    all_csv_data = {}
    for path in sorted(Path(directory).rglob("*.csv")):
        try:
            all_csv_data[path.stem] = pd.read_csv(path)
        except Exception as exc:
            print(f"Error reading {path}: {exc}")
    return all_csv_data


def prepare_harmonisation_inputs(
    unmapped_path,
    test_limit=None,
    set_all_unmapped_to_pending=False,
):
    """Load staged unmapped entities, optionally reset status, and apply a test slice."""
    unmapped_path = Path(unmapped_path)
    if set_all_unmapped_to_pending:
        all_unmapped_entities, _, _ = load_pending_unmapped(unmapped_path)
        print("Setting all staged entities to 'to_be_mapped' status...")
        mark_all_unmapped_entities_pending(unmapped_path, all_unmapped_entities)

    all_unmapped_entities, ue, ue_indices = load_pending_unmapped(unmapped_path)
    if test_limit is not None:
        ue = ue[:test_limit]
        ue_indices = ue_indices[:test_limit]

    return {
        "all_unmapped_entities": all_unmapped_entities,
        "ue": ue,
        "ue_indices": ue_indices,
    }


def start_harmonisation_run(paths, all_schemas, all_unmapped_entities, ue, test_limit=None):
    """Start timing and logging for one harmonisation notebook run."""
    harmonisation_started = time.perf_counter()
    harmonisation_log = start_harmonisation_log(settings={
        "unmapped_path": str(Path(paths["unmapped_path"]).resolve()),
        "schema_path": str(Path(paths["schema_dir"]).resolve()),
        "database_path": str(Path(paths["database_dir"]).resolve()),
        "linked_entity_path": str(Path(paths["linked_entity_path"]).resolve()),
        "mapping_path": str(Path(paths["mapping_dir"]).resolve()),
        "loaded_schema_count": len(all_schemas),
        "entity_registry_paths": {
            entity_type: str(Path(config["path"]).resolve())
            for entity_type, config in ENTITY_CONFIG.items()
        },
        "llm_model": MODEL,
        "harmonisation_version": HARMONISATION_VERSION,
        "test_limit": test_limit,
        "staged_entities": len(all_unmapped_entities),
        "entities_selected": len(ue),
    })
    return harmonisation_started, harmonisation_log


def apply_setup_controls(
    harmonisation_log,
    create_motel_db_backup=False,
    reset_motel_db_outputs=False,
):
    """Apply optional backup/reset controls and log the result."""
    setup_started = time.perf_counter()
    setup_actions = []

    if create_motel_db_backup:
        backup_derived_data()
        setup_actions.append("backup")
    else:
        print("Skipping motel-db backup.")

    if reset_motel_db_outputs:
        reset_derived_data()
        setup_actions.append("reset")
    else:
        print("Skipping motel-db cleanup/reset.")

    log_harmonisation_event(
        harmonisation_log,
        "setup",
        "setup_controls_applied",
        duration_seconds=round(time.perf_counter() - setup_started, 3),
        actions=setup_actions,
        create_motel_db_backup=create_motel_db_backup,
        reset_motel_db_outputs=reset_motel_db_outputs,
    )
    return setup_actions


def start_harmonisation_log(settings=None, log_dir=LOG_DIR):
    """Create a timestamped JSON-lines log for one harmonisation run."""
    started_at = datetime.datetime.now().astimezone()
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"harmonisation_{started_at.strftime('%Y%m%d_%H%M%S')}.log"
    suffix = 1
    while log_path.exists():
        log_path = log_dir / (
            f"harmonisation_{started_at.strftime('%Y%m%d_%H%M%S')}_{suffix:02d}.log"
        )
        suffix += 1

    log_harmonisation_event(
        log_path,
        "run",
        "started",
        harmonisation_version=HARMONISATION_VERSION,
        llm_model=MODEL,
        settings=settings or {},
    )
    return log_path


def log_harmonisation_event(log_path, step, action, **details):
    """Append one timestamped event to a harmonisation JSON-lines log."""
    event = {
        "timestamp": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": step,
        "action": action,
        **details,
    }
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

# ---------------------------------------------------------------------------
# Entity configuration
# ---------------------------------------------------------------------------
ENTITY_CONFIG = {
    "technology": {
        "path": "../motel-db/secondary/technology.csv",
        "id_field": "tech_id", "prefix": "TECH", "name_field": "technology_name",
        "cols": [
            "tech_id",
            "technology_name",
            "technology_description",
            "technology_variant",
            "main_process",
            "main_operation_unit",
            "ontology_iri",
        ],
        "schema_key": "technology.yaml",
    },
    "process": {
        "path": "../motel-db/secondary/process.csv",
        "id_field": "process_id", "prefix": "PROC", "name_field": "process_name",
        "cols": [
            "process_id",
            "process_name",
            "process_description",
            "process_type",
            "process_category",
            "main_sector",
            "feedstocks",
            "products",
        ],
        "schema_key": "process.yaml",
    },
    "source": {
        "path": "../motel-db/secondary/source.csv",
        "id_field": "source_id", "prefix": "SRC", "name_field": "source_name",
        "cols": [
            "source_id",
            "source_name",
            "source_description",
            "source_type",
            "link",
            "access_date",
            "confidence_level",
            "assessment_method",
            "reference_year",
            "note",
        ],
        "schema_key": "source.yaml",
    },
    "carrier": {
        "path": "../motel-db/controlled_vocabulary/carrier.csv",
        "id_field": "carrier_id", "prefix": "CAR", "name_field": "carrier_name",
        "cols": ["carrier_id", "carrier_name", "carrier_description", "carrier_type", "carrier_category"],
        "schema_key": "carrier.yaml",
    },
}

PROCESS_LLM_FIELDS = [
    "process_description",
    "process_type",
    "process_category",
    "main_sector",
    "feedstocks",
    "products",
]

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
UNMAPPED_STATUS_PENDING = "to_be_mapped"
UNMAPPED_STATUS_MAPPED = "mapped"

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


def load_pending_unmapped(path):
    """
    Load a staging YAML file and select entities that still need harmonisation.

    Records created before mapping_status was introduced are treated as pending
    for backward compatibility.

    Returns:
        tuple[list[dict], list[dict], list[int]]: Full document, pending records,
        and their indices in the full document.
    """
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        all_entities = yaml.safe_load(f) or []

    def get_mapping_status(entity):
        record = entity.get("harmonisation_record") or {}
        return record.get(
            "mapping_status",
            entity.get("mapping_status", UNMAPPED_STATUS_PENDING),
        )

    pending_indices = [
        i for i, entity in enumerate(all_entities)
        if get_mapping_status(entity) != UNMAPPED_STATUS_MAPPED
    ]
    pending_entities = [all_entities[i] for i in pending_indices]
    return all_entities, pending_entities, pending_indices


def mark_unmapped_entities_mapped(
    path, all_entities, source_indices, linked_entities, date_mapped
):
    """
    Mark successfully harmonised staging records as mapped and save atomically.

    The status file is updated only after the caller has successfully written
    the linked entities.
    """
    if len(source_indices) != len(linked_entities):
        raise ValueError(
            "Cannot update mapping status: source and linked entity counts differ"
        )

    for source_index, linked_entity in zip(source_indices, linked_entities):
        entity = all_entities[source_index]
        record = dict(entity.get("harmonisation_record") or {})
        record["mapping_status"] = UNMAPPED_STATUS_MAPPED
        record["linked_entity_id"] = linked_entity["linked_entity_id"]
        record["date_mapped"] = str(date_mapped)
        entity["harmonisation_record"] = record
        entity.pop("mapping_status", None)
        entity.pop("linked_entity_id", None)
        entity.pop("date_mapped", None)

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            all_entities,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    temporary.replace(path)


def mark_all_unmapped_entities_pending(path, all_entities):
    """
    Reset all staging records to pending and remove prior harmonisation outputs.

    This is useful when re-running the harmonisation pipeline from scratch on
    an existing staging YAML that has already been marked as mapped.
    """
    for entity in all_entities:
        record = dict(entity.get("harmonisation_record") or {})
        record["mapping_status"] = UNMAPPED_STATUS_PENDING
        record.pop("linked_entity_id", None)
        record.pop("date_mapped", None)
        entity["harmonisation_record"] = record
        entity.pop("mapping_status", None)
        entity.pop("linked_entity_id", None)
        entity.pop("date_mapped", None)

    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            all_entities,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    temporary.replace(path)

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


def save_registry(entity_type, rows):
    """Rewrite a registry CSV after enriching existing rows with new metadata."""
    cfg = ENTITY_CONFIG[entity_type]
    path = Path(cfg["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cfg["cols"])
        writer.writeheader()
        for row in rows:
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


def _has_value(value):
    """Return True when a candidate field carries real content."""
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() != "nan"


def enrich_registry_row(entity_type, row, candidate):
    """Backfill missing registry fields from a richer candidate record."""
    changed = False
    cfg = ENTITY_CONFIG[entity_type]
    protected = {cfg["id_field"], cfg["name_field"]}

    for key in cfg["cols"]:
        if key in protected:
            continue
        candidate_value = candidate.get(key)
        if not _has_value(candidate_value):
            continue
        if _has_value(row.get(key)):
            continue
        row[key] = candidate_value
        changed = True

    return changed

# ---------------------------------------------------------------------------
# LLM field filling and schema validation
# ---------------------------------------------------------------------------
def _parse_llm_json(response):
    """Extract one JSON object from an Ollama response."""
    try:
        content = response["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Ollama response did not contain message content") from exc

    raw = str(content or "").strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
    raw = re.sub(r"```(?:json)?\s*|```", "", raw, flags=re.IGNORECASE).strip()
    if not raw:
        raise ValueError("Ollama returned an empty response")

    decoder = json.JSONDecoder()
    for start, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    preview = raw[:200].replace("\n", " ")
    raise ValueError(f"Ollama did not return a valid JSON object: {preview!r}")


def build_attribute_llm_context(notes):
    """Add explicit currency guidance for attribute-related LLM calls."""
    notes = str(notes or "").strip()
    if not notes:
        return notes

    currency_match = re.search(
        r"(?:source\s+currency|currency)\s*:\s*([A-Za-z]{3})",
        notes,
        flags=re.IGNORECASE,
    )
    if not currency_match:
        return notes

    currency = currency_match.group(1).upper()
    guidance = (
        f"\n\nCurrency guidance:\n"
        f"- The source currency for this attribute is {currency}.\n"
        f"- If the unit format contains generic 'Currency', interpret it as {currency}.\n"
        f"- Preserve {currency} in the canonical unit and description.\n"
        f"- Do not convert to USD or assume USD unless the source explicitly says so."
    )
    return notes + guidance


def build_process_llm_context(candidate):
    """Assemble rich context for process-field inference."""
    parts = []

    original_name = candidate.get("process_original_name")
    if _has_value(original_name):
        parts.append(f"Original process name: {original_name}")

    process_notes = candidate.get("process_notes")
    if _has_value(process_notes):
        parts.append(f"Process notes: {process_notes}")

    technology_description = candidate.get("technology_description")
    if _has_value(technology_description):
        parts.append(f"Related technology description: {technology_description}")

    technology_category = candidate.get("technology_category")
    if _has_value(technology_category):
        parts.append(f"Related technology category: {technology_category}")

    raw_inputs = candidate.get("raw_input_carriers")
    if raw_inputs:
        parts.append(
            "Inputs from unmapped balancing data: "
            + ", ".join(str(x) for x in raw_inputs if _has_value(x))
        )

    raw_outputs = candidate.get("raw_output_carriers")
    if raw_outputs:
        parts.append(
            "Outputs from unmapped balancing data: "
            + ", ".join(str(x) for x in raw_outputs if _has_value(x))
        )

    parts.append(
        "When filling feedstocks and products, use the raw carrier names from the unmapped balancing data."
    )
    parts.append(
        "Do not invent carrier IDs at this stage; preserve human-readable carrier names."
    )
    return "\n".join(parts)


def build_technology_llm_context(candidate):
    """Assemble technology description and note context for field inference."""
    parts = []

    technology_description = candidate.get("technology_description")
    if _has_value(technology_description):
        parts.append(f"Technology description: {technology_description}")

    technology_notes = candidate.get("technology_notes")
    if _has_value(technology_notes):
        parts.append(f"Technology notes: {technology_notes}")

    technology_type = candidate.get("technology_type")
    if _has_value(technology_type):
        parts.append(f"Technology type: {technology_type}")

    technology_category = candidate.get("technology_category")
    if _has_value(technology_category):
        parts.append(f"Technology category: {technology_category}")

    process_name = candidate.get("process_name")
    if _has_value(process_name):
        parts.append(f"Related process name: {process_name}")

    parts.append(
        "Use the technology description as the primary source for technology_description."
    )
    parts.append(
        "Use the notes as supportive context when inferring variant, operation unit, or other missing fields."
    )
    return "\n".join(parts)


def build_carrier_llm_context(candidate):
    """Assemble carrier notes and usage context for carrier-field inference."""
    parts = []

    carrier_notes = candidate.get("note") or candidate.get("carrier_notes")
    if _has_value(carrier_notes):
        parts.append(f"Carrier notes: {carrier_notes}")

    raw_roles = candidate.get("carrier_roles")
    if raw_roles:
        parts.append(
            "Observed carrier roles in balancing data: "
            + ", ".join(str(x) for x in raw_roles if _has_value(x))
        )

    parts.append(
        "Use the carrier notes to infer carrier_description, carrier_type, and carrier_category."
    )
    parts.append(
        "Prefer the source wording when the notes explicitly describe the carrier."
    )
    return "\n".join(parts)


def build_source_llm_context(candidate):
    """Assemble source notes and locator context for source-field inference."""
    parts = []

    source_description = candidate.get("source_description")
    if _has_value(source_description):
        parts.append(f"Source description: {source_description}")

    source_note = candidate.get("note")
    if _has_value(source_note):
        parts.append(f"Source notes: {source_note}")

    source_type = candidate.get("source_type")
    if _has_value(source_type):
        parts.append(f"Source type: {source_type}")

    link = candidate.get("link")
    if _has_value(link):
        parts.append(f"Source link: {link}")

    parts.append(
        "Use the source notes as general supporting context for source_description, source_type, and note."
    )
    return "\n".join(parts)


def llm_fill_fields(row, schema, extra_context="", target_fields=None):
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
    if target_fields is None:
        target_fields = schema.get("required", [])
    missing = [f for f in target_fields if not str(row.get(f, "")).strip()]
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
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": prompt},
    ]
    filled = None
    for attempt in range(2):
        resp = ollama.chat(
            model=MODEL,
            messages=messages,
            options={"temperature": 0.0},
        )
        try:
            filled = _parse_llm_json(resp)
            break
        except ValueError as exc:
            if attempt == 0:
                try:
                    previous_content = resp["message"]["content"]
                except (KeyError, TypeError):
                    previous_content = ""
                messages.append({
                    "role": "assistant",
                    "content": str(previous_content or ""),
                })
                messages.append({
                    "role": "user",
                    "content": (
                        "Your previous response was not a valid JSON object. "
                        f"Return only one JSON object with these fields: {missing}"
                    ),
                })
            else:
                print(f"  [WARN] LLM field fill skipped after invalid response: {exc}")

    if filled is None:
        return row

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


def _name_matches_schema_guideline(entity_type, proposed_name):
    """Apply lightweight checks when the schema uses prose instead of a pattern."""
    proposed_name = str(proposed_name or "").strip()
    if not proposed_name:
        return False, "name is empty"
    if entity_type in {"attribute", "carrier", "technology", "source"}:
        if "_" in proposed_name:
            return False, f"{entity_type} name must not contain underscores"
        if proposed_name[:1] != proposed_name[:1].upper():
            return False, f"{entity_type} name must start with a capital letter"
    return True, ""


def llm_name_from_schema(entity_type, candidate, schema, extra_context=""):
    """Ask the LLM to name an entity using its schema guideline."""
    if entity_type == "attribute":
        name_field = "attribute_name"
    elif entity_type in SCOPE_CONFIG:
        name_field = entity_type
    else:
        cfg = ENTITY_CONFIG[entity_type]
        name_field = cfg["name_field"]
    original_name = str(candidate.get(name_field, "")).strip()
    if not original_name:
        return original_name

    field_schema = schema.get("properties", {}).get(name_field, {})
    prompt = (
        f"Create the canonical {name_field} for this {entity_type} record.\n\n"
        f"Candidate record:\n{json.dumps(candidate, indent=2)}\n\n"
        f"Schema guideline for {name_field}:\n"
        f"{json.dumps(field_schema, indent=2)}\n\n"
        "Infer a clear, meaningful name from the candidate information. "
        "Do not merely perform a mechanical character replacement. "
        f'Reply ONLY with JSON: {{"{name_field}": "<canonical name>"}}'
    )
    if extra_context:
        prompt += f"\n\nAdditional context:\n{extra_context}"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a database naming curator. Follow the supplied schema "
                "exactly and output only valid JSON."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    pattern = field_schema.get("pattern")
    min_length = field_schema.get("minLength")
    max_length = field_schema.get("maxLength")

    for attempt in range(2):
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            options={"temperature": 0.0},
        )
        try:
            result = _parse_llm_json(response)
            proposed_name = str(result.get(name_field, "")).strip()
            if not proposed_name:
                raise ValueError(f"LLM omitted {name_field}")
            if min_length is not None and len(proposed_name) < min_length:
                raise ValueError(
                    f"LLM name {proposed_name!r} is shorter than minLength {min_length}"
                )
            if max_length is not None and len(proposed_name) > max_length:
                raise ValueError(
                    f"LLM name {proposed_name!r} exceeds maxLength {max_length}"
                )
            if pattern and re.fullmatch(pattern, proposed_name) is None:
                raise ValueError(
                    f"LLM name {proposed_name!r} does not match schema pattern {pattern!r}"
                )
            if not pattern:
                is_valid, message = _name_matches_schema_guideline(entity_type, proposed_name)
                if not is_valid:
                    raise ValueError(message)
            return proposed_name
        except ValueError as exc:
            if attempt == 1:
                raise ValueError(
                    f"Could not generate a schema-compliant {name_field} "
                    f"for {original_name!r}"
                ) from exc
            messages.extend([
                {
                    "role": "assistant",
                    "content": str(response.get("message", {}).get("content", "")),
                },
                {
                    "role": "user",
                    "content": (
                        f"The proposed name was invalid: {exc}. "
                        f"Return only a schema-compliant JSON object containing {name_field}."
                    ),
                },
            ])


# ---------------------------------------------------------------------------
# Entity resolver
# ---------------------------------------------------------------------------
def resolve_entity(entity_type, candidate, registry, all_schemas, skip_llm_match=False):
    """
    Resolve a candidate entity against the registry: exact match → LLM match → create.

    On creation, missing required fields are filled via the schema and LLM, then
    the row is validated before being written to the CSV.

    Args:
        entity_type (str): Key in ENTITY_CONFIG.
        candidate (dict): Candidate entity fields.
        registry (list[dict]): In-memory registry rows; mutated when a new row is created.
        all_schemas (dict): Loaded schema definitions keyed by filename.
        skip_llm_match (bool): When True, bypass semantic LLM matching and fall
            through to creation if no exact name match exists.

    Returns:
        tuple[str, str]: (resolved_id, status) where status is "exact", "llm", or "created".
    """
    cfg = ENTITY_CONFIG[entity_type]
    id_field, name_field = cfg["id_field"], cfg["name_field"]
    schema = all_schemas.get(cfg.get("schema_key"), {})
    candidate = dict(candidate)
    candidate[name_field] = llm_name_from_schema(entity_type, candidate, schema)
    entity_context = ""
    if entity_type == "technology":
        entity_context = build_technology_llm_context(candidate)
    elif entity_type == "process":
        entity_context = build_process_llm_context(candidate)
    elif entity_type == "carrier":
        entity_context = build_carrier_llm_context(candidate)
    elif entity_type == "source":
        entity_context = build_source_llm_context(candidate)

    if entity_type == "technology" and schema:
        candidate = llm_fill_fields(
            candidate,
            schema,
            extra_context=entity_context,
            target_fields=[
                "technology_description",
                "technology_variant",
                "main_operation_unit",
            ],
        )
    if entity_type == "process" and schema:
        candidate = llm_fill_fields(
            candidate,
            schema,
            extra_context=entity_context,
            target_fields=PROCESS_LLM_FIELDS,
        )
    if entity_type == "carrier" and schema:
        candidate = llm_fill_fields(
            candidate,
            schema,
            extra_context=entity_context,
            target_fields=["carrier_description", "carrier_type", "carrier_category"],
        )
    if entity_type == "source" and schema:
        candidate = llm_fill_fields(
            candidate,
            schema,
            extra_context=entity_context,
            target_fields=[
                "source_description",
                "source_type",
                "link",
                "access_date",
                "confidence_level",
                "assessment_method",
                "reference_year",
                "note",
            ],
        )
    candidate_name = str(candidate.get(name_field, "")).strip().lower()

    for row in registry:
        if str(row.get(name_field, "")).strip().lower() == candidate_name:
            if enrich_registry_row(entity_type, row, candidate):
                save_registry(entity_type, registry)
            return row[id_field], "exact"

    if registry and not skip_llm_match:
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
        try:
            decision = _parse_llm_json(resp)
        except ValueError as exc:
            print(f"  [WARN] LLM entity match skipped after invalid response: {exc}")
            decision = {"match": False}
        if decision.get("match"):
            match_id = decision["id"]
            for row in registry:
                if row.get(id_field) == match_id:
                    if enrich_registry_row(entity_type, row, candidate):
                        save_registry(entity_type, registry)
                    break
            return match_id, "llm"

    new_id  = f"{cfg['prefix']}_{len(registry) + 1:05d}"
    new_row = {id_field: new_id}
    for key in cfg["cols"]:
        if key == id_field:
            continue
        if key in candidate:
            new_row[key] = candidate[key]
    if schema:
        new_row = llm_fill_fields(new_row, schema, extra_context=entity_context)
        validate_row(new_row, schema, label=f"{entity_type}:{candidate.get(name_field)}")
    append_row(entity_type, new_row)
    registry.append(new_row)
    return new_id, "created"

# ---------------------------------------------------------------------------
# Attribute and scope helpers
# ---------------------------------------------------------------------------
def ensure_attr(name, registry, notes="", attr_schema=None):
    """
    Return the attribute ID for the given name, creating a new registry entry if needed.

    The attribute_name itself is first standardised by the LLM using the schema
    guideline. All other schema-required fields start empty so llm_fill_fields
    can extract them from the notes string (which contains column header,
    unit/format, allowed values, and description from the source YAML).

    Args:
        name (str): Attribute name to look up or create.
        registry (dict[str, str]): In-memory {name: id} mapping; mutated on creation.
        notes (str): Raw notes string from the unmapped entity YAML attribute entry.
        attr_schema (dict | None): JSON Schema for the attribute entity.

    Returns:
        tuple[str, str, str]: (attribute_id, canonical_name, status) where
            status is "existing" or "created".
    """
    attr_context = build_attribute_llm_context(notes)
    candidate = {"attribute_name": name}
    canonical_name = llm_name_from_schema(
        "attribute",
        candidate,
        attr_schema or {},
        extra_context=attr_context,
    )
    if canonical_name in registry:
        return registry[canonical_name], canonical_name, "existing"

    new_id  = f"ATTR_{len(registry) + 1:05d}"
    new_row = {
        "attribute_id":          new_id,
        "attribute_name":        canonical_name,
        "attribute_description": "",
        "unit":                  "",
        "data_format":           "",
    }
    if attr_schema:
        new_row = llm_fill_fields(new_row, attr_schema, extra_context=attr_context)
        validate_row(new_row, attr_schema, label=f"attribute:{canonical_name}")

    registry[canonical_name] = new_id
    Path(ATTR_PATH).parent.mkdir(parents=True, exist_ok=True)
    file_exists = Path(ATTR_PATH).exists()
    with open(ATTR_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ATTR_COLS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: new_row.get(k, "") for k in ATTR_COLS})
    return new_id, canonical_name, "created"


def ensure_scope(scope_type, value, scope_schema=None, description_seed="", extra_context=""):
    """
    Ensure a schema-guided scope entry exists in the corresponding CSV.

    Args:
        scope_type (str): Key in SCOPE_CONFIG (e.g. "geographic_scope").
        value (str | None): Raw scope description or token from staging data.
        scope_schema (dict | None): JSON Schema for the scope registry entry.
        description_seed (str): Preferred semantic description for this scope value.
        extra_context (str): Additional field-specific context for this scope value.

    Returns:
        tuple[str | None, str | None]: (scope_token, status) where status is
            "existing", "created", or None if value was empty.
    """
    if not value:
        return None, None
    raw_value = str(value).strip()
    path  = SCOPE_CONFIG[scope_type]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    desc_field = f"{scope_type}_description"
    seeded_description = description_seed or raw_value
    candidate = {
        scope_type: raw_value,
        desc_field: seeded_description,
    }
    token = llm_name_from_schema(
        scope_type,
        candidate,
        scope_schema or {},
        extra_context="\n".join(part for part in [raw_value, extra_context] if part),
    )
    existing_tokens = set()
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            existing_tokens = {r.get(scope_type, "").strip() for r in csv.DictReader(f)}
    if token in existing_tokens:
        return token, "existing"
    cols       = [scope_type, desc_field, "note"]
    new_row = {
        scope_type: token,
        desc_field: seeded_description,
        "note": extra_context or "",
    }
    if scope_schema:
        fill_context = (
            f"Original scope value: {raw_value}\n"
            f"Generated canonical token: {token}\n"
            f"Pre-filled {desc_field}: {new_row.get(desc_field, '')}\n"
            "If the nomenclature context provides a source or classification "
            "scheme, keep it in the description when it helps define the scope, "
            "and record supporting provenance in the note field."
        )
        if extra_context:
            fill_context += f"\nAdditional context:\n{extra_context}"
        new_row = llm_fill_fields(new_row, scope_schema, extra_context=fill_context)
        validate_row(new_row, scope_schema, label=f"{scope_type}:{token}")
    file_exists = Path(path).exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: new_row.get(k, "") for k in cols})
    return token, "created"


def get_scope_value(scope: dict, scope_type: str):
    """Return the canonical token if present, otherwise fall back to the raw description."""
    return scope.get(scope_type) or scope.get(f"{scope_type}_description")


def get_scope_note_context(scope: dict, scope_type: str) -> str:
    """Extract field-specific metadata note fragments for one scope property."""
    scope_notes = scope.get("scope_notes")
    if not scope_notes:
        return ""

    property_name = scope_type
    parts = []
    for segment in str(scope_notes).split(" | "):
        segment = segment.strip()
        if segment.startswith(f"{property_name} metadata:"):
            parts.append(segment)
    return " | ".join(parts)

def get_scope_description_context(scope: dict, scope_type: str) -> str:
    """Return the semantic description stored for one scope field."""
    return str(scope.get(f"{scope_type}_description") or "").strip()

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
    def upsert_candidate(bucket, key, candidate):
        existing = bucket.setdefault(key, {})
        for field, value in candidate.items():
            if isinstance(value, list):
                merged = []
                for item in existing.get(field, []):
                    if item not in merged:
                        merged.append(item)
                for item in value:
                    if item not in merged:
                        merged.append(item)
                if merged:
                    existing[field] = merged
                continue
            if _has_value(value) and not _has_value(existing.get(field)):
                existing[field] = value

    candidates = {et: {} for et in ENTITY_CONFIG}
    for e in unmapped_entities:
        t     = e.get("technology", {})
        tname = e.get("technology_name")
        if tname:
            upsert_candidate(candidates["technology"], tname, {
                "technology_name":        tname,
                "technology_type":        t.get("technology_type"),
                "technology_category":    t.get("technology_category"),
                "technology_description": t.get("technology_description"),
                "technology_notes":       t.get("technology_notes"),
                "process_name":           t.get("process_name"),
            })
        pname = t.get("process_name")
        if pname:
            balancing = e.get("balancing", {})
            raw_inputs = [
                item.get("carrier_name")
                for item in balancing.get("inputs", [])
                if _has_value(item.get("carrier_name"))
            ]
            raw_outputs = [
                item.get("carrier_name")
                for item in balancing.get("outputs", [])
                if _has_value(item.get("carrier_name"))
            ]
            upsert_candidate(candidates["process"], pname, {
                "process_name":         pname,
                "process_original_name": t.get("process_name"),
                "process_type":         t.get("process_type"),
                "process_category":     t.get("process_category"),
                "process_notes":        t.get("process_notes"),
                "technology_description": t.get("technology_description"),
                "technology_category":  t.get("technology_category"),
                "raw_input_carriers":   raw_inputs,
                "raw_output_carriers":  raw_outputs,
            })
        for src in e.get("sources", []):
            sname = src.get("source_name")
            if sname:
                upsert_candidate(candidates["source"], sname, {
                    "source_name":        sname,
                    "source_description": src.get("source_description"),
                    "source_type":        src.get("source_type"),
                    "link":               src.get("link"),
                    "access_date":        src.get("access_date"),
                    "confidence_level":   src.get("confidence_level"),
                    "assessment_method":  src.get("assessment_method"),
                    "reference_year":     src.get("reference_year"),
                    "note":               " | ".join(
                        str(value).strip()
                        for value in [
                            src.get("note"),
                            src.get("source_notes"),
                            src.get("source_locator"),
                        ]
                        if _has_value(value)
                    ),
                })
        for role, items in (
            ("input", e.get("balancing", {}).get("inputs", [])),
            ("output", e.get("balancing", {}).get("outputs", [])),
        ):
            for item in items:
                cname = item.get("carrier_name")
                if cname:
                    upsert_candidate(candidates["carrier"], cname, {
                        "carrier_name": cname,
                        "note": item.get("carrier_notes"),
                        "carrier_roles": [role],
                    })
    return candidates


def resolve_entities_step(candidates, all_schemas, harmonisation_log=None):
    """Resolve technology, process, source, and carrier candidates and write lookup maps."""
    step_started = time.perf_counter()
    registries = {et: load_registry(et) for et in ENTITY_CONFIG}
    resolved_ids = {et: {} for et in ENTITY_CONFIG}
    resolved_ids["technology_process"] = {}
    resolved_names = {et: {} for et in ENTITY_CONFIG}
    resolution_status = {et: {} for et in ENTITY_CONFIG}
    counts_by_type = {}
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)

    for entity_type, entity_candidates in candidates.items():
        print(f"\nResolving {entity_type}...")
        registry = registries[entity_type]
        name_field = ENTITY_CONFIG[entity_type]["name_field"]
        counts = {"exact": 0, "llm": 0, "created": 0}
        total_candidates = len(entity_candidates)
        if entity_type == "process":
            for status in resolution_status["process"].values():
                counts[status] += 1

        for index, (name, candidate) in enumerate(entity_candidates.items(), start=1):
            if entity_type == "process" and name in resolved_ids["process"]:
                continue

            skip_llm_match = False
            print(f"  [{index}/{total_candidates}] resolving {entity_type}: {name!r}")
            rid, status = resolve_entity(
                entity_type,
                candidate,
                registry,
                all_schemas,
                skip_llm_match=skip_llm_match,
            )
            resolved_row = next(
                row for row in registry
                if row.get(ENTITY_CONFIG[entity_type]["id_field"]) == rid
            )
            resolved_ids[entity_type][name] = rid
            resolved_names[entity_type][name] = resolved_row.get(name_field, "")
            resolution_status[entity_type][name] = status
            counts[status] += 1
            if entity_type == "technology":
                process_name = candidate.get("process_name")
                if process_name:
                    process_candidate = candidates.get("process", {}).get(process_name)
                    if process_candidate and process_name not in resolved_ids["process"]:
                        process_total = len(candidates.get("process", {}))
                        process_index = list(candidates.get("process", {}).keys()).index(process_name) + 1
                        print(
                            f"    -> [{process_index}/{process_total}] resolving linked process for "
                            f"technology {name!r}: {process_name!r}"
                        )
                        process_rid, process_status = resolve_entity(
                            "process",
                            process_candidate,
                            registries["process"],
                            all_schemas,
                            skip_llm_match=(status == "created"),
                        )
                        process_row = next(
                            row for row in registries["process"]
                            if row.get(ENTITY_CONFIG["process"]["id_field"]) == process_rid
                        )
                        resolved_ids["process"][process_name] = process_rid
                        resolved_names["process"][process_name] = process_row.get(
                            ENTITY_CONFIG["process"]["name_field"],
                            "",
                        )
                        resolution_status["process"][process_name] = process_status
                        if harmonisation_log:
                            log_harmonisation_event(
                                harmonisation_log,
                                "step_2",
                                "entity_resolved",
                                entity_type="process",
                                original_name=process_name,
                                resolved_name=resolved_names["process"][process_name],
                                resolved_id=process_rid,
                                status=process_status,
                                skip_llm_match=(status == "created"),
                                resolved_via="technology",
                                technology_name=name,
                            )
                    resolved_ids["technology_process"][name] = resolved_ids["process"].get(
                        process_name,
                        "",
                    )
                    technology_row = next(
                        row for row in registries["technology"]
                        if row.get(ENTITY_CONFIG["technology"]["id_field"]) == rid
                    )
                    main_process_id = resolved_ids["technology_process"][name]
                    if main_process_id and technology_row.get("main_process") != main_process_id:
                        technology_row["main_process"] = main_process_id
                        save_registry("technology", registries["technology"])
            resolved_name = resolved_names[entity_type][name]
            if status == "created":
                print(f"  + created: {name!r} -> {resolved_name!r}  [{rid}]")
            if harmonisation_log:
                log_harmonisation_event(
                    harmonisation_log,
                    "step_2",
                    "entity_resolved",
                    entity_type=entity_type,
                    original_name=name,
                    resolved_name=resolved_name,
                    resolved_id=rid,
                    status=status,
                    skip_llm_match=skip_llm_match,
                )

        mapping_path = MAPPING_DIR / f"{entity_type}_map.csv"
        id_field = ENTITY_CONFIG[entity_type]["id_field"]
        with open(mapping_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["original_name", name_field, id_field, "status"],
            )
            writer.writeheader()
            for original_name, rid in resolved_ids[entity_type].items():
                writer.writerow({
                    "original_name": original_name,
                    name_field: resolved_names[entity_type][original_name],
                    id_field: rid,
                    "status": resolution_status[entity_type][original_name],
                })

        counts_by_type[entity_type] = counts
        total = sum(counts.values())
        print(
            f"  total: {total}  |  exact match: {counts['exact']}  |  "
            f"LLM match: {counts['llm']}  |  newly created: {counts['created']}"
        )
        print(f"  mapping: {mapping_path}")
        if harmonisation_log:
            log_harmonisation_event(
                harmonisation_log,
                "step_2",
                "entity_type_completed",
                entity_type=entity_type,
                counts=counts,
                mapping_path=str(mapping_path.resolve()),
            )

    print("\nLLM resolution complete.")
    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "step_2",
            "completed",
            duration_seconds=round(time.perf_counter() - step_started, 3),
        )
    return {
        "registries": registries,
        "resolved_ids": resolved_ids,
        "resolved_names": resolved_names,
        "resolution_status": resolution_status,
        "counts_by_type": counts_by_type,
    }


def resolve_controlled_vocabulary_step(
    all_schemas,
    ue,
    full_unmapped_path=DEFAULT_UNMAPPED_PATH,
    rebuild_attribute_registry=True,
    harmonisation_log=None,
):
    """Resolve attributes and scope tokens and optionally rebuild attribute.csv from staged data."""
    step_started = time.perf_counter()
    attr_schema = all_schemas.get("attribute.yaml", {})

    if rebuild_attribute_registry:
        print("Rebuilding attribute.csv from scratch...")
        Path(ATTR_PATH).unlink(missing_ok=True)

    attr_registry = {}
    attr_ids = {}
    attr_names = {}
    attr_status = {}
    scope_ids = {}
    attr_counts = {"existing": 0, "created": 0}
    scope_counts = {"existing": 0, "created": 0}

    with open(full_unmapped_path, "r", encoding="utf-8") as f:
        ue_all = yaml.safe_load(f) or []

    unique_attributes = []
    seen_attribute_names = set()
    for entity in ue_all:
        for attr in entity.get("attributes", []):
            name = attr.get("attribute_name")
            if name and name not in seen_attribute_names:
                unique_attributes.append((name, attr))
                seen_attribute_names.add(name)

    print(f"Resolving attributes ({len(unique_attributes)} unique values)...")
    for index, (name, attr) in enumerate(unique_attributes, start=1):
        print(f"  [{index}/{len(unique_attributes)}] resolving attribute: {name!r}")
        aid, canonical_name, status = ensure_attr(
            name,
            registry=attr_registry,
            notes=attr.get("attribute_notes") or attr.get("notes", ""),
            attr_schema=attr_schema,
        )
        attr_ids[name] = aid
        attr_names[name] = canonical_name
        attr_status[name] = status
        attr_counts[status] += 1
        if status == "created":
            print(f"  + attribute: {name!r} -> {canonical_name!r}  [{aid}]")

    unique_scopes = []
    seen_scope_keys = set()
    for entity in ue:
        scope = entity.get("scope", {})
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
        token, status = ensure_scope(
            scope_type,
            value,
            scope_schema=all_schemas.get(f"{scope_type}.yaml", {}),
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
            "step_3",
            "controlled_vocabulary_resolved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            attribute_counts=attr_counts,
            scope_counts=scope_counts,
            attribute_path=str(Path(ATTR_PATH).resolve()),
        )
    return {
        "attr_ids": attr_ids,
        "attr_names": attr_names,
        "attr_status": attr_status,
        "scope_ids": scope_ids,
        "attr_counts": attr_counts,
        "scope_counts": scope_counts,
    }


def build_and_save_linked_entities(
    ue,
    ue_indices,
    all_unmapped_entities,
    unmapped_path,
    resolved_ids,
    attr_ids,
    attr_names,
    scope_ids,
    harmonisation_log=None,
):
    """Build linked entities, save them, and mark the staged source entities as mapped."""
    step_started = time.perf_counter()
    today = str(datetime.date.today())
    le_path = Path(LE_PATH)

    if le_path.exists():
        with open(le_path, "r", encoding="utf-8") as f:
            existing_linked_entities = yaml.safe_load(f) or []
    else:
        existing_linked_entities = []

    existing_numbers = [
        int(le["linked_entity_id"].split("_")[-1])
        for le in existing_linked_entities
        if str(le.get("linked_entity_id", "")).startswith("LE_")
    ]
    next_linked_number = max(existing_numbers, default=0) + 1
    linked_entities = []

    for i, entity in enumerate(ue):
        technology = entity.get("technology", {})
        scope = entity.get("scope", {})
        technology_name = entity.get("technology_name")
        linked_entities.append({
            "linked_entity_id": f"LE_{next_linked_number + i:05d}",
            "tech_id": resolved_ids["technology"].get(technology_name, ""),
            "process_id": (
                resolved_ids.get("technology_process", {}).get(technology_name, "")
                or resolved_ids["process"].get(technology.get("process_name"), "")
            ),
            "scope": {
                "geographic_scope": scope.get("geographic_scope") or scope_ids.get(("geographic_scope", get_scope_value(scope, "geographic_scope")), ""),
                "temporal_scope": scope.get("temporal_scope") or scope_ids.get(("temporal_scope", get_scope_value(scope, "temporal_scope")), ""),
                "capacity_scope": scope.get("capacity_scope") or scope_ids.get(("capacity_scope", get_scope_value(scope, "capacity_scope")), ""),
                "system_boundary": scope.get("system_boundary") or scope_ids.get(("system_boundary", get_scope_value(scope, "system_boundary")), ""),
            },
            "balancing": {
                "inputs": [
                    {
                        "carrier_id": resolved_ids["carrier"].get(x["carrier_name"], ""),
                        "share": x.get("share"),
                        "unit": x.get("unit"),
                    }
                    for x in entity.get("balancing", {}).get("inputs", [])
                    if x.get("carrier_name")
                ],
                "outputs": [
                    {
                        "carrier_id": resolved_ids["carrier"].get(x["carrier_name"], ""),
                        "share": x.get("share"),
                        "unit": x.get("unit"),
                    }
                    for x in entity.get("balancing", {}).get("outputs", [])
                    if x.get("carrier_name")
                ],
            },
            "sources": [
                {
                    "source_id": resolved_ids["source"].get(source["source_name"], ""),
                    "linked_attribute_ids": [
                        attr_ids.get(attribute_name) or f"[unregistered: {attribute_name}]"
                        for attribute_name in source.get("linked_attribute", [])
                    ],
                }
                for source in entity.get("sources", [])
                if source.get("source_name")
            ],
            "values": [
                {
                    "attribute_id": attr_ids.get(attr["attribute_name"], ""),
                    "attribute_name": attr_names.get(attr["attribute_name"], attr["attribute_name"]),
                    "value": attr.get("value"),
                    "time_index": attr.get("time_index"),
                }
                for attr in entity.get("attributes", [])
                if attr.get("attribute_name")
            ],
            "date_created": today,
        })

    all_linked_entities = existing_linked_entities + linked_entities
    le_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_le_path = le_path.with_suffix(le_path.suffix + ".tmp")
    with open(temporary_le_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(all_linked_entities, f, allow_unicode=True, sort_keys=False)
    temporary_le_path.replace(le_path)

    mark_unmapped_entities_mapped(
        unmapped_path,
        all_unmapped_entities,
        ue_indices,
        linked_entities,
        today,
    )

    print(f"Saved {len(linked_entities)} new linked entities -> {LE_PATH}")
    print(f"Updated mapping status to mapped for {len(linked_entities)} staged entities")
    for linked_entity in linked_entities:
        print(
            f"  {linked_entity['linked_entity_id']}  "
            f"tech={linked_entity['tech_id']}  "
            f"process={linked_entity['process_id']}  "
            f"scope={linked_entity['scope']}"
        )

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "step_4",
            "linked_entities_saved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            created_count=len(linked_entities),
            preserved_count=len(existing_linked_entities),
            output_path=str(le_path.resolve()),
            linked_entity_ids=[le["linked_entity_id"] for le in linked_entities],
        )
    return {
        "linked_entities": linked_entities,
        "existing_linked_entities": existing_linked_entities,
        "today": today,
    }


def save_mapping_files_step(
    ue,
    ue_indices,
    linked_entities,
    today,
    attr_ids,
    attr_names,
    attr_status,
    scope_ids,
    harmonisation_log=None,
):
    """Write provenance, attribute, and scope mapping files for the current run."""
    step_started = time.perf_counter()
    MAPPING_DIR.mkdir(parents=True, exist_ok=True)

    map_a_path = MAPPING_DIR / "unmapped_to_linked.csv"
    map_a_cols = [
        "unmapped_index", "technology_name",
        "linked_entity_id", "tech_id", "process_id",
        "geographic_scope", "temporal_scope", "capacity_scope", "system_boundary",
        "source_ids", "date_mapped",
    ]

    with open(map_a_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=map_a_cols)
        writer.writeheader()
        for source_index, entity, linked_entity in zip(ue_indices, ue, linked_entities):
            source_ids = [source["source_id"] for source in linked_entity.get("sources", [])]
            writer.writerow({
                "unmapped_index": source_index,
                "technology_name": entity.get("technology_name", ""),
                "linked_entity_id": linked_entity["linked_entity_id"],
                "tech_id": linked_entity["tech_id"],
                "process_id": linked_entity["process_id"],
                "geographic_scope": linked_entity["scope"].get("geographic_scope", ""),
                "temporal_scope": linked_entity["scope"].get("temporal_scope", ""),
                "capacity_scope": linked_entity["scope"].get("capacity_scope", ""),
                "system_boundary": linked_entity["scope"].get("system_boundary", ""),
                "source_ids": json.dumps(source_ids),
                "date_mapped": today,
            })
    print(f"Provenance map: saved {len(linked_entities)} rows -> {map_a_path}")

    attr_path = MAPPING_DIR / "attribute_map.csv"
    with open(attr_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["original_name", "attribute_name", "attribute_id", "status"],
        )
        writer.writeheader()
        for name, aid in attr_ids.items():
            writer.writerow({
                "original_name": name,
                "attribute_name": attr_names.get(name, name),
                "attribute_id": aid,
                "status": attr_status.get(name, "created"),
            })
    print(f"Entity lookup map: attribute_map.csv  ({len(attr_ids)} rows)")

    for scope_type in SCOPE_CONFIG:
        path = MAPPING_DIR / f"{scope_type}_map.csv"
        scope_entries = {value: token for (st, value), token in scope_ids.items() if st == scope_type}
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["original_value", "scope_token", "status"])
            writer.writeheader()
            for value, token in scope_entries.items():
                writer.writerow({
                    "original_value": value,
                    "scope_token": token,
                    "status": "created",
                })
        print(f"Entity lookup map: {scope_type}_map.csv  ({len(scope_entries)} rows)")

    if harmonisation_log:
        log_harmonisation_event(
            harmonisation_log,
            "step_5",
            "mapping_files_saved",
            duration_seconds=round(time.perf_counter() - step_started, 3),
            provenance_rows=len(linked_entities),
            provenance_path=str(map_a_path.resolve()),
            attribute_map_path=str(attr_path.resolve()),
            entity_mapping_paths={
                entity_type: str((MAPPING_DIR / f"{entity_type}_map.csv").resolve())
                for entity_type in ENTITY_CONFIG
            },
            scope_mapping_paths={
                scope_type: str((MAPPING_DIR / f"{scope_type}_map.csv").resolve())
                for scope_type in SCOPE_CONFIG
            },
        )
    return {
        "provenance_path": map_a_path,
        "attribute_map_path": attr_path,
    }


def finish_harmonisation_run(
    harmonisation_log,
    harmonisation_started,
    ue,
    linked_entities,
    attr_ids,
    ue_indices,
    audit_indices=None,
):
    """Generate a short audit report and close out the run log."""
    audit_indices = audit_indices or [0, 1, 2]
    audit_results = generate_audit(ue, attr_ids, indices=audit_indices, source_indices=ue_indices)

    print("=== Per-Entity Audit Report ===")
    print(f"Auditing {len(audit_results)} of {len(ue)} entities.")
    print("Each entry shows the linked entity ID and how every sub-entity")
    print("(technology, process, sources, carriers, scope) was resolved.\n")
    for entry in audit_results:
        print(json.dumps(entry, indent=2))

    log_harmonisation_event(
        harmonisation_log,
        "audit",
        "completed",
        audited_indices=audit_indices,
        audited_count=len(audit_results),
    )
    log_harmonisation_event(
        harmonisation_log,
        "run",
        "completed",
        total_duration_seconds=round(time.perf_counter() - harmonisation_started, 3),
        mapped_entities=len(linked_entities),
    )
    print(f"\nHarmonisation complete. Log saved to: {harmonisation_log}")
    return audit_results

# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------
def generate_audit(ue, attr_ids, indices=None, source_indices=None):
    """
    Build a per-entity audit report by joining the provenance map, entity lookup
    maps, and the original unmapped entity YAML data.

    Args:
        ue (list[dict]): The working slice of unmapped entities.
        attr_ids (dict[str, str]): {attribute_name: attribute_id} resolved in Step 3.
        indices (list[int] | None): Indices to audit; None audits all.
        source_indices (list[int] | None): Original indices in the staging YAML.
            When omitted, working-list indices are used.

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
                c_maps[et] = {
                    r.get("original_name", r.get(cfg["name_field"], "")): r
                    for r in csv.DictReader(f)
                }

    scope_c = {}
    for scope_type in SCOPE_CONFIG:
        path = MAPPING_DIR / f"{scope_type}_map.csv"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                scope_c[scope_type] = {r["original_value"]: r["scope_token"] for r in csv.DictReader(f)}

    if source_indices is None:
        source_indices = list(range(len(ue)))
    if len(source_indices) != len(ue):
        raise ValueError("source_indices must align with the working entity list")

    targets = indices if indices is not None else range(len(ue))
    report  = []
    for working_index in targets:
        entity = ue[working_index]
        source_index = source_indices[working_index]
        a = map_a.get(source_index, {})
        t      = entity.get("technology", {})
        report.append({
            "unmapped_index":   source_index,
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
    backup_root = Path(backup_dir)
    dest_root = backup_root / timestamp
    suffix = 1
    while dest_root.exists():
        dest_root = backup_root / f"{timestamp}_{suffix:02d}"
        suffix += 1

    data_root = MAPPING_DIR.parent.resolve()

    def backup_destination(src):
        """Return src's destination while preserving its path below motel-db."""
        try:
            relative_path = src.resolve().relative_to(data_root)
        except ValueError as exc:
            raise ValueError(
                f"Cannot back up {src}: it is outside the data root {data_root}"
            ) from exc
        return dest_root / relative_path

    flat_paths = [Path(p) for p in FLAT_FILE_SCHEMA_MAP] + SUPPLEMENTARY_PATHS
    backed_up, skipped = [], []

    for src in flat_paths:
        if src.exists():
            dest = backup_destination(src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            backed_up.append(str(src))
        else:
            skipped.append(str(src))

    if MAPPING_DIR.exists():
        dest_map = backup_destination(MAPPING_DIR)
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
