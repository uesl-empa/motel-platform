# Public Release TODO

This file tracks remaining work before the repository is announced publicly.

## Data Quality

- Verify that all `motel-db/` records can be released under compatible source-data licenses.
- Review generated mapping tables for duplicate records and rerun harmonisation where needed.
- Confirm attribute names follow the schema naming guidance.
- Ensure each unmapped entity has a `harmonisation_record.mapping_status`.
- Record the LLM model and harmonisation settings used for each production run.

## Carrier-Bound Data Track

The carrier track records modelling data that belongs to an energy carrier rather
than to a technology: energy prices, carbon and emission intensities, resource
availability. The framework is in place; the data and the ontology terms are not.

Blocking before the carrier version can be published:

- [] populate `motel-db/linked_carrier_data/` — it currently ships empty, and
  0 of 28 attributes are marked `applies_to: carrier`. Needs real prices and
  emission factors under a licence that permits redistribution. Note that
  ecoinvent-derived factors are **not** redistributable; check KBOB, BFE, and
  Swissgrid terms before ingesting.
- [] agree the ontology terms with @james.allan. `CarrierPrice`,
  `CarrierEmissionIntensity`, and `CarrierAnnualAvailability` are MOTEL
  placeholders declared in `3_ontology_mapping/config/attribute_ontology_mapping.yaml`;
  they do not exist in `digicities-ontology`. Publishing TTL with them mints
  terms into the `dici_onto:` namespace that the ontology does not define.
  Changing them is config-only, no code change.
- [] confirm how DigiCities wants carrier-level data modelled. The current
  export attaches attributes to a carrier instance typed `EnergyCarrier` and
  scoped by region and year, because that pattern invents no new predicates.
  Whether that is the intended shape is an open ontology question.
- [] replace `1_ingest/examples/carrier_data/output/unmapped_carrier_data_example.yaml`
  or clearly gate it. Every number in it is an invented placeholder.

Worth doing, not blocking:

- [] add a Step 2 smoke test to the validation workflow. `use_llm=False` exists
  so the carrier pipeline can run without Ollama; a run over the example file
  plus `validate_linked_carrier_data()` would catch regressions. Also add
  `3_ontology_mapping` to the `compileall` list.
- [] add a schema drift test asserting that the blocks shared by the technology
  and carrier schemas stay byte-identical (`sources`, `metadata`, `scope`,
  `version`, `values`, `assumptions`), with an explicit allow-list for the
  differences that are intended: the `attributes` block description names its
  metric domain, and `harmonisation_record` carries a different ID field.
- [] decide whether carrier records need review coverage.
  `supplementary/review.csv` keys on `linked_entity_id`, so there is no path to
  review a `linked_carrier_data` record. Cheaper to decide before records exist.
- [] check whether `motel-webapp` needs a matching change: `motel-db/` gained a
  top-level folder, and `attribute.csv` gained an `applies_to` column.
- [] consider renaming `linked_carrier_data_id` and `motel-db/linked_carrier_data/`
  to match the `linked_entity_carrier` schema name. Free to do now because
  nothing published or downstream depends on them yet; expensive later.

## TODO

- [] check the whole workflow again, after assessment_date was change to reference_year (link to ontology!?)
- [] the harmonisation process seem not working with non-empty datasets in motel-db
      — this affects a carrier run against a populated database too
- [] in source, the LLM cannot identify which one is journal paper
- [] `scope.scenario` is staged in both unmapped schemas but never written into
      `linked_entity`, so the value is lost during harmonisation. Either write it
      in `build_and_save_linked_entities` or drop it from the staging schema.
      `linked_entity_carrier` does carry it.

## DONE

- [x] more guidelines needed to be added to classify technology and process, now the process.csv only has name but no other info.
- [x] add a carrier-bound track so prices and emission intensities are recorded
      against a carrier instead of being duplicated onto every technology that
      consumes it (schemas, Step 2 pipeline, Step 3 export, Step 4 exploration)
- [x] rename the schemas so the two tracks read as one family:
      `unmapped_entity_technology` / `unmapped_entity_carrier`, and
      `linked_entity_technology` / `linked_entity_carrier`
- [x] align the blocks shared by both tracks so they stay diffable; only the
      `attributes` domain phrase, `harmonisation_record`'s ID field, and
      `scope.scenario` still differ
- [x] declare `attribute_name` and `time_index` in `linked_entity_technology`,
      which the harmoniser has always written but the schema never described

## Future Work

- add mathmatical equations in the secondary datasets or a property of attributes [this was mentioned in the MOTEL proposal but do not address in the project duration]
- a third subject type (a system-wide CO2 price, discount rate, or weather year
  belongs to neither a technology nor a carrier). At two tracks the duplication
  between schemas is cheaper than abstraction; at three it inverts, and the
  shared blocks should be generated from fragments rather than hand-kept in sync.
