# MOTEL Platform

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC--BY%204.0-blue.svg)](DATA_LICENSE)

MOTEL (Methodology for Open Technology Data in Energy Models) is an ETH Domain ORD Program project for collecting, harmonising, and publishing technology data for energy system models.

This repository contains the current MOTEL data workflow, schemas, curated database files, and a static documentation site.

## Repository Structure

```text
.
├── 1_ingest/         # Source-specific ingestion notebooks and helpers
├── 2_harmonise/      # Harmonisation notebooks and helper functions
├── docs/             # Static GitHub Pages site
├── motel-db/         # Published MOTEL database files
├── schema/           # Machine-readable YAML schemas
└── schema_simple/    # Human-readable simplified schema blueprints
```

## Data Workflow

1. **Ingest** source data into the unmapped entity schema.
   - Main notebook: `1_ingest/1_data_ingestion.ipynb`
   - reFuel.ch pipeline: `1_ingest/ingestion_space/refuel/ingestion_pipeline.ipynb`
   - Output: `motel-db/unmapped_entity/unmapped_entities_refuel.yaml`

2. **Harmonise** unmapped entities into controlled vocabularies and linked records.
   - Main notebook: `2_harmonise/2_data_harmonisation.ipynb`
   - Helper module: `2_harmonise/harmonise_helpers.py`
   - Outputs: `motel-db/secondary/`, `motel-db/controlled_vocabulary/`, `motel-db/mapping/`, and `motel-db/linked_entity/`

3. **Publish** curated database files and documentation.
   - Data: `motel-db/`
   - Schemas: `schema/`
   - Website: `docs/index.html`

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

## Documentation

The static documentation site is in `docs/` and is deployed by GitHub Pages from the `Deploy Docs` workflow. To preview it locally, open `docs/index.html` in a browser.

## Public Release Checklist

- Review source-data licensing before publishing any raw or derived third-party data.
- Confirm `motel-db/` contains only records intended for public release.
- Run the repository validation workflow locally or in GitHub Actions before tagging a release.
- Update `CITATION.cff` with final author, affiliation, DOI, and release metadata when available.

## Licensing

- Code and workflow scripts are released under the MIT License.
- Data, schemas, documentation, and ontology-ready database files are released under CC BY 4.0 unless otherwise stated.
