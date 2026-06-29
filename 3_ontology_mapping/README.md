# 3 Ontology Mapping

This folder is the Step 3 handoff from harmonised MOTEL database files to ontology-ready TTL output.

## Structure

```text
3_ontology_mapping/
|-- ttl_creation_from_motel_db.ipynb   notebook walkthrough for Step 3
|-- README.md                          folder guide
|-- config/                            ontology-mapping inputs and audit notes
|   |-- attribute_ontology_mapping.yaml
|   `-- attribute_ontology_linkage_audit.md
|-- scripts/                           executable Step 3 processing logic
|   |-- gen_ttl.py
|   `-- generator_core.py
`-- output_ttl/                        generated ontology-ready artifacts
    `-- cls_atr_motel.ttl
```

## Input / Process / Output

- Input data:
  - `../motel-db/linked_entity/linked_entity.yaml`
  - `../motel-db/secondary/*.csv`
  - `../motel-db/controlled_vocabulary/*.csv`
  - `../motel-db/mapping/unmapped_to_linked.csv`
- Input mapping config:
  - `config/attribute_ontology_mapping.yaml`
- Process scripts:
  - `scripts/generator_core.py` is the shared Step 3 generation logic
  - `scripts/gen_ttl.py` is the command-line entrypoint
  - `ttl_creation_from_motel_db.ipynb` is the notebook-facing workflow
- Output artifact:
  - `output_ttl/cls_atr_motel.ttl`

## How To Run

From the repository root:

```powershell
.\.venv\Scripts\python.exe 3_ontology_mapping\scripts\gen_ttl.py
```

This reads the current `motel-db/` content and writes the generated TTL to `3_ontology_mapping/output_ttl/cls_atr_motel.ttl`.

Import note: the ontology-mapping workflow itself is included in this repository. The generated file `3_ontology_mapping/output_ttl/cls_atr_motel.ttl` is the Step 3 handoff artifact and should be used as the input file in the `motel_ontology` repository.

## Step Boundary

- `1_ingest/` creates staged unmapped records.
- `2_harmonise/` creates harmonised MOTEL entities, vocabularies, mappings, and linked entities.
- `3_ontology_mapping/` converts those harmonised MOTEL outputs into ontology-ready TTL.
- `4_data_explore/` provides a notebook-first entrypoint for inspecting and querying the published MOTEL data product.
