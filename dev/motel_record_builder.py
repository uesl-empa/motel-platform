from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from pydantic import BaseModel, Field


# Controlled-vocabulary stubs (extend as needed)
class AttributeRef(BaseModel):
    attribute_id: str
    attribute_name: Optional[str] = None
    attribute_unit: Optional[str] = None


class GeographicScope(BaseModel):
    geographic_scope: str
    geographic_scope_description: Optional[str] = None


class TemporalScope(BaseModel):
    temporal_scope: str
    temporal_scope_description: Optional[str] = None


class CapacityScope(BaseModel):
    capacity_scope: str
    capacity_scope_description: Optional[str] = None


class SystemBoundary(BaseModel):
    system_boundary: str
    system_boundary_description: Optional[str] = None


class Version(BaseModel):
    version_number: str = Field(..., examples=["1.0"])
    date_created: date
    date_modified: date


class Scope(BaseModel):
    geographic_scope: str = Field(..., description="e.g. GEO_CH, GEO_EU")
    temporal_scope: str = Field(..., description="e.g. TIME_2030")
    capacity_scope: str = Field(..., description="e.g. CAP_UTILITY")
    system_boundary: str = Field(..., description="e.g. COND_ISO_BASELOAD")


class ValueItem(BaseModel):
    attribute_id: str = Field(..., description="e.g. ATTR_CAPEX")
    value: Any = Field(..., description="numeric, text, bool, list, or dict")
    value_format: str = Field(..., description="int | float | controlled_vocab")
    value_type: str = Field(
        ..., description="numeric | text | boolean | array | timeseries | distribution"
    )
    unit: str = Field(..., description="e.g. CHF/kW, fraction, years")
    uncertainty: Optional[Union[float, dict[str, float]]] = None
    note: Optional[str] = None


class Record(BaseModel):
    record_id: str = Field(..., description="e.g. REC_001")
    version: Version
    tech_id: str = Field(..., description="FK -> tech.tech_id")
    source_id: str = Field(..., description="FK -> source.source_id")
    assumption_id: Optional[str] = None
    scope: Scope
    values: list[ValueItem] = Field(default_factory=list, min_length=1)

    def display(self) -> None:
        import pprint

        pprint.pprint(self.model_dump())


class Tech(BaseModel):
    tech_id: str
    technology_name: str
    ehubx_tech_id: Optional[str] = None
    ontology_iri: Optional[str] = None
    process_id: Optional[str] = None


class Source(BaseModel):
    source_id: str
    source_description: str
    source_type: str = Field(..., description="report|database|article|website|book|other")
    link: Optional[str] = None
    access_date: Optional[date] = None
    pdf_backup: Optional[str] = None
    confidence_level: Optional[str] = Field(None, description="high|medium|low")
    assessment_method: Optional[str] = Field(
        None,
        description="measured|modeled|estimated|survey|manufacturer_spec|literature",
    )
    assessment_date: Optional[date] = None


class Contributor(BaseModel):
    contributor_id: str
    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None


class Process(BaseModel):
    process_id: str
    process_name: str
    process_description: Optional[str] = None
    process_type: Optional[str] = None
    process_category: Optional[str] = None


class MotelDataStore(BaseModel):
    tech: dict[str, Tech] = Field(default_factory=dict)
    source: dict[str, Source] = Field(default_factory=dict)
    contributor: dict[str, Contributor] = Field(default_factory=dict)
    process: dict[str, Process] = Field(default_factory=dict)
    geographic_scope: set[str] = Field(default_factory=set)
    temporal_scope: set[str] = Field(default_factory=set)
    capacity_scope: set[str] = Field(default_factory=set)
    system_boundary: set[str] = Field(default_factory=set)
    records: list[Record] = Field(default_factory=list)


class RecordCheckItem(BaseModel):
    field: str
    value: str
    dataset: str
    exists: bool
    suggestion: str


class RecordCheckReport(BaseModel):
    ready: bool
    items: list[RecordCheckItem]

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([item.model_dump() for item in self.items])


