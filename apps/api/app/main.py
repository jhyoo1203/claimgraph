from fastapi import FastAPI

from app.api.research_runs import router as research_runs_router

app = FastAPI(title="ClaimGraph API", version="0.1.0")

app.include_router(research_runs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
