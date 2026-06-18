"""Public rule-based demo pipeline composed from algorithm modules."""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional

from backend.app.algorithms.common import dataclass_to_dict
from backend.app.algorithms.gap_analyzer import GapAnalyzer
from backend.app.algorithms.jd_parser import JDParser
from backend.app.algorithms.matcher import Matcher, RuleBasedMatcher
from backend.app.algorithms.model_adapter import ModelAdapter, RuleModelAdapter
from backend.app.algorithms.normalizer import SkillNormalizer
from backend.app.algorithms.profile_builder import SkillProfileBuilder
from backend.app.algorithms.resume_parser import ResumeParser
from backend.app.core.config import DEFAULT_GRAPH_VERSION, USE_LLM
from backend.app.graph.graph_builder import GraphBuilder
from backend.app.graph.graph_repository import save_graph_bundle
from backend.app.graph.graph_views import build_graph_views
from backend.app.llm.client import is_llm_available
from backend.app.llm.jd_extractor import extract_jd_with_llm, merge_jd_profiles
from backend.app.llm.match_explainer import explain_match_with_llm
from backend.app.llm.resume_extractor import extract_resume_with_llm, merge_resume_profiles
from backend.app.storage import json_store, paths
from backend.app.storage.id_generator import (
    make_candidate_id,
    make_doc_id,
    make_evidence_id,
    make_match_id,
    make_position_id,
)


