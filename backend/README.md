# Backend (FastAPI)

This folder contains the MOTEL backend API scaffold.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs for Swagger UI.
