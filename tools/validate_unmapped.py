"""
Validate MOTEL staging records against the unmapped entity schemas.

Stage 1 (``unmapped_entity``) is the MOTEL deliverable: it is what a project
repository authors and what everything downstream reads. This script is the
contract check for it.

It is deliberately standalone — standard library plus PyYAML, no imports from
this repository — so a project staging its own data can copy this single file
next to its ingestion script and validate before opening a pull request.

Usage
-----
    python tools/validate_unmapped.py motel-db/unmapped_entity/
    python tools/validate_unmapped.py records.yaml --schema-dir path/to/schema
    python tools/validate_unmapped.py records.yaml --schema unmapped_entity_carrier
    python tools/validate_unmapped.py records.yaml --strict

Paths may be files or directories; directories are searched for ``*.yaml`` and
``*.yml``. The schema is auto-detected per record from its anchor field
(``technology_name`` or ``carrier_name``) unless ``--schema`` is given.

Exit status is 1 when any error is found, 0 otherwise. Warnings alone do not
fail the run unless ``--strict`` is passed.

What it checks
--------------
- every schema-required field is present and non-empty
- no unknown keys (catches typos such as ``sourc_name`` that would otherwise be
  silently dropped)
- declared types, including nested objects and arrays of objects
- ``enum`` membership
- ``schema_version`` agreement with the schema being validated against

A file whose name contains ``TEMPLATE`` is treated as showing record structure
rather than carrying data: an empty required field becomes a warning instead of
an error, so a template can ship with ``value: null`` while still being checked
for unknown keys, wrong types, and bad enum values.

It is not a full JSON Schema implementation: MOTEL's schemas use a flat subset
(``type``, ``required``, ``properties``, ``items``, ``enum``) and this covers
exactly that subset.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - dependency guidance
    sys.exit("PyYAML is required: pip install pyyaml")


# Staging schemas, keyed by the anchor field that identifies the record's subject.
ANCHOR_FIELDS = {
    "technology_name": "unmapped_entity_technology",
    "carrier_name": "unmapped_entity_carrier",
}

# JSON Schema type name -> accepted Python types. "any" accepts anything.
TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class Finding:
    """One problem found in one record."""

    def __init__(self, severity: str, source: str, index: object, path: str, message: str):
        self.severity = severity
        self.source = source
        self.index = index
        self.path = path
        self.message = message

    def __str__(self) -> str:
        where = f"{self.source}[{self.index}]"
        location = f"{where}.{self.path}" if self.path else where
        return f"  {self.severity.upper():<7} {location}: {self.message}"


def is_empty(value: object) -> bool:
    """Treat None and blank/whitespace strings as absent."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def type_name(value: object) -> str:
    """Human-readable type name for an error message."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value: object, declared: object) -> bool:
    """Check a value against a declared type, which may be a list of alternatives."""
    if declared is None or declared == "any":
        return True
    if isinstance(declared, list):
        return any(type_matches(value, option) for option in declared)
    expected = TYPE_MAP.get(declared)
    if expected is None:
        return True
    # bool is a subclass of int in Python; keep them distinct here.
    if declared in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, expected)


def check_value(value, spec, source, index, path, findings, template=False):
    """Validate one value against one schema property spec."""
    declared = spec.get("type")
    if not type_matches(value, declared):
        want = declared if isinstance(declared, str) else "/".join(map(str, declared or []))
        findings.append(Finding(
            "error", source, index, path,
            f"expected {want}, found {type_name(value)}",
        ))
        return

    enum = spec.get("enum")
    if enum and not is_empty(value) and value not in enum:
        findings.append(Finding(
            "error", source, index, path, f"{value!r} is not one of {enum}",
        ))

    if declared == "object" and isinstance(value, dict) and "properties" in spec:
        check_object(value, spec, source, index, path, findings, template)

    if declared == "array" and isinstance(value, list):
        item_spec = spec.get("items") or {}
        if item_spec:
            for position, item in enumerate(value):
                check_value(item, item_spec, source, index, f"{path}[{position}]", findings, template)


def check_object(record, schema, source, index, prefix, findings, template=False):
    """
    Validate required fields, unknown keys, and each property of one object.

    In template mode an absent required field is a warning rather than an error:
    a template exists to show the shape of a record, so its value slots are
    deliberately empty. Every other check still applies, so a typo in a template
    is still caught.
    """
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    for field in required:
        if field not in record or is_empty(record.get(field)):
            findings.append(Finding(
                "warning" if template else "error",
                source, index, f"{prefix}.{field}".lstrip("."),
                "required field is empty (expected in a template)" if template
                else "required field is missing or empty",
            ))

    for key, value in record.items():
        path = f"{prefix}.{key}".lstrip(".")
        if key not in properties:
            findings.append(Finding(
                "error", source, index, path,
                "unknown field; not declared in the schema (check the spelling)",
            ))
            continue
        if value is None:
            continue
        check_value(value, properties[key], source, index, path, findings, template)


def load_schema(schema_dir: Path, name: str) -> dict:
    path = schema_dir / f"{name}.yaml"
    if not path.exists():
        raise SystemExit(f"schema not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def pick_schema(record: dict) -> str | None:
    """Choose a staging schema from the record's anchor field."""
    present = [name for field, name in ANCHOR_FIELDS.items() if record.get(field)]
    if len(present) == 1:
        return present[0]
    return None


