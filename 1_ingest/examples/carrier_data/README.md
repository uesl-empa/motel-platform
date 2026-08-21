# Carrier Data Ingestion Example

Worked example of the **carrier-bound** MOTEL track: modelling data that belongs to an energy carrier rather than to a technology.

Energy prices and carbon intensities are the motivating cases. A price for grid electricity in Switzerland in 2030 is not a property of any single electrolyser or heat pump — it applies to every technology that consumes that carrier in that region and year. Forcing such a value onto a technology record would duplicate it across every consumer and give it a `tech_id` it does not have.

## Structure

```text
1_ingest/examples/carrier_data/
|-- README.md                   this guide
`-- output/
    `-- unmapped_carrier_data_example.yaml   illustrative staging records
```

## Input / Process / Output

- Input schema:
  - `../../../schema/unmapped_entity_carrier.yaml`
  - `../../../schema_human/unmapped_entity_carrier.yaml`
- Output schema (produced by Step 2):
  - `../../../schema/linked_entity_carrier.yaml`
- Example staging file:
  - `output/unmapped_carrier_data_example.yaml`
- Published staging location:
  - `../../../motel-db/unmapped_carrier_data/`
- Published harmonised output:
  - `../../../motel-db/linked_carrier_data/linked_carrier_data.yaml`

> The example file contains **illustrative placeholder numbers only**. They are invented to show the record shape and to let the pipeline be exercised end to end. Nothing in it is measured or citable. Replace it with real, licensed source data before publishing.

## What a Record Looks Like

Each staging record answers: *which carrier, what kind of statement, under which scope, from which source, with what value.*

| Block | Purpose |
| ----- | ------- |
| `carrier_name`, `carrier` | The commodity the record describes, resolved against `controlled_vocabulary/carrier.csv`. |
| `data_category` | Coarse grouping: `price`, `emission_intensity`, `availability`, `resource_potential`, `demand`, `other`. |
| `scope` | Where and when the value holds, plus the accounting boundary and consumption band. |
| `sources` | Provenance, resolved against `secondary/source.csv`. Identical in shape to the technology track. |
| `attributes` | The values themselves. Use `value` plus `time_index` for a multi-period series. |

Scope carries more weight here than on the technology side, because carrier values are only comparable within a stated boundary:

- `system_boundary` separates a retail tariff from a wholesale price, and a combustion-only emission factor from a cradle-to-gate one.
- `capacity_scope` carries the consumption band or contract size a tariff refers to.
- `scenario` separates competing price tracks in the same year.

## Running Step 2 on This File

Copy the staging file into the database staging folder, then harmonise it:

```powershell
Copy-Item 1_ingest\examples\carrier_data\output\unmapped_carrier_data_example.yaml `
          motel-db\unmapped_carrier_data\unmapped_carrier_data.yaml
```

```python
# from 2_harmonise/
import carrier_data_helpers as cdh

result = cdh.run_carrier_data_harmonisation(
    "../motel-db/unmapped_carrier_data/unmapped_carrier_data.yaml",
    use_llm=False,   # exact-match resolution, no Ollama required
)
print(cdh.validate_linked_carrier_data() or "no problems found")
```

Set `use_llm=True` to reuse the same semantic matching Step 2 applies to technology records; that path needs a reachable Ollama service and the model named in `harmonise_helpers.MODEL`.

## Writing an Ingestion Script

For a real source, follow the pattern in `../refuel/scripts/ingestion_helper.py`: read the raw file, emit one dict per carrier/scope/statement combination matching `schema/unmapped_entity_carrier.yaml`, set `harmonisation_record.mapping_status` to `to_be_mapped`, and write the list to `motel-db/unmapped_carrier_data/`.

Two conventions make the deterministic (`use_llm=False`) path work well:

- Write the unit as the first token after `Unit` in `attribute_notes`, for example `Unit EUR/kWh. Price paid by the consumer.` The harmoniser reads it into the attribute vocabulary.
- Use canonical scope tokens (`GEO_CH`, `TIME_2030`) when the source already maps cleanly onto existing vocabulary entries. Free text is accepted and turned into a new token, but reusing tokens keeps the vocabulary tight.
