"""Convert parsed and matched results into graph data for visualization."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from backend.app.algorithms.common import GapAnalysisResult, GraphData, JDParseResult, MatchResult, ResumeParseResult, SkillMention, SkillProfile
from backend.app.algorithms.skill_catalog import RELATED_LOOKUP, SKILL_CATALOG, skill_id_for


class GraphBuilder:
    def build(
        self,
        jd_parse: JDParseResult,
        resume_parse: ResumeParseResult,
        job_profile: SkillProfile,
        resume_profile: SkillProfile,
        match_result: MatchResult,
        gap_analysis: GapAnalysisResult,
    ) -> GraphData:
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        def add_node(node_id: str, node_type: str, label: str, properties: Optional[Dict[str, Any]] = None) -> None:
            nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label, "properties": properties or {}})

        def add_edge(source: str, target: str, edge_type: str, weight: float, properties: Optional[Dict[str, Any]] = None) -> None:
            key = (source, target, edge_type)
            edges[key] = {
                "source": source,
                "target": target,
                "type": edge_type,
                "weight": round(float(weight), 3),
                "properties": properties or {},
            }

        add_node("job:primary", "Job", jd_parse.job_title, {"job_category": jd_parse.job_category})
        add_node("resume:primary", "Resume", resume_parse.candidate_id or "候选人简历", {"education": resume_parse.education, "experience_years": resume_parse.experience_years})
        add_edge("resume:primary", "job:primary", "matches", match_result.final_score / 100, {"final_score": match_result.final_score})

        skill_names = set()
        job_skill_map = {skill["name"]: skill for skill in job_profile.skills}
        resume_skill_map = {skill["name"]: skill for skill in resume_profile.skills}
        skill_names.update(job_skill_map)
        skill_names.update(resume_skill_map)
        jd_mentions_by_id = {mention.mention_id: mention for mention in jd_parse.raw_skill_mentions}
        resume_mentions_by_id = {mention.mention_id: mention for mention in resume_parse.raw_skill_mentions}
        jd_evidence_by_id = {item["evidence_id"]: item for item in jd_parse.evidence_items}
        resume_evidence_by_id = {item["evidence_id"]: item for item in resume_parse.evidence_items}

        for name in sorted(skill_names):
            info = SKILL_CATALOG.get(name, {"skill_id": skill_id_for(name), "skill_type": "未知"})
            skill_node_id = info["skill_id"]
            skill_type = info["skill_type"]
            skill_type_id = f"skill_type:{skill_type}"
            add_node(skill_node_id, "Skill", name, {"skill_type": skill_type})
            add_node(skill_type_id, "SkillType", skill_type, {})
            add_edge(skill_node_id, skill_type_id, "belongs_to", 1.0, {})
            if name in job_skill_map:
                job_skill = job_skill_map[name]
                add_edge("job:primary", skill_node_id, "requires", job_skill["weight"], {"requirement_level": job_skill["requirement_level"]})
                self._add_evidence_edges(add_node, add_edge, skill_node_id, job_skill.get("evidence_refs", []), jd_mentions_by_id, jd_evidence_by_id, "jd")
            if name in resume_skill_map:
                resume_skill = resume_skill_map[name]
                add_edge("resume:primary", skill_node_id, "has", resume_skill["proficiency"], {"confidence": resume_skill["confidence"], "recency": resume_skill["recency"]})
                self._add_evidence_edges(add_node, add_edge, skill_node_id, resume_skill.get("evidence_refs", []), resume_mentions_by_id, resume_evidence_by_id, "resume")

        for missing in match_result.missing_skills:
            add_edge("resume:primary", missing["skill_id"], "lacks", missing["jd_weight"], {"priority": missing["priority"]})

        for source, related_items in RELATED_LOOKUP.items():
            if source not in skill_names:
                continue
            source_id = SKILL_CATALOG[source]["skill_id"]
            for target, relation_type in related_items:
                if target in skill_names:
                    add_edge(source_id, SKILL_CATALOG[target]["skill_id"], "related_to", 0.5, {"relation_type": relation_type})

        return GraphData(
            nodes=list(nodes.values()),
            edges=list(edges.values()),
            graph_metadata={
                "created_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "schema_version": "demo-v1",
                "source_ids": {"jd": "job:primary", "resume": "resume:primary"},
                "gap_summary": gap_analysis.gap_summary,
            },
        )

    def _add_evidence_edges(
        self,
        add_node: Any,
        add_edge: Any,
        skill_node_id: str,
        mention_refs: Sequence[str],
        mention_by_id: Mapping[str, SkillMention],
        evidence_by_id: Mapping[str, Dict[str, Any]],
        source_type: str,
    ) -> None:
        if not mention_refs:
            return
        seen_evidence_ids = set()
        for ref in mention_refs:
            mention = mention_by_id.get(ref)
            if not mention or not mention.evidence_id or mention.evidence_id in seen_evidence_ids:
                continue
            evidence = evidence_by_id.get(mention.evidence_id)
            if not evidence:
                continue
            seen_evidence_ids.add(mention.evidence_id)
            evidence_id = f"evidence:{source_type}:{evidence['evidence_id']}"
            add_node(
                evidence_id,
                "Evidence",
                evidence["text"][:36],
                {"source_type": source_type, "section": evidence["section"], "text": evidence["text"]},
            )
            add_edge(skill_node_id, evidence_id, "evidenced_by", 1.0, {})
