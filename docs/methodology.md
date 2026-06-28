# MOTEL Methodology

## 1. Purpose

MOTEL (Methodology for Open Technology Data in Energy Models) provides a workflow for turning heterogeneous technology data into structured records that can be reviewed, harmonised, and reused in energy system modelling. In the current repository, the implemented core is the ingestion of source data into an `unmapped` staging format and the harmonisation of those staged records into a MOTEL database structure with controlled vocabularies, secondary entities, mapping tables, and a `linked_entity` schema.

The repository already includes machine-readable schemas in [schema/unmapped_entity.yaml](/E:/Barton/repositories/motel-platform/schema/unmapped_entity.yaml), [schema/linked_entity.yaml](/E:/Barton/repositories/motel-platform/schema/linked_entity.yaml), and the supporting entity schemas under [schema/secondary](/E:/Barton/repositories/motel-platform/schema/secondary/source.yaml) and [schema/controlled_vocabulary](/E:/Barton/repositories/motel-platform/schema/controlled_vocabulary/attribute.yaml). The current implementation does not yet include a populated ontology-linked graph database, backend API, or web application in the public tree. Those parts should therefore be treated as future work rather than current capabilities.

## 2. Overall workflow

The intended end-to-end MOTEL workflow can be described as:

```text
raw technology data
    -> unmapped YAML records
    -> harmonised MOTEL entities and vocabularies
    -> linked entity records and mapping tables
    -> ontology / graph export (future work in current repo)
    -> backend query layer (future work in current repo)
    -> frontend inspection and export tools (future work in current repo)
```

![Diagram of the MOTEL ingestion and harmonisation workflow](assets/ingest_harmonise.svg "Stage 1 shows the implemented motel-platform workflow from raw source data through ingestion, harmonisation, registries, mappings, and linked entities.")

In the current repository snapshot, the implemented steps are:

1. Collect or receive raw technology data.
2. Store unresolved records as `unmapped` data.
3. Harmonise data into the MOTEL database structure.
4. Create referenced entities and mapping tables for technologies, processes, sources, carriers, attributes, and scopes.
5. Define, but do not yet fully populate, a `linked_entity` target structure.

Current limitation:
Steps involving ontology class/property mapping, graph database construction, backend querying, frontend interaction, and model-ready export are described in project materials but are not implemented as executable code in the present public repository. The `3_graphdb/` directory exists but is empty, and no backend or frontend application code is present in the current tree.

## 3. Data ingestion and harmonisation

### Data ingestion

The primary ingestion method implemented in MOTEL is schema-first staging into the `unmapped` format. For a new project or external user, the intended starting point is not the reFuel.ch notebook itself, but the generic `unmapped` contract defined in [schema/unmapped_entity.yaml](/E:/Barton/repositories/motel-platform/schema/unmapped_entity.yaml) and explained in simplified form in [schema_simple/unmapped_entity.yaml](/E:/Barton/repositories/motel-platform/schema_simple/unmapped_entity.yaml). The introductory notebook [1_ingest/1_data_ingestion.ipynb](/E:/Barton/repositories/motel-platform/1_ingest/1_data_ingestion.ipynb) serves as the current guide to that structure.

In practice, a new contributor can work as follows:

1. Collect raw technology information from spreadsheets, reports, databases, or manual review.
2. Map each raw record into the `unmapped` schema with at least a `technology_name`, optional technology and scope descriptions, source references, attributes, balancing information, and metadata.
3. Save those records as YAML in the `unmapped` structure.
4. Run the harmonisation workflow to resolve free-text names into MOTEL registries and controlled vocabularies.

This staging can be done manually or with project-specific transformation code:

- Manual route: a user can prepare YAML directly against [schema/unmapped_entity.yaml](/E:/Barton/repositories/motel-platform/schema/unmapped_entity.yaml).
- Scripted route: a project can create its own ingestion notebook or helper script, following the pattern used in the existing reFuel.ch example.
- LLM-supported route: in the current repository, LLM support is implemented mainly in harmonisation rather than in generic ingestion. The harmonisation helper in [2_harmonise/harmonise_helpers.py](/E:/Barton/repositories/motel-platform/2_harmonise/harmonise_helpers.py) uses a local Ollama model to help standardise names, fill required fields, and match records against existing registries after the `unmapped` YAML has been created.

