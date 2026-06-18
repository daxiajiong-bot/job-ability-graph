"""Smoke test for the reorganized FastAPI demo project."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.algorithms.panorama_graph import build_panorama_graph
from backend.app.algorithms.pipeline import match_jd_resume, parse_jd, parse_resume
from backend.app.api.router import match as match_endpoint
from backend.app.api.router import samples
from backend.app.graph.graph_views import VIEW_FILES
from backend.app.main import app, health
from backend.app.schemas.api import MatchRequest
from backend.app.storage import paths
from backend.app.storage.json_store import load_json


def main() -> None:
    assert health() == {"status": "ok"}
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    for path in (
        "/health",
        "/samples",
        "/parse/jd",
        "/parse/resume",
        "/match",
        "/graph/full",
        "/graph/view",
        "/graph/panorama",
        "/evolution/discover",
        "/evolution/update",
    ):
        assert path in paths, f"missing route: {path}"

    payload = samples()
    assert payload["jds"], "sample JDs are empty"
    assert payload["resumes"], "sample resumes are empty"

    jd_text = payload["jds"][0]["text"]
    resume_text = payload["resumes"][0]["text"]

    jd_result = parse_jd(jd_text)
    resume_result = parse_resume(resume_text)
    graph_result = build_panorama_graph(payload["jds"][:2])
    match_result = match_jd_resume(jd_text, resume_text)
    llm_match_result = match_jd_resume(jd_text, resume_text, use_llm=True)
    api_llm_response = match_endpoint(MatchRequest(jd_text=jd_text, resume_text=resume_text, use_llm=True))

    assert jd_result["mode"] == "jd_parse"
    assert resume_result["mode"] == "resume_parse"
    assert "final_score" in match_result["match_result"]
    assert match_result["match_result"]["llm_used"] is False
    assert llm_match_result["match_result"]["llm_used"] is False
    assert llm_match_result["match_result"]["final_score"] == match_result["match_result"]["final_score"]
    assert api_llm_response.match_result["llm_used"] is False
    assert api_llm_response.match_result["final_score"] == match_result["match_result"]["final_score"]
    assert graph_result["nodes"]
    assert graph_result["edges"]

    artifacts = assert_storage_artifacts(match_result)

    print(
        json.dumps(
            {
                "status": "ok",
                "routes": len(paths),
                "jd_title": jd_result["jd_parse"].get("job_title"),
                "resume_candidate": resume_result["resume_parse"].get("candidate_id"),
                "match_score": match_result["match_result"].get("final_score"),
                "llm_used": match_result["match_result"].get("llm_used"),
                "panorama_nodes": len(graph_result["nodes"]),
                "storage": artifacts,
            },
            ensure_ascii=False,
        )
    )


def assert_storage_artifacts(result: dict) -> dict:
    jd_id = result["match_result"]["jd_id"]
    resume_doc_id = result["resume_parse"]["doc_id"]
    match_id = result["match_result"]["match_id"]
    graph_id = result["graph"]["graph_id"]

    raw_jd_path = paths.RAW_JD_DIR / f"{jd_id}.json"
    raw_resume_path = paths.RAW_RESUME_DIR / f"{resume_doc_id}.json"
    parsed_jd_path = paths.PARSED_JD_PROFILES_DIR / f"{jd_id}.json"
    parsed_resume_path = paths.PARSED_RESUME_PROFILES_DIR / f"{resume_doc_id}.json"
    match_path = paths.MATCHES_DIR / f"{match_id}.json"
    graph_path = paths.GRAPH_DIR / "graph_full.json"
    evidence_path = paths.EVIDENCE_DIR / "evidence_index.json"

    raw_jd = load_json(raw_jd_path)
    raw_resume = load_json(raw_resume_path)
    parsed_jd = load_json(parsed_jd_path)
    parsed_resume = load_json(parsed_resume_path)
    saved_match = load_json(match_path)
    saved_graph = load_json(graph_path)
    evidence_index = load_json(evidence_path)

    assert raw_jd and raw_jd["doc_id"] == jd_id and raw_jd["raw_text"]
    assert raw_resume and raw_resume["doc_id"] == resume_doc_id and raw_resume["raw_text"]
    assert parsed_jd and parsed_jd["doc_id"] == jd_id and parsed_jd["profile"]
    assert parsed_resume and parsed_resume["doc_id"] == resume_doc_id and parsed_resume["profile"]
    assert saved_match and saved_match["match_id"] == match_id
    assert saved_match["jd_id"] == jd_id
    assert saved_match["resume_id"] == result["match_result"]["resume_id"]
    assert saved_match["final_score"] == result["match_result"]["final_score"]
    assert saved_match["decision"] in {"strong_match", "partial_match", "low_match"}
    assert saved_graph and saved_graph["graph_id"] == graph_id and saved_graph["nodes"] and saved_graph["edges"]
    node_types = {node["type"] for node in saved_graph["nodes"]}
    for node_type in ("Position", "Skill", "Candidate", "Evidence"):
        assert node_type in node_types, f"missing graph node type: {node_type}"
    for edge in saved_graph["edges"]:
        assert "relation" in edge and "properties" in edge

    views = {}
    for view_type, filename in VIEW_FILES.items():
        view_path = paths.GRAPH_DIR / filename
        view = load_json(view_path)
        assert view and view["nodes"] and view["edges"], f"empty graph view: {view_type}"
        views[view_type] = str(view_path)
    match_view = load_json(paths.GRAPH_DIR / VIEW_FILES["match"])
    assert "matched_skills" in match_view["metadata"]
    assert "missing_skills" in match_view["metadata"]
    assert "partial_skills" in match_view["metadata"]
    tech_stack_view = load_json(paths.GRAPH_DIR / VIEW_FILES["tech_stack"])
    assert any(node["type"] == "TechStack" for node in tech_stack_view["nodes"])
    evolution_view = load_json(paths.GRAPH_DIR / VIEW_FILES["evolution"])
    assert any(node["type"] == "Version" for node in evolution_view["nodes"])
    assert evidence_index and evidence_index["count"] > 0
    assert all(item.get("source_doc_id") for item in evidence_index["items"])

    return {
        "raw_jd": str(raw_jd_path),
        "raw_resume": str(raw_resume_path),
        "parsed_jd": str(parsed_jd_path),
        "parsed_resume": str(parsed_resume_path),
        "match": str(match_path),
        "graph": str(graph_path),
        "graph_views": views,
        "evidence": str(evidence_path),
    }


if __name__ == "__main__":
    main()