_record_counter = 0


def next_record_id() -> str:
    global _record_counter
    _record_counter += 1
    return f"REC_{_record_counter:03d}"


def build_secondary_index(
    tech_items: Optional[list[Tech]] = None,
    source_items: Optional[list[Source]] = None,
) -> dict[str, set[str]]:
    """Build a simple lookup index for secondary datasets used by Record FKs."""
    tech_ids = {item.tech_id for item in (tech_items or [])}
    source_ids = {item.source_id for item in (source_items or [])}
    return {"tech": tech_ids, "source": source_ids}


def validate_secondary_references(
    *,
    tech_id: str,
    source_id: str,
    secondary_index: dict[str, set[str]],
) -> None:
    """Ensure record foreign keys exist in the already created secondary datasets."""
    missing_messages: list[str] = []

    tech_ids = secondary_index.get("tech", set())
    if tech_id not in tech_ids:
        missing_messages.append(
            f"tech_id '{tech_id}' not found in secondary dataset 'tech'."
        )

    source_ids = secondary_index.get("source", set())
    if source_id not in source_ids:
        missing_messages.append(
            f"source_id '{source_id}' not found in secondary dataset 'source'."
        )

    if missing_messages:
        joined = " ".join(missing_messages)
        raise ValueError(
            "Record creation blocked: missing secondary dataset references. "
            f"{joined}"
        )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _non_empty_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        if any((v or "").strip() for v in row.values()):
            out.append(row)
    return out


def load_data_store(dataset_dir: Path) -> MotelDataStore:
    """Load existing secondary/supplementary/control-vocabulary CSVs into one object."""
    store = MotelDataStore()

    tech_rows = _non_empty_rows(_read_csv_rows(dataset_dir / "tech.csv"))
    for row in tech_rows:
        tech_id = (row.get("tech_id") or "").strip()
        if not tech_id:
            continue
        store.tech[tech_id] = Tech(
            tech_id=tech_id,
            technology_name=(row.get("technology_name") or tech_id).strip(),
            ehubx_tech_id=(row.get("ehubx_tech_id") or None),
            ontology_iri=(row.get("ontology_iri") or None),
            process_id=(row.get("process_id") or None),
        )

    source_rows = _non_empty_rows(_read_csv_rows(dataset_dir / "source.csv"))
    for row in source_rows:
        source_id = (row.get("source_id") or "").strip()
        if not source_id:
            continue
        store.source[source_id] = Source(
            source_id=source_id,
            source_description=(row.get("source_description") or source_id).strip(),
            source_type=(row.get("source_type") or "other").strip(),
            link=(row.get("link") or None),
            pdf_backup=(row.get("pdf_backup") or None),
            confidence_level=(row.get("confidence_level") or None),
            assessment_method=(row.get("assessment_method") or None),
        )

    contributor_rows = _non_empty_rows(_read_csv_rows(dataset_dir / "contributor.csv"))
    for row in contributor_rows:
        contributor_id = (row.get("contributor_id") or "").strip()
        if not contributor_id:
            continue
        store.contributor[contributor_id] = Contributor(
            contributor_id=contributor_id,
            name=(row.get("name") or contributor_id).strip(),
            affiliation=(row.get("affiliation") or None),
            email=(row.get("email") or None),
        )

    process_rows = _non_empty_rows(_read_csv_rows(dataset_dir / "process.csv"))
    for row in process_rows:
        process_id = (row.get("process_id") or "").strip()
        if not process_id:
            continue
        store.process[process_id] = Process(
            process_id=process_id,
            process_name=(row.get("process_name") or process_id).strip(),
            process_description=(row.get("process_description") or None),
            process_type=(row.get("process_type") or None),
            process_category=(row.get("process_category") or None),
        )

    def _load_id_set(file_name: str, key: str) -> set[str]:
        rows = _non_empty_rows(_read_csv_rows(dataset_dir / file_name))
        return {(r.get(key) or "").strip() for r in rows if (r.get(key) or "").strip()}

    store.geographic_scope = _load_id_set("geographic_scope.csv", "geographic_scope")
    store.temporal_scope = _load_id_set("temporal_scope.csv", "temporal_scope")
    store.capacity_scope = _load_id_set("capacity_scope.csv", "capacity_scope")
    store.system_boundary = _load_id_set("system_boundary.csv", "system_boundary")

    return store


