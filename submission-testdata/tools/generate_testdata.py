#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
作品提交 (3) 测试数据生成器（纯标准库，可复现）

从仓库真实数据源抽取：
  既有岗位 = job:40857992907  python自动化测试工程师（双休/福利好）
            JD 原始数据 -> data/outputs/jd_raw.jsonl
            能力图谱   -> data/small_raw_200_lskt_tech_v2/{graph_nodes,graph_edges}.jsonl
  新岗位   = role:51fda9ea3aba30e88342  AI Agent安全评测工程师
            岗位/技能提案 -> jobtrend-team-delivery-2026-08-09/component/emerging_roles.jsonl
            图谱增量提案 -> .../component/kg_link_delta.jsonl
            支撑证据     -> .../component/evidence.jsonl

用法（在仓库根目录 job-ability-graph/ 下）：
  python submission-testdata/tools/generate_testdata.py
输出到 submission-testdata/ 下（自动覆盖同名文件）。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]          # job-ability-graph/
OUT = REPO / "submission-testdata"
EXISTING_JOB_ID = "40857992907"
NEW_ROLE_ID = "role:51fda9ea3aba30e88342"

JD_SRC = REPO / "data" / "outputs" / "jd_raw.jsonl"
GRAPH_NODES = REPO / "data" / "small_raw_200_lskt_tech_v2" / "graph_nodes.jsonl"
GRAPH_EDGES = REPO / "data" / "small_raw_200_lskt_tech_v2" / "graph_edges.jsonl"
EMERGING_ROLES = REPO / "jobtrend-team-delivery-2026-08-09" / "component" / "emerging_roles.jsonl"
KG_LINK_DELTA = REPO / "jobtrend-team-delivery-2026-08-09" / "component" / "kg_link_delta.jsonl"
EVIDENCE = REPO / "jobtrend-team-delivery-2026-08-09" / "component" / "evidence.jsonl"

