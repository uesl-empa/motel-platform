# author: Barton Chen
# Date: 2026-06-21
# This script contains helper functions for the Refuel ingestion pipeline, including data cleaning, 
# parsing, and transformation utilities.


import math
import re
from copy import deepcopy
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yaml

## --- supportive functions

ATTRIBUTE_NAMES = [
    "technical_efficiency",
    "trl",
    "tech_maturity",
    "reference_unit_size",
    "theoretical_efficiency",
    "operating_temperature_c",
    "min_installation_size",
    "lifetime_yr",
    "capex_per_capacity",
    "capex_one_time",
    "opex_fix_pct_of_capex",
    "opex_per_capacity_yr",
    "opex_per_energy",
    "discount_rate_pct",
    "uncertainty_rating",
    "storage_carrier",
    "min_installation",
    "charging_capacity_factor",
    "discharging_capacity_factor",
    "charging_efficiency",
    "discharging_efficiency",
    "min_soc",
    "max_soc",
    "standby_loss_per_hour",
    "capex_per_stor_capacity",
    "opex_one_time",
    "opex_per_stor_capacity_yr",
]

STANDARD_SHEETS = ["ConvTech", "StorTech"]
EMBEDDEDCARBON_SCENARIOS = {
    "ssp2_ndc": ["ssp2_ndc_2025", "ssp2_ndc_2030", "ssp2_ndc_2040", "ssp2_ndc_2050"],
    "ssp2_pkbudg1000": [
        "ssp2_pkbudg1000_2025",
        "ssp2_pkbudg1000_2030",
        "ssp2_pkbudg1000_2040",
        "ssp2_pkbudg1000_2050",
    ],
}
EMBEDDEDCARBON_YEARS = [2025, 2030, 2040, 2050]

def is_nan(value):
    """Checks if a value is None or NaN."""
    return value is None or (
        isinstance(value, float) and math.isnan(value)
    )

def clean(value):
    """Returns None if the value is NaN, otherwise returns the original value."""
    return None if is_nan(value) else value

def split_csv(value):
    if is_nan(value):
        return []
    return [
        x.strip()
        for x in str(value).split(",")
        if x.strip() and x.strip().lower() not in {"na", "nan"}
    ]

def split_csv_float(value):
    out = []
    for token in split_csv(value):
        try:
            out.append(float(token))
        except ValueError:
            out.append(None)
    return out

def normalize_unit(unit_text):
    if is_nan(unit_text):
        return None
    unit = str(unit_text).strip()
    if not unit or unit == "-":
        return None
    return unit


def find_project_root(start: Path | None = None) -> Path:
    """Find the repository root from any path inside motel-platform."""
    start = (start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "motel-db").is_dir() and (candidate / "schema_human").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate the repository root. Start the notebook from inside motel-platform."
    )


def get_refuel_paths(project_root: Path | None = None) -> dict[str, Path]:
    """Return the key notebook, data, schema, and output paths for this pipeline."""
    root = (project_root or find_project_root()).resolve()
    example_dir = root / "1_ingest" / "examples" / "refuel"
    return {
        "project_root": root,
        "example_dir": example_dir,
        "notebook_path": example_dir / "ingestion_pipeline.ipynb",
        "workbook_path": example_dir / "input" / "reFuel_TechDatabase_Clean_2026-06-03.xlsx",
        "schema_path": root / "schema_human" / "unmapped_entity.yaml",
        "staging_path": root / "motel-db" / "unmapped_entity" / "unmapped_entities_refuel.yaml",
        "convtech_output": example_dir / "output" / "unmapped_entities_refuel_convtech.yaml",
        "stortech_output": example_dir / "output" / "unmapped_entities_refuel_stortech.yaml",
        "embeddedcarbon_output": example_dir / "output" / "unmapped_entities_refuel_embeddedcarbon.yaml",
    }


