import re

import pandas as pd
import yaml


def read_yaml(path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_lookup(df, key_col, value_col):
    return df.dropna(subset=[key_col]).set_index(key_col)[value_col].to_dict()


def lookup_label(identifier, lookup):
    if identifier in (None, ""):
        return pd.NA
    return lookup.get(identifier, identifier)


def extract_year(value):
    if value is None:
        return pd.NA
    match = re.search(r"(19|20)\d{2}", str(value))
    return int(match.group(0)) if match else pd.NA


def load_lookup_tables(mapping_dir, vocab_dir):
    technology_map_df = pd.read_csv(mapping_dir / "technology_map.csv")
    process_map_df = pd.read_csv(mapping_dir / "process_map.csv")
    source_map_df = pd.read_csv(mapping_dir / "source_map.csv")

    attribute_vocab_df = pd.read_csv(vocab_dir / "attribute.csv")
    carrier_vocab_df = pd.read_csv(vocab_dir / "carrier.csv")
    geographic_scope_vocab_df = pd.read_csv(vocab_dir / "geographic_scope.csv")
    temporal_scope_vocab_df = pd.read_csv(vocab_dir / "temporal_scope.csv")
    system_boundary_vocab_df = pd.read_csv(vocab_dir / "system_boundary.csv")

    return {
        "technology_lookup": make_lookup(technology_map_df, "tech_id", "technology_name"),
        "process_lookup": make_lookup(process_map_df, "process_id", "process_name"),
        "source_lookup": make_lookup(source_map_df, "source_id", "source_name"),
        "attribute_lookup": make_lookup(attribute_vocab_df, "attribute_id", "attribute_name"),
        "carrier_lookup": make_lookup(carrier_vocab_df, "carrier_id", "carrier_name"),
        "carrier_type_lookup": make_lookup(carrier_vocab_df, "carrier_id", "carrier_type"),
        "carrier_category_lookup": make_lookup(carrier_vocab_df, "carrier_id", "carrier_category"),
        "geographic_scope_lookup": make_lookup(
            geographic_scope_vocab_df,
            "geographic_scope",
            "geographic_scope_description",
        ),
        "temporal_scope_lookup": make_lookup(
            temporal_scope_vocab_df,
            "temporal_scope",
            "temporal_scope_description",
        ),
        "system_boundary_lookup": make_lookup(
            system_boundary_vocab_df,
            "system_boundary",
            "system_boundary_description",
        ),
    }


def build_analysis_tables(linked_entities, lookups):
    entity_rows = []
    value_rows = []
    source_rows = []
    source_attribute_rows = []
    carrier_rows = []

    for entity in linked_entities:
        tech_id = entity.get("tech_id")
        process_id = entity.get("process_id")
        scope = entity.get("scope", {})

        tech_name = lookup_label(tech_id, lookups["technology_lookup"])
        process_name = lookup_label(process_id, lookups["process_lookup"])
        geographic_scope_id = scope.get("geographic_scope")
        temporal_scope_id = scope.get("temporal_scope")
        system_boundary_id = scope.get("system_boundary")
        reference_year = extract_year(temporal_scope_id)

        inputs = entity.get("balancing", {}).get("inputs", [])
        outputs = entity.get("balancing", {}).get("outputs", [])
        sources = entity.get("sources", [])
        values = entity.get("values", [])

        input_names = []
        output_names = []

        for direction, flows in (("input", inputs), ("output", outputs)):
            for flow in flows:
                carrier_id = flow.get("carrier_id")
                carrier_name = lookup_label(carrier_id, lookups["carrier_lookup"])
                carrier_rows.append(
                    {
                        "linked_entity_id": entity.get("linked_entity_id"),
                        "tech_id": tech_id,
                        "tech_name": tech_name,
                        "process_id": process_id,
                        "process_name": process_name,
                        "reference_year": reference_year,
                        "direction": direction,
                        "carrier_id": carrier_id,
                        "carrier_name": carrier_name,
                        "carrier_type": lookup_label(carrier_id, lookups["carrier_type_lookup"]),
                        "carrier_category": lookup_label(
                            carrier_id, lookups["carrier_category_lookup"]
                        ),
                        "share": flow.get("share"),
                        "unit": flow.get("unit"),
                    }
                )
                if direction == "input":
                    input_names.append(str(carrier_name))
                else:
                    output_names.append(str(carrier_name))

        entity_rows.append(
            {
                "linked_entity_id": entity.get("linked_entity_id"),
                "tech_id": tech_id,
                "tech_name": tech_name,
                "process_id": process_id,
                "process_name": process_name,
                "geographic_scope_id": geographic_scope_id,
                "geographic_scope": lookup_label(
                    geographic_scope_id, lookups["geographic_scope_lookup"]
                ),
                "temporal_scope_id": temporal_scope_id,
                "temporal_scope": lookup_label(temporal_scope_id, lookups["temporal_scope_lookup"]),
                "reference_year": reference_year,
                "system_boundary_id": system_boundary_id,
                "system_boundary": lookup_label(
                    system_boundary_id, lookups["system_boundary_lookup"]
                ),
                "source_count": len(sources),
                "value_count": len(values),
                "input_carriers": ", ".join(sorted(set(filter(None, input_names)))),
                "output_carriers": ", ".join(sorted(set(filter(None, output_names)))),
                "date_created": entity.get("date_created"),
            }
        )

        for value in values:
            attribute_id = value.get("attribute_id")
            value_rows.append(
                {
                    "linked_entity_id": entity.get("linked_entity_id"),
                    "tech_id": tech_id,
                    "tech_name": tech_name,
                    "process_id": process_id,
                    "process_name": process_name,
                    "reference_year": reference_year,
                    "attribute_id": attribute_id,
                    "attribute_name": lookup_label(attribute_id, lookups["attribute_lookup"]),
                    "value": value.get("value"),
                    "value_numeric": pd.to_numeric(
                        pd.Series([value.get("value")]), errors="coerce"
                    ).iloc[0],
                    "time_index": pd.to_numeric(
                        pd.Series([value.get("time_index")]), errors="coerce"
                    ).iloc[0],
                }
            )

        for source in sources:
            source_id = source.get("source_id")
            source_name = lookup_label(source_id, lookups["source_lookup"])
            linked_attribute_ids = source.get("linked_attribute_ids", [])

            source_rows.append(
                {
                    "linked_entity_id": entity.get("linked_entity_id"),
                    "tech_id": tech_id,
                    "tech_name": tech_name,
                    "process_id": process_id,
                    "process_name": process_name,
                    "reference_year": reference_year,
                    "source_id": source_id,
                    "source_name": source_name,
                    "linked_attribute_count": len(linked_attribute_ids),
                }
            )

            for attribute_ref in linked_attribute_ids:
                if isinstance(attribute_ref, str) and attribute_ref.startswith("ATTR_"):
                    attribute_id = attribute_ref
                    attribute_name = lookup_label(attribute_id, lookups["attribute_lookup"])
                else:
                    attribute_id = attribute_ref
                    attribute_name = attribute_ref

                source_attribute_rows.append(
                    {
                        "linked_entity_id": entity.get("linked_entity_id"),
                        "tech_id": tech_id,
                        "tech_name": tech_name,
                        "process_id": process_id,
                        "process_name": process_name,
                        "reference_year": reference_year,
                        "source_id": source_id,
                        "source_name": source_name,
                        "attribute_id": attribute_id,
                        "attribute_name": attribute_name,
                    }
                )

    return {
        "entities_df": pd.DataFrame(entity_rows),
        "values_df": pd.DataFrame(value_rows),
        "sources_df": pd.DataFrame(source_rows),
        "source_attributes_df": pd.DataFrame(source_attribute_rows),
        "carriers_df": pd.DataFrame(carrier_rows),
    }


def build_overview_df(entities_df, values_df, sources_df, carriers_df):
    return pd.DataFrame(
        [
            {"metric": "linked entities", "value": entities_df["linked_entity_id"].nunique()},
            {"metric": "technologies", "value": entities_df["tech_id"].nunique()},
            {"metric": "processes", "value": entities_df["process_id"].nunique()},
            {"metric": "sources", "value": sources_df["source_id"].nunique()},
            {"metric": "attributes in values table", "value": values_df["attribute_id"].nunique()},
            {"metric": "carriers", "value": carriers_df["carrier_id"].nunique()},
            {
                "metric": "reference years",
                "value": ", ".join(
                    map(str, sorted(entities_df["reference_year"].dropna().astype(int).unique()))
                ),
            },
        ]
    )


def filter_entities_by_keywords(entities_df, keywords):
    pattern = "|".join(re.escape(keyword) for keyword in keywords)
    return entities_df[
        entities_df["tech_name"].astype(str).str.contains(pattern, case=False, na=False)
        | entities_df["process_name"].astype(str).str.contains(pattern, case=False, na=False)
    ].sort_values(["tech_name", "reference_year", "linked_entity_id"])


def summarize_sources_for_entities(sources_df, linked_entity_ids):
    return (
        sources_df[sources_df["linked_entity_id"].isin(linked_entity_ids)]
        .groupby("source_name", as_index=False)
        .agg(
            linked_entities=("linked_entity_id", "nunique"),
            linked_attributes=("linked_attribute_count", "sum"),
        )
        .sort_values("linked_attributes", ascending=False)
    )


def summarize_attributes_for_entities(values_df, linked_entity_ids, top_n=12):
    return (
        values_df[values_df["linked_entity_id"].isin(linked_entity_ids)]
        .groupby("attribute_name", as_index=False)
        .agg(records=("linked_entity_id", "count"))
        .sort_values("records", ascending=False)
        .head(top_n)
    )


def select_attribute_values(values_df, linked_entity_ids, attribute_name):
    return values_df[
        values_df["linked_entity_id"].isin(linked_entity_ids)
        & values_df["attribute_name"].eq(attribute_name)
        & values_df["value_numeric"].notna()
    ].sort_values(["tech_name", "reference_year"])


def filter_source_attributes_by_keywords(source_attributes_df, keywords):
    pattern = "|".join(re.escape(keyword) for keyword in keywords)
    return source_attributes_df[
        source_attributes_df["source_name"].astype(str).str.contains(pattern, case=False, na=False)
    ].copy()


def summarize_source_attribute_coverage(selected_source_attributes):
    return (
        selected_source_attributes.groupby("source_name", as_index=False)
        .agg(
            linked_attributes=("attribute_id", "count"),
            distinct_attribute_types=("attribute_name", "nunique"),
            distinct_technologies=("tech_id", "nunique"),
            distinct_processes=("process_id", "nunique"),
        )
        .sort_values("linked_attributes", ascending=False)
    )


def top_attribute_types_by_source(selected_source_attributes, top_n=8):
    top_attribute_types = (
        selected_source_attributes.groupby(["source_name", "attribute_name"], as_index=False)
        .agg(records=("linked_entity_id", "count"))
        .sort_values(["source_name", "records"], ascending=[True, False])
    )
    return top_attribute_types.groupby("source_name").head(top_n)


def filter_carriers_by_query(carriers_df, carrier_query):
    return carriers_df[
        carriers_df["carrier_name"].astype(str).str.contains(carrier_query, case=False, na=False)
    ].copy()


def summarize_technologies_by_carrier(matched_carriers):
    return (
        matched_carriers.groupby(["direction", "tech_name", "process_name"], as_index=False)
        .agg(
            linked_entities=("linked_entity_id", "nunique"),
            first_year=("reference_year", "min"),
            last_year=("reference_year", "max"),
        )
        .sort_values(["direction", "tech_name"])
    )