# 节点 label -> 面向评审的中文分类
LABEL_CN = {
    "Job": "岗位",
    "Company": "公司",
    "Technology": "技术",
    "Skill": "技能",
    "Knowledge": "知识",
    "TransversalCompetence": "通用能力",
    "LanguageCompetence": "语言能力",
    "Candidate": "候选人",
    "Evidence": "证据",
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with io.open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def dump(obj, rel: str) -> None:
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    with io.open(target, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    print(f"wrote {target.relative_to(REPO)}  ({target.stat().st_size} bytes)")


def node_name(node: dict) -> str:
    props = node.get("properties") or {}
    return props.get("title") or props.get("name") or props.get("quote") or node.get("node_id", "")


def build_existing_job() -> None:
    jd_rows = load_jsonl(JD_SRC)
    jd = next((r for r in jd_rows if str(r.get("job_id", "")) == EXISTING_JOB_ID), None)
    if jd is None:
        raise SystemExit(f"JD record {EXISTING_JOB_ID} not found in {JD_SRC}")

    nodes = load_jsonl(GRAPH_NODES)
    edges = load_jsonl(GRAPH_EDGES)
    node_by_id = {n["node_id"]: n for n in nodes}

    job_id = f"job:{EXISTING_JOB_ID}"
    job_node = node_by_id.get(job_id)
    if job_node is None:
        raise SystemExit(f"graph Job node {job_id} not found")

    # 1) 岗位 -> 技术/技能/知识/能力 (REQUIRES_*)
    req_edges = [e for e in edges if e.get("source_id") == job_id and str(e.get("relation_type", "")).startswith("REQUIRES_")]
    cap_ids = {e["target_id"] for e in req_edges if e.get("target_id") in node_by_id}

    # 2) 能力 -> 证据 (SUPPORTED_BY)：能力节点为全图共享，仅保留本岗位 JD 的证据
    ev_prefix = f"evidence:jd_{EXISTING_JOB_ID}:"
    def is_own_evidence(nid: str) -> bool:
        return nid.startswith(ev_prefix)
    sup_edges = [
        e for e in edges
        if e.get("source_id") in cap_ids
        and e.get("relation_type") == "SUPPORTED_BY"
        and is_own_evidence(str(e.get("target_id")))
        and e.get("target_id") in node_by_id
    ]
    ev_ids = {e["target_id"] for e in sup_edges}
    used_ids = {job_id} | cap_ids | ev_ids

    out_nodes = []
    for nid in sorted(used_ids):
        n = node_by_id[nid]
        props = n.get("properties") or {}
        out_nodes.append({
            "id": nid,
            "label": n.get("label"),
            "label_cn": LABEL_CN.get(n.get("label"), n.get("label")),
            "name": node_name(n),
            "properties": props,
        })

    def edge_out(e: dict) -> dict:
        props = dict(e.get("properties") or {})
        keep = {k: props[k] for k in ("role", "confidence", "surface") if k in props}
        return {
            "id": e.get("edge_id"),
            "source": e.get("source_id"),
            "target": e.get("target_id"),
            "relation_type": e.get("relation_type"),
            "evidence_ids": e.get("evidence_ids", []),
            "properties": keep,
        }

    out_edges = [edge_out(e) for e in req_edges] + [edge_out(e) for e in sup_edges]

    from collections import Counter
    cap_counter = Counter()
    for e in req_edges:
        cap_counter[node_by_id[e["target_id"]].get("label")] += 1
    evidence_quotes = [
        {"id": nid, "quote": (node_by_id[nid].get("properties") or {}).get("quote", "")}
        for nid in sorted(ev_ids)
    ]

    dump({
        "说明": "既有岗位能力图谱输出（子图：岗位 -> 技术/技能/知识 -> 证据），取自预构建图谱快照 kg_prebuilt_v2 的原始 JSONL",
        "graph_source": str(GRAPH_NODES.relative_to(REPO)),
        "job": {"id": job_id, "name": node_name(job_node)},
        "graph": {"nodes": out_nodes, "edges": out_edges},
        "summary": {
            "node_count": len(out_nodes),
            "edge_count": len(out_edges),
            "capability_edges_by_label": dict(cap_counter),
            "evidence_node_count": len(ev_ids),
            "evidence_quotes": evidence_quotes,
        },
    }, "existing-job_python-auto-test-engineer/output/job_ability_graph.json")

    # 输入：原始 JD（结构化保留，jd_text 为岗位数据源原文）
    jd_in = {k: jd[k] for k in (
        "source_type", "source_name", "job_id", "job_title", "company_name", "industry",
        "location", "salary_min", "salary_max", "experience", "education", "publish_date",
        "jd_text", "responsibilities", "requirements",
    ) if k in jd}
    jd_in["_说明"] = "原始招聘岗位数据源（智联 zhaopin 抓取字段 + 岗位原文 jd_text），对应能力图谱证据注释（sentence_annotations.jsonl）"
    dump(jd_in, "existing-job_python-auto-test-engineer/input/jd_source.json")


def build_new_job() -> None:
    roles = load_jsonl(EMERGING_ROLES)
    role = next((r for r in roles if r.get("role_id") == NEW_ROLE_ID), None)
    if role is None:
        raise SystemExit(f"role {NEW_ROLE_ID} not found in {EMERGING_ROLES}")

    deltas = [d for d in load_jsonl(KG_LINK_DELTA) if d.get("source_id") == NEW_ROLE_ID]
    evidence_rows = load_jsonl(EVIDENCE)
    ev_by_id = {str(r.get("id") or r.get("evidence_id") or ""): r for r in evidence_rows}

    # 输入 1：新岗位候选（含职责/必需技能/证据）
    dump(role, "new-job_ai-agent-security-evaluator/input/emerging_role.json")

    # 输入 2：支撑证据样例（取该岗位证据 id 子集）
    want = role.get("evidence_ids") or []
    sample = []
    for eid in want:
        row = ev_by_id.get(eid)
        if row is None:
            continue
        sample.append(row)
        if len(sample) >= 6:
            break
    dump({
        "说明": "AI Agent安全评测工程师 岗位数据源支撑证据样例（from evidence.jsonl；evidence_id 与 emerging_role.json 中 required_skills[*].evidence_ids 对应）",
        "evidence": sample,
    }, "new-job_ai-agent-security-evaluator/input/evidence_sample.json")

    # 输出 1：图谱增量提案（原始 deltas 精简视图）
    delta_out = []
    for d in deltas:
        props = d.get("properties") or {}
        evs = d.get("evidence_ids") or []
        delta_out.append({
            "delta_id": d.get("delta_id"),
            "operation": d.get("operation"),
            "source_id": d.get("source_id"),
            "target_id": d.get("target_id"),
            "relation_type": d.get("relation_type"),
            "ability_name": props.get("ability_name"),
            "category": props.get("category"),
            "resolution_status": d.get("resolution_status"),
            "evidence_count": len(evs),
            "evidence_sample": evs[:5],
        })
    dump({
        "说明": "新岗位 -> 既有能力节点 的图谱增量提案（trend_kg_delta_v1；需评审通过后由 merge_kg_delta.py 合并进演化快照 kg_evolved_v1）",
        "role_id": NEW_ROLE_ID,
        "canonical_title": role.get("canonical_title"),
        "delta_count": len(delta_out),
        "deltas": delta_out,
    }, "new-job_ai-agent-security-evaluator/output/kg_link_delta.json")

    # 输出 2：新岗位“能力边”视图（role -> abilities, 附带证据数）
    edges = []
    node_ops = []
    for d in delta_out:
        if d["operation"] == "propose_edge" and d.get("ability_name"):
            edges.append({
                "source": d["source_id"],
                "target": d["target_id"],
                "relation_type": d["relation_type"],
                "ability_name": d["ability_name"],
                "resolution_status": d["resolution_status"],
                "evidence_count": d["evidence_count"],
            })
        else:
            node_ops.append({
                "delta_id": d["delta_id"],
                "operation": d["operation"],
                "source_id": d["source_id"],
            })
    dump({
        "说明": "新岗位能力图谱（提案形态）：角色节点指向既有能力/证据，合并后即进入动态演化图谱",
        "role": {
            "id": NEW_ROLE_ID,
            "canonical_title": role.get("canonical_title"),
            "aliases": role.get("aliases", []),
            "core_responsibilities": role.get("core_responsibilities", []),
        },
        "required_skill_names": [s.get("name") for s in role.get("required_skills", [])],
        "ability_edges": edges,
        "summary": {
            "role_count": 1,
            "proposed_ability_edge_count": len(edges),
            "propose_node_ops": node_ops,
            "evidence_ids_total": len(role.get("evidence_ids") or []),
        },
    }, "new-job_ai-agent-security-evaluator/output/ability_edges_proposal.json")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    build_existing_job()
    build_new_job()
    print("done.")
