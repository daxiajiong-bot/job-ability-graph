"""Read/write bridge for JobTrend discovery outputs (offline component).

Serves the trend / emerging-role / skill-update artifacts produced by the
``jobtrend-team-delivery-2026-08-09`` component as JSON so the frontend
"岗位发现" page can render them without running the heavy pipeline in-process.

Beyond the read-only component artifacts, this module adds a *runtime overlay*
layer (``backend/data/runtime/trend/``) that supports the competition-required
loop:  generate job definition (LLM) -> human optimization (edit) -> review
(approve / reject) -> dynamic update.  Overlay entries win over the component
artifacts when both exist.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.api.v1.dependencies import get_repository
from backend.app.api.v1.errors import success
from backend.app.domain.entities import DocumentType, SourceDocument

router = APIRouter(tags=["JobTrend discovery"])

_COMPONENT_DIR = (
    Path(__file__).resolve().parents[5]
    / "jobtrend-team-delivery-2026-08-09"
    / "component"
)

_RUNTIME_DIR = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "runtime"
    / "trend"
)

_OVERLAY_FILE = _RUNTIME_DIR / "emerging_roles_overlay.jsonl"
_SKILL_UPDATES_OVERLAY_FILE = _RUNTIME_DIR / "skill_updates_overlay.jsonl"
_LOCK = threading.Lock()

# 变化类型 → 图谱操作归类：通过"采纳"审核后如何写图。
_ADD_KINDS = {"added", "rising", "modified"}
_REMOVE_KINDS = {"removal_candidate"}
# declining 表示占比下降但技能仍然需要，默认不改变图谱边，仅记录审核结果。

# ── helpers: component read-only data ───────────────────


def _read_jsonl(name: str) -> list[dict]:
    path = _COMPONENT_DIR / name
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _read_csv(name: str) -> list[dict]:
    path = _COMPONENT_DIR / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_evidence_map() -> dict[str, dict]:
    return {row["evidence_id"]: row for row in _read_jsonl("evidence.jsonl")}


# ── helpers: runtime overlay ─────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_overlay() -> list[dict]:
    if not _OVERLAY_FILE.exists():
        return []
    rows: list[dict] = []
    for line in _OVERLAY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_overlay(rows: list[dict]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _OVERLAY_FILE.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _get_overlay(role_id: str) -> dict | None:
    for row in _read_overlay():
        if row.get("role_id") == role_id:
            return row
    return None


def _upsert_overlay(role_id: str, patch: dict) -> dict:
    with _LOCK:
        rows = _read_overlay()
        merged = None
        kept: list[dict] = []
        for row in rows:
            if row.get("role_id") == role_id:
                merged = {**row, **patch}
                kept.append(merged)
            else:
                kept.append(row)
        if merged is None:
            merged = {"role_id": role_id, **patch}
            kept.append(merged)
        _write_overlay(kept)
    return merged


def _merge_role(role: dict) -> dict:
    """Apply runtime overlay (edited definition + review state) onto a role."""
    overlay = _get_overlay(role.get("role_id", ""))
    if not overlay:
        return role
    merged = {**role}
    # 1) 定义字段：优先 overlay 顶层，其次 generated_definition
    def _pick(field, fallback):
        if field in overlay and overlay[field] is not None:
            return overlay[field]
        gd = overlay.get("generated_definition") or {}
        if field in gd and gd[field] is not None:
            return gd[field]
        return fallback

    merged["canonical_title"] = _pick("canonical_title", role.get("canonical_title"))
    merged["aliases"] = _pick("aliases", role.get("aliases"))
    merged["core_responsibilities"] = _pick("core_responsibilities", role.get("core_responsibilities"))
    merged["required_skills"] = _pick("required_skills", role.get("required_skills"))
    merged["preferred_skills"] = _pick("preferred_skills", role.get("preferred_skills"))
    merged["typical_industry_scenarios"] = _pick(
        "typical_industry_scenarios", role.get("typical_industry_scenarios")
    )
    merged["industries"] = _pick("industries", role.get("industries"))
    merged["regions"] = _pick("regions", role.get("regions"))
    if "status" in overlay and overlay["status"]:
        merged["status"] = overlay["status"]
    if "review" in overlay:
        merged["review"] = overlay["review"]
    if "definition_source" in overlay:
        merged["definition_source"] = overlay["definition_source"]
    if "generated_definition" in overlay:
        merged["generated_definition"] = overlay["generated_definition"]
    if "updated_at" in overlay:
        merged["updated_at"] = overlay["updated_at"]
    if overlay.get("publish") is not None:
        merged["publish"] = overlay["publish"]
    return merged


def _publish_role_document(repository: Any, role_id: str, role: dict, now: str) -> dict:
    """把审核通过的新岗位写入系统 JD 文档库，供求职者检索/匹配参考。

    - 使用确定性文档 ID（``sys_emr_<hash(role_id)>``）与 ``INSERT OR REPLACE``，
      重复"通过"为幂等刷新（人工优化后再审核会覆盖原文案）。
    - user_id = 'system'，对所有用户可见：求职者的智能推荐 / 人岗匹配会自动
      把它纳入 JD 候选池。
    """
    title = str(role.get("canonical_title") or "").strip()
    if not title:
        return {"published": False, "document_id": None, "reason": "岗位名称缺失，无法入库"}

    def _names(value) -> list[str]:
        out: list[str] = []
        for item in value or []:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item).strip()
            if name:
                out.append(name)
        return out

    required = _names(role.get("required_skills"))
    preferred = _names(role.get("preferred_skills"))
    skills = list(dict.fromkeys([*required, *preferred]))
    core = [str(x).strip() for x in (role.get("core_responsibilities") or []) if str(x).strip()]
    scenarios = [
        str(x).strip()
        for x in (role.get("typical_industry_scenarios") or [])
        if str(x).strip()
    ]

    blocks = [f"岗位名称：{title}", "【新兴岗位 · 由岗位趋势分析与 HR 审核确认后发布】", ""]
    if core:
        blocks += ["岗位职责：", *[f"{i}. {item}" for i, item in enumerate(core, 1)], ""]
    if required:
        blocks += [f"必备技能：{'、'.join(required)}", ""]
    if preferred:
        blocks += [f"加分技能：{'、'.join(preferred)}", ""]
    if scenarios:
        blocks += [f"典型行业应用场景：{' / '.join(scenarios)}", ""]
    text = "\n".join(blocks).rstrip()

    doc_id = "sys_emr_" + hashlib.sha256(role_id.encode("utf-8")).hexdigest()[:12]
    metadata = {
        "title": title,
        "job_title": title,
        "company_name": None,
        "industry": scenarios[0] if scenarios else None,
        "skills": skills,
        "location": None,
        "experience": None,
        "education": None,
        "source_type": "emerging_role_review",
        "role_id": role_id,
        "is_emerging_role": True,
        "published_at": now,
    }
    source = {"source_system": "jobtrend_review", "external_id": role_id}
    document = SourceDocument(
        id=doc_id,
        document_type=DocumentType.JD,
        text=text,
        source=source,
        metadata=metadata,
        created_at=now,
        content_digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    if hasattr(repository, "_db"):
        if hasattr(repository, "ensure_user"):
            repository.ensure_user("system")
        repository.add_document(document, user_id="system")
    else:
        repository.add_document(document)
    return {
        "published": True,
        "document_id": doc_id,
        "title": title,
        "skill_count": len(skills),
    }


# ── helpers: runtime overlay for skill updates ───────────


def _read_skill_overlay() -> list[dict]:
    if not _SKILL_UPDATES_OVERLAY_FILE.exists():
        return []
    rows: list[dict] = []
    for line in _SKILL_UPDATES_OVERLAY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _write_skill_overlay(rows: list[dict]) -> None:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _SKILL_UPDATES_OVERLAY_FILE.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _get_skill_overlay(update_id: str) -> dict | None:
    for row in _read_skill_overlay():
        if row.get("update_id") == update_id:
            return row
    return None


def _upsert_skill_overlay(update_id: str, patch: dict) -> dict:
    """Upsert one skill-update overlay row, deep-merging per-change decisions."""
    with _LOCK:
        rows = _read_skill_overlay()
        merged = None
        kept: list[dict] = []
        for row in rows:
            if row.get("update_id") == update_id:
                merged = {**row, **patch}
                merged["changes"] = {
                    **dict(row.get("changes") or {}),
                    **dict(patch.get("changes") or {}),
                }
                kept.append(merged)
            else:
                kept.append(row)
        if merged is None:
            merged = {"update_id": update_id, **patch}
            merged["changes"] = dict(patch.get("changes") or {})
            kept.append(merged)
        _write_skill_overlay(kept)
    return merged


def _derive_skill_update_status(update: dict, decided: dict) -> str:
    """Aggregate per-change decisions into an update-level review status."""
    total = len(update.get("changes") or [])
    if total == 0:
        return "candidate"
    decisions = [
        entry.get("decision")
        for entry in decided.values()
        if entry.get("decision") in {"approved", "rejected"}
    ]
    if len(decisions) >= total:
        if all(d == "approved" for d in decisions):
            return "approved"
        if all(d == "rejected" for d in decisions):
            return "rejected"
        return "partial"
    return "partial" if any(d == "approved" for d in decisions) else "candidate"


def _merge_skill_update(update: dict) -> dict:
    """Apply the runtime overlay (per-change decisions + review state) onto an update."""
    overlay = _get_skill_overlay(update.get("update_id", ""))
    merged = {**update}
    decisions = dict((overlay or {}).get("changes") or {})
    merged["changes"] = []
    for change in update.get("changes") or []:
        row = {**change}
        decision = decisions.get(change.get("skill_name")) or {}
        row["decision"] = decision.get("decision") or "pending"
        row["reviewed_at"] = decision.get("reviewed_at")
        merged["changes"].append(row)
    if overlay:
        merged["status"] = overlay.get("status") or merged.get("status") or "candidate"
        merged["review"] = {
            "reviewer": overlay.get("reviewer"),
            "reviewed_at": overlay.get("reviewed_at"),
            "notes": overlay.get("notes"),
        }
        if overlay.get("graph_apply") is not None:
            merged["graph_apply"] = overlay["graph_apply"]
    return merged


def _apply_skill_updates_to_graph(
    update: dict,
    additions: list[dict],
    removals: list[dict],
    reviewer: str = "expert",
    notes: str = "",
) -> dict:
    """Write approved skill changes onto existing job nodes of the live graph."""
    backend = os.getenv("GRAPH_BACKEND", "neo4j").strip().lower()
    if backend != "neo4j":
        return {
            "applied": False,
            "backend": backend or "unavailable",
            "reason": "GRAPH_BACKEND 未启用 neo4j，本次仅记录审核结果，图谱未写入",
        }
    try:
        from backend.app.infrastructure.neo4j.adapters import (  # noqa: PLC0415
            Neo4jGraphStore,
            Neo4jSettings,
        )
    except Exception as exc:  # pragma: no cover - depends on env
        return {
            "applied": False,
            "backend": "neo4j",
            "reason": f"Neo4j 依赖不可用：{exc}",
        }
    snapshot_id = (os.getenv("TREND_UPDATE_GRAPH_SNAPSHOT", "kg_prebuilt_v2").strip() or "kg_prebuilt_v2")
    store = None
    try:
        store = Neo4jGraphStore(Neo4jSettings.from_env())
        return store.apply_role_skill_delta(
            snapshot_id=snapshot_id,
            role_title=update.get("canonical_role") or "",
            additions=additions,
            removals=removals,
            reviewer=reviewer,
            notes=notes,
        )
    except Exception as exc:  # pragma: no cover - depends on live Neo4j
        return {"applied": False, "backend": "neo4j", "reason": f"图谱更新失败：{exc}"}
    finally:
        if store is not None:
            store.close()


# ── LLM-backed definition generation ─────────────────────


def _llm_client():
    from backend.app.infrastructure.llm.client import OpenAICompatibleChatClient
    from backend.app.infrastructure.llm.settings import LLMSettings

    return OpenAICompatibleChatClient(LLMSettings.from_env())


def _evidence_context(role: dict, max_blocks: int = 6) -> str:
    """Collect the raw JD excerpts (原文证据) that support this role."""
    evidence_map = _read_evidence_map()
    ids = role.get("evidence_ids") or []
    blocks: list[str] = []
    for ev_id in ids[: max_blocks * 3]:
        ev = evidence_map.get(ev_id)
        if not ev:
            continue
        text = (ev.get("text") or "").strip()
        if not text:
            continue
        uri = ev.get("uri") or ""
        blocks.append(f"【来源 {uri or ev_id}】\n{text}")
        if len(blocks) >= max_blocks:
            break
    return "\n\n".join(blocks)


def _build_generation_messages(role: dict) -> list[dict[str, str]]:
    existing = {
        "岗位名称(候选)": role.get("canonical_title") or "",
        "核心职责(草稿)": role.get("core_responsibilities") or [],
        "必备技能(草稿)": [s.get("name") for s in (role.get("required_skills") or [])],
        "加分技能(草稿)": [s.get("name") for s in (role.get("preferred_skills") or [])],
        "行业场景(草稿)": role.get("typical_industry_scenarios") or [],
    }
    system = (
        "你是人力资源领域的岗位定义专家。根据招聘JD原文证据，为新兴岗位生成规范、"
        "准确、可核验的岗位定义。只依据证据原文，不得编造；若证据不足，字段留空或写'待补充'。"
        "严格输出 JSON，不要输出任何其他文字。"
    )
    user = (
        "请为以下新岗位候选生成完整岗位定义，JSON 结构如下：\n"
        "{\n"
        '  "canonical_title": "岗位名称（正式名称）",\n'
        '  "core_responsibilities": ["核心职责1", "核心职责2", ...],\n'
        '  "required_skills": [{"name": "必备技能名"}],\n'
        '  "preferred_skills": [{"name": "加分技能名"}],\n'
        '  "typical_industry_scenarios": ["典型行业应用场景1", ...]\n'
        "}\n\n"
        "现有草稿：\n"
        f"{json.dumps(existing, ensure_ascii=False)}\n\n"
        "招聘JD原文证据：\n"
        f"{_evidence_context(role)}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _mock_generate_definition(role: dict) -> dict:
    """Deterministic fallback: polish the existing candidate fields into a definition."""
    return {
        "canonical_title": role.get("canonical_title") or "新兴岗位（待命名）",
        "core_responsibilities": list(role.get("core_responsibilities") or []),
        "required_skills": [
            {"name": s.get("name")} for s in (role.get("required_skills") or []) if s.get("name")
        ],
        "preferred_skills": [
            {"name": s.get("name")} for s in (role.get("preferred_skills") or []) if s.get("name")
        ],
        "typical_industry_scenarios": list(role.get("typical_industry_scenarios") or []),
    }


def _generate_definition(role: dict) -> tuple[dict, str]:
    """Generate a 5-element job definition. Returns (definition, source)."""
    settings = None
    try:
        from backend.app.infrastructure.llm.settings import LLMSettings

        settings = LLMSettings.from_env()
    except Exception:
        settings = None

    if settings is not None and settings.backend != "mock":
        try:
            content = _llm_client().chat(_build_generation_messages(role))
            payload = json.loads(content)
            definition = {
                "canonical_title": str(payload.get("canonical_title") or "").strip(),
                "core_responsibilities": [
                    str(x).strip() for x in (payload.get("core_responsibilities") or []) if str(x).strip()
                ],
                "required_skills": [
                    {"name": str(x.get("name")).strip()}
                    for x in (payload.get("required_skills") or [])
                    if isinstance(x, dict) and str(x.get("name") or "").strip()
                ],
                "preferred_skills": [
                    {"name": str(x.get("name")).strip()}
                    for x in (payload.get("preferred_skills") or [])
                    if isinstance(x, dict) and str(x.get("name") or "").strip()
                ],
                "typical_industry_scenarios": [
                    str(x).strip() for x in (payload.get("typical_industry_scenarios") or []) if str(x).strip()
                ],
            }
            if definition.get("canonical_title"):
                return definition, "llm"
        except Exception:
            pass  # fall back to mock so the demo always works

    return _mock_generate_definition(role), "mock"


# ── routes ───────────────────────────────────────────────


@router.get("/trend/emerging-roles")
def list_emerging_roles(request: Request) -> dict:
    """New-role candidates with definitions, scores and evidence (runtime overlay applied)."""
    roles = [_merge_role(role) for role in _read_jsonl("emerging_roles.jsonl")]
    return success(request, {"emerging_roles": roles})


@router.get("/trend/skill-updates")
def list_skill_updates(request: Request) -> dict:
    """Existing-role skill changes (added/rising/modified/declining).

    Runtime overlay (per-change 采纳/驳回 decisions) is applied onto the
    read-only component artifacts before returning.
    """
    updates = [_merge_skill_update(row) for row in _read_jsonl("job_skill_updates.jsonl")]
    return success(request, {"skill_updates": updates})


@router.get("/trend/features")
def list_trend_features(request: Request) -> dict:
    """Trend indicators for roles and abilities."""
    return success(request, {"features": _read_jsonl("trend_features.jsonl")})


@router.get("/trend/review-queue")
def list_review_queue(request: Request) -> dict:
    """Human review queue (candidate -> approved / rejected)."""
    return success(request, {"review_queue": _read_csv("review_queue.csv")})


@router.get("/trend/summary")
def trend_summary(request: Request) -> dict:
    """Counts for the discovery dashboard."""
    return success(
        request,
        {
            "emerging_roles": len(_read_jsonl("emerging_roles.jsonl")),
            "skill_updates": len(_read_jsonl("job_skill_updates.jsonl")),
            "features": len(_read_jsonl("trend_features.jsonl")),
            "review_queue": len(_read_csv("review_queue.csv")),
            "source": "jobtrend-team-delivery-2026-08-09/component",
        },
    )


@router.post("/trend/emerging-roles/{role_id}/generate-definition")
def generate_role_definition(request: Request, role_id: str) -> dict:
    """Generate a 5-element job definition (title, duties, must/preferred skills, scenarios).

    Uses the configured LLM when available (LLM_BACKEND=ollama); otherwise falls
    back to a deterministic mock so the demo always returns a usable definition.
    """
    role = next((r for r in _read_jsonl("emerging_roles.jsonl") if r.get("role_id") == role_id), None)
    if role is None:
        raise HTTPException(status_code=404, detail=f"role not found: {role_id}")

    definition, source = _generate_definition(role)
    now = _now_iso()
    overlay = _upsert_overlay(
        role_id,
        {
            "generated_definition": definition,
            "definition_source": source,
            "updated_at": now,
            "status": "needs_review",
        },
    )
    # surface the merged role for the frontend
    merged = _merge_role(role)
    merged["generated_definition"] = definition
    merged["definition_source"] = source
    merged["status"] = overlay.get("status", "needs_review")
    merged["updated_at"] = now
    return success(
        request,
        {
            "role_id": role_id,
            "definition": definition,
            "source": source,
            "status": merged["status"],
            "role": merged,
        },
    )


@router.put("/trend/emerging-roles/{role_id}/definition")
def save_role_definition(request: Request, role_id: str, payload: dict) -> dict:
    """Persist a human-optimized (人工优化) job definition."""
    role = next((r for r in _read_jsonl("emerging_roles.jsonl") if r.get("role_id") == role_id), None)
    if role is None:
        raise HTTPException(status_code=404, detail=f"role not found: {role_id}")

    def _strings(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [x.strip() for x in value.splitlines() if x.strip()] or [value.strip()]
        return [str(x).strip() for x in value if str(x).strip()]

    def _skills(value) -> list[dict]:
        if value is None:
            return []
        out: list[dict] = []
        for item in value:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item).strip()
            if name:
                out.append({"name": name})
        return out

    definition = {
        "canonical_title": str(payload.get("canonical_title") or "").strip(),
        "core_responsibilities": _strings(payload.get("core_responsibilities")),
        "required_skills": _skills(payload.get("required_skills")),
        "preferred_skills": _skills(payload.get("preferred_skills")),
        "typical_industry_scenarios": _strings(payload.get("typical_industry_scenarios")),
    }
    now = _now_iso()
    overlay = _upsert_overlay(
        role_id,
        {
            "generated_definition": definition,
            "definition_source": "human_edit",
            "updated_at": now,
            "status": payload.get("status") or "needs_review",
        },
    )
    merged = _merge_role(role)
    merged["generated_definition"] = definition
    merged["definition_source"] = "human_edit"
    merged["updated_at"] = now
    return success(
        request,
        {
            "role_id": role_id,
            "definition": definition,
            "source": "human_edit",
            "status": overlay.get("status", "needs_review"),
            "role": merged,
        },
    )


@router.post("/trend/emerging-roles/{role_id}/review")
def review_role_definition(
    request: Request,
    role_id: str,
    payload: dict,
    repository: Any = Depends(get_repository),
) -> dict:
    """Human review decision: approved / rejected with optional notes.

    通过（approved）：除记录状态外，还会把该新岗位写入系统 JD 文档库
    （确定性 ID，幂等 upsert），使求职者在智能推荐 / 人岗匹配中能检索到。
    """
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    role = next((r for r in _read_jsonl("emerging_roles.jsonl") if r.get("role_id") == role_id), None)
    if role is None:
        raise HTTPException(status_code=404, detail=f"role not found: {role_id}")

    reviewer = str(payload.get("reviewer") or "expert").strip() or "expert"
    notes = str(payload.get("notes") or "").strip()
    now = _now_iso()

    previous_overlay = _get_overlay(role_id) or {}
    previous_publish = previous_overlay.get("publish")

    # 通过 → 新岗位入库（供求职者参考）；先合并 overlay 拿到最终定义
    publish = previous_publish
    overlay_patch: dict = {
        "status": decision,
        "review": {
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": now,
            "notes": notes,
        },
        "updated_at": now,
    }
    if decision == "approved":
        merged_before = _merge_role(role)
        try:
            publish = _publish_role_document(repository, role_id, merged_before, now)
        except Exception as exc:  # pragma: no cover - DB failure path
            publish = {"published": False, "document_id": None, "reason": f"入库失败：{exc}"}
        overlay_patch["publish"] = publish

    overlay = _upsert_overlay(role_id, overlay_patch)
    merged = _merge_role(role)
    merged["status"] = overlay.get("status", decision)
    merged["review"] = overlay.get("review")
    merged["updated_at"] = now
    return success(
        request,
        {
            "role_id": role_id,
            "status": merged["status"],
            "review": merged["review"],
            "publish": publish,
            "role": merged,
        },
    )


@router.post("/trend/skill-updates/{update_id}/review")
def review_skill_update(request: Request, update_id: str, payload: dict) -> dict:
    """逐条/批量审核"既有岗位技能更新"：采纳→写回知识图谱，驳回→仅记录。

    Body:
      decision: "approved" | "rejected"   （采纳 / 驳回）
      skill_names: list[str] 可选，缺省或为空数组表示对该更新所有变化项生效
      reviewer / notes: 可选

    采纳的行为按变化类型写图：
      added / rising / modified      → 在既有岗位节点上 MERGE REQUIRES_* 边
      removal_candidate              → 删除既有岗位到该能力的 REQUIRES_* 边
      declining                      → 仅记录审核，不改动图谱
    """
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    updates = _read_jsonl("job_skill_updates.jsonl")
    update = next((row for row in updates if row.get("update_id") == update_id), None)
    if update is None:
        raise HTTPException(status_code=404, detail=f"skill update not found: {update_id}")

    requested = payload.get("skill_names") or []
    if isinstance(requested, str):
        requested = [x.strip() for x in requested.split(",") if x.strip()]
    changes = update.get("changes") or []
    if requested:
        wanted = {str(x) for x in requested}
        targeted = [c for c in changes if c.get("skill_name") in wanted]
    else:
        targeted = list(changes)
    if not targeted:
        raise HTTPException(
            status_code=422,
            detail="no matching skill changes in this update (skill_names invalid)",
        )

    reviewer = str(payload.get("reviewer") or "expert").strip() or "expert"
    notes = str(payload.get("notes") or "").strip()
    now = _now_iso()
    decisions = {
        str(c.get("skill_name")): {
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": now,
            "notes": notes,
        }
        for c in targeted
    }

    # 写图（仅在采纳且存在会改变图谱的变化类型时触发）
    graph_apply = None
    if decision == "approved":
        additions = [
            {
                "skill_name": c.get("skill_name"),
                "change_type": c.get("change_type"),
                "evidence_ids": c.get("evidence_ids") or [],
                "update_id": update_id,
            }
            for c in targeted
            if c.get("change_type") in _ADD_KINDS
        ]
        removals = [
            {
                "skill_name": c.get("skill_name"),
                "change_type": c.get("change_type"),
                "evidence_ids": c.get("evidence_ids") or [],
                "update_id": update_id,
            }
            for c in targeted
            if c.get("change_type") in _REMOVE_KINDS
        ]
        if additions or removals:
            graph_apply = _apply_skill_updates_to_graph(
                update,
                additions,
                removals,
                reviewer=reviewer,
                notes=notes,
            )

    with _LOCK:
        current = _get_skill_overlay(update_id)
        decided_map = dict((current or {}).get("changes") or {})
        decided_map.update(decisions)
        status = _derive_skill_update_status(update, decided_map)
    overlay = _upsert_skill_overlay(
        update_id,
        {
            "status": status,
            "changes": decisions,
            "reviewer": reviewer,
            "reviewed_at": now,
            "notes": notes,
            "graph_apply": graph_apply,
        },
    )
    merged = _merge_skill_update(update)
    return success(
        request,
        {
            "update_id": update_id,
            "decision": decision,
            "status": overlay.get("status", status),
            "review": {
                "reviewer": reviewer,
                "reviewed_at": now,
                "notes": notes,
            },
            "graph_apply": graph_apply,
            "skill_update": merged,
        },
    )
