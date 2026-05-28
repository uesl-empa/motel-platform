# API Reference

The FastAPI backend publishes OpenAPI documentation through Swagger UI.

## Local Swagger UI

1. Run backend with `uvicorn app.main:app --reload` from `backend/`.
2. Open `http://localhost:8000/docs`.

## Endpoints (Current Scaffold)

- `GET /health`
- `GET /technologies`

Future endpoint references can be generated directly from OpenAPI as the backend expands.
