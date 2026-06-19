"""FastAPI application entrypoint for the demo backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes_evolution import router as evolution_router
from backend.app.api.routes_graph import router as graph_router
from backend.app.api.routes_match import router as match_router
from backend.app.api.routes_parse import router as parse_router
from backend.app.core.config import FRONTEND_DIR


app = FastAPI(
    title="Job Ability Graph Demo API",
    description="Rule-based JD/resume matching API for the competition demo.",
    version="0.1.0",
)

# 允许 Vue 前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

app.include_router(parse_router)
app.include_router(match_router)
app.include_router(graph_router)
app.include_router(evolution_router)


@app.get("/", include_in_schema=False)
def index() -> object:
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"status": "ok", "frontend": "not_found"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
