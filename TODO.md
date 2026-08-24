# Public Release TODO

This file tracks remaining work before the repository is announced publicly.

## Priority model

Decided 2026-08-24. The workflow has three stages and they are not equally important:

| Stage | Status | What it delivers |
| ----- | ------ | ---------------- |
| 1. `unmapped_entity` staging | **MUST** | Project data stored in a structured, citable form. This is the deliverable. |
| 2. `linked_entity` harmonisation | **Nice to have** | Controlled vocabularies, dedup, canonical units. This is what makes the data model-ready. |
| 3. Ontology mapping | **Not needed for this release** | TTL export for the knowledge graph. Kept working, off the critical path. |

Two consequences worth keeping in mind:

- A staging-only release is a **structured archive**, not a model-ready dataset.
  Canonical units, controlled attribute names, scope tokens, and source dedup are
  all produced by stage 2. Say so in the README rather than letting readers infer it.
- Staging data sits *closer* to the raw source than harmonised data does, so
  source-licence clearance gets harder under this priority, not easier.

## Blocking release

- [] **IMPORTANT — source-data licence clearance.** This is the one blocker that
      cannot be solved by writing code, and it carries legal exposure.

      `DATA_LICENSE` places everything in `motel-db/` under CC BY 4.0: anyone may
      reuse it, commercially, indefinitely. But MOTEL did not create most of that
      data. `motel-db/unmapped_entity/` publishes **2080 attribute values**
      extracted from **31 registered sources**, including the Danish Energy Agency
      technology catalogue, VSE, JRC, and a dozen journal articles behind
      `doi.org/10.1016/...`. As it stands the repository re-licenses other
      people's numbers under CC BY 4.0.

      Some of those are fine — JRC publications are typically CC BY, and the
      Danish catalogue is generally permissive. Journal articles under commercial
      publisher copyright typically are not: extracted data tables usually may not
      be republished.

      This gets *worse*, not better, under the staging-first priority. Staging
      records reproduce source values, column headers, and locators nearly
      verbatim, whereas a harmonised derivative is at least transformed.

      What has to happen:
      - go through all 31 rows of `motel-db/secondary/source.csv` and record, per
        source, whether its terms permit redistribution of extracted values
      - for any source that does not permit it: drop the values, or publish only
        the reference and let users fetch the numbers themselves
      - re-check after each new ingestion, including the Dübendorf project

      Related: there is currently **no licence field** in
      `schema/secondary/source.yaml` or in the `sources` block of either staging
      schema, so this cannot be recorded at ingest time and has to be redone as an
      audit every time. See the ingestion-workflow item below.
- [] add a source licence field to the schemas so clearance becomes a data-entry
      step rather than a recurring audit. `source.csv` stores source_id,
      source_name, source_description, source_type, link, access_date,
      confidence_level, assessment_method, reference_year, note — nothing about
      terms of use. A `source_licence` plus `redistribution_permitted` pair on the
      staging `sources` block and on `secondary/source.yaml` would let the
      validator flag an unlicensed source before it ever reaches `motel-db/`.
- [] ensure each unmapped entity has a `harmonisation_record.mapping_status`, and
      document that `to_be_mapped` is a legitimate terminal state under this
      priority rather than unfinished work.
- [] confirm attribute names follow the schema naming guidance.

## Nice to have — linked entity

- [] make harmonisation runnable without an LLM. `carrier_data_helpers.py` already
      supports `use_llm=False` (exact-match resolution, no Ollama); the technology
      track still requires a local `qwen3:14b`. Stage 2 being both optional *and*
      requiring a GPU is a hard sell for external contributors; exact-match
      resolution would make it optional and cheap.
- [] populate `motel-db/linked_carrier_data/` — currently empty, and 0 of 28
      attributes are marked `applies_to: carrier`. Needs prices and emission
      factors under a licence that permits redistribution. ecoinvent-derived
      factors are **not** redistributable; check KBOB, BFE, and Swissgrid terms
      before ingesting.
- [] `scope.scenario` is staged in both unmapped schemas but never written into
      `linked_entity`, so the value is lost during harmonisation. Either write it
      in `build_and_save_linked_entities` or drop it from the staging schema.
      `linked_entity_carrier` does carry it.
- [] `data_category` (`linked_entity_carrier` only, e.g. `price` vs
      `emission_intensity` vs `availability`) is carrier-only by design, not an
      oversight like `scope.scenario` above — don't conflate the two when
      revisiting schema parity. A single `carrier_id` can carry several record
      types, so `data_category` disambiguates them; `linked_entity_technology`
      has no equivalent because `technology_type` / `technology_category` /
      `process_type` already classify the asset at ingest time, and per-record
      metrics are split by `attribute_id` instead. Revisit only if a technology
      use case emerges that actually needs the same kind of record-level split.
- [] the harmonisation process seem not working with non-empty datasets in motel-db
      — this affects a carrier run against a populated database too
- [] in source, the LLM cannot identify which one is journal paper
- [] review generated mapping tables for duplicate records and rerun harmonisation
      where needed.
- [] record the LLM model and harmonisation settings used for each production run.
- [] decide whether carrier records need review coverage.
      `supplementary/review.csv` keys on `linked_entity_id`, so there is no path to
      review a `linked_carrier_data` record. Cheaper to decide before records exist.
