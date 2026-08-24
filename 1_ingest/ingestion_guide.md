# MOTEL Ingestion Guide

**Audience: whoever is converting a source into MOTEL staging records — most often an LLM working from a raw file.**

This is the contract and the decision rules. It is not a library. Every source is shaped differently — a spreadsheet, a report table, a CSV export, an API — so MOTEL does not ship generic ingestion code. What it ships is this guide, the schemas it describes, and a validator that tells you whether you got it right.

Work the loop:

```
read the source  ->  write records  ->  python tools/validate_unmapped.py <your-file>
                          ^                              |
                          +------- fix what it reports ---+
```

Stop when the validator reports `0 error(s)`. Warnings are advisory except for licensing, which is covered in section 6.

---

## 1. Pick the track

MOTEL stages two kinds of record. Choose by asking **what one row of your source describes**.

| If one row describes… | Use | Anchor field |
| --- | --- | --- |
| a piece of equipment — its cost, efficiency, lifetime, size | `schema/unmapped_entity_technology.yaml` | `technology_name` |
| an energy carrier — its price, emission intensity, availability | `schema/unmapped_entity_carrier.yaml` | `carrier_name` |

The test that settles most cases: **would this value be the same for every technology that touches this carrier?** The price of grid electricity in Zürich in 2030 is the same whether a heat pump or an electrolyser consumes it — that is carrier data. A heat pump's CAPEX is not — that is technology data.

Set exactly one anchor field per record. Setting both, or neither, produces:

```
cannot tell which schema applies: set exactly one of carrier_name or technology_name
```

A source often yields **both kinds**. Split them into separate records — and separate files is fine.

## 2. Minimum viable record

Only these are required. Everything else is optional and should be filled where the source supports it.

| Level | Required |
| --- | --- |
| record | `technology_name` **or** `carrier_name` |
| `sources[]` | `source_name` |
| `attributes[]` | `attribute_name`, `value` |
| `balancing.inputs[]` / `outputs[]` | `carrier_name` |

A file is a **YAML list of records**, even when it holds one:

```yaml
- schema_version: "0.3.0"
  technology_name: ...
```

A bare mapping at the top level validates with a warning, but the harmonisation loader iterates a sequence and will not read it.

## 3. The rules that are easy to get wrong

### 3.1 `time_index` is a scalar, one entry per period

A value that varies by year becomes **one attribute entry per year**, each with its own scalar `time_index`. Do not pack a series into a list.

```yaml
# CORRECT
attributes:
  - attribute_name: Carrier Emission Intensity
    value: 128.0
    time_index: "2025"
  - attribute_name: Carrier Emission Intensity
    value: 96.0
    time_index: "2030"

# WRONG - the validator reports: expected string, found array
  - attribute_name: Carrier Emission Intensity
    value: [128.0, 96.0]
    time_index: ["2025", "2030"]
```

This changed in v0.2.0. Records written against older guidance use the list form.

### 3.2 Units go in `attribute_notes`, as the first token after `Unit`

The staging schema has no unit field — deliberately, so ingestion never has to normalise. Write the unit into the note in this exact shape:

```yaml
attribute_notes: Unit EUR/kWh. Price paid by the consumer per unit of delivered energy.
```

Harmonisation reads the **first whitespace-delimited token after `Unit`**. `Unit EUR/kWh` works; `unit: euros per kWh` does not.

### 3.3 Record the source's silences, do not invent

If a source gives no value, omit the field or write `null`. Do not substitute `0`, `n/a`, or a guess. Staging preserves what the source said, including what it did not say. `balancing` requires only `carrier_name` precisely so a carrier with an unstated share can still be recorded.

### 3.4 Keep raw labels raw

Do not normalise names, units, or scope values to look tidy. Stage 2 does that, and it needs the original wording to do it well. Put your own observations in the `*_notes` fields rather than editing the value.

## 4. Reuse the existing vocabulary

Staging accepts free text, but every novel spelling becomes a new vocabulary row or an LLM judgement call later. Before inventing a name, check whether one exists:

| Vocabulary | File | Entries |
| --- | --- | --- |
| attributes | `motel-db/controlled_vocabulary/attribute.csv` | 28 |
| carriers | `motel-db/controlled_vocabulary/carrier.csv` | 33 |
| geographic scope | `motel-db/controlled_vocabulary/geographic_scope.csv` | 4 |
| temporal scope | `motel-db/controlled_vocabulary/temporal_scope.csv` | 4 |
| system boundary | `motel-db/controlled_vocabulary/system_boundary.csv` | 3 |

If your source's concept matches an existing entry, use that entry's exact name (`Technical Efficiency`, `Grid Electricity`). If it genuinely differs, use the source's own wording and explain the difference in the notes.

Where the source's scope maps cleanly onto an existing token, use the token (`GEO_CH`, `TIME_2030`). Otherwise free text is fine.

## 5. Scope carries the comparability

Two values are only comparable inside the same scope. This is where most silently-wrong data comes from.