def register_tech(store: MotelDataStore, tech: Tech) -> None:
    store.tech[tech.tech_id] = tech


def register_source(store: MotelDataStore, source: Source) -> None:
    store.source[source.source_id] = source


def register_scope_value(store: MotelDataStore, scope_type: str, value: str) -> None:
    if scope_type == "geographic_scope":
        store.geographic_scope.add(value)
    elif scope_type == "temporal_scope":
        store.temporal_scope.add(value)
    elif scope_type == "capacity_scope":
        store.capacity_scope.add(value)
    elif scope_type == "system_boundary":
        store.system_boundary.add(value)
    else:
        raise ValueError(f"Unsupported scope type '{scope_type}'.")


def check_record_dependencies(
    *,
    draft: dict[str, Any],
    store: MotelDataStore,
) -> RecordCheckReport:
    checks: list[RecordCheckItem] = []

    def _add(field: str, dataset: str, exists: bool, value: str) -> None:
        if exists:
            suggestion = "existing"
        else:
            suggestion = f"create new {dataset} entry for '{value}'"
        checks.append(
            RecordCheckItem(
                field=field,
                value=value,
                dataset=dataset,
                exists=exists,
                suggestion=suggestion,
            )
        )

    tech_id = str(draft.get("tech_id") or "")
    source_id = str(draft.get("source_id") or "")
    geographic_scope = str(draft.get("geographic_scope") or "")
    temporal_scope = str(draft.get("temporal_scope") or "")
    capacity_scope = str(draft.get("capacity_scope") or "")
    system_boundary = str(draft.get("system_boundary") or "")

    _add("tech_id", "tech", tech_id in store.tech, tech_id)
    _add("source_id", "source", source_id in store.source, source_id)
    _add(
        "geographic_scope",
        "geographic_scope",
        geographic_scope in store.geographic_scope,
        geographic_scope,
    )
    _add(
        "temporal_scope",
        "temporal_scope",
        temporal_scope in store.temporal_scope,
        temporal_scope,
    )
    _add(
        "capacity_scope",
        "capacity_scope",
        capacity_scope in store.capacity_scope,
        capacity_scope,
    )
    _add(
        "system_boundary",
        "system_boundary",
        system_boundary in store.system_boundary,
        system_boundary,
    )

    ready = all(item.exists for item in checks)
    return RecordCheckReport(ready=ready, items=checks)


def create_record_if_ready(
    *,
    draft: dict[str, Any],
    store: MotelDataStore,
) -> Record:
    report = check_record_dependencies(draft=draft, store=store)
    missing = [item for item in report.items if not item.exists]
    if missing:
        details = "; ".join(f"{m.field}={m.value}" for m in missing)
        raise ValueError(
            "Record not added. Missing dependencies detected: "
            f"{details}. Add these entities first, then retry."
        )

    record = create_record(
        tech_id=str(draft["tech_id"]),
        source_id=str(draft["source_id"]),
        geographic_scope=str(draft["geographic_scope"]),
        temporal_scope=str(draft["temporal_scope"]),
        capacity_scope=str(draft["capacity_scope"]),
        system_boundary=str(draft["system_boundary"]),
        values=list(draft["values"]),
        record_id=draft.get("record_id"),
        assumption_id=draft.get("assumption_id"),
        version_number=str(draft.get("version_number", "1.0")),
        secondary_index=build_secondary_index(
            tech_items=list(store.tech.values()),
            source_items=list(store.source.values()),
        ),
    )
    store.records.append(record)
    return record


