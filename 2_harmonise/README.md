# 2 Harmonise

This folder is Step 2 of the MOTEL workflow. It takes staged `unmapped_entity` records from Step 1 and resolves them into canonical MOTEL registries, controlled vocabularies, mappings, and linked entities.

## Structure

```text
2_harmonise/
|-- 2_data_harmonisation.ipynb   workflow-facing Step 2 notebook
|-- harmonise_helpers.py         shared harmonisation logic (technology-bound track)
|-- carrier_data_helpers.py      harmonisation logic for the carrier-bound track
`-- README.md                    folder guide
```

## Input / Process / Output

- Input data:
  - `../motel-db/unmapped_entity/unmapped_entities_refuel.yaml`
  - `../motel-db/unmapped_carrier_data/` for carrier-bound records
- Input schemas:
  - `../schema/`
- Input controlled-vocabulary context:
  - `../1_ingest/examples/refuel/input/reFuel_TechDatabase_Clean_2026-06-03.xlsx`
- Process notebook and script:
  - `2_data_harmonisation.ipynb` is the main Step 2 workflow
  - `harmonise_helpers.py` contains the reusable harmonisation logic
  - `carrier_data_helpers.py` contains the carrier-bound counterpart
- Canonical outputs written by Step 2:
  - `../motel-db/controlled_vocabulary/`
  - `../motel-db/secondary/`
  - `../motel-db/mapping/`
  - `../motel-db/linked_entity/linked_entity.yaml`
  - `../motel-db/linked_carrier_data/linked_carrier_data.yaml`

## Carrier-Bound Track

Energy prices, carbon intensities, and resource availability describe an energy carrier, not a technology. They are harmonised by `carrier_data_helpers.py` into `linked_carrier_data` records anchored to a `carrier_id`, using the same carrier, source, attribute, and scope registries as the technology track.

```python
import carrier_data_helpers as cdh

result = cdh.run_carrier_data_harmonisation(
    "../motel-db/unmapped_carrier_data/unmapped_carrier_data.yaml",
    use_llm=False,   # exact-match resolution; True reuses the Step 2 LLM resolvers
)
print(cdh.validate_linked_carrier_data() or "no problems found")
```

The run appends to `linked_carrier_data.yaml`, marks the staging records mapped, and writes `mapping/unmapped_to_linked_carrier_data.csv` and `mapping/carrier_data_attribute_map.csv`. These are separate files from the technology-track maps, so neither run overwrites the other's provenance.

`validate_linked_carrier_data()` checks required fields, foreign keys into every registry, the `data_category` enum, and that each series has one `time_index` entry per value.

Both tracks share one attribute vocabulary. The `applies_to` column in `attribute.csv` records whether a metric describes a `technology`, a `carrier`, or `both`.

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
