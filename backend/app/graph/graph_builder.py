"""Build a unified full graph from structured profiles and match results."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from backend.app.algorithms.skill_catalog import CAPABILITY_DOMAIN_MAPPING, SKILL_CATALOG, TECH_STACK_MAPPING, skill_id_for
from backend.app.core.config import DEFAULT_GRAPH_VERSION
from backend.app.graph.graph_schema import make_edge, make_graph, make_node
from backend.app.storage.id_generator import make_candidate_id, make_doc_id, make_position_id


class GraphBuilder:
    def build(
        self,
        jd_profile: Mapping[str, Any],
        resume_profile: Mapping[str, Any],
        match_result: Mapping[str, Any],
        gap_analysis: Mapping[str, Any],
        evidence_items: Sequence[Mapping[str, Any]],
        version: str = DEFAULT_GRAPH_VERSION,
    ) -> Dict[str, Any]:
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        def add_node(node_id: str, label: str, node_type: str, level: int = 0, properties: Optional[Mapping[str, Any]] = None) -> None:
            existing = nodes.get(node_id)
            if existing:
                existing["properties"].update(dict(properties or {}))
                return
            nodes[node_id] = make_node(node_id, label, node_type, level, properties)

        def add_edge(source: str, target: str, relation: str, weight: float = 1.0, properties: Optional[Mapping[str, Any]] = None) -> None:
            key = (source, target, relation)
            if key in edges:
                edges[key]["weight"] = round(max(float(edges[key]["weight"]), float(weight)), 3)
                edges[key]["properties"].update(dict(properties or {}))
                return
            edges[key] = make_edge(source, target, relation, weight, properties)

        job_meta = dict(jd_profile.get("metadata") or {})
        resume_meta = dict(resume_profile.get("metadata") or {})
        position_label = str(job_meta.get("job_title") or "目标岗位")
        candidate_label = str(resume_meta.get("candidate_id") or "候选人")
        position_id = str(jd_profile.get("position_id") or job_meta.get("position_id") or make_position_id(position_label))
        candidate_id = str(resume_profile.get("resume_id") or resume_meta.get("resume_id") or make_candidate_id(candidate_label))
        match_id = str(match_result.get("match_id") or "match:current")
        version_id = f"version:{version}"

        add_node(
            position_id,
            position_label,
            "Position",
            0,
            {
                "job_category": job_meta.get("job_category"),
                "education_requirement": job_meta.get("education_requirement"),
                "experience_requirement": job_meta.get("experience_requirement"),
                "domain_requirement": job_meta.get("domain_requirement", []),
                "doc_id": jd_profile.get("doc_id") or match_result.get("jd_id"),
            },
        )
        add_node(
            candidate_id,
            candidate_label,
            "Candidate",
            0,
            {
                "education": resume_meta.get("education"),
                "experience_years": resume_meta.get("experience_years"),
                "target_position": resume_meta.get("target_position"),
                "doc_id": resume_profile.get("doc_id"),
            },
        )
        add_node(version_id, version, "Version", 0, {"version": version, "match_id": match_id})
        add_edge(candidate_id, position_id, "matches", float(match_result.get("final_score", 0.0)) / 100, {"match_id": match_id, "final_score": match_result.get("final_score"), "decision": match_result.get("decision")})

        job_skills = {skill["name"]: skill for skill in jd_profile.get("skills", [])}
        resume_skills = {skill["name"]: skill for skill in resume_profile.get("skills", [])}
        skill_names = set(job_skills) | set(resume_skills)
        skill_names.update(item.get("name") for item in match_result.get("missing_skills", []) if item.get("name"))
        skill_names.update(item.get("name") for item in match_result.get("insufficient_skills", []) if item.get("name"))

        for skill_name in sorted(skill_names):
            skill = job_skills.get(skill_name) or resume_skills.get(skill_name) or {"name": skill_name}
            skill_id = str(skill.get("skill_id") or SKILL_CATALOG.get(skill_name, {}).get("skill_id") or skill_id_for(skill_name))
            skill_type = str(skill.get("skill_type") or SKILL_CATALOG.get(skill_name, {}).get("skill_type") or "未知")
            capability_name = CAPABILITY_DOMAIN_MAPPING.get(skill_type, skill_type)
            capability_id = f"capability:{capability_name}"

            add_node(skill_id, skill_name, "Skill", 2, {"skill_type": skill_type, "aliases": skill.get("aliases", [])})
            add_node(capability_id, capability_name, "Capability", 1, {"skill_type": skill_type})
            add_edge(position_id, capability_id, "requires_capability", 1.0, {"skill_type": skill_type})
            add_edge(capability_id, skill_id, "contains_skill", float(job_skills.get(skill_name, {}).get("weight", 1.0)), {"skill_type": skill_type})

            for stack_name in self._tech_stacks_for(skill_name):
                stack_id = f"tech_stack:{stack_name}"
                add_node(stack_id, stack_name, "TechStack", 1, {})
                add_edge(stack_id, skill_id, "contains_skill", 1.0, {"view": "tech_stack"})
                add_edge(skill_id, stack_id, "belongs_to_stack", 1.0, {})

            if skill_name in job_skills:
                job_skill = job_skills[skill_name]
                requirement_level = str(job_skill.get("requirement_level") or "required")
                level_id = f"level:requirement:{requirement_level}"
                add_node(level_id, requirement_level, "Level", 3, {"level_type": "requirement"})
                add_edge(position_id, skill_id, "requires_skill", float(job_skill.get("weight", 1.0)), {"requirement_level": requirement_level, "match_id": match_id})
                add_edge(level_id, skill_id, "contains_skill", float(job_skill.get("weight", 1.0)), {"level_type": "requirement", "owner": "position"})
                evolution_relation = self._evolution_relation(job_skill)
                add_edge(position_id, skill_id, evolution_relation, float(job_skill.get("weight", 1.0)), {"version_id": version_id})
                add_edge(skill_id, version_id, evolution_relation, float(job_skill.get("weight", 1.0)), {"position_id": position_id})

            if skill_name in resume_skills:
                resume_skill = resume_skills[skill_name]
                proficiency = float(resume_skill.get("proficiency", 0.0))
                level_name = self._proficiency_level(proficiency)
                level_id = f"level:proficiency:{level_name}"
                add_node(level_id, level_name, "Level", 3, {"level_type": "proficiency"})
                add_edge(candidate_id, skill_id, "has_skill", proficiency, {"confidence": resume_skill.get("confidence"), "recency": resume_skill.get("recency"), "match_id": match_id})
                add_edge(level_id, skill_id, "contains_skill", proficiency, {"level_type": "proficiency", "owner": "candidate"})

        for item in match_result.get("missing_skills", []):
            skill_id = str(item.get("skill_id") or skill_id_for(str(item.get("name", ""))))
            add_edge(candidate_id, skill_id, "lacks", float(item.get("jd_weight", 1.0)), {"priority": item.get("priority"), "match_status": "missing"})

        for item in match_result.get("insufficient_skills", []):
            skill_id = str(item.get("skill_id") or skill_id_for(str(item.get("name", ""))))
            add_edge(candidate_id, skill_id, "partially_matches", float(item.get("resume_level", 0.5)), {"gap_type": item.get("gap_type"), "required_level": item.get("required_level"), "current_level": item.get("resume_level"), "match_status": "partial"})

        for matched in match_result.get("matched_skills", []):
            if matched.get("match_type") == "related":
                skill_id = str(matched.get("skill_id") or skill_id_for(str(matched.get("name", ""))))
                add_edge(candidate_id, skill_id, "partially_matches", float(matched.get("resume_proficiency", 0.5)), {"gap_type": "related_only", "related_resume_skill": matched.get("related_resume_skill"), "match_status": "partial"})

        self._add_evidence(nodes, edges, add_node, add_edge, evidence_items, [*job_skills.values(), *resume_skills.values()])

        metadata = {
            "match_id": match_id,
            "jd_id": match_result.get("jd_id") or jd_profile.get("doc_id"),
            "resume_id": match_result.get("resume_id") or resume_profile.get("resume_id"),
            "position_id": position_id,
            "candidate_id": candidate_id,
            "final_score": match_result.get("final_score"),
            "decision": match_result.get("decision"),
            "gap_summary": gap_analysis.get("gap_summary"),
            "node_count": len(nodes),
            "edge_count": len(edges),
        }
        return make_graph("graph_full", nodes.values(), edges.values(), metadata, version=version)

    def _add_evidence(
        self,
        nodes: Dict[str, Dict[str, Any]],
        edges: Dict[Tuple[str, str, str], Dict[str, Any]],
        add_node: Any,
        add_edge: Any,
        evidence_items: Sequence[Mapping[str, Any]],
        skills: Sequence[Mapping[str, Any]],
    ) -> None:
        for evidence in evidence_items:
            evidence_id = str(evidence.get("evidence_id"))
            text = str(evidence.get("text") or "")
            add_node(evidence_id, text[:36] or evidence_id, "Evidence", 3, dict(evidence))
            for skill in skills:
                if self._evidence_supports_skill(text, skill):
                    add_edge(evidence_id, str(skill.get("skill_id") or skill_id_for(str(skill.get("name")))), "supports", 1.0, {"source_type": evidence.get("source_type"), "section": evidence.get("section")})

    def _evidence_supports_skill(self, evidence_text: str, skill: Mapping[str, Any]) -> bool:
        texts = [str(item) for item in skill.get("evidence_texts", [])]
        if any(text and (text in evidence_text or evidence_text in text) for text in texts):
            return True
        name = str(skill.get("name") or "")
        if name and name in evidence_text:
            return True
        return any(str(alias) and str(alias) in evidence_text for alias in skill.get("aliases", []))

    def _tech_stacks_for(self, skill_name: str) -> List[str]:
        stacks = [stack for stack, names in TECH_STACK_MAPPING.items() if skill_name in names]
        if stacks:
            return stacks
        skill_type = SKILL_CATALOG.get(skill_name, {}).get("skill_type")
        if skill_type == "编程语言":
            return ["编程语言栈"]
        if skill_type:
            return [f"{skill_type}栈"]
        return ["未分类技术栈"]

    def _proficiency_level(self, proficiency: float) -> str:
        if proficiency >= 0.8:
            return "advanced"
        if proficiency >= 0.6:
            return "intermediate"
        return "basic"

    def _evolution_relation(self, job_skill: Mapping[str, Any]) -> str:
        if job_skill.get("requirement_level") == "preferred":
            return "declining_in"
        if float(job_skill.get("weight", 0.0)) >= 1.0:
            return "rising_in"
        return "newly_requires"
