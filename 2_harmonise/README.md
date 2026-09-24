# 2 Harmonise

This folder is Step 2 of the MOTEL workflow. It takes staged `unmapped_entity` records from Step 1 and resolves them into canonical MOTEL registries, controlled vocabularies, mappings, and linked entities.

## Structure

```text
2_harmonise/
|-- 2_data_harmonisation.ipynb   workflow-facing Step 2 notebook
|-- harmonise.py                 CLI: add a new source to the populated database
|-- harmonise_helpers.py         shared harmonisation logic (technology-bound track)
|-- carrier_data_helpers.py      harmonisation logic for the carrier-bound track
|-- llm_client.py                LLM client: Claude (default) or a local Ollama model
`-- README.md                    folder guide
```

## Input / Process / Output

- Input data:
  - `../motel-db/unmapped_entity/*.yaml` (for example `unmapped_entities_refuel.yaml`, `unmapped_entities_dac.yaml`)
  - `../motel-db/unmapped_carrier_data/` for carrier-bound records
- Input schemas:
  - `../schema/`
- Input controlled-vocabulary context:
  - `../1_ingest/examples/refuel/input/reFuel_TechDatabase_Clean_2026-06-03.xlsx`
- Process notebook and script:
  - `2_data_harmonisation.ipynb` is the main Step 2 workflow
  - `harmonise.py` runs the same steps from a terminal
  - `harmonise_helpers.py` contains the reusable harmonisation logic
  - `carrier_data_helpers.py` contains the carrier-bound counterpart
- Canonical outputs written by Step 2:
  - `../motel-db/controlled_vocabulary/`
  - `../motel-db/secondary/`
  - `../motel-db/mapping/`
  - `../motel-db/linked_entity/linked_entity.yaml`
  - `../motel-db/linked_carrier_data/linked_carrier_data.yaml`

## Adding a New Source

The database grows one source at a time. Stage the new records in
`motel-db/unmapped_entity/` (Step 1), then from the repository root:

```bash
python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_dac.yaml --limit 1
python 2_harmonise/harmonise.py motel-db/unmapped_entity/unmapped_entities_dac.yaml
```

The first command harmonises one pending record so its decisions can be checked
in the audit output; the second picks up the remaining pending records. Passing
the directory instead of a file harmonises every file that still has pending
records.

Each run:

1. validates the staging records with `tools/validate_unmapped.py` and writes
   nothing if any record is invalid,
2. backs up the derived files to `motel-db/_backup/` (skip with `--no-backup`),
3. resolves every technology, process, source, carrier, attribute, and scope
   against the existing registries and vocabularies, creating only what is new,
4. appends the linked entities, marks the staging records `mapped`, and merges
   the mapping tables,
5. checks that every reference in the new linked entities resolves
   (`validate_linked_entities`), exiting with status 1 if one does not.

Running on a populated database is safe by design:

- IDs are never renumbered. New registry rows, attributes, and linked entities
  continue the existing sequences, and the attribute registry is appended to
  rather than rebuilt.
- The mapping tables in `motel-db/mapping/` are merged, not overwritten, so they
  keep the provenance of every earlier run. `unmapped_to_linked.csv` records the
  staging file each linked entity came from.
- A name that an earlier run already resolved is looked up in the mapping tables
  and reuses the recorded ID without an LLM call (status `known`), so repeated
  names across sources resolve consistently and cheaply.

Resolution order for each name is: known alias, exact name match, LLM
semantic match, then creation of a new row. `--no-llm` stops after the exact
match and creates new rows as named in the staging data; it needs no API key or
local model and is what the `Validate Repository` workflow runs as a smoke test.

## LLM Configuration

LLM-assisted steps run on Claude through the Anthropic API by default. A local
model served by Ollama remains available as an alternative, for example when
data must not leave the machine or no API key is at hand. `llm_client.py` holds
both backends; the helpers call its single `ask_json()` function and never see
which one answered.

Choose the backend per run:

| Where | Claude (default) | Local model |
| --- | --- | --- |
| Environment | `MOTEL_LLM_PROVIDER=anthropic` | `MOTEL_LLM_PROVIDER=ollama` |
| Notebook run controls | `llm_provider = "anthropic"` | `llm_provider = "ollama"` |
| CLI | `harmonise.py <file>` | `harmonise.py <file> --llm-provider ollama` |
| Python | `llm_client.configure(provider="anthropic")` | `llm_client.configure(provider="ollama")` |

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `MOTEL_LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `MOTEL_LLM_MODEL` | `claude-opus-5` / `qwen3:14b` | model name; the default depends on the provider (CLI: `--model`) |
| `MOTEL_CLAUDE_EFFORT` | `high` | Claude only: `low` to `max`; empty for models without effort support such as `claude-haiku-4-5` |
| `ANTHROPIC_API_KEY` | — | Claude credential (any credential the Anthropic SDK resolves also works) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server address |

For the local model, start the server and pull the model once:

```bash
ollama serve
ollama pull qwen3:14b
```

How the calls are made:

- Every call sends a JSON schema for the reply. Claude enforces it through
  structured outputs, so the reply always parses and enum fields such as
  `source_type` or `carrier_category` can only take values the MOTEL schema
  allows. Ollama receives the same schema as its `format`; its reply is parsed
  defensively (thinking blocks and code fences are stripped) and retried once
  if it is not valid JSON.
- A proposed entity match is accepted only if its ID exists in the registry,
  whichever backend proposed it.
- Name patterns and length limits are checked after the reply, and a failing
  name is sent back once with the reason.
- Claude only: the registry listing used for matching is sent as a cached
  system block, so consecutive matches against an unchanged registry are billed
  at the cache-read rate, and server-side refusal fallbacks are enabled
  (`fallbacks: "default"`).
- The run log records the provider, model, and token usage of the run, and the
  notebook and CLI print a usage summary at the end.

A run makes a few calls per new name (standardise the name, fill fields, match)
and none for known names. Harmonising the four DAC records against the current
database takes on the order of a hundred calls.

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

`validate_linked_carrier_data()` checks required fields, foreign keys into every registry, the `data_category` enum, and that no entry packs a series into a single value instead of using one entry per period.

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
