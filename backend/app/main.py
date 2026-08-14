"""FastAPI entrypoint for v3 Contract Skeleton."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

# Load .env from project root before any other imports read env vars
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Windows DLL fix: register torch/lib before paddle/torch are imported
if hasattr(os, "add_dll_directory"):
    for _d in [
        Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib",
        Path(sys.prefix) / "Library" / "bin",
    ]:
        if _d.is_dir():
            os.add_dll_directory(str(_d))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.api.v1.errors import install_exception_handlers
from backend.app.api.v1.router import router as v1_router
from backend.app.infrastructure.wiring import build_container

logger = logging.getLogger(__name__)


app = FastAPI(
    title="v3 Contract Skeleton",
    description="Formal resource contracts for future LLM, RAG, Neo4j, and graph-enhanced matching integrations.",
    version="3.0.0",
)
app.state.container = build_container()

# ── Auto-seed initial JD data on startup ──
_seed_done = False


@app.on_event("startup")
def seed_initial_data() -> None:
    global _seed_done
    if _seed_done:
        return
    repository = app.state.container.repository
    # Only seed if using SQLite repository
    if hasattr(repository, "_db"):
        if hasattr(repository, "recover_stale_tasks"):
            # A task marked running belongs to a previous worker once startup
            # runs; waiting for its age threshold would leave the UI polling
            # an orphan forever after a reload.
            recovered = repository.recover_stale_tasks(max_age_seconds=0)
            if recovered:
                logger.warning("Marked %d stale profile tasks as failed after restart", recovered)
        from backend.app.infrastructure.sqlite.seed import ensure_prebuilt_graph, load_initial_jds

        jsonl_path = Path(__file__).resolve().parent.parent.parent / "data" / "small-raw" / "jd_raw_100.jsonl"
        if jsonl_path.exists():
            count = load_initial_jds(repository._db, jsonl_path)
            if count > 0:
                logger.info("Seeded %d initial JD records from %s", count, jsonl_path)
            else:
                logger.info("Initial JD data already loaded, skipping seed")
        else:
            logger.warning("Seed file not found: %s", jsonl_path)
        registered = ensure_prebuilt_graph(
            repository,
            Path(__file__).resolve().parent.parent.parent / "data",
        )
        if registered:
            logger.info("Registered pre-built knowledge graph snapshot kg_prebuilt_v2")
    _seed_done = True


@app.on_event("shutdown")
def close_db_connections() -> None:
    repository = app.state.container.repository
    if hasattr(repository, "_db"):
        repository._db.close()


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

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8002, reload=True)
