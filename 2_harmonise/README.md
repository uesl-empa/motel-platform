# 2 Harmonise

This folder is Step 2 of the MOTEL workflow. It takes staged `unmapped_entity` records from Step 1 and resolves them into canonical MOTEL registries, controlled vocabularies, mappings, and linked entities.

## Structure

```text
2_harmonise/
|-- 2_data_harmonisation.ipynb   workflow-facing Step 2 notebook
|-- harmonise_helpers.py         shared harmonisation logic
`-- README.md                    folder guide
```

## Input / Process / Output

- Input data:
  - `../motel-db/unmapped_entity/unmapped_entities_refuel.yaml`
- Input schemas:
  - `../schema/`
- Input controlled-vocabulary context:
  - `../1_ingest/examples/refuel/input/reFuel_TechDatabase_Clean_2026-06-03.xlsx`
- Process notebook and script:
  - `2_data_harmonisation.ipynb` is the main Step 2 workflow
  - `harmonise_helpers.py` contains the reusable harmonisation logic
- Canonical outputs written by Step 2:
  - `../motel-db/controlled_vocabulary/`
  - `../motel-db/secondary/`
  - `../motel-db/mapping/`
  - `../motel-db/linked_entity/linked_entity.yaml`

## Important Boundary

Step 2 does not write its main outputs into `2_harmonise/` itself.

Instead:
- `2_harmonise/` contains the process
- `motel-db/` contains the canonical harmonised data product produced by that process
- `3_ontology_mapping/` consumes `motel-db/` as the Step 2 handoff

This means `motel-db/` is both the published MOTEL database state and the shared output boundary between Step 2 and Step 3.

It is also the main data product explored in `../4_data_explore/4_data_exploration.ipynb`.

## Extra Runtime Files

When enabled from the notebook, Step 2 may also create:
- `../motel-db/log/` for harmonisation logs
- `../motel-db/_backup/` for local backups before reset/rebuild

These are runtime support files rather than core published outputs.