def export_data_store_csv(store: MotelDataStore, dataset_dir: Path) -> list[Path]:
    """Persist current in-memory secondary/supplementary/scope datasets to CSV files."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    tech_path = dataset_dir / "tech.csv"
    with tech_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["tech_id", "technology_name", "ehubx_tech_id", "ontology_iri", "process_id"])
        for item in store.tech.values():
            writer.writerow([
                item.tech_id,
                item.technology_name,
                item.ehubx_tech_id or "",
                item.ontology_iri or "",
                item.process_id or "",
            ])
    written.append(tech_path)

    source_path = dataset_dir / "source.csv"
    with source_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source_id",
            "source_description",
            "source_type",
            "link",
            "access_date",
            "pdf_backup",
            "confidence_level",
            "assessment_method",
            "assessment_date",
        ])
        for item in store.source.values():
            writer.writerow([
                item.source_id,
                item.source_description,
                item.source_type,
                item.link or "",
                item.access_date.isoformat() if item.access_date else "",
                item.pdf_backup or "",
                item.confidence_level or "",
                item.assessment_method or "",
                item.assessment_date.isoformat() if item.assessment_date else "",
            ])
    written.append(source_path)

    contributor_path = dataset_dir / "contributor.csv"
    with contributor_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["contributor_id", "name", "affiliation", "email"])
        for item in store.contributor.values():
            writer.writerow([item.contributor_id, item.name, item.affiliation or "", item.email or ""])
    written.append(contributor_path)

    process_path = dataset_dir / "process.csv"
    with process_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "process_id",
            "process_name",
            "process_description",
            "process_type",
            "process_category",
        ])
        for item in store.process.values():
            writer.writerow([
                item.process_id,
                item.process_name,
                item.process_description or "",
                item.process_type or "",
                item.process_category or "",
            ])
    written.append(process_path)

    for name, values in [
        ("geographic_scope", store.geographic_scope),
        ("temporal_scope", store.temporal_scope),
        ("capacity_scope", store.capacity_scope),
        ("system_boundary", store.system_boundary),
    ]:
        path = dataset_dir / f"{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([name])
            for value in sorted(values):
                writer.writerow([value])
        written.append(path)

    return written


def create_record(
    *,
    tech_id: str,
    source_id: str,
    geographic_scope: str,
    temporal_scope: str,
    capacity_scope: str,
    system_boundary: str,
    values: list[dict[str, Any]],
    record_id: Optional[str] = None,
    assumption_id: Optional[str] = None,
    version_number: str = "1.0",
    date_created: Optional[date] = None,
    date_modified: Optional[date] = None,
    secondary_index: dict[str, set[str]],
) -> Record:
    today = date.today()
    validate_secondary_references(
        tech_id=tech_id,
        source_id=source_id,
        secondary_index=secondary_index,
    )

    return Record(
        record_id=record_id or next_record_id(),
        version=Version(
            version_number=version_number,
            date_created=date_created or today,
            date_modified=date_modified or today,
        ),
        tech_id=tech_id,
        source_id=source_id,
        assumption_id=assumption_id,
        scope=Scope(
            geographic_scope=geographic_scope,
            temporal_scope=temporal_scope,
            capacity_scope=capacity_scope,
            system_boundary=system_boundary,
        ),
        values=[ValueItem(**v) for v in values],
    )


def parse_schema_entities(schema_path: Path) -> dict[str, str]:
    raw_text = schema_path.read_text(encoding="utf-8")
    section_re = re.compile(r"^(\w+):\s*$", re.MULTILINE)
    type_re = re.compile(r"_type:\s*(\w+)")

    sections: dict[str, str] = {}
    entity_names = section_re.findall(raw_text)
    for name in entity_names:
        block_match = re.search(
            rf"^{name}:.*?(?=^\w|\Z)", raw_text, re.MULTILINE | re.DOTALL
        )
        if block_match:
            t = type_re.search(block_match.group())
            sections[name] = t.group(1) if t else "unknown"
    return sections


def records_to_dataframe(records: list[Record]) -> pd.DataFrame:
    rows = []
    for rec in records:
        base = {
            "record_id": rec.record_id,
            "version_number": rec.version.version_number,
            "date_created": rec.version.date_created,
            "date_modified": rec.version.date_modified,
            "tech_id": rec.tech_id,
            "source_id": rec.source_id,
            "assumption_id": rec.assumption_id,
            "geographic_scope": rec.scope.geographic_scope,
            "temporal_scope": rec.scope.temporal_scope,
            "capacity_scope": rec.scope.capacity_scope,
            "system_boundary": rec.scope.system_boundary,
        }
        for v in rec.values:
            rows.append({**base, **v.model_dump()})
    return pd.DataFrame(rows)


def export_records_jsonl(records: list[Record], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(rec.model_dump_json() + "\n")
    return output_path


def export_records_csv(records: list[Record], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = records_to_dataframe(records)
    df.to_csv(output_path, index=False)
    return output_path


def _extract_top_level_fields(block_text: str) -> list[str]:
    fields: list[str] = []
    for line in block_text.splitlines()[1:]:
        if re.match(r"^    [A-Za-z_][A-Za-z0-9_]*:\s*", line):
            key = line.strip().split(":", 1)[0]
            if not key.startswith("_"):
                fields.append(key)
    return fields


def _extract_nested_fields(block_text: str, parent_key: str) -> list[str]:
    pattern = re.compile(
        rf"^    {re.escape(parent_key)}:\s*$.*?(?=^    [A-Za-z_]|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(block_text)
    if not match:
        return []
    nested = []
    for line in match.group().splitlines()[1:]:
        m = re.match(r"^        ([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", line)
        if m and not m.group(1).startswith("_"):
            nested.append(m.group(1))
    return nested


def _extract_value_item_fields(block_text: str) -> list[str]:
    values_block = re.search(
        r"^    values:\s*$.*?(?=^    [A-Za-z_]|\Z)", block_text, re.MULTILINE | re.DOTALL
    )
    if not values_block:
        return []
    item_block = re.search(
        r"^        _item:\s*$.*?(?=^        [A-Za-z_]|\Z)",
        values_block.group(),
        re.MULTILINE | re.DOTALL,
    )
    if not item_block:
        return []
    fields = []
    for line in item_block.group().splitlines()[1:]:
        m = re.match(r"^            ([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", line)
        if m and not m.group(1).startswith("_"):
            fields.append(m.group(1))
    return fields


def schema_headers(schema_path: Path) -> dict[str, list[str]]:
    raw_text = schema_path.read_text(encoding="utf-8")
    entities = re.findall(r"^(\w+):\s*$", raw_text, flags=re.MULTILINE)

    out: dict[str, list[str]] = {}
    for entity in entities:
        block = re.search(
            rf"^{entity}:.*?(?=^\w|\Z)", raw_text, flags=re.MULTILINE | re.DOTALL
        )
        if not block:
            continue
        block_text = block.group()

        if entity == "record":
            headers = [
                "record_id",
                "version_number",
                "date_created",
                "date_modified",
                "tech_id",
                "source_id",
                "assumption_id",
                "geographic_scope",
                "temporal_scope",
                "capacity_scope",
                "system_boundary",
            ] + _extract_value_item_fields(block_text)
            out[entity] = headers
            continue

        fields = _extract_top_level_fields(block_text)
        if "version" in fields:
            fields.remove("version")
            fields.extend([f"version.{f}" for f in _extract_nested_fields(block_text, "version")])
        if "scope" in fields:
            fields.remove("scope")
            fields.extend([f"scope.{f}" for f in _extract_nested_fields(block_text, "scope")])
        if "values" in fields:
            fields.remove("values")
            fields.extend([f"values.{f}" for f in _extract_value_item_fields(block_text)])
        out[entity] = fields

    return out


def export_dataset_csv_templates(schema_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    headers_map = schema_headers(schema_path)

    paths: list[Path] = []
    for entity, headers in headers_map.items():
        path = output_dir / f"{entity}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
        paths.append(path)
    return paths
