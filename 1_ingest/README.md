# 1 Ingest

This folder is Step 1 of the MOTEL workflow. It converts raw source data into the `unmapped_entity` staging format used by Step 2 harmonisation.

## Structure

```text
1_ingest/
|-- 1_data_ingestion.ipynb      generic Step 1 notebook and schema walkthrough
|-- README.md                   folder guide
`-- examples/
    `-- refuel/
        |-- ingestion_pipeline.ipynb   worked source-specific notebook
        |-- input/                     raw source files
        |   `-- reFuel_TechDatabase_Clean_2026-06-03.xlsx
        |-- scripts/                   source-specific ingestion helpers
        |   `-- ingestion_helper.py
        `-- output/                    sheet-level unmapped YAML exports
            |-- unmapped_entities_refuel_convtech.yaml
            |-- unmapped_entities_refuel_stortech.yaml
            `-- unmapped_entities_refuel_embeddedcarbon.yaml
```

## Input / Process / Output

- Input schema:
  - `../schema/unmapped_entity.yaml`
  - `../schema_simple/unmapped_entity.yaml`
- Input source example:
  - `examples/refuel/input/reFuel_TechDatabase_Clean_2026-06-03.xlsx`
- Process notebooks and scripts:
  - `1_data_ingestion.ipynb` explains the generic Step 1 contract
  - `examples/refuel/ingestion_pipeline.ipynb` is the worked reFuel.ch example
  - `examples/refuel/scripts/ingestion_helper.py` contains the source-specific transformation logic
- Output example files:
  - `examples/refuel/output/unmapped_entities_refuel_convtech.yaml`
  - `examples/refuel/output/unmapped_entities_refuel_stortech.yaml`
  - `examples/refuel/output/unmapped_entities_refuel_embeddedcarbon.yaml`
- Published staging output:
  - `../motel-db/unmapped_entity/unmapped_entities_refuel.yaml`

## Step Boundary

- Step 1 creates `unmapped` staging records from raw source material.
- Step 2 harmonises those records into controlled vocabularies, mappings, and linked entities.