def first_present(mapping, *keys):
    """Return the first non-empty value from a mapping for the provided keys."""
    for key in keys:
        if key not in mapping:
            continue
        value = clean(mapping.get(key))
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() == "nan":
            continue
        return text
    return None


def normalize_source_type(raw_type):
    """Map source-medium labels to the source schema enum."""
    value = first_present({"value": raw_type}, "value")
    if value is None:
        return None

    token = value.strip().lower()
    lookup = {
        "article": "article",
        "journal article": "article",
        "paper": "article",
        "report": "report",
        "database": "database",
        "web": "website",
        "website": "website",
        "url": "website",
        "book": "book",
    }
    return lookup.get(token, "other")


def build_unmapped_source(ref_row, linked_attrs):
    """Convert one reference-sheet row into an unmapped source record."""
    source = {
        "source_name": first_present(ref_row, "source_id", "reference_id", "id"),
        "source_description": first_present(ref_row, "description", "title", "source_description"),
        "source_type": normalize_source_type(
            first_present(ref_row, "reference_type", "source_type", "type")
        ),
        "link": first_present(ref_row, "doi_or_url", "link", "url", "doi"),
        "access_date": first_present(ref_row, "access_date"),
        "confidence_level": first_present(ref_row, "confidence_level"),
        "assessment_method": first_present(ref_row, "assessment_method"),
        "reference_year": first_present(ref_row, "reference_year", "publication_year", "year", "assessment_year"),
        "source_locator": first_present(ref_row, "comments", "assessment_notes", "source_locator", "note"),
        "linked_attribute": sorted(linked_attrs),
    }
    return {key: value for key, value in source.items() if value is not None}

def prepare_df(df_raw):
    """Normalize ConvTech table where row 1 contains machine-friendly headers."""
    df = df_raw.copy()
    header_idx = 1
    df.columns = [str(c).strip() for c in df.loc[header_idx]]
    df = df.loc[header_idx + 1:].reset_index(drop=True)

    # Remove section/header-like rows
    if "tech_id" in df.columns:
        df = df[df["tech_id"].notna()]
        df = df[df["tech_id"].astype(str).str.strip().str.lower() != "nan"]
        df = df[df["tech_id"].astype(str).str.strip().str.lower() != "tech_id"]
    if "unit_operation" in df.columns:
        df = df[df["unit_operation"].notna()]

    return df.reset_index(drop=True)


def apply_manual_fixes(workbook: dict[str, pd.DataFrame]) -> None:
    """Apply source-specific cleanup that should happen before transformation."""
    convtech = workbook["ConvTech"]

    for field_name in ["min_installation_size", "operating_temperature_c"]:
        column_index = convtech.iloc[1].tolist().index(field_name)
        column_name = convtech.columns[column_index]
        convtech[column_name] = convtech[column_name].replace(0, None)


def limit_sheet_rows(
    df: pd.DataFrame,
    sheet_name: str,
    sample_limit: int | None = None,
) -> pd.DataFrame:
    """Optionally trim a sheet to a small sample for notebook testing."""
    if sample_limit is None:
        print(f"{sheet_name}: using all {len(df)} rows")
        return df

    sample_limit = int(sample_limit)
    if sample_limit <= 0:
        raise ValueError("sample_limit must be None or a positive integer")

    df_limited = df.head(sample_limit).copy()
    print(f"{sheet_name}: using {len(df_limited)} of {len(df)} rows for testing")
    return df_limited


def load_workbook(workbook_path: Path | str) -> dict[str, pd.DataFrame]:
    """Load the reFuel workbook and apply source-specific cleanup."""
    workbook = pd.read_excel(workbook_path, sheet_name=None)
    apply_manual_fixes(workbook)
    return workbook


def load_schema(schema_path: Path | str) -> dict:
    """Load the simplified unmapped-entity schema used for notebook context."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_reference_data(workbook: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Extract and normalize the Reference sheet."""
    df_ref = workbook["Reference"].copy()
    df_ref.columns = df_ref.iloc[0]
    return df_ref.iloc[1:].reset_index(drop=True)


