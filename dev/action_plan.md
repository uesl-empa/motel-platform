# MOTEL Workflow v2: Execution Plan

**Project**: Developing a Methodology for Open Technology Data in Energy Models (MOTEL)  
**Version**: 1.0  
**Date**: 2026-01-15  
**Status**: Draft  
**Owner**: Barton Chen, Dennis Beermann

---

## Overview

This plan outlines the implementation of Workflow v2 for the MOTEL project, enabling flexible data collection followed by structured mapping to technologies, processes, and ontologies. The goal is to lower the barrier for contributors while ensuring traceability, interoperability, and standardization.

### Key Principles

- User-first: users submit records with descriptions, scopes, and sources (no upfront `tech_id` or `process_id` required).
- Automated plus manual mapping: records are automatically mapped where possible and manually validated by domain experts.
- Traceability: every record retains provenance for sources, assumptions, and mapping decisions.
- Ontology integration: mapped records are linked to Open Energy Ontology (OEO) or MOTEL terms.

---

## Workflow v2 Diagram

```mermaid
graph TD
    A[User Submits Record] -->|Description, Scope, Sources| B[Store as Unmapped Record]
    B --> C[Automated Mapping Suggestion]
    C --> D[Manual Review by Expert]
    D -->|Approved| E[Assign tech_id/process_id]
    D -->|Rejected| F[Request Clarification]
    E --> G[Link to Ontology (OEO/MOTEL)]
    G --> H[Publish to Database]
    H --> I[Notify User of Mapping]
```

---

## Repository Structure

```text
motel-db/
├── data/
│   ├── unmapped_records/          # Records awaiting mapping
│   │   ├── REC_001.yaml
│   │   └── ...
│   ├── mapped_records/            # Records after mapping
│   │   ├── REC_001.yaml
│   │   └── ...
│   ├── technologies/              # Technology definitions
│   │   ├── tech_list.csv
│   │   └── ...
│   ├── processes/                 # Process definitions
│   │   ├── process_list.csv
│   │   └── ...
│   └── sources/                   # Source metadata
│
├── ontology/                      # Ontology files
│   ├── motel.ttl                  # Custom ontology (TTL format)
│   └── imports/                   # Imported ontologies (e.g., OEO)
│
├── scripts/
│   └── mapping/
│       ├── auto_mapper.py         # Automated mapping
│       ├── ontology_mapper.py     # Ontology-based matching
│       ├── combined_mapper.py     # Merge mapping signals
│       ├── deduplicator.py        # Detect duplicate records
│       ├── validator.py           # Validate YAML records
│       ├── save_record.py         # Save records to YAML
│       ├── update_mapping.py      # Update records with mappings
│       └── link_to_ontology.py    # Link records to ontology terms
│
├── tools/
│   ├── streamlit/
│   │   ├── user_submission.py
│   │   └── reviewer_dashboard.py
│   └── fastapi/
│       └── app.py
│
├── docs/
│   ├── workflow.md
│   ├── user_guide.md
│   └── reviewer_guide.md
│
├── schema/
│   └── motel_schema.yaml
│
└── README.md
```

---

## Timeline and Milestones

| Phase | Tasks | Timeline | Owner |
| --- | --- | --- | --- |
| Phase 1: Setup and Preparation | Update schema, create directories, draft guidelines | Week 1-2 | Barton/Dennis |
| Phase 2: User Submission Interface | Build Streamlit form, YAML validator, temp ID generator | Week 3-5 | Dennis |
| Phase 3: Automated Mapping | Develop matching, deduplication, and suggestions | Week 6-9 | Barton |
| Phase 4: Manual Review Interface | Build reviewer dashboard and approval workflow | Week 10-12 | Dennis |
| Phase 5: Ontology Integration | Update ontology, link records, validate | Week 13-15 | Barton |
| Phase 6: Testing and Validation | Test end-to-end workflow and validate data | Week 16-18 | Barton/Dennis |
| Phase 7: Deployment and Public Release | Deploy apps and announce release | Week 19-20 | Barton/Dennis |

---

## Phase 1: Setup and Preparation

Goal: Prepare repository, schema, and tools for Workflow v2.

### Tasks

| Task | Details | Files | Owner |
| --- | --- | --- | --- |
| Update YAML schema | Add temp_id, status, mapped_tech_id, and mapped_process_id fields | schema/motel_schema.yaml | Barton |
| Create data directories | Set up unmapped and mapped record folders | data/unmapped_records/, data/mapped_records/ | Dennis |
| Update technology list | Add ontology_iri and oeo_equivalent columns | data/technologies/tech_list.csv | Barton |
| Update process list | Add ontology_iri and oeo_equivalent columns | data/processes/process_list.csv | Barton |
| Draft user guide | Document submission steps and quality requirements | docs/user_guide.md | Dennis |
| Draft reviewer guide | Document review criteria and decision rules | docs/reviewer_guide.md | Barton |

---

## Phase 2: User Submission Interface

Goal: Allow users to submit records without pre-assigned tech_id/process_id.

### Implementation Checklist

- Build tools/streamlit/user_submission.py.
- Create scripts/mapping/validator.py.
- Create scripts/mapping/save_record.py.
- Create scripts/mapping/generate_temp_id.py.
- Create scripts/mapping/notify_user.py.
- Test submission form with 5-10 records.

---

## Phase 3: Automated Mapping

Goal: Suggest likely technology and process mappings for unmapped records.

### Implementation Checklist

- Build scripts/mapping/auto_mapper.py.
- Build scripts/mapping/ontology_mapper.py.
- Build scripts/mapping/combined_mapper.py.
- Build scripts/mapping/deduplicator.py.
- Test mapping on 5-10 records.

---

## Phase 4: Manual Review Interface

Goal: Enable reviewer validation and approval of mapping suggestions.

### Implementation Checklist

- Build tools/streamlit/reviewer_dashboard.py.
- Create scripts/mapping/update_mapping.py.
- Create scripts/mapping/move_record.py.
- Test reviewer dashboard with 5-10 records.

---

## Phase 5: Ontology Integration

Goal: Ensure mapped records are linked to OEO or MOTEL terms.

### Implementation Checklist

- Update ontology/motel.ttl with new terms.
- Create scripts/mapping/link_to_ontology.py.
- Create scripts/mapping/validate_ontology.py.
- Add ontology/README.md.
- Link 5-10 test records to ontology.

---

## Phase 6: Testing and Validation

Goal: Validate functional correctness and data quality.

### Implementation Checklist

- Test user submission with 5-10 records.
- Test automated mapping on test records.
- Test manual review in the dashboard.
- Test ontology integration.
- Validate full workflow end-to-end.
- Performance test with 100+ records.

---

## Phase 7: Deployment and Public Release

Goal: Release a usable public workflow.

### Implementation Checklist

- Deploy Streamlit apps to Streamlit Cloud.
- Deploy FastAPI backend (optional).
- Make repository public.
- Announce public release to stakeholders.
- Monitor and iterate based on feedback.

---

## References

- MOTEL Project Proposal
- ETH Domain ORD Program
- Open Energy Ontology (OEO)
- Streamlit Documentation
- RDFLib Documentation
- GitHub Actions Documentation