class RuleBasedDemoPipeline:
    def __init__(
        self,
        jd_parser: Optional[JDParser] = None,
        resume_parser: Optional[ResumeParser] = None,
        normalizer: Optional[SkillNormalizer] = None,
        profile_builder: Optional[SkillProfileBuilder] = None,
        model_adapter: Optional[ModelAdapter] = None,
        matcher: Optional[Matcher] = None,
        gap_analyzer: Optional[GapAnalyzer] = None,
        graph_builder: Optional[GraphBuilder] = None,
    ) -> None:
        self.jd_parser = jd_parser or JDParser()
        self.resume_parser = resume_parser or ResumeParser()
        self.normalizer = normalizer or SkillNormalizer()
        self.profile_builder = profile_builder or SkillProfileBuilder()
        self.model_adapter = model_adapter or RuleModelAdapter()
        self.matcher = matcher or RuleBasedMatcher()
        self.gap_analyzer = gap_analyzer or GapAnalyzer()
        self.graph_builder = graph_builder or GraphBuilder()

    def analyze_jd(self, jd_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
        """Parse a JD and build a reusable job skill profile.

        This keeps the JD capability independent from resume matching, which is
        important for competition tasks such as岗位能力图谱构建、既有岗位能力更新
        and新岗位定义.
        """
        jd_parse = self.jd_parser.parse(jd_text)
        jd_normalized = self.normalizer.normalize(jd_parse.raw_skill_mentions)
        job_profile = self.profile_builder.build_job_profile(jd_parse, jd_normalized.normalized_skills)
        artifact_refs = self._persist_jd(jd_text, jd_parse, jd_normalized, job_profile)

        jd_parse_dict = dataclass_to_dict(jd_parse)
        jd_parse_dict["doc_id"] = artifact_refs["doc_id"]
        jd_parse_dict["position_id"] = artifact_refs["position_id"]
        jd_parse_dict["skills"] = job_profile.skills
        jd_parse_dict["skill_distribution"] = job_profile.skill_distribution
        jd_parse_dict["normalization_logs"] = jd_normalized.normalization_logs
        llm_profile = extract_jd_with_llm(jd_text) if use_llm else self._llm_not_requested()
        merged_job_profile = merge_jd_profiles(dataclass_to_dict(job_profile), llm_profile)

        return {
            "mode": "jd_parse",
            "jd_parse": jd_parse_dict,
            "job_profile": merged_job_profile,
            "llm": self._llm_summary(use_llm, llm_profile),
            "competition_hooks": {
                "supports_job_skill_graph": True,
                "supports_emerging_job_definition_input": True,
                "supports_existing_job_update_input": True,
                "next_stage_required": ["multi_source_evidence", "time_series_update", "human_review"],
            },
        }

    def analyze_resume(self, resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
        """Parse a resume and build a reusable candidate skill profile."""
        resume_parse = self.resume_parser.parse(resume_text)
        resume_normalized = self.normalizer.normalize(resume_parse.raw_skill_mentions)
        resume_profile = self.profile_builder.build_resume_profile(resume_parse, resume_normalized.normalized_skills)
        artifact_refs = self._persist_resume(resume_text, resume_parse, resume_normalized, resume_profile)

        resume_parse_dict = dataclass_to_dict(resume_parse)
        resume_parse_dict["doc_id"] = artifact_refs["doc_id"]
        resume_parse_dict["resume_id"] = artifact_refs["resume_id"]
        resume_parse_dict["skills"] = resume_profile.skills
        resume_parse_dict["skill_distribution"] = resume_profile.skill_distribution
        resume_parse_dict["normalization_logs"] = resume_normalized.normalization_logs
        llm_profile = extract_resume_with_llm(resume_text) if use_llm else self._llm_not_requested()
        merged_resume_profile = merge_resume_profiles(dataclass_to_dict(resume_profile), llm_profile)

        return {
            "mode": "resume_parse",
            "resume_parse": resume_parse_dict,
            "resume_profile": merged_resume_profile,
            "llm": self._llm_summary(use_llm, llm_profile),
            "competition_hooks": {
                "supports_resume_skill_extraction": True,
                "supports_person_job_gap_analysis_input": True,
                "next_stage_required": ["pdf_docx_text_extraction", "large_scale_accuracy_evaluation", "privacy_masking"],
            },
        }

    def run(self, jd_text: str, resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
        jd_parse = self.jd_parser.parse(jd_text)
        resume_parse = self.resume_parser.parse(resume_text)

        jd_normalized = self.normalizer.normalize(jd_parse.raw_skill_mentions)
        resume_normalized = self.normalizer.normalize(resume_parse.raw_skill_mentions)

        job_profile = self.profile_builder.build_job_profile(jd_parse, jd_normalized.normalized_skills)
        resume_profile = self.profile_builder.build_resume_profile(resume_parse, resume_normalized.normalized_skills)
        jd_artifacts = self._persist_jd(jd_text, jd_parse, jd_normalized, job_profile)
        resume_artifacts = self._persist_resume(resume_text, resume_parse, resume_normalized, resume_profile)

        model_output = self.model_adapter.predict(
            job_profile=job_profile,
            resume_profile=resume_profile,
            jd_evidence_items=jd_parse.evidence_items,
            resume_evidence_items=resume_parse.evidence_items,
        )
        jd_parse_dict = dataclass_to_dict(jd_parse)
        jd_parse_dict["doc_id"] = jd_artifacts["doc_id"]
        jd_parse_dict["position_id"] = jd_artifacts["position_id"]
        jd_parse_dict["skills"] = job_profile.skills
        jd_parse_dict["skill_distribution"] = job_profile.skill_distribution
        jd_parse_dict["normalization_logs"] = jd_normalized.normalization_logs

        resume_parse_dict = dataclass_to_dict(resume_parse)
        resume_parse_dict["doc_id"] = resume_artifacts["doc_id"]
        resume_parse_dict["resume_id"] = resume_artifacts["resume_id"]
        resume_parse_dict["skills"] = resume_profile.skills
        resume_parse_dict["skill_distribution"] = resume_profile.skill_distribution
        resume_parse_dict["normalization_logs"] = resume_normalized.normalization_logs

        match_result = self.matcher.match(job_profile, resume_profile, model_output)
        gap_analysis = self.gap_analyzer.analyze(job_profile, resume_profile, match_result)
        match_id = make_match_id(jd_artifacts["doc_id"], resume_artifacts["resume_id"])
        match_result_dict = dataclass_to_dict(match_result)
        match_result_dict["match_id"] = match_id
        match_result_dict["jd_id"] = jd_artifacts["doc_id"]
        match_result_dict["resume_id"] = resume_artifacts["resume_id"]
        match_result_dict["decision"] = self._decision(match_result.final_score)
        match_result_dict["gap_analysis"] = dataclass_to_dict(gap_analysis)
        match_result_dict["model_output"] = dataclass_to_dict(model_output)

        job_profile_dict = dataclass_to_dict(job_profile)
        job_profile_dict["doc_id"] = jd_artifacts["doc_id"]
        job_profile_dict["position_id"] = jd_artifacts["position_id"]
        job_profile_dict.setdefault("metadata", {})["position_id"] = jd_artifacts["position_id"]

        resume_profile_dict = dataclass_to_dict(resume_profile)
        resume_profile_dict["doc_id"] = resume_artifacts["doc_id"]
        resume_profile_dict["resume_id"] = resume_artifacts["resume_id"]
        resume_profile_dict.setdefault("metadata", {})["resume_id"] = resume_artifacts["resume_id"]

        llm_explanation = explain_match_with_llm(
            jd_profile=job_profile_dict,
            resume_profile=resume_profile_dict,
            match_result=match_result_dict,
            evidence_items=[*jd_artifacts["evidence_items"], *resume_artifacts["evidence_items"]],
        ) if use_llm else {"llm_used": False, **self._llm_not_requested(), "explanation": match_result.explanation, "source": "rule_based"}
        match_result_dict["llm_used"] = bool(llm_explanation.get("llm_used"))
        match_result_dict["llm_status"] = {
            "requested": bool(use_llm),
            "available": bool(llm_explanation.get("available", False)),
            "message": llm_explanation.get("message", "LLM was not requested."),
        }
        match_result_dict["llm_explanation"] = llm_explanation
        json_store.save_match_result(match_result_dict)

        evidence_items = [*jd_artifacts["evidence_items"], *resume_artifacts["evidence_items"]]
        graph_dict = self.graph_builder.build(
            jd_profile=job_profile_dict,
            resume_profile=resume_profile_dict,
            match_result=match_result_dict,
            gap_analysis=dataclass_to_dict(gap_analysis),
            evidence_items=evidence_items,
            version=DEFAULT_GRAPH_VERSION,
        )
        graph_dict["metadata"]["legacy_graph_id"] = f"graph_{match_id}"
        graph_dict["metadata"]["graph_views"] = {}
        graph_views = build_graph_views(graph_dict)
        graph_dict["metadata"]["graph_views"] = {view_type: view["graph_id"] for view_type, view in graph_views.items()}
        graph_paths = save_graph_bundle(graph_dict, graph_views)
        graph_dict["metadata"]["graph_paths"] = graph_paths
        json_store.save_evidence_items(evidence_items)

        return {
            "jd_parse": jd_parse_dict,
            "resume_parse": resume_parse_dict,
            "match_result": match_result_dict,
            "graph": graph_dict,
        }

    def _persist_jd(self, jd_text: str, jd_parse: Any, jd_normalized: Any, job_profile: Any) -> Dict[str, Any]:
        doc_id = make_doc_id("jd", jd_text)
        position_id = make_position_id(jd_parse.job_title)
        json_store.save_raw_document(
            "jd",
            jd_text,
            {
                "doc_id": doc_id,
                "position_id": position_id,
                "job_title": jd_parse.job_title,
                "job_category": jd_parse.job_category,
            },
        )
        json_store.save_parsed_profile(
            "jd",
            {
                "doc_id": doc_id,
                "position_id": position_id,
                "jd_parse": dataclass_to_dict(jd_parse),
                "job_profile": dataclass_to_dict(job_profile),
            },
        )
        self._save_normalized("jd", doc_id, jd_normalized)
        evidence_items = self._stable_evidence_items("jd", doc_id, jd_parse.evidence_items)
        json_store.save_evidence_items(evidence_items)
        return {"doc_id": doc_id, "position_id": position_id, "evidence_items": evidence_items}

    def _persist_resume(self, resume_text: str, resume_parse: Any, resume_normalized: Any, resume_profile: Any) -> Dict[str, Any]:
        doc_id = make_doc_id("resume", resume_text)
        resume_id = make_candidate_id(resume_parse.candidate_id or doc_id)
        json_store.save_raw_document(
            "resume",
            resume_text,
            {
                "doc_id": doc_id,
                "resume_id": resume_id,
                "candidate_id": resume_parse.candidate_id,
                "target_position": resume_parse.target_position,
            },
        )
        json_store.save_parsed_profile(
            "resume",
            {
                "doc_id": doc_id,
                "resume_id": resume_id,
                "resume_parse": dataclass_to_dict(resume_parse),
                "resume_profile": dataclass_to_dict(resume_profile),
            },
        )
        self._save_normalized("resume", doc_id, resume_normalized)
        evidence_items = self._stable_evidence_items("resume", doc_id, resume_parse.evidence_items)
        json_store.save_evidence_items(evidence_items)
        return {"doc_id": doc_id, "resume_id": resume_id, "evidence_items": evidence_items}

    def _save_normalized(self, source_type: str, doc_id: str, normalized: Any) -> None:
        json_store.save_json(
            paths.NORMALIZED_DIR / f"{doc_id}.json",
            {
                "doc_id": doc_id,
                "source_type": source_type,
                "created_at": json_store.utc_now(),
                "normalized_skills": dataclass_to_dict(normalized.normalized_skills),
                "unmatched_mentions": dataclass_to_dict(normalized.unmatched_mentions),
                "normalization_logs": normalized.normalization_logs,
            },
        )

    def _stable_evidence_items(self, source_type: str, doc_id: str, evidence_items: Any) -> list[Dict[str, Any]]:
        records = []
        for index, item in enumerate(evidence_items, start=1):
            records.append(
                {
                    "evidence_id": make_evidence_id(doc_id, index),
                    "source_doc_id": doc_id,
                    "source_type": source_type,
                    "original_evidence_id": item.get("evidence_id"),
                    "section": item.get("section"),
                    "text": item.get("text"),
                    "position": item.get("position"),
                }
            )
        return records

    def _decision(self, final_score: float) -> str:
        if final_score >= 75:
            return "strong_match"
        if final_score >= 55:
            return "partial_match"
        return "low_match"

    def _llm_not_requested(self) -> Dict[str, Any]:
        availability = is_llm_available()
        return {
            "llm_used": False,
            "available": availability["available"],
            "message": "LLM was not requested. Using rule-based pipeline.",
        }

    def _llm_summary(self, requested: bool, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "requested": bool(requested),
            "llm_used": bool(llm_result.get("llm_used")),
            "available": bool(llm_result.get("available", False)),
            "message": llm_result.get("message", "LLM was not requested."),
        }


def match_jd_resume(jd_text: str, resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
    """Run the first-stage rule-based demo and return JSON-serializable data."""
    return RuleBasedDemoPipeline().run(jd_text, resume_text, use_llm=use_llm)


def parse_jd(jd_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
    """Parse a JD without requiring a resume."""
    return RuleBasedDemoPipeline().analyze_jd(jd_text, use_llm=use_llm)


def parse_resume(resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
    """Parse a resume without requiring a JD."""
    return RuleBasedDemoPipeline().analyze_resume(resume_text, use_llm=use_llm)


def analyze_match(jd_text: str, resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
    return match_jd_resume(jd_text, resume_text, use_llm=use_llm)


def run_demo(jd_text: str, resume_text: str, use_llm: bool = USE_LLM) -> Dict[str, Any]:
    return match_jd_resume(jd_text, resume_text, use_llm=use_llm)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rule-based JD/resume matcher demo.")
    parser.add_argument("--mode", choices=("match", "jd", "resume"), default="match")
    parser.add_argument("--jd", help="JD text. If omitted, read a JSON object from stdin.")
    parser.add_argument("--resume", help="Resume text. If omitted, read a JSON object from stdin.")
    args = parser.parse_args()

    if args.mode == "jd" and args.jd is not None:
        result = parse_jd(args.jd)
    elif args.mode == "resume" and args.resume is not None:
        result = parse_resume(args.resume)
    elif args.jd is not None and args.resume is not None:
        result = match_jd_resume(args.jd, args.resume)
    else:
        payload = json.loads(input())
        if args.mode == "jd":
            result = parse_jd(payload.get("jd_text", ""))
        elif args.mode == "resume":
            result = parse_resume(payload.get("resume_text", ""))
        else:
            result = match_jd_resume(payload.get("jd_text", ""), payload.get("resume_text", ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))
