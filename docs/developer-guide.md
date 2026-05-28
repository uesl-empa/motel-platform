# Developer Guide

## Local Setup

1. Clone repository.
2. Create Python environments for `backend/` and `streamlit/` as needed.
3. Install dependencies using each module's `requirements.txt`.

## Conventions

- Keep technology data in `data/technologies/`.
- Track provenance in `data/sources/sources.csv`.
- Maintain ontology terms in `ontology/motel-ontology.ttl`.

## CI/CD

- `test-backend.yml` validates backend import on pushes/PRs.
- `deploy-docs.yml` publishes documentation to GitHub Pages from `main`.
