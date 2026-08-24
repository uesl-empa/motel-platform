# 1 Ingest

This folder is Step 1 of the MOTEL workflow. It converts raw source data into the `unmapped_entity` staging format used by Step 2 harmonisation.

## Structure

```text
1_ingest/
|-- 1_data_ingestion.ipynb      generic Step 1 notebook and schema walkthrough
|-- README.md                   folder guide
`-- examples/
    |-- carrier_data/           carrier-bound staging example (prices, intensities)
    |   |-- README.md           carrier data ingestion guide
    |   `-- output/
    |       `-- unmapped_carrier_data_TEMPLATE.yaml
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

- Input schema (technology-bound track):
  - `../schema/unmapped_entity_technology.yaml`
  - `../schema_human/unmapped_entity_technology.yaml`
- Input schema (carrier-bound track):
  - `../schema/unmapped_entity_carrier.yaml`
  - `../schema_human/unmapped_entity_carrier.yaml`
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
  - `../motel-db/unmapped_carrier_data/` for carrier-bound records

## Two Staging Formats

Step 1 produces one of two staging formats depending on what the value describes.

- `unmapped_entity` for data that belongs to a piece of hardware: cost, efficiency, lifetime, embedded carbon. Anchored to `technology_name`.
- `unmapped_carrier_data` for data that belongs to an energy carrier: prices, carbon and emission intensities, availability. Anchored to `carrier_name`.

Use the carrier-bound format whenever the value would otherwise have to be copied onto every technology that touches the carrier. See `examples/carrier_data/README.md`.

## Validating What You Produce

Before handing staging records to Step 2, check them:

```bash
python ../tools/validate_unmapped.py ../motel-db/unmapped_entity/
```

The schema is auto-detected per record from its anchor field (`technology_name`
or `carrier_name`). Set `schema_version` on each record to pin the contract it
was written against; the validator warns when it is missing or disagrees.

## Record the Source Licence

Every source you cite needs two fields filled in at ingest:

- `source_licence` — the licence as the publisher states it (`CC BY 4.0`, `OGL`,
  `all rights reserved`, or the publisher name for a paywalled article)
- `redistribution_permitted` — `permitted`, `not_permitted`, or `unknown`

MOTEL republishes extracted values under the repository data licence, which is
only defensible where the source allows it. Recording the decision while you have
the source open costs seconds; auditing it afterwards means revisiting every
source. Neither field is ever filled by the LLM — a guessed licence looks exactly
like a checked one.

Where a source does not permit redistribution, keep the citation and drop the
values. `--strict` turns unrecorded terms into a failure, so it can be switched on
as a release gate once the existing sources are cleared.

## Step Boundary

- Step 1 creates `unmapped` staging records from raw source material.
- Step 2 harmonises those records into controlled vocabularies, mappings, and linked entities or linked carrier data.