- [] check whether `motel-webapp` needs a matching change: `motel-db/` gained a
      top-level folder, and `attribute.csv` gained an `applies_to` column. Also
      confirm whether it reads `linked_entity` — if so, stage 2 has a consumer
      that assumes it exists.
- [] rename `linked_carrier_data_id` and `motel-db/linked_carrier_data/` to match
      the `linked_entity_carrier` schema name. Free now because nothing published
      or downstream depends on them; expensive later.
- [] add a Step 2 smoke test to the validation workflow using `use_llm=False`,
      plus `validate_linked_carrier_data()`. Also add `3_ontology_mapping` to the
      `compileall` list.
- [] add a schema drift test asserting that the blocks shared by the technology
      and carrier schemas stay byte-identical (`sources`, `metadata`, `scope`,
      `version`, `values`, `assumptions`), with an explicit allow-list for the
      intended differences: the `attributes` block description names its metric
      domain, and `harmonisation_record` carries a different ID field.

## Not needed for this release — ontology

All verified against `uesl-empa/digicities-ontology` core on 2026-08-23. Kept
because the mapping step still runs and still produces valid TTL; none of it
blocks a staging-first release.

- [] publish a MOTEL ontology extension file. The ontology expects minted terms to
      be declared in a workspace `ontology/extensions/*.ttl` using the shared
      `dici_onto:` namespace, validated with `tools/validate_extension.py` (it
      checks that parents are declared, that labels and comments are present, and
      that no core term is redefined). MOTEL declares nothing today, yet the
      generated TTL uses 19 minted attribute classes (TRL, CAPEX, CAPEXPerCapacity,
      Lifetime, OPEX, InterestRate, the 3 carrier ones, ...) plus `EmbeddedCarbon`,
      `CapacityBasis`, `ConversionFactor`, `Introduced`, `IsMainInput`,
      `IsMainOutput`, `LCA_unit`, `ssp2_NDC`, `ssp2_PkBudg1000`, `Year`, and four
      `has...` predicates. Minting is the sanctioned workflow; leaving the terms
      undeclared is the gap.
- [] reuse `dici_onto:hasEnergyCarrierEnergyCostAttribute` for carrier price
      instead of minting `CarrierPrice`. It already exists in core, under
      `hasEnergyCarrierAttribute` -> `hasComponentAttribute`.
- [] mint `CarrierEmissionIntensity` properly. Core has **no** emission, carbon,
      intensity, or GWP term of any kind, so this one genuinely has to be created.
      Same for a carrier availability term; core has a `Resource` /
      `ResourceAttribute` branch (`RenewableResource`, `NonRenewableResource`) that
      may fit better than a carrier attribute.
- [] consider `CustomPhysicalRatioAttribute` as the category class for both price
      (EUR/kWh) and intensity (gCO2eq/kWh). It exists in core and is defined for
      exactly this shape: a unit that is a ratio of two QUDT units, carried as a
      string in `hasUnitLabel` with no `qudt:unit` IRI emitted.
- [] carrier-level modelling shape is confirmed OK: `EnergyCarrier` is a subclass
      of `Component`, and components carry attributes through `hasAttribute` /
      `hasComponentAttribute`, so attaching scoped attributes to a carrier instance
      is structurally valid. Still open: whether a price or intensity trajectory
      should stay one scoped instance per year, or use the core `FutureTimeSeries`
      class with `hasFutureTimeSeries`, which is defined for forecast and scenario
      projections.
- [] MOTEL emits `dici_onto:hasAttributeValue` for every attribute type, but
      `docs/attribute-types.md` in the ontology specifies `qudt:value` for
      `PhysicalAttribute`, `hasCategoricalValue` for `CategoricalAttribute`, and
      `hasTemporalValue` for `EventAttribute`. Only `SimpleValueAttribute`
      matches today. Affects the whole technology track, not just carrier.
- [] check the whole workflow again, after assessment_date was change to reference_year (link to ontology!?)

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
- [x] check the carrier ontology terms against digicities-ontology core, and
      correct the assumption that minting terms was itself the problem
- [x] state in the README what a staging-only release provides, and stop the
      licensing section implying MOTEL can re-license third-party source data
- [x] convert the carrier example into a data-free TEMPLATE with null values;
      the validator now treats *TEMPLATE* files as structure, not data
- [x] merge the carrier track (PR #13) and tag v0.1.0 / v0.2.0, so a downstream
      repository can pin a schema release instead of a branch
- [x] tag v0.1.0 on the pre-carrier state, declare `schema_version` in every
      schema and staging record, and bump this release to 0.2.0
- [x] build `tools/validate_unmapped.py` and wire it into CI. First run found
      three schema-vs-reality mismatches: `metadata.other_notes` is written as a
      list, and `balancing` share/unit were required but legitimately absent in
      64 records

## Future Work

- **a third subject type.** A building, a system-wide CO2 price, a discount rate,
  or a weather year belongs to neither a technology nor a carrier. At two tracks
  the duplication between schemas is cheaper than abstraction; at three it
  inverts, and the shared blocks should be generated from fragments rather than
  hand-kept in sync. This becomes live as soon as a project needs to stage
  something that is not a technology or a carrier.
- add mathmatical equations in the secondary datasets or a property of attributes [this was mentioned in the MOTEL proposal but do not address in the project duration]
