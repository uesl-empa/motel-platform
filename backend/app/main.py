from fastapi import FastAPI

from app.routes.technologies import router as technologies_router

app = FastAPI(
    title="MOTEL Technology API",
    description="Backend API for the MOTEL open technology database",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(technologies_router)
