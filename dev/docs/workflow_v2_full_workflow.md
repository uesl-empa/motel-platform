# MOTEL Workflow v2: Full User Workflow

This is the single, end-to-end explanation of how Workflow v2 works for contributors and reviewers.

## Purpose

Workflow v2 is designed so users can submit data without first knowing technology IDs or process IDs.

The system then:
1. Stores the record as unmapped.
2. Suggests likely mappings.
3. Lets a reviewer approve or adjust mapping.
4. Moves approved records into mapped storage with audit metadata.

## User Roles

- Contributor: Submits records with description, scope, sources, and values.
- Reviewer: Generates suggestions, reviews evidence, and approves mapping.
- Maintainer: Tunes mapping rules, reviews duplicates, and manages releases.

## Data Lifecycle

1. Submit record
- Input fields: description, source, scope, values.
- Output: one file in dev/workflow_data/unmapped_records.

2. Suggest mapping
- Matching method: rule-based fuzzy similarity against technology and process catalogs.
- Output: suggestions file at dev/workflow_data/suggestions/latest.yaml.

3. Review and approve
- Reviewer approves a selected suggestion.
- Output: record is moved from unmapped_records to mapped_records.
- Mapping metadata added: mapped_tech_id, mapped_process_id, confidence, method, reviewer, approval time.

4. Duplicate check
- System scans mapped and unmapped records for exact or high-similarity duplicates.
- Output: duplicate pair list (empty list if none found).

## File and Folder Map

- Engine code: dev/workflow_v2/
- Submission app: dev/tools/streamlit/user_submission.py
- Reviewer app: dev/tools/streamlit/reviewer_dashboard.py
- Demo notebook: dev/workflow_v2_demo.ipynb
- Catalog data: dev/workflow_data/technologies.csv and dev/workflow_data/processes.csv
- Unmapped records: dev/workflow_data/unmapped_records/
- Mapped records: dev/workflow_data/mapped_records/
- Suggestions: dev/workflow_data/suggestions/latest.yaml

## How Users Run It

1. Reset demo data
- python -m dev.workflow_v2.reset_demo_data

2. Generate suggestions
- python -m dev.workflow_v2.cli suggest

3. Approve one record
- python -m dev.workflow_v2.cli approve --record-id REC_0001 --reviewer reviewer_01

4. Optional apps
- streamlit run dev/tools/streamlit/user_submission.py
- streamlit run dev/tools/streamlit/reviewer_dashboard.py

## What to Inspect

Before approval:
- Raw unmapped file in dev/workflow_data/unmapped_records/REC_XXXX.yaml

After approval:
- Raw mapped file in dev/workflow_data/mapped_records/REC_XXXX.yaml
- Confirm mapping metadata fields are populated.

## Validation Checklist

- Record submission writes a new unmapped file.
- Suggestion generation creates suggestion entries for each unmapped record.
- Approval moves record to mapped folder.
- Mapping metadata is present after approval.
- Duplicate detection executes and returns expected pairs.

## Known Limits in Current MVP

- Matching quality is baseline and explainable, not ontology-deep semantic matching.
- Confidence scores are similarity-based heuristics.
- Reviewer approval is the quality gate.

## Recommended Next Improvements

1. Add ontology synonym expansion to mapping.
2. Add threshold policy for auto-flagging low-confidence suggestions.
3. Add richer tests for edge cases and malformed records.
4. Add API endpoints for integration use cases.
