# 4 Data Explore

This folder is Step 4 of the MOTEL workflow. It provides a lightweight, notebook-first entrypoint for exploring the published MOTEL data product without rerunning ingestion, harmonisation, or ontology generation.

## Structure

```text
4_data_explore/
|-- 4_data_exploration.ipynb   main demo notebook focused on usage and operations
|-- config.py                  notebook paths and default demo parameters
|-- exploration_utils.py       reusable loading, lookup, flattening, and query helpers
`-- README.md                  folder guide
```

## Input / Process / Output

- Input data:
  - `../motel-db/linked_entity/linked_entity.yaml`
  - `../motel-db/linked_carrier_data/linked_carrier_data.yaml`
  - `../motel-db/secondary/*.csv`
  - `../motel-db/controlled_vocabulary/*.csv`
  - `../motel-db/mapping/*.csv`
- Optional human-readable companion:
  - `../motel-db/linked_entity_human/linked_entity.yaml`
- Process notebook:
  - `4_data_exploration.ipynb` is the main exploration notebook for filtering, searching, and understanding the published MOTEL records
  - `config.py` keeps paths and demo defaults separate from the notebook
  - `exploration_utils.py` keeps reusable data preparation and query logic separate from the notebook
- Typical outputs:
  - in-notebook tables and summaries
  - exploratory plots or pivot tables
  - ad hoc exports created by users as needed

## Suggested Questions

- Which linked entities contain a given `attribute_id` or `attribute_name`?
- Which technologies or processes are available for a target year or scope?
- Which sources support the values attached to a linked entity?
- How do the machine-readable and human-readable linked-entity views differ?
- What price or carbon intensity is recorded for a carrier in a target region and year, and under which system boundary?

## Carrier-Bound Data

`load_carrier_data(config.LINKED_CARRIER_DATA_PATH, config.VOCAB_DIR)` returns a tidy table with one row per value observation, with a `year` parsed from each entry's scalar `time_index`. `filter_carrier_data`, `summarize_carrier_data`, and `prepare_carrier_data_analysis` narrow and summarise it by carrier, `data_category`, or attribute. A missing or empty carrier data file yields an empty table rather than an error.

## Important Boundary

Step 4 is a consumer-facing exploration layer.

It should help users inspect and query the published MOTEL data product, but it should not modify the canonical database files in `motel-db/`.
