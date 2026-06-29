# MOTEL Platform

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC--BY%204.0-blue.svg)](DATA_LICENSE)

MOTEL (Methodology for Open Technology Data in Energy Models) is an ETH Domain ORD Program project for collecting, harmonising, and publishing technology data for energy system models.

This repository contains the current MOTEL data workflow, schemas, curated database files, ontology-mapping scripts, and a static documentation site. The separate public downstream application stack lives in [`BartonChenTW/motel-webapp`](https://github.com/BartonChenTW/motel-webapp).

## Repository Structure

```text
.
|-- 1_ingest/            source-specific ingestion notebooks and helpers
|-- 2_harmonise/         harmonisation notebooks and helper functions
|-- 3_ontology_mapping/  ontology-ready TTL generation from harmonised MOTEL data
|-- docs/                static GitHub Pages site
|-- motel-db/            published MOTEL database files
|-- schema/              machine-readable YAML schemas
`-- schema_human/        human-readable schema blueprints mirroring `schema/`
```

## Data Workflow

1. **Ingest** source data into the unmapped entity schema.
   - Main notebook: `1_ingest/1_data_ingestion.ipynb`
   - Folder guide: `1_ingest/README.md`
   - reFuel.ch example: `1_ingest/examples/refuel/ingestion_pipeline.ipynb`
   - Helper script: `1_ingest/examples/refuel/scripts/ingestion_helper.py`
   - Output: `motel-db/unmapped_entity/unmapped_entities_refuel.yaml`

2. **Harmonise** unmapped entities into controlled vocabularies and linked records.
   - Main notebook: `2_harmonise/2_data_harmonisation.ipynb`
   - Helper module: `2_harmonise/harmonise_helpers.py`
   - Outputs: `motel-db/secondary/`, `motel-db/controlled_vocabulary/`, `motel-db/mapping/`, and `motel-db/linked_entity/`

3. **Ontology mapping** converts harmonised MOTEL outputs into ontology-ready TTL.
   - Main notebook: `3_ontology_mapping/3_ontology_mapping.ipynb`
   - Helper module: `3_ontology_mapping/scripts/generator_core.py`
   - CLI entrypoint: `3_ontology_mapping/scripts/gen_ttl.py`
   - Mapping config: `3_ontology_mapping/config/attribute_ontology_mapping.yaml`
   - Output: `3_ontology_mapping/output_ttl/cls_atr_motel.ttl`

4. **Publish** curated database files and documentation.
   - Data: `motel-db/`
   - Schemas: `schema/`
   - Website: `docs/index.html`
   - Public docs: `https://bartonchentw.github.io/motel-platform/`

## Database Layout

- `motel-db/unmapped_entity/`: staging YAML records before harmonisation.
- `motel-db/linked_entity/`: harmonised linked records.
- `motel-db/controlled_vocabulary/`: controlled vocabularies such as carriers, attributes, scopes, and boundaries.
- `motel-db/secondary/`: referenced entities such as technologies, processes, and sources.
- `motel-db/mapping/`: provenance and mapping tables generated during harmonisation.
- `motel-db/supplementary/`: contributor and review metadata.

Runtime logs and local backups are intentionally excluded from the public repository.

## Quick Start

Create a Python environment and install the notebook/data dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Open the notebooks in Jupyter, VS Code, or another notebook environment. The harmonisation helper currently uses a local Ollama model (`qwen3:14b`) for LLM-assisted matching and field completion.

To generate the ontology-ready TTL from the harmonised MOTEL database:

```powershell
.\.venv\Scripts\python.exe 3_ontology_mapping\scripts\gen_ttl.py
```

## Documentation

The static documentation site is in `docs/` and is deployed by GitHub Pages from the `Deploy Docs` workflow.

- GitHub Pages: https://bartonchentw.github.io/motel-platform/
- Local entrypoint: `docs/index.html`
- Downstream webapp repository: https://github.com/BartonChenTW/motel-webapp

## Public Release Checklist

- Review source-data licensing before publishing any raw or derived third-party data.
- Confirm `motel-db/` contains only records intended for public release.
- Run the repository validation workflow locally or in GitHub Actions before tagging a release.
- Update `CITATION.cff` with final author, affiliation, DOI, and release metadata when available.

## Licensing

- Code and workflow scripts are released under the MIT License.
- Data, schemas, documentation, and ontology-ready database files are released under CC BY 4.0 unless otherwise stated.
