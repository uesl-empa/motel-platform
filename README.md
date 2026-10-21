# MOTEL Platform

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data%20License-CC--BY%204.0-blue.svg)](DATA_LICENSE)

MOTEL (Methodology for Open Technology Data in Energy Models) is an ETH Domain ORD Program project for collecting, harmonising, and publishing technology data for energy system models.

This repository contains the MOTEL code (ingestion, harmonisation, ontology mapping, and release tools), the schemas, the documentation site with its data explorer, and the public release of the MOTEL database in `motel-db/`.

## The MOTEL Repositories

```text
uesl-empa/motel-data  (private)     full database, including values whose
        |                           sources do not permit redistribution
        |  tools/build_release.py: only values backed by permitted sources
        v
uesl-empa/motel-platform  (public)  code, schemas, docs, and the release in
        |                           motel-db/; explorer and downloads at
        |                           https://uesl-empa.github.io/motel-platform/
        |  ontology TTL built from the release:
        |  https://uesl-empa.github.io/motel-platform/data/cls_atr_motel.ttl
        v
uesl-empa/motel-webapp  (public)    knowledge graph (GraphDB), API, and web app
```

| Repository | Visibility | Holds |
| --- | --- | --- |
| `uesl-empa/motel-data` | private, for the MOTEL team | the full database and its history; no code |
| [`uesl-empa/motel-platform`](https://github.com/uesl-empa/motel-platform) (this one) | public | all code, the schemas, the docs, and the release of the database |
| [`uesl-empa/motel-webapp`](https://github.com/uesl-empa/motel-webapp) | public | the knowledge-graph stack that serves the data through an API and web app |

Code lives only here and data changes start in `motel-data`; a new release
arrives here as a pull request made by `tools/publish_release.py` (see
[Working With the Full Data](#working-with-the-full-data)). Everything in this
repository's `motel-db/` is the release: `motel-db/RELEASE.md` says how it was
built and `motel-db/WITHHELD.csv` lists what it withholds.

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
   - **Ingestion guide: `1_ingest/ingestion_guide.md`** — the contract and decision rules for converting a source, written for humans and LLMs alike
   - Main notebook: `1_ingest/1_data_ingestion.ipynb`
   - Folder guide: `1_ingest/README.md`
   - reFuel.ch example: `1_ingest/examples/refuel/ingestion_pipeline.ipynb`
   - Helper script: `1_ingest/examples/refuel/scripts/ingestion_helper.py`
   - Carrier data example: `1_ingest/examples/carrier_data/README.md`
   - Output: `motel-db/unmapped_entity/unmapped_entities_refuel.yaml`

2. **Harmonise** unmapped entities into controlled vocabularies and linked records.
   - Main notebook: `2_harmonise/2_data_harmonisation.ipynb`
   - CLI entrypoint: `2_harmonise/harmonise.py` (adds a new source to the populated database)
   - Helper module: `2_harmonise/harmonise_helpers.py`
   - LLM client (Claude via Claude Code by default; Claude API or local Ollama optional): `2_harmonise/llm_client.py`
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

So a record may read `technical_efficiency: 0.6` with its unit in a note, or
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

Following the same convention as the technology track, `time_index` is a scalar: a multi-period series is one attribute entry per period. The carrier-bound pipeline runs either with LLM-assisted matching (`use_llm=True`, calls Claude) or with deterministic exact-match resolution (`use_llm=False`, no model required). See `1_ingest/examples/carrier_data/README.md` for a worked example.

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

## Building the Public Release

`motel-db/` holds values extracted from third-party sources, and many of those
sources do not permit their numbers to be republished. `tools/build_release.py`
writes a copy of the database in which every such value is withheld:

```bash
python tools/build_release.py            # writes dist/motel-db/
```

A value is released only when at least one source is linked to it and every
linked source is marked `permitted`. Values from `not_permitted` or `unknown`
sources, and values with no source linked at all, are removed; records, scopes,
carriers, and every source citation stay, so a withheld value can be looked up
in its source. The free-text notes of a source that is not `permitted` are
withheld too, because notes tend to restate the source's numbers. `dist/motel-db/WITHHELD.csv` lists each withheld value (without
the value) and the reason, and `RELEASE.md` summarises the run.

The script re-reads its own output and fails if a withheld value is still in it,
and it refuses to build when `motel-db/` holds a file it does not know how to
filter. The `Validate Repository` workflow builds the release on every push, and
the `Deploy Docs` workflow publishes the data explorer from it. To release more
values, record the source's terms (or link a cleared source) at ingest; the
release picks the change up on the next build.

`python tools/build_release.py --check <db>` verifies that a database is
already a release, with nothing left to withhold.

## Working With the Full Data

The full database, the raw source workbooks, and everything extracted from them
belong in the private `uesl-empa/motel-data` repository, because many sources do
not permit their values to be republished. This repository carries
only the public release in `motel-db/`; CI runs
`tools/build_release.py --check motel-db` to keep it that way, and
`tools/publish_release.py` proposes each new release as a pull request. To work
on the full data, clone
`motel-data` next to this repository and point `MOTEL_DATA` at it:

```bash
export MOTEL_DATA=../motel-data      # PowerShell: $env:MOTEL_DATA = "..\motel-data"
```

With `MOTEL_DATA` set, every stage reads and writes the private checkout instead
of this repository: harmonisation (`harmonise.py` and the notebook), the reFuel
ingestion helper, the ontology generator, the exploration notebook,
`tools/build_release.py`, and `docs/build_data.py`. The private checkout is laid
out as:

```text
motel-data/
|-- motel-db/              the full database
|-- raw/refuel/            source workbooks, e.g. reFuel_TechDatabase_Clean_2026-06-03.xlsx
`-- ingest_output/refuel/  ingestion outputs extracted from them
```

Without `MOTEL_DATA`, everything runs on the release in this repository. Do not
commit spreadsheets or notebooks with saved outputs here; the `Validate
Repository` workflow rejects both.

After committing a change to `motel-data`, propose the new release here:

```bash
python tools/publish_release.py --data ../motel-data
```

It builds the release from the full database, replaces `motel-db/` with it,
checks it, and opens a pull request on a `sync/release-<commit>` branch, using
your own git and `gh` login. A change that only touches withheld values
produces no pull request, because the release does not change. `--no-push`
stops after the local commit.

## Adding a New Source

Stage the new source's records as `unmapped_entity_technology` YAML (Step 1),
save them in `motel-db/unmapped_entity/`, then harmonise them into the
populated database:

```bash
python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_<source>.yaml
```

The run validates the staging records first and writes nothing if any is
invalid. It backs up the derived files, resolves every name against the
existing registries, appends the new linked entities, and checks that every
reference in them resolves. Existing IDs are never renumbered, and the mapping
tables are merged rather than overwritten, so a name resolved in an earlier run
maps to the same ID again without another LLM call. `--limit N` harmonises only
the first N pending records, so the decisions can be reviewed on a few records
before the rest; `--llm-provider ollama` uses the local model instead of
Claude, and `--no-llm` resolves by exact name match and needs no LLM at all.
See `2_harmonise/README.md` for details.

## Quick Start

Create a Python environment and install the notebook/data dependencies:

```bash
python -m venv .venv
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Open the notebooks in Jupyter, VS Code, or another notebook environment.

LLM-assisted harmonisation uses Claude by default, run through Claude Code under your Claude subscription, so it needs neither an API key nor a local model or GPU. Claude Code only has to be installed and signed in; the copy bundled with the VS Code extension is found automatically.

Two alternatives remain available (see `2_harmonise/README.md` for all settings):

- the Claude API: `--llm-provider anthropic` (or `MOTEL_LLM_PROVIDER=anthropic`), which needs `ANTHROPIC_API_KEY` and is billed per token separately from the subscription;
- a local model served by Ollama (default `qwen3:14b`): `--llm-provider ollama`, or `llm_provider = "ollama"` in the notebook.

With `use_llm=False` or `--no-llm`, harmonisation resolves by exact match and needs no model at all.

To generate the ontology-ready TTL from the harmonised MOTEL database (written
to `3_ontology_mapping/output_ttl/`, which is not committed; `--db` and `--out`
choose other paths):

```powershell
.\.venv\Scripts\python.exe 3_ontology_mapping\scripts\gen_ttl.py
```

## Documentation

The static documentation site is in `docs/` and is deployed by GitHub Pages from the `Deploy Docs` workflow.

- GitHub Pages: https://uesl-empa.github.io/motel-platform/
- Local entrypoint: `docs/index.html`
- Downstream webapp repository: https://github.com/uesl-empa/motel-webapp

### Data explorer

`docs/explorer.html` (published at https://uesl-empa.github.io/motel-platform/explorer.html)
lets anyone browse the database without installing anything:

- every technology with its records, parameters by year, units, scope, energy
  balance, and the source of each value;
- a comparison of one parameter across all technologies, for a chosen year and
  region, as a bar chart with the full table below it;
- the sources and the controlled vocabularies;
- downloads of the whole database as JSON and of every value as one CSV table.

Each technology page has a "Suggest a correction or a source" button that opens
a pre-filled GitHub issue, so feedback arrives in the repository where it can be
reviewed.

The explorer shows the public release in `motel-db/`: the `Deploy Docs`
workflow checks that it is a release, then generates the explorer's data from
it with `docs/build_data.py`, on every publish and whenever `motel-db/` changes
on `main`. Values whose sources do not
permit redistribution are therefore withheld from the pages and the downloads;
the explorer says so, links the list of withheld values, and shows each
source's redistribution status. The generated files in `docs/data/` are not
committed. To view the explorer locally:

```bash
python docs/build_data.py
# then open docs/explorer.html in a browser
```

The `Deploy Docs` workflow also publishes the ontology TTL built from the
release, at https://uesl-empa.github.io/motel-platform/data/cls_atr_motel.ttl.
The TTL is no longer committed, because one built from the full database carries
every value.

Without `--db`, `build_data.py` reads `motel-db/` unfiltered, which is fine for
local inspection but must not be published.

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
- Distribute the output of `tools/build_release.py`, not `motel-db/` itself.
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
- What MOTEL distributes is built by `tools/build_release.py`, which withholds
  every value that is not backed exclusively by `permitted` sources; see
  [Building the Public Release](#building-the-public-release).