def load_attribute_data(
    workbook: dict[str, pd.DataFrame],
    attribute_names: list[str] | None = None,
) -> pd.DataFrame:
    """Extract the attribute metadata used during unmapped-entity conversion."""
    attribute_names = attribute_names or ATTRIBUTE_NAMES
    df_attr = workbook["Metadata"].copy()
    df_attr = df_attr[df_attr["Variable Name"].isin(attribute_names)].reset_index(drop=True)
    df_attr = df_attr.set_index("Variable Name")
    return df_attr[["Column Header", "Unit / Format", "Allowed Values", "Description", "Note"]].copy()


def load_nomenclature_data(workbook: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Extract the Nomenclature sheet used to expand controlled-vocabulary notes."""
    df_nom = workbook["Nomenclature"].copy()
    return df_nom.fillna("")


def load_carrier_data(workbook: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Extract the Carrier sheet used to enrich balancing carriers."""
    df_carrier = workbook["Carrier"].copy()
    return df_carrier.fillna("")


def build_ingestion_context(workbook: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Bundle the workbook-derived context needed by the converters."""
    return {
        "df_ref": load_reference_data(workbook),
        "df_attr": load_attribute_data(workbook),
        "df_nom": load_nomenclature_data(workbook),
        "df_carrier": load_carrier_data(workbook),
    }



## --- functions to get sources/references

def get_src_attrs(source_text):
    if not source_text or not source_text.strip():
        return []

    # Collect: source_id -> set of linked attributes
    source_to_attrs: dict[str, set] = defaultdict(set)

    # Split on ";" to get individual attribute-group : source(s) segments
    segments = re.split(r";", source_text)

    for segment in segments:
        segment = segment.strip().rstrip(";").strip()
        if not segment:
            continue

        # Split on ":" — left side = quoted attribute names, right side = source IDs
        parts = segment.split(":", 1)
        if len(parts) != 2:
            continue

        attrs_part, sources_part = parts[0].strip(), parts[1].strip()

        # Extract attribute names (quoted strings)
        attributes = re.findall(r'"([^"]+)"', attrs_part)
        attributes = [a.strip() for a in attributes if a.strip()]

        # Extract source IDs (comma-separated, unquoted identifiers)
        # Remove any trailing punctuation or whitespace
        raw_sources = [s.strip().strip('"').strip() for s in sources_part.split(",")]
        source_ids = [s for s in raw_sources if s and s.lower() != "missing"]

        for source_id in source_ids:
            source_to_attrs[source_id].update(attributes)
    
    return source_to_attrs

def parse_source_text(source_text: str, df_ref: pd.DataFrame) -> list[dict]:
    """
    Parse a raw source_text string of the form:
        "attr1", "attr2": source_id_A; "attr3": source_id_B, source_id_C;
    
    Returns a list of source dicts following the unmapped_record schema:
        [
            {
                "source_name": "source_id_A",
                "source_description": "Full reference title",
                "source_type": "article",
                "link": "https://doi.org/...",
                "access_date": "2026-06-03",
                "source_locator": "page or curation comments",
                "linked_attribute": ["attr1", "attr2"]
            },
            ...
        ]
    
    Notes:
    - A single attribute can be linked to multiple source IDs (comma-separated after the colon).
    - Duplicate source IDs across segments are merged: their linked_attributes are unioned.
    - Source IDs equal to "missing" are skipped.
    """
    
    source_to_attrs = get_src_attrs(source_text)

    # Build the sources array
    sources = []
    for source_id, linked_attrs in source_to_attrs.items():
        src_name = source_id  # Use source_id directly if no mapping is provided

        ## get source data from `ds_src`
        df = df_ref[df_ref['source_id']==src_name]
        if len(df) == 0:
            print(f'Cannot find source_id "{source_id}" in source dataset')
        elif len(df) > 1:
            print(f'Multiple entries found for source_id "{source_id}" in source dataset; using the first match.')
        else:
            di_src = df.iloc[0].to_dict()
            sources.append(build_unmapped_source(di_src, linked_attrs))

    return sources

def add_sources_to_record(record: dict, source_text: str, df_ref: pd.DataFrame) -> dict:
    """
    Parse source_text and inject a 'sources' key into the record.

    Args:
        record:      The unmapped_record dict (modified in-place and returned).
        source_text: Raw string from row.get("list_of_source_id").
        df_ref:       A pandas DataFrame containing source information.

    Returns:
        The same record dict with 'sources' populated.
    """
    if source_text == source_text:      # skip if source_text is NaN
        record["sources"] = parse_source_text(source_text, df_ref)
    return record



## --- functions to get attributes

def build_nomenclature_lookup(df_nom: pd.DataFrame) -> dict[str, str]:
    """Create a case-insensitive lookup of nomenclature term -> definition."""
    lookup = {}
    for _, row in df_nom.iterrows():
        term = first_present(row, "Term / Abbreviation", "Term", "Abbreviation")
        definition = first_present(row, "Definition", "Description")
        if term and definition:
            lookup[str(term).strip().lower()] = str(definition).strip()
    return lookup


def build_carrier_lookup(df_carrier: pd.DataFrame) -> dict[str, str]:
    """Create a case-insensitive lookup of carrier token -> descriptive notes."""
    lookup = {}
    for _, row in df_carrier.iterrows():
        keys = [
            first_present(row, "Carrier Abbreviation", "carrier_abbreviation"),
            first_present(row, "Carrier", "carrier_name"),
        ]
        desc = first_present(row, "Carrier Description", "Description")
        ctype = first_present(row, "Carrier Type", "Type")
        parts = []
        if desc:
            parts.append(f"Description: {desc}")
        if ctype:
            parts.append(f"Type: {ctype}")
        note = " | ".join(parts)
        if not note:
            continue
        for key in keys:
            if key:
                lookup[str(key).strip().lower()] = note
    return lookup


def build_nomenclature_context(text, nomenclature_lookup: dict[str, str]) -> str:
    """Attach relevant nomenclature definitions referenced by the metadata note text."""
    text = str(text or "")
    if not text.strip() or not nomenclature_lookup:
        return ""

    matches = []
    lowered = text.lower()
    for term, definition in nomenclature_lookup.items():
        if len(term) < 3:
            continue
        if term in lowered:
            matches.append(f"{term}: {definition}")

    if not matches and "nomenclature" not in lowered:
        return ""

    if not matches:
        return " | CV context: source note refers to the Nomenclature sheet."

    return " | CV context: " + " ; ".join(dict.fromkeys(matches))


def get_attr_note(row: pd.Series, nomenclature_lookup: dict[str, str] | None = None) -> str:
    """Extract a structured attribute note and expand any nomenclature references."""
    parts = []
    for key in ["Column Header", "Unit / Format", "Allowed Values", "Description", "Note"]:
        value = clean(row.get(key))
        if value is not None:
            parts.append(f"{key}: {value}")

    note = ", ".join(parts)
    note += build_nomenclature_context(note, nomenclature_lookup or {})
    return note


def add_attributes_to_record(
    ue: dict,
    row: pd.Series,
    df_attr: pd.DataFrame,
    nomenclature_lookup: dict[str, str] | None = None,
) -> dict:
    """
    Extracts attribute-related fields from a DataFrame row and adds them to the unmapped_record.

    Args:
        ue:  The unmapped_record dict (modified in-place and returned).
        row: A pandas Series representing a row from the ConvTech DataFrame.
        df_attr: A pandas DataFrame containing attribute information.
    Returns:
        The same unmapped_record dict with 'attributes' populated.
    """
    attributes = []
    currency = clean(row.get('currency'))

    for attr in df_attr.index:
        if attr not in row.keys():
            continue  # Skip if the attribute is not present in the row

        if is_nan(row[attr]):
            continue  # Skip if the attribute value is NaN

        attr_row = df_attr.loc[attr]
        notes = get_attr_note(attr_row, nomenclature_lookup=nomenclature_lookup)
        unit_spec = str(attr_row.get('Unit / Format', ''))
        if currency and 'Currency' in unit_spec:
            notes += (
                f" | source currency: {currency}"
            )

        attr = {
            'attribute_name': attr,
            'value': clean(row[attr]),
            'uncertainty_notes': None,
            'time_index': clean(row.get('tech_year', None)),
            'notes': notes
        }
        attributes.append(attr)

    ue["attributes"] = attributes
    return ue



## --- functions to get balancing

def build_balancing_entries(carriers, shares, units):
    size = max(len(carriers), len(shares), len(units))
    entries = []

    for i in range(size):
        carrier = carriers[i] if i < len(carriers) else None
        share = shares[i] if i < len(shares) else None
        unit = units[i] if i < len(units) else None

        if carrier is None and share is None and unit is None:
            continue

        entries.append({
            "carrier": carrier,
            "share": share,
            "unit": unit,
        })

    return entries

def to_balance_list(items, carrier_lookup: dict[str, str] | None = None):
    """Normalize balancing items to list of dicts with carrier_name/share/unit."""
    normalized = []
    for item in items or []:
        if not isinstance(item, dict):
            continue

        carrier_name = clean(item.get("carrier_name"))
        if carrier_name is None:
            carrier_name = clean(item.get("carrier"))

        share = clean(item.get("share"))
        unit = clean(item.get("unit"))

        if carrier_name is None and share is None and unit is None:
            continue

        carrier_notes = None
        if carrier_name is not None and carrier_lookup:
            carrier_notes = carrier_lookup.get(str(carrier_name).strip().lower())

        normalized.append({
            "carrier_name": carrier_name,
            "carrier_notes": carrier_notes,
            "share": share,
            "unit": unit,
        })

    return normalized


def infer_main_output_unit(main_output_carrier, output_carriers, output_units):
    """Infer the unit for the selected main output carrier."""
    if main_output_carrier is not None:
        for carrier, unit in zip(output_carriers, output_units):
            if clean(carrier) == main_output_carrier:
                unit_norm = normalize_unit(unit)
                if unit_norm:
                    return unit_norm
                

def add_balancing_to_record(
    ue: dict,
    row: pd.Series,
    carrier_lookup: dict[str, str] | None = None,
) -> dict:
    """
    Extracts balancing-related fields from a DataFrame row and adds them to the unmapped_record.

    Args:
        ue:  The unmapped_record dict (modified in-place and returned).
        row: A pandas Series representing a row from the ConvTech DataFrame.
    Returns:
        The same unmapped_record dict with 'balancing' populated.
    """

    input_carriers = split_csv(row.get("carriers_in"))
    input_shares = split_csv_float(row.get("ratios_in"))
    input_units = split_csv(row.get("units_in_ratios"))

    output_carriers = split_csv(row.get("carriers_out"))
    output_shares = split_csv_float(row.get("ratios_out"))
    output_units = split_csv(row.get("units_out_ratios"))

    ue["balancing"] = {}

    ue["balancing"]["inputs"] = to_balance_list(
        build_balancing_entries(
            input_carriers,
            input_shares,
            input_units,
        ),
        carrier_lookup=carrier_lookup,
    )
    ue["balancing"]["outputs"] = to_balance_list(
        build_balancing_entries(
            output_carriers,
            output_shares,
            output_units,
        ),
        carrier_lookup=carrier_lookup,
    )

    main_output_carrier = clean(row.get("main_output")) #!
    main_output_unit = infer_main_output_unit(
        main_output_carrier,
        output_carriers,
        output_units,
    )

    return ue


def refuel2unmapped(
    row: pd.Series,
    df_ref: pd.DataFrame,
    df_attr: pd.DataFrame,
    nomenclature_lookup: dict[str, str] | None = None,
    carrier_lookup: dict[str, str] | None = None,
) -> dict:
    """Convert one ConvTech or StorTech row into an unmapped entity."""
    record = {
        "technology_name": row.get("tech_id", ""),
        "technology": {
            "technology_description": clean(row.get("description")),
            "technology_type": clean(row.get("tech_type")),
            "technology_category": clean(row.get("technology_class")),
            "technology_assumption": None,
            "process_name": clean(row.get("unit_operation")),
            "process_type": None,
            "process_category": clean(row.get("tech_category")),
            "process_assumption": None,
        },
        "scope": {
            "geographic_scope_description": clean(row.get("cost_base")),
            "temporal_scope_description": (
                str(row.get("tech_year"))
                if not is_nan(row.get("tech_year"))
                else None
            ),
            "capacity_scope_description": clean(row.get("min_installation_size")),
            "system_boundary_description": clean(row.get("tech_boundary")),
            "scope_assumption": clean(row.get("tech_maturity")),
        },
        "metadata": {
            "related_project": "reFuel.ch",
            "tags": ["Switzerland", "power-to-X"],
            "other_notes": [
                "This unmapped entity was generated from the reFuel TechDatabase "
                "(2026-06-03) using the MOTEL ingestion pipeline."
            ],
        },
    }

    record = add_sources_to_record(record, row.get("list_of_source_id"), df_ref)
    record = add_attributes_to_record(
        record,
        row,
        df_attr,
        nomenclature_lookup=nomenclature_lookup,
    )
    record = add_balancing_to_record(
        record,
        row,
        carrier_lookup=carrier_lookup,
    )
    return record


def embeddedcarbon2unmapped(row: pd.Series) -> dict:
    """Convert one EmbeddedCarbon row into an unmapped entity."""
    record = {
        "technology_name": row.get("tech_id", ""),
        "technology": {
            "technology_description": clean(row.get("lca_activity")),
            "technology_type": clean(row.get("tech_type")),
            "technology_category": None,
            "technology_assumption": None,
            "process_name": clean(row.get("ref_product")),
            "process_type": None,
            "process_category": None,
            "process_assumption": None,
        },
        "scope": {
            "geographic_scope_description": clean(row.get("lca_location")),
            "temporal_scope_description": None,
            "capacity_scope_description": None,
            "system_boundary_description": None,
            "scope_assumption": None,
        },
        "sources": [],
        "balancing": {"inputs": [], "outputs": []},
        "metadata": {
            "related_project": "reFuel.ch",
            "tags": ["Switzerland", "power-to-X", "embedded-carbon", "LCA"],
            "other_notes": [
                "Generated from the reFuel TechDatabase (2026-06-03) EmbeddedCarbon sheet."
            ],
        },
    }

    lca_unit = clean(row.get("lca_unit"))
    notes_base = (
        f"lca_unit: {lca_unit}"
        f" | ref_product: {clean(row.get('ref_product'))}"
        f" | lca_location: {clean(row.get('lca_location'))}"
    )
    if not is_nan(row.get("notes")):
        notes_base += f" | notes: {row.get('notes')}"

    attributes = []
    for scenario_key, columns in EMBEDDEDCARBON_SCENARIOS.items():
        for year, column_name in zip(EMBEDDEDCARBON_YEARS, columns):
            value = clean(row.get(column_name))
            if value is None:
                continue
            attributes.append(
                {
                    "attribute_name": "embedded_carbon",
                    "value": value,
                    "uncertainty_notes": f"climate scenario: {scenario_key}",
                    "time_index": year,
                    "notes": notes_base,
                }
            )

    record["attributes"] = attributes
    return record


def process_standard_sheet(
    workbook: dict[str, pd.DataFrame],
    sheet_name: str,
    df_ref: pd.DataFrame,
    df_attr: pd.DataFrame,
    df_nom: pd.DataFrame,
    df_carrier: pd.DataFrame,
    sample_limit: int | None = None,
) -> list[dict]:
    """Convert one standard technology sheet into unmapped entities."""
    df_sheet = prepare_df(workbook[sheet_name])
    df_sheet = limit_sheet_rows(df_sheet, sheet_name, sample_limit=sample_limit)
    nomenclature_lookup = build_nomenclature_lookup(df_nom)
    carrier_lookup = build_carrier_lookup(df_carrier)
    return [
        refuel2unmapped(
            df_sheet.loc[index],
            df_ref,
            df_attr,
            nomenclature_lookup=nomenclature_lookup,
            carrier_lookup=carrier_lookup,
        )
        for index in df_sheet.index
    ]


def process_embeddedcarbon_sheet(
    workbook: dict[str, pd.DataFrame],
    sheet_name: str = "EmbeddedCarbon",
    sample_limit: int | None = None,
) -> list[dict]:
    """Convert the EmbeddedCarbon sheet into unmapped entities."""
    df_sheet = prepare_df(workbook[sheet_name])
    df_sheet = limit_sheet_rows(df_sheet, sheet_name, sample_limit=sample_limit)
    return [embeddedcarbon2unmapped(df_sheet.loc[index]) for index in df_sheet.index]


def preview_entities(sheet_name: str, entities: list[dict], preview_rows: int = 3) -> None:
    """Print a compact preview of the first few converted entities."""
    print(f"{sheet_name}: {len(entities)} entities")
    for entity in entities[:preview_rows]:
        print(f"- {entity.get('technology_name')}")


def write_yaml(records: list[dict], output_path: Path | str) -> None:
    """Write records to YAML with stable formatting for inspection."""
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            records,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def export_sheet_entities(sheet_entities: dict[str, list[dict]], output_paths: dict[str, Path | str]) -> None:
    """Write one YAML file per sheet."""
    for sheet_name, records in sheet_entities.items():
        write_yaml(records, output_paths[sheet_name])


def run_refuel_pipeline(
    workbook: dict[str, pd.DataFrame],
    df_ref: pd.DataFrame,
    df_attr: pd.DataFrame,
    df_nom: pd.DataFrame,
    df_carrier: pd.DataFrame,
    sample_limit: int | None = None,
) -> dict[str, list[dict]]:
    """Run all three sheet conversions and return entities grouped by sheet."""
    sheet_entities = {}
    for sheet_name in STANDARD_SHEETS:
        sheet_entities[sheet_name] = process_standard_sheet(
            workbook,
            sheet_name,
            df_ref,
            df_attr,
            df_nom,
            df_carrier,
            sample_limit=sample_limit,
        )
    sheet_entities["EmbeddedCarbon"] = process_embeddedcarbon_sheet(
        workbook,
        sample_limit=sample_limit,
    )
    return sheet_entities


def publish_unmapped_entities(entity_groups, destination):
    """
    Publish ingested entities to the database staging area.

    A fresh copy is created so the notebook's in-memory records are not mutated.
    Every published entity starts in the ``to_be_mapped`` lifecycle state.

    Args:
        entity_groups (iterable[iterable[dict]]): Groups of ingested entities.
        destination (str | Path): Combined YAML file in motel-db/unmapped_entity.

    Returns:
        list[dict]: The combined records written to ``destination``.
    """
    published = []
    for group in entity_groups:
        for entity in group:
            record = deepcopy(entity)
            record["mapping_status"] = "to_be_mapped"
            record.pop("linked_entity_id", None)
            record.pop("date_mapped", None)
            published.append(record)

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            published,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    temporary.replace(destination)
    return published
