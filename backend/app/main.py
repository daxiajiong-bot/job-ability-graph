"""FastAPI entrypoint for v3 Contract Skeleton."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.v1.errors import install_exception_handlers
from backend.app.api.v1.router import router as v1_router
from backend.app.infrastructure.wiring import build_container


app = FastAPI(
    title="v3 Contract Skeleton",
    description="Formal resource contracts for future LLM, RAG, Neo4j, and graph-enhanced matching integrations.",
    version="3.0.0",
)
app.state.container = build_container()


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


install_exception_handlers(app)
app.include_router(v1_router)


@app.get("/", include_in_schema=False)
def index() -> dict[str, str]:
    return {
        "service": "v3 Contract Skeleton",
        "docs": "/docs",
        "api_base": "/api/v1",
    }


@app.get("/health", tags=["System"])
def health(request: Request) -> JSONResponse:
    repository_health = request.app.state.container.repository.health()
    return JSONResponse(
        {
            "status": "ok",
            "service": "v3 Contract Skeleton",
            "persistence": repository_health["persistence"],
            "repository": repository_health,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
