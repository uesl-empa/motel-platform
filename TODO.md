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
- [] reuse `dici_onto:hasEnergyCarrierEnergyCostAttribute` for carrier price
  instead of minting `CarrierPrice`. It already exists in core, under
  `hasEnergyCarrierAttribute` -> `hasComponentAttribute`. Checked against
  `digicities-ontology` core on 2026-08-23.
- [] mint `CarrierEmissionIntensity` properly. Core has **no** emission, carbon,
  intensity, or GWP term of any kind, so this one genuinely has to be created.
  Same for a carrier availability term; core has a `Resource` /
  `ResourceAttribute` branch (`RenewableResource`, `NonRenewableResource`) that
  may fit better than a carrier attribute.
- [] consider `CustomPhysicalRatioAttribute` as the category class for both
  price (EUR/kWh) and intensity (gCO2eq/kWh). It exists in core and is defined
  for exactly this shape: a unit that is a ratio of two QUDT units, carried as
  a string in `hasUnitLabel` with no `qudt:unit` IRI emitted.
- [] carrier-level modelling shape is confirmed OK: `EnergyCarrier` is a
  subclass of `Component`, and components carry attributes through
  `hasAttribute` / `hasComponentAttribute`, so attaching scoped attributes to a
  carrier instance is structurally valid. Still open: whether a price or
  intensity trajectory should stay one scoped instance per year, or use the core
  `FutureTimeSeries` class with `hasFutureTimeSeries`, which is defined for
  forecast and scenario projections.
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
- [] publish a MOTEL ontology extension file. `digicities-ontology` expects
      minted terms to be declared in a workspace `ontology/extensions/*.ttl`
      using the shared `dici_onto:` namespace, validated with
      `tools/validate_extension.py` (it checks that parents are declared, that
      labels and comments are present, and that no core term is redefined).
      MOTEL declares nothing today, yet the generated TTL uses 19 minted
      attribute classes (TRL, CAPEX, CAPEXPerCapacity, Lifetime, OPEX,
      InterestRate, the 3 carrier ones, ...) plus `EmbeddedCarbon`,
      `CapacityBasis`, `ConversionFactor`, `Introduced`, `IsMainInput`,
      `IsMainOutput`, `LCA_unit`, `ssp2_NDC`, `ssp2_PkBudg1000`, `Year`, and
      four `has...` predicates. Minting is the sanctioned workflow; leaving the
      terms undeclared is the gap.
- [] MOTEL emits `dici_onto:hasAttributeValue` for every attribute type, but
      `docs/attribute-types.md` in the ontology specifies `qudt:value` for
      `PhysicalAttribute`, `hasCategoricalValue` for `CategoricalAttribute`, and
      `hasTemporalValue` for `EventAttribute`. Only `SimpleValueAttribute`
      matches today. Affects the whole technology track, not just carrier.
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
