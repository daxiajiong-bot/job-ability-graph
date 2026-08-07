from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .extractor import SKILL_PATTERNS


def _compact(value: str | None) -> str:
    return re.sub(r"\s+", "", (value or "").strip()).lower()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _contains_evidence(evidence: str | None, raw_text: str | None) -> bool:
    if not evidence:
        return False
    return _compact(evidence) in _compact(raw_text)


def _candidate_terms(raw_text: str) -> list[str]:
    terms: list[str] = []
    for pattern in SKILL_PATTERNS:
        for match in re.finditer(pattern, raw_text or "", flags=re.I):
            term = re.sub(r"\s+", " ", match.group(0).strip())
            if term:
                terms.append(term)
    return terms


def evaluate_extraction(
    profiles_path: Path,
    validation_results_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    profiles = _read_jsonl(profiles_path)
    validation_rows = _read_jsonl(validation_results_path) if validation_results_path and validation_results_path.exists() else []
    validation_status_counts = Counter(row.get("status", "unknown") for row in validation_rows)

    total_docs = len(profiles)
    docs_with_title = 0
    docs_with_skill = 0
    docs_with_required_skill = 0
    docs_with_preferred_skill = 0
    docs_with_mentioned_skill = 0
    docs_with_education = 0
    docs_with_experience = 0
    docs_with_location = 0
    skill_mentions = 0
    duplicate_skill_mentions = 0
    skill_evidence_total = 0
    skill_evidence_supported = 0
    constraint_evidence_total = 0
    constraint_evidence_supported = 0
    level_counts: Counter[str] = Counter()
    extracted_skill_counter: Counter[str] = Counter()
    candidate_term_counter: Counter[str] = Counter()
    missed_candidate_counter: Counter[str] = Counter()
    docs_with_candidate_terms = 0
    docs_with_candidate_but_no_skill = 0
    docs_with_skill_but_no_candidate = 0
    docs_with_low_skill_density = 0

    for profile in profiles:
        raw_text = profile.get("raw_text") or ""
        title = profile.get("title")
        constraints = profile.get("constraints") or {}
        skills = profile.get("skills") or []
        if title:
            docs_with_title += 1
        if skills:
            docs_with_skill += 1
        if len(skills) <= 1:
            docs_with_low_skill_density += 1

        seen_skill_keys: set[tuple[str, str, str]] = set()
        extracted_terms = {_compact(skill.get("name")) for skill in skills if skill.get("name")}
        candidates = _candidate_terms(raw_text)
        candidate_terms = {_compact(term) for term in candidates if term}
        if candidate_terms:
            docs_with_candidate_terms += 1
        if candidate_terms and not extracted_terms:
            docs_with_candidate_but_no_skill += 1
        if extracted_terms and not candidate_terms:
            docs_with_skill_but_no_candidate += 1
        for term in candidates:
            candidate_term_counter[term] += 1
            if _compact(term) not in extracted_terms:
                missed_candidate_counter[term] += 1

        doc_levels = {skill.get("level") for skill in skills}
        if "required" in doc_levels:
            docs_with_required_skill += 1
        if "preferred" in doc_levels:
            docs_with_preferred_skill += 1
        if "mentioned" in doc_levels:
            docs_with_mentioned_skill += 1

        for skill in skills:
            name = str(skill.get("name") or "").strip()
            level = str(skill.get("level") or "").strip()
            evidence = str(skill.get("evidence") or "").strip()
            key = (name, level, evidence)
            if key in seen_skill_keys:
                duplicate_skill_mentions += 1
            seen_skill_keys.add(key)
            if name:
                extracted_skill_counter[name] += 1
            if level:
                level_counts[level] += 1
            skill_mentions += 1
            skill_evidence_total += 1
            if _contains_evidence(evidence, raw_text):
                skill_evidence_supported += 1

        for field in ("education", "experience_years", "location"):
            item = constraints.get(field) or {}
            value = item.get("value")
            evidence = item.get("evidence")
            if value is None or value == "":
                continue
            if field == "education":
                docs_with_education += 1
            elif field == "experience_years":
                docs_with_experience += 1
            elif field == "location":
                docs_with_location += 1
            constraint_evidence_total += 1
            if _contains_evidence(evidence, raw_text):
                constraint_evidence_supported += 1

    skill_coverage = docs_with_skill / total_docs if total_docs else 0
    required_coverage = docs_with_required_skill / total_docs if total_docs else 0
    preferred_coverage = docs_with_preferred_skill / total_docs if total_docs else 0
    mentioned_coverage = docs_with_mentioned_skill / total_docs if total_docs else 0
    title_coverage = docs_with_title / total_docs if total_docs else 0
    education_coverage = docs_with_education / total_docs if total_docs else 0
    experience_coverage = docs_with_experience / total_docs if total_docs else 0
    location_coverage = docs_with_location / total_docs if total_docs else 0
    avg_skills_per_doc = skill_mentions / total_docs if total_docs else 0
    skill_evidence_support_rate = skill_evidence_supported / skill_evidence_total if skill_evidence_total else 1
    constraint_evidence_support_rate = constraint_evidence_supported / constraint_evidence_total if constraint_evidence_total else 1
    docs_candidate_but_no_skill_ratio = docs_with_candidate_but_no_skill / total_docs if total_docs else 0
    docs_low_skill_density_ratio = docs_with_low_skill_density / total_docs if total_docs else 0
    candidate_term_total = sum(candidate_term_counter.values())
    missed_candidate_total = sum(missed_candidate_counter.values())
    lexicon_recall_proxy = 1 - (missed_candidate_total / candidate_term_total) if candidate_term_total else 1

    rag_recommendation = _recommend_rag(
        skill_coverage=skill_coverage,
        skill_evidence_support_rate=skill_evidence_support_rate,
        lexicon_recall_proxy=lexicon_recall_proxy,
        docs_candidate_but_no_skill_ratio=docs_candidate_but_no_skill_ratio,
        docs_low_skill_density_ratio=docs_low_skill_density_ratio,
        unique_skill_count=len(extracted_skill_counter),
    )

    report = {
        "schema_version": "jd_extraction_eval_v1",
        "source_profile_count": total_docs,
        "profile_validation_status_counts": dict(validation_status_counts),
        "metrics": {
            "title_coverage": round(title_coverage, 4),
            "skill_coverage": round(skill_coverage, 4),
            "required_skill_doc_coverage": round(required_coverage, 4),
            "preferred_skill_doc_coverage": round(preferred_coverage, 4),
            "mentioned_skill_doc_coverage": round(mentioned_coverage, 4),
            "education_coverage": round(education_coverage, 4),
            "experience_coverage": round(experience_coverage, 4),
            "location_coverage": round(location_coverage, 4),
            "avg_skills_per_doc": round(avg_skills_per_doc, 4),
            "skill_evidence_support_rate": round(skill_evidence_support_rate, 4),
            "constraint_evidence_support_rate": round(constraint_evidence_support_rate, 4),
            "lexicon_recall_proxy": round(lexicon_recall_proxy, 4),
            "docs_with_candidate_terms": docs_with_candidate_terms,
            "docs_with_candidate_but_no_skill": docs_with_candidate_but_no_skill,
            "docs_with_candidate_but_no_skill_ratio": round(docs_candidate_but_no_skill_ratio, 4),
            "docs_with_skill_but_no_candidate": docs_with_skill_but_no_candidate,
            "docs_with_low_skill_density": docs_with_low_skill_density,
            "docs_with_low_skill_density_ratio": round(docs_low_skill_density_ratio, 4),
            "duplicate_skill_mentions": duplicate_skill_mentions,
            "unique_skill_count": len(extracted_skill_counter),
            "candidate_term_total": candidate_term_total,
            "missed_candidate_total": missed_candidate_total,
        },
        "level_counts": dict(level_counts),
        "top_extracted_skills": [{"name": name, "count": count} for name, count in extracted_skill_counter.most_common(30)],
        "top_missed_candidate_terms": [{"name": name, "count": count} for name, count in missed_candidate_counter.most_common(30)],
        "rag_recommendation": rag_recommendation,
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "extraction_eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "extraction_eval.md").write_text(render_markdown_report(report), encoding="utf-8")
    return report


def _recommend_rag(
    skill_coverage: float,
    skill_evidence_support_rate: float,
    lexicon_recall_proxy: float,
    docs_candidate_but_no_skill_ratio: float,
    docs_low_skill_density_ratio: float,
    unique_skill_count: int,
) -> dict[str, Any]:
    reasons: list[str] = []
    risks: list[str] = []
    mode = "not_required_for_current_rule_based_extraction"

    if skill_evidence_support_rate < 0.99:
        mode = "do_not_add_rag_before_fixing_grounding"
        reasons.append("技能证据支持率低于 99%，应先修复证据校验和抽取规则。")
        risks.append("直接加入 RAG 可能扩大无证据事实和幻觉。")
    else:
        if skill_coverage < 0.95:
            mode = "recommended"
            reasons.append("技能覆盖率低于 95%，可用检索增强词表提升召回。")
        if lexicon_recall_proxy < 0.9:
            mode = "recommended"
            reasons.append("词表召回代理指标低于 90%，说明原文中存在较多未进入 Profile 的技术词。")
        if docs_candidate_but_no_skill_ratio > 0.03:
            mode = "recommended"
            reasons.append("存在较多原文含候选技术词但没有技能输出的岗位。")
        if docs_low_skill_density_ratio > 0.2:
            if mode != "recommended":
                mode = "optional"
            reasons.append("低技能密度岗位比例偏高，可考虑检索相似岗位样例辅助抽取。")
        if unique_skill_count < 300:
            if mode != "recommended":
                mode = "optional"
            reasons.append("技能表面词数量较少，RAG 更适合用于术语扩展和技能归一化。")

    if not reasons:
        reasons.append("当前证据支持率和技能覆盖率较高，基础抽取阶段不必强制加入 RAG。")

    strategy = [
        "优先保留当前证据优先抽取流程，RAG 只作为候选术语/相似 JD 样例检索器。",
        "RAG 返回的术语必须再次在 raw_text 中命中，不能直接写入 Profile。",
        "用于提升召回时，建议检索技能词表、岗位族样例、人工标注样例，而不是检索泛化解释文本。",
        "用于人岗匹配前，建议把 RAG 放在技能归一化与岗位族对齐阶段，而不是替代 evidence 校验。",
    ]

    return {
        "mode": mode,
        "reasons": reasons,
        "risks": risks,
        "recommended_strategy": strategy,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    rag = report["rag_recommendation"]
    lines = [
        "# JD 知识抽取效果评估报告",
        "",
        f"- Profile 数量：{report['source_profile_count']}",
        f"- RAG 建议：`{rag['mode']}`",
        "",
        "## 核心指标",
        "",
        "| 指标 | 数值 | 含义 |",
        "| --- | ---: | --- |",
        f"| title_coverage | {metrics['title_coverage']} | 有岗位名称的比例 |",
        f"| skill_coverage | {metrics['skill_coverage']} | 至少抽到一个技能的岗位比例 |",
        f"| required_skill_doc_coverage | {metrics['required_skill_doc_coverage']} | 有必需技能的岗位比例 |",
        f"| preferred_skill_doc_coverage | {metrics['preferred_skill_doc_coverage']} | 有优先技能的岗位比例 |",
        f"| education_coverage | {metrics['education_coverage']} | 有学历要求的岗位比例 |",
        f"| experience_coverage | {metrics['experience_coverage']} | 有经验年限要求的岗位比例 |",
        f"| location_coverage | {metrics['location_coverage']} | 有地点信息的岗位比例 |",
        f"| avg_skills_per_doc | {metrics['avg_skills_per_doc']} | 平均每条岗位抽取技能数 |",
        f"| skill_evidence_support_rate | {metrics['skill_evidence_support_rate']} | 技能证据可回溯到原文的比例 |",
        f"| constraint_evidence_support_rate | {metrics['constraint_evidence_support_rate']} | 约束证据可回溯到原文的比例 |",
        f"| lexicon_recall_proxy | {metrics['lexicon_recall_proxy']} | 基于当前技能词表复扫 raw_text 的召回代理指标 |",
        f"| docs_with_candidate_but_no_skill_ratio | {metrics['docs_with_candidate_but_no_skill_ratio']} | 原文含候选技能词但 Profile 无技能的岗位比例 |",
        f"| docs_with_low_skill_density_ratio | {metrics['docs_with_low_skill_density_ratio']} | 技能数小于等于 1 的岗位比例 |",
        "",
        "## RAG 是否需要加入",
        "",
    ]
    lines.extend(f"- {reason}" for reason in rag["reasons"])
    if rag["risks"]:
        lines.append("")
        lines.append("### 风险")
        lines.extend(f"- {risk}" for risk in rag["risks"])
    lines.append("")
    lines.append("### 建议策略")
    lines.extend(f"- {item}" for item in rag["recommended_strategy"])
    lines.append("")
    lines.append("## 高频已抽取技能")
    lines.append("")
    lines.append("| 技能 | 次数 |")
    lines.append("| --- | ---: |")
    for item in report["top_extracted_skills"][:20]:
        lines.append(f"| {item['name']} | {item['count']} |")
    lines.append("")
    lines.append("## 可能漏抽的候选术语")
    lines.append("")
    lines.append("| 候选术语 | 次数 |")
    lines.append("| --- | ---: |")
    for item in report["top_missed_candidate_terms"][:20]:
        lines.append(f"| {item['name']} | {item['count']} |")
    lines.append("")
    lines.append("说明：该报告是无人工标注情况下的自动代理评估。若要证明 JD 解析准确率 ≥90%，仍需要构造人工金标集计算 precision / recall / F1。")
    lines.append("")
    return "\n".join(lines)