The main implemented project-specific example is the reFuel.ch workflow in [1_ingest/examples/refuel/ingestion_pipeline.ipynb](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/ingestion_pipeline.ipynb), supported by [1_ingest/examples/refuel/scripts/ingestion_helper.py](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/scripts/ingestion_helper.py). This example reads an Excel workbook with multiple sheets, including `ConvTech`, `StorTech`, `EmbeddedCarbon`, and `Reference`, transforms those records into the `unmapped` schema, and writes sheet-level exports such as:

- [1_ingest/examples/refuel/output/unmapped_entities_refuel_convtech.yaml](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/output/unmapped_entities_refuel_convtech.yaml)
- [1_ingest/examples/refuel/output/unmapped_entities_refuel_stortech.yaml](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/output/unmapped_entities_refuel_stortech.yaml)
- [1_ingest/examples/refuel/output/unmapped_entities_refuel_embeddedcarbon.yaml](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/output/unmapped_entities_refuel_embeddedcarbon.yaml)

The same notebook then publishes a combined staging file to [motel-db/unmapped_entity/unmapped_entities_refuel.yaml](/E:/Barton/repositories/motel-platform/motel-db/unmapped_entity/unmapped_entities_refuel.yaml).

This reFuel.ch notebook should therefore be read as a worked example of how a project-specific adapter can populate the generic MOTEL staging format, not as the only allowed ingestion route.

Current supported input format:

- Excel workbook input through the reFuel.ch notebook workflow.

Current limitation:

- No general-purpose CSV, JSON, API, or form-based ingestion pipeline is implemented in the current public tree.
- Ingestion is notebook-driven rather than packaged as a reusable command-line tool or service.

### Unmapped versus linked entities

`unmapped` data is the raw staging format. It keeps source-oriented names, free-text scope descriptions, flexible attribute payloads, and source references before they are matched to MOTEL registries. This contract is defined in [schema/unmapped_entity.yaml](/E:/Barton/repositories/motel-platform/schema/unmapped_entity.yaml).

`linked_entity` is the target relational structure for harmonised records. It is defined in [schema/linked_entity.yaml](/E:/Barton/repositories/motel-platform/schema/linked_entity.yaml) and is intended to reference standardised technologies, attributes, carriers, scopes, and sources through foreign-key style identifiers.

In practice, the harmonisation step currently writes:

- controlled vocabularies under [motel-db/controlled_vocabulary](/E:/Barton/repositories/motel-platform/motel-db/controlled_vocabulary/attribute.csv)
- referenced secondary entities under [motel-db/secondary](/E:/Barton/repositories/motel-platform/motel-db/secondary/source.csv)
- provenance and crosswalk tables under [motel-db/mapping](/E:/Barton/repositories/motel-platform/motel-db/mapping/source_map.csv)

The harmonisation notebook is [2_harmonise/2_data_harmonisation.ipynb](/E:/Barton/repositories/motel-platform/2_harmonise/2_data_harmonisation.ipynb), and its main logic lives in [2_harmonise/harmonise_helpers.py](/E:/Barton/repositories/motel-platform/2_harmonise/harmonise_helpers.py).

Current limitation:

- The current `linked_entity` output file at [motel-db/linked_entity/linked_entity.yaml](/E:/Barton/repositories/motel-platform/motel-db/linked_entity/linked_entity.yaml) is empty in this repository snapshot, even though the schema and notebook logic for producing linked entities exist.

## 4. MOTEL data structure

The implemented data model in this repository is split across schemas and CSV/YAML registries.

Main entities currently represented:

- `technology`: standardised technology registry in [schema/secondary/technology.yaml](/E:/Barton/repositories/motel-platform/schema/secondary/technology.yaml) and [motel-db/secondary/technology.csv](/E:/Barton/repositories/motel-platform/motel-db/secondary/technology.csv)
- `process`: standardised process registry in [schema/secondary/process.yaml](/E:/Barton/repositories/motel-platform/schema/secondary/process.yaml)
- `source`: standardised reference registry in [schema/secondary/source.yaml](/E:/Barton/repositories/motel-platform/schema/secondary/source.yaml) and [motel-db/secondary/source.csv](/E:/Barton/repositories/motel-platform/motel-db/secondary/source.csv)
- `attribute`: controlled parameter vocabulary in [schema/controlled_vocabulary/attribute.yaml](/E:/Barton/repositories/motel-platform/schema/controlled_vocabulary/attribute.yaml) and [motel-db/controlled_vocabulary/attribute.csv](/E:/Barton/repositories/motel-platform/motel-db/controlled_vocabulary/attribute.csv)
- `carrier`: controlled carrier vocabulary in [schema/controlled_vocabulary/carrier.yaml](/E:/Barton/repositories/motel-platform/schema/controlled_vocabulary/carrier.yaml)
- scope vocabularies: `geographic_scope`, `temporal_scope`, `capacity_scope`, `system_boundary`
- `linked_entity`: harmonised record structure in [schema/linked_entity.yaml](/E:/Barton/repositories/motel-platform/schema/linked_entity.yaml)

Minimum fields for a technology in the current schema:

- `tech_id`
- `technology_name`

Additional currently defined fields include `technology_description`, `technology_variant`, `main_process`, `main_operation_unit`, and `ontology_iri`.

Minimum fields for an attribute in the current schema:

- `attribute_id`
- `attribute_name`
- `attribute_description`
- `unit`
- `data_format`

Additional currently defined fields include `ontology_iri` and `note`.

The `unmapped` record structure is broader and includes:

- `technology_name`
- nested `technology`
- nested `scope`
- `sources`
- `attributes`
- `balancing`
- `metadata`
- `harmonisation_record`

This makes `unmapped` suitable for preserving source-level context before standardisation.

## 5. Ontology mapping

The current repository shows ontology intent mainly through schema fields rather than through a completed ontology mapping workflow. In particular, the `technology` and `attribute` schemas both include an `ontology_iri` field:

- [schema/secondary/technology.yaml](/E:/Barton/repositories/motel-platform/schema/secondary/technology.yaml)
- [schema/controlled_vocabulary/attribute.yaml](/E:/Barton/repositories/motel-platform/schema/controlled_vocabulary/attribute.yaml)

This indicates that MOTEL entities are designed to carry resolvable ontology links. However, no ontology files such as `.ttl`, `.owl`, or mapping configuration files are present in the current public repository snapshot, and no executable ontology transformation script is present under `3_graphdb/`.

![Diagram of the MOTEL ontology and graph workflow](assets/ontology_graphdb.svg "Stage 2 shows the downstream path from harmonised MOTEL datasets into ontology mapping, graph-ready data, knowledge graph creation, and search or exploration tools.")

The current mapping tables in [motel-db/mapping](/E:/Barton/repositories/motel-platform/motel-db/mapping/source_map.csv) support harmonisation traceability rather than ontology conversion. For example:

| MOTEL field/entity | Ontology class/property | Purpose |
| ------------------ | ----------------------- | ------- |
| `technology.ontology_iri` | external ontology IRI | placeholder field for linking a technology to an ontology concept |
| `attribute.ontology_iri` | external ontology IRI | placeholder field for linking an attribute to an ontology concept |
| `linked_entity.tech_id` | `technology.tech_id` foreign-key style reference | connects a harmonised record to a standard technology entity |
| `linked_entity.values[].attribute_id` | `attribute.attribute_id` foreign-key style reference | connects a harmonised value to a standard attribute definition |

Current limitation:

- No repository-local ontology vocabulary files were found.
- No implemented mapping from MOTEL fields to RDF predicates or OWL classes was found.
- Ontology linkage is currently a schema provision, not a completed export workflow.

## 6. Graph database construction

The current repository does not contain an implemented graph database build pipeline. The folder [3_graphdb](/E:/Barton/repositories/motel-platform/3_graphdb) exists but is empty. No RDF, Turtle, SPARQL, GraphDB, or Neo4j configuration files were found in the active tree.

What is implemented today is the relational precondition for graph construction:

- harmonised entities in `motel-db/secondary/`
- controlled vocabularies in `motel-db/controlled_vocabulary/`
- source mappings in `motel-db/mapping/`
- linked-entity schema in `schema/linked_entity.yaml`

