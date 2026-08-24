# MOTEL Platform

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC--BY%204.0-blue.svg)](DATA_LICENSE)

MOTEL (Methodology for Open Technology Data in Energy Models) is an ETH Domain ORD Program project for collecting, harmonising, and publishing technology data for energy system models.

This repository contains the current MOTEL data workflow, schemas, curated database files, ontology-mapping scripts, and a static documentation site. The separate public downstream application stack lives in [`uesl-empa/motel-webapp`](https://github.com/uesl-empa/motel-webapp).

## Repository Structure

```text
.
|-- 1_ingest/            source-specific ingestion notebooks and helpers
|-- 2_harmonise/         harmonisation notebooks and helper functions
|-- 3_ontology_mapping/  ontology-ready TTL generation from harmonised MOTEL data
|-- 4_data_explore/      notebook-first exploration of the published MOTEL data product
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
   - Carrier data example: `1_ingest/examples/carrier_data/README.md`
   - Output: `motel-db/unmapped_entity/unmapped_entities_refuel.yaml`

2. **Harmonise** unmapped entities into controlled vocabularies and linked records.
   - Main notebook: `2_harmonise/2_data_harmonisation.ipynb`
   - Helper module: `2_harmonise/harmonise_helpers.py`
   - Carrier data helper module: `2_harmonise/carrier_data_helpers.py`
   - Outputs: `motel-db/secondary/`, `motel-db/controlled_vocabulary/`, `motel-db/mapping/`, `motel-db/linked_entity/`, and `motel-db/linked_carrier_data/`

3. **Ontology mapping** converts harmonised MOTEL outputs into ontology-ready TTL.
   - Main notebook: `3_ontology_mapping/3_ontology_mapping.ipynb`
   - Helper module: `3_ontology_mapping/scripts/generator_core.py`
   - CLI entrypoint: `3_ontology_mapping/scripts/gen_ttl.py`
   - Mapping config: `3_ontology_mapping/config/attribute_ontology_mapping.yaml`
   - Output: `3_ontology_mapping/output_ttl/cls_atr_motel.ttl`
   - Ontology definitions: [`uesl-empa/digicities-ontology`](https://github.com/uesl-empa/digicities-ontology)

4. **Explore** the published MOTEL data product.
   - Main notebook: `4_data_explore/4_data_exploration.ipynb`
   - Folder guide: `4_data_explore/README.md`
   - Input: `motel-db/`
   - Output: interactive inspection, filtering, and ad hoc analysis

## What This Release Provides

MOTEL has three workflow stages and they are not equally complete. Read this
before building on `motel-db/`.

| Stage | Status | What it gives you |
| ----- | ------ | ----------------- |
| 1. `unmapped_entity` staging | **Complete** | Source data captured in a structured, citable form, with provenance attached to every value. |
| 2. `linked_entity` harmonisation | **Partial** | Controlled vocabularies, canonical units, deduplicated entities. Implemented, but not run for every dataset, and it requires a local LLM. |
| 3. Ontology mapping | **Off the critical path** | Ontology-ready TTL. Runs and produces valid output, but its terms are not yet aligned with the DigiCities ontology. |

**A staging-only dataset is a structured archive, not a model-ready one.**
Everything that makes values directly comparable across sources is produced by
stage 2:

- canonical units — staging keeps the unit in free text, inside `attribute_notes`
- controlled attribute and carrier names — staging keeps the source's own labels
- deduplicated sources and technologies — staging keeps one entry per source spelling
- scope tokens — staging keeps raw scope values

So a record may read `technical_efficiency: 0.58` with its unit in a note, or
carry the literal string `na` where a source gave no value. That is intentional
at stage 1: staging preserves what the source said, including its silences.
Feeding `motel-db/` into a solver means running stage 2 first, or normalising the
values yourself.

## Two Data Tracks

MOTEL records two kinds of modelling data, using the same registries and the same harmonisation lifecycle for both.

| | Technology-bound track | Carrier-bound track |
| --- | --- | --- |
| Answers | What does this piece of hardware cost and how does it perform? | What does this energy carrier cost and how clean is it? |
| Examples | CAPEX, efficiency, lifetime, embedded carbon | energy price, carbon intensity, resource availability |
| Anchored to | `tech_id` | `carrier_id` |
| Staging schema | `schema/unmapped_entity_technology.yaml` | `schema/unmapped_entity_carrier.yaml` |
| Harmonised schema | `schema/linked_entity_technology.yaml` | `schema/linked_entity_carrier.yaml` |
| Harmonisation module | `2_harmonise/harmonise_helpers.py` | `2_harmonise/carrier_data_helpers.py` |
| Published output | `motel-db/linked_entity/` | `motel-db/linked_carrier_data/` |

A price for grid electricity in a given region and year applies to every technology that consumes that carrier, so it belongs to the carrier rather than to any one consumer. Both tracks resolve against the same carrier, source, attribute, and scope vocabularies; the `applies_to` column in `attribute.csv` marks which side a metric belongs to.

Following the same convention as the technology track, `time_index` is a scalar: a multi-period series is one attribute entry per period. The carrier-bound pipeline runs either with LLM-assisted matching (`use_llm=True`, needs Ollama) or with deterministic exact-match resolution (`use_llm=False`, no model required). See `1_ingest/examples/carrier_data/README.md` for a worked example.

## Database Layout

- `motel-db/unmapped_entity/`: staging YAML records before harmonisation.
- `motel-db/linked_entity/`: harmonised linked records.
- `motel-db/unmapped_carrier_data/`: staging YAML records for carrier-bound modelling data.
- `motel-db/linked_carrier_data/`: harmonised carrier-bound records such as prices and emission intensities.
- `motel-db/controlled_vocabulary/`: controlled vocabularies such as carriers, attributes, scopes, and boundaries.
- `motel-db/secondary/`: referenced entities such as technologies, processes, and sources.
- `motel-db/mapping/`: provenance and mapping tables generated during harmonisation.
- `motel-db/supplementary/`: contributor and review metadata.

Runtime logs and local backups are intentionally excluded from the public repository.

## Schema Versioning

The schemas are released with the repository. Each schema file declares a
`schema_version`, and every staging record may carry a matching `schema_version`
field so a downstream project can pin the contract it was written against.

| Release | Staging schemas |
| ------- | --------------- |
| `v0.1.0` | `schema/unmapped_entity.yaml` |
| `v0.2.0` | `schema/unmapped_entity_technology.yaml`, `schema/unmapped_entity_carrier.yaml` |

A repository ingesting into MOTEL should pin a tag rather than track the default
branch, and stamp the version it targeted onto its records.

## Validating Staging Records

`tools/validate_unmapped.py` checks staging records against the unmapped schemas:
required fields, unknown keys (so a typo is caught rather than silently dropped),
declared types, enum membership, and `schema_version` agreement.

```bash
python tools/validate_unmapped.py motel-db/unmapped_entity/
python tools/validate_unmapped.py records.yaml --schema unmapped_entity_carrier
```

It is standalone — standard library plus PyYAML, no imports from this repository
— so a project staging its own data can copy the single file next to its
ingestion script. It runs on every push through the `Validate Repository`
workflow.

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

- GitHub Pages: https://uesl-empa.github.io/motel-platform/
- Local entrypoint: `docs/index.html`
- Downstream webapp repository: https://github.com/uesl-empa/motel-webapp

## Contributors and Acknowledgement

MOTEL is a collaborative project. We gratefully acknowledge the following contributors:

| Name | Role | Email |
| ---- | ---- | ----- |
| Yi-Chung Chen | Method and platform development | yi-chung.chen@empa.ch |
| Dennis Beermann | Method and platform development | dennis.beermann@empa.ch |
| Tycho Noah Frei | Web app development | tycho214@gmail.com |
| James Allan | Ontology integration | james.allan@empa.ch |
| Francesco Albisetti | Data integration and test | francesco.albisetti@empa.ch |

Special thanks to the reFuel.ch project for important input to the platform and workflow, especially Robin Mutschler (Robin.Mutschler@empa.ch), Arash Ebneali Samani (Arash.EbnealiSamani@empa.ch), and Arijit Alip Upadhyay (Arijit.Upadhyay@empa.ch).

## Public Release Checklist

- Review source-data licensing before publishing any raw or derived third-party data.
- Confirm `motel-db/` contains only records intended for public release.
- Run the repository validation workflow locally or in GitHub Actions before tagging a release.
- Update `CITATION.cff` with final author, affiliation, DOI, and release metadata when available.

## Licensing

- Code and workflow scripts are released under the MIT License.
- Schemas, documentation, and MOTEL-authored database files are released under CC BY 4.0 unless otherwise stated.
- **Source data retains the licence of its origin.** Records under `motel-db/`
  carry values extracted from third-party sources listed in
  `motel-db/secondary/source.csv`. The CC BY 4.0 grant covers MOTEL's own
  structuring, vocabularies, and mappings — it does not and cannot re-license the
  underlying source material. Check the terms of the originating source, cited on
  each record, before redistributing extracted values.
- Each source records its own terms: `source_licence` holds the licence as the
  publisher states it, and `redistribution_permitted` (`permitted`,
  `not_permitted`, `unknown`) holds the decision. Both are captured at ingest and
  never inferred by the LLM. `python tools/validate_unmapped.py <path> --strict`
  fails on any source whose terms have not been recorded.
