# MOTEL Workflow v2 User Guide

This guide explains how to run the overnight MVP for Workflow v2.

For the complete end-to-end explanation, see dev/docs/workflow_v2_full_workflow.md.

## What is included

- A Python workflow engine for record submission, mapping suggestions, and approval.
- A Streamlit submission app.
- A Streamlit reviewer dashboard.
- A notebook demo for end-to-end execution.
- Sample technology and process catalogs.

## Location

- Engine package: dev/workflow_v2/
- Data area: dev/workflow_data/
- Apps: dev/tools/streamlit/
- Tests: dev/tests/

## Quick start

1. Activate your Python environment.
2. From repository root, run bootstrap data:
   - python -m dev.workflow_v2.bootstrap
3. Reset demo state anytime:
   - python -m dev.workflow_v2.reset_demo_data
4. Generate suggestions:
   - python -m dev.workflow_v2.cli suggest
5. Approve one record:
   - python -m dev.workflow_v2.cli approve --record-id REC_0001 --reviewer reviewer_01

## Run apps

- User submission app:
  - streamlit run dev/tools/streamlit/user_submission.py
- Reviewer dashboard:
  - streamlit run dev/tools/streamlit/reviewer_dashboard.py

## End-to-end flow

1. Submit records with description, source, scope, and values.
2. Record is stored in dev/workflow_data/unmapped_records/.
3. Reviewer generates suggestions from catalog matching.
4. Reviewer approves a suggestion.
5. Record moves to dev/workflow_data/mapped_records/ with mapping metadata.

## Notes

- Mapping method is rule-based fuzzy matching for explainability and low dependency overhead.
- Duplicate detection uses exact normalized fingerprint and text similarity checks.
- Records are written as YAML when PyYAML is available; otherwise JSON syntax is written to .yaml files.