If a graph layer is added later, the likely relationship pattern would be:

```text
technology -> has parameter -> attribute
attribute -> has value/unit/source -> value record
technology/attribute -> maps to ontology IRI
source -> provides provenance for parameter values
```

Current limitation:

- No implemented graph construction script exists in the current public tree.
- No serialized RDF or graph database export artifact is present.

## 7. Backend and frontend workflow

No backend API or frontend application code is present in the current public repository snapshot. The repository contains a static documentation site in [docs/index.html](/E:/Barton/repositories/motel-platform/docs/index.html), but no service code for querying or editing the MOTEL database.

Therefore, the following workflow is not yet implemented in code in this tree:

1. Open a webapp.
2. Browse or select technologies.
3. Inspect parameters and provenance through an API.
4. Edit or customise values through the interface.
5. Export model-ready configuration from the interface.

Current limitation:

- No backend endpoints exist in the active repository.
- No frontend pages or components exist beyond static documentation.
- No implemented browser-based editor or query UI was found.

## 8. Export to model-ready input

The implemented export in the current repository is YAML export for staging data rather than model-ready solver configuration export.

Implemented exports:

- per-sheet unmapped YAML exports in [1_ingest/examples/refuel/ingestion_pipeline.ipynb](/E:/Barton/repositories/motel-platform/1_ingest/examples/refuel/ingestion_pipeline.ipynb)
- consolidated staging export to [motel-db/unmapped_entity/unmapped_entities_refuel.yaml](/E:/Barton/repositories/motel-platform/motel-db/unmapped_entity/unmapped_entities_refuel.yaml)
- harmonised CSV registries under `motel-db/secondary/`, `motel-db/controlled_vocabulary/`, and `motel-db/mapping/`

The current export preserves, depending on the stage:

- technology name
- raw or harmonised parameter names
- values
- units
- source references and linked attributes
- harmonisation mappings
- selected provenance metadata

Current limitation:

- No implemented export to model-specific YAML, TOML, JSON, or solver configuration files was found.
- No API-based export function exists in the current public tree.
- No graph-enriched export is implemented.

## 9. ORD and FAIR contribution

The implemented workflow already contributes to ORD and FAIR goals in several concrete ways.

First, it improves traceability by preserving raw source references in `unmapped` records and by generating explicit mapping tables such as [motel-db/mapping/source_map.csv](/E:/Barton/repositories/motel-platform/motel-db/mapping/source_map.csv). Second, it makes assumptions more visible by storing scope descriptions, notes, and source-linked attributes before and during harmonisation. Third, it creates reusable structured data through explicit YAML schemas and CSV registries rather than leaving technology assumptions only in spreadsheets.

The workflow also supports reproducibility because the transformation from spreadsheet input to staging YAML and then to harmonised registries is encoded in notebooks and helper scripts rather than being entirely manual. Finally, the presence of `ontology_iri` fields in the schemas establishes a concrete interoperability path, even though the ontology export layer is not yet implemented in this repository snapshot.

## 10. Current limitations and future work

- Current limitation: only the reFuel.ch ingestion workflow is implemented as a full example.
- Current limitation: ingestion and harmonisation are notebook-driven rather than packaged as stable command-line or service workflows.
- Current limitation: the `linked_entity` schema is defined, but the checked-in [motel-db/linked_entity/linked_entity.yaml](/E:/Barton/repositories/motel-platform/motel-db/linked_entity/linked_entity.yaml) is currently empty.
- Current limitation: ontology mapping is only partial. Schema fields such as `ontology_iri` exist, but no ontology files or mapping scripts are present in the active repository.
- Current limitation: graph database construction is not implemented in the current `3_graphdb/` tree.
- Current limitation: no backend API or frontend application is present in the public repository snapshot.
- Current limitation: no model-ready export beyond YAML staging files and harmonised CSV registries is implemented.
- Future work: add a formal ontology vocabulary and explicit field-to-predicate mappings.
- Future work: implement graph export and query infrastructure.
- Future work: add a backend service and frontend interface for inspection, editing, and export.
- Future work: broaden ingestion beyond the current notebook example and add stronger automated validation.
