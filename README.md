[to be updated]
# MOTEL Database (motel-db)

[![Code License: MIT](https://img.shields.io/badge/Code%20License-MIT-green.svg)](LICENSE)
[![Data License: CC%20BY%204.0](https://img.shields.io/badge/Data%20License-CC--BY%204.0-blue.svg)](DATA_LICENSE)

Methodology for Open Technology Data in Energy Models (MOTEL) is an ETH Domain ORD Program project.

This repository centralizes project components for an open, ontology-ready technology database and workflow for energy system models (ESMs), including documentation, data, ontology, backend/API, and visualization tools.

## Project Links

- Documentation (GitHub Pages): https://YOUR-ORG.github.io/motel-db/
- Streamlit App: https://YOUR-STREAMLIT-APP-URL.streamlit.app/
- ETH Domain ORD Program: https://ethrat.ch/en/eth-domain/open-research-data/

## Repository Structure

Key modules in this repository:

- `.github/workflows/`: CI/CD for docs deployment and backend checks.
- `backend/`: FastAPI backend scaffold.
- `frontend/`: Placeholder for optional Next.js + TypeScript frontend.
- `streamlit/`: Streamlit app with sample data visualizations.
- `data/`: CSV/JSON-LD-ready technology datasets and source metadata.
- `ontology/`: RDF/OWL ontology assets (Turtle format).
- `docs/`: MkDocs source files for documentation website.
- `workflows/`: Data processing scripts and future Renku-compatible workflows.

## Quick Start

### 1. Documentation (MkDocs)

```bash
pip install mkdocs mkdocs-material
mkdocs serve --config-file docs/mkdocs.yml
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open Swagger UI at http://localhost:8000/docs.

### 3. Streamlit App

```bash
cd streamlit
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Licensing

- Code (backend, app code, workflows): MIT License ([LICENSE](LICENSE))
- Data and ontology files: CC BY 4.0 ([DATA_LICENSE](DATA_LICENSE))

## Status

This repository currently contains the requested scaffold and starter files.
Existing backend/frontend/data assets can be moved into their corresponding folders.