def is_template(path: Path) -> bool:
    """A file named *TEMPLATE* shows record structure and carries no data."""
    return "TEMPLATE" in path.stem.upper()


def validate_file(path: Path, schemas: dict, forced: str | None) -> list[Finding]:
    findings: list[Finding] = []
    source = path.name
    template = is_template(path)
    try:
        records = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [Finding("error", source, "-", "", f"file is not valid YAML: {exc}")]

    if records is None:
        return [Finding("warning", source, "-", "", "file is empty")]
    if isinstance(records, dict):
        # A bare mapping is a single-record document. Reference examples are
        # written this way, but the harmonisation loader iterates a list, so a
        # file destined for the pipeline has to be a list even when it holds one
        # record. Accept it here and say so rather than failing a valid example.
        findings.append(Finding(
            "warning", source, "-", "",
            "single record at the top level; wrap it in a list before using it as "
            "pipeline input, which expects a sequence of records",
        ))
        records = [records]
    elif not isinstance(records, list):
        return [Finding("error", source, "-", "",
                        f"expected a list of records, found {type_name(records)}")]

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            findings.append(Finding("error", source, index, "",
                                    f"expected a record object, found {type_name(record)}"))
            continue

        name = forced or pick_schema(record)
        if name is None:
            anchors = " or ".join(sorted(ANCHOR_FIELDS))
            findings.append(Finding(
                "error", source, index, "",
                f"cannot tell which schema applies: set exactly one of {anchors}, "
                "or pass --schema",
            ))
            continue

        schema = schemas[name]
        declared = record.get("schema_version")
        expected = schema.get("schema_version")
        if declared and expected and str(declared) != str(expected):
            findings.append(Finding(
                "warning", source, index, "schema_version",
                f"record targets {declared}, validating against {expected}",
            ))
        elif not declared and not template:
            findings.append(Finding(
                "warning", source, index, "schema_version",
                f"not set; recommend \"{expected}\" so the contract is pinned",
            ))

        check_object(record, schema, source, index, "", findings, template)

    return findings


def collect_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.yaml") if p.is_file()))
            files.extend(sorted(p for p in path.rglob("*.yml") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise SystemExit(f"no such file or directory: {target}")
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate MOTEL staging records against the unmapped entity schemas.",
    )
    parser.add_argument("targets", nargs="+", help="YAML files or directories to check")
    parser.add_argument("--schema-dir", default=None,
                        help="directory holding the schema YAML files (default: <repo>/schema)")
    parser.add_argument("--schema", choices=sorted(set(ANCHOR_FIELDS.values())), default=None,
                        help="force one schema instead of detecting it per record")
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures")
    args = parser.parse_args(argv)

    schema_dir = Path(args.schema_dir) if args.schema_dir else Path(__file__).resolve().parents[1] / "schema"
    schemas = {name: load_schema(schema_dir, name) for name in set(ANCHOR_FIELDS.values())}

    files = collect_files(args.targets)
    if not files:
        print("No YAML files found.")
        return 0

    errors = warnings = 0
    for path in files:
        findings = validate_file(path, schemas, args.schema)
        file_errors = [f for f in findings if f.severity == "error"]
        file_warnings = [f for f in findings if f.severity == "warning"]
        errors += len(file_errors)
        warnings += len(file_warnings)

        status = "FAIL" if file_errors else ("warn" if file_warnings else "ok")
        label = " (template: structure only)" if is_template(path) else ""
        print(f"[{status}] {path}{label}")
        for finding in findings:
            print(finding)

    print(f"\n{len(files)} file(s) checked — {errors} error(s), {warnings} warning(s)")
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