- `system_boundary` — for a cost: what equipment is included. For an emission factor: which life-cycle stages. For a price: whether taxes and grid fees are in.
- `capacity_scope` — an installation size tier, or for a tariff, the consumption band it applies to.
- `temporal_scope` — the projection year or period.
- `geographic_scope` — region, country, or market zone.
- `scenario` — separates competing price tracks or narratives for the same year.

If the source states a boundary, record it verbatim in the field and explain it in the matching `*_description` field. If the source does not state one, say so in `scope_notes` rather than guessing.

## 6. Record the licence — this one is not optional in spirit

MOTEL republishes extracted values under the repository data licence. That is only defensible where the source permits it. Fill both fields on every source:

```yaml
sources:
  - source_name: DanishEnergyAgency2025
    source_licence: CC BY 4.0
    redistribution_permitted: permitted     # permitted | not_permitted | unknown
```

- Use the licence **as the publisher states it**. Leave `source_licence` empty rather than guessing.
- `redistribution_permitted` is `unknown` until a person has actually checked. That is an honest answer; a wrong `permitted` is a licensing exposure that reads like a checked fact.
- **Never infer either field.** They are deliberately excluded from LLM field-filling in harmonisation for this reason, and the same restraint applies during ingestion.
- Where a source does not permit redistribution, keep the citation and drop the values.

The enum is `permitted` / `not_permitted` / `unknown` rather than yes/no because YAML reads bare `yes` and `no` as booleans.

## 7. Stamp the version

Set `schema_version` on every record to the release you wrote against:

```yaml
schema_version: "0.3.0"
```

Pin a tag rather than tracking the default branch. The validator warns when the field is missing, and when a record's version disagrees with the schema it is being checked against.

## 8. Mark the lifecycle state

```yaml
harmonisation_record:
  mapping_status: to_be_mapped     # to_be_mapped | mapped
```

Ingestion always writes `to_be_mapped`. Harmonisation sets `mapped` and fills in the rest. Leaving records at `to_be_mapped` indefinitely is legitimate — stage 2 is optional.

## 9. Validate

```bash
python tools/validate_unmapped.py <your-file>.yaml
python tools/validate_unmapped.py <your-directory>/ --strict    # also gate on licensing
```

What the messages mean:

| Message | Cause |
| --- | --- |
| `required field is missing or empty` | a required field is absent, `null`, or blank |
| `unknown field; not declared in the schema (check the spelling)` | a typo, or a field the schema does not define — it would be silently dropped |
| `expected string, found array` | wrong type; most often a packed `time_index` or `value` series |
| `'X' is not one of [...]` | a value outside an enum |
| `cannot tell which schema applies` | zero or both anchor fields set |
| `no licence recorded` / `nobody has recorded whether this source permits…` | section 6 |
| `record targets X, validating against Y` | `schema_version` disagrees with the schema |

The validator is standalone — standard library plus PyYAML, no imports from this repository. Copy `tools/validate_unmapped.py` into your own project repo and run it there.

## 10. Worked example

A source table row:

| Technology | Year | Region | CAPEX (EUR/kW) | Efficiency | Boundary |
| --- | --- | --- | --- | --- | --- |
| Alkaline electrolyser | 2030 | CH | 1200 | 0.68 | Plant ready to operate |

becomes:

```yaml
- schema_version: "0.3.0"
  technology_name: Alkaline electrolyser
  technology:
    technology_description: Alkaline water electrolysis for hydrogen production
    technology_type: conversion
    process_name: Hydrogen Production
  scope:
    geographic_scope: GEO_CH
    geographic_scope_description: Switzerland
    temporal_scope: TIME_2030
    system_boundary: Plant ready to operate
    system_boundary_description: Equipment, installation and essential auxiliaries. Excludes grid reinforcement.
  sources:
    - source_name: YourSource2026
      source_description: Full citation as printed in the source.
      link: https://doi.org/...
      source_licence: CC BY 4.0
      redistribution_permitted: permitted
      source_locator: Table 3, p. 12
      linked_attribute:
        - Capital Expenditure Per Capacity
        - Technical Efficiency
  attributes:
    - attribute_name: Capital Expenditure Per Capacity
      value: 1200
      time_index: "2030"
      attribute_notes: Unit EUR/kW. From Table 3.
    - attribute_name: Technical Efficiency
      value: 0.68
      time_index: "2030"
      attribute_notes: Unit ratio. Lower heating value basis.
  balancing:
    inputs:
      - carrier_name: Grid Electricity
    outputs:
      - carrier_name: Hydrogen
  metadata:
    related_project: YourProject
    tags: [electrolysis, hydrogen]
  harmonisation_record:
    mapping_status: to_be_mapped
```

Note what it does *not* do: it does not convert the unit, rename the technology, resolve `Plant ready to operate` to a token, or invent a share for the electricity input. All of that belongs to stage 2.

## See also

- `1_ingest/README.md` — folder layout and where outputs go
- `schema_human/unmapped_entity_technology.yaml` — the same contract in readable form
- `schema_human/unmapped_entity_carrier.yaml` — the carrier contract
- `1_ingest/examples/refuel/` — a full worked pipeline over an Excel workbook
- `1_ingest/examples/carrier_data/` — a carrier-track template
