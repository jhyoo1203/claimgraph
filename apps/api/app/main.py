from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.sources import (
    SourceErrorResponse,
    SourceNotFoundError,
    router as sources_router,
)

app = FastAPI(title="ClaimGraph API", version="0.1.0")
app.include_router(sources_router)


@app.exception_handler(SourceNotFoundError)
async def source_not_found_handler(_: Request, _exc: SourceNotFoundError) -> JSONResponse:
    """Keep missing Source responses stable for clients and retries."""

    body = SourceErrorResponse(
        error_code="source_not_found",
        message="Source not found.",
    )
    return JSONResponse(status_code=404, content=body.model_dump())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
