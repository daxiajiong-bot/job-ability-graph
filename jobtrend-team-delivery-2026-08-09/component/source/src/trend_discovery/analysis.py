"""Auditable trend, emerging-role and job-skill-change analysis."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from .dedup import cluster_documents, normalize_company, normalize_text, normalize_title
from .io_utils import stable_id
from .kg import KGIndex
from .schemas import (
    AbilityRef,
    EmergingRole,
    EmergingRoleScores,
    Evidence,
    ExternalDocument,
    JobObservation,
    JobSkillUpdate,
    KGLinkDelta,
    RoleAbility,
    SkillChange,
    TrendFeature,
    TrendMetrics,
    TrendWindow,
)


DEFAULT_ANALYSIS_CONFIG: dict[str, Any] = {
    "recent_days": 28,
    "baseline_days": 84,
    "min_cluster_size": 8,
    "min_samples": 4,
    "min_companies": 3,
    "min_week_snapshots": 2,
    "max_known_role_similarity": 0.82,
    "min_growth_rate": 1.5,
    "candidate_score_threshold": 0.65,
    "high_confidence_threshold": 0.75,
    "skill_min_companies": 5,
    "skill_min_share_delta": 0.10,
    "skill_min_relative_lift": 1.5,
    "significance_q": 0.05,
    "score_weights": {
        "novelty": 0.30,
        "growth": 0.25,
        "persistence": 0.20,
        "source_diversity": 0.15,
        "evidence_coverage": 0.10,
    },
}

_FALLBACK_SKILLS = (
    "Python",
    "Java",
    "C++",
    "SQL",
    "Linux",
    "Docker",
    "Kubernetes",
    "PyTorch",
    "TensorFlow",
    "RAG",
    "LangChain",
    "大语言模型",
    "大模型",
    "生成式AI",
    "生成式人工智能",
    "知识图谱",
    "机器学习",
    "深度学习",
    "自然语言处理",
    "提示词工程",
    "Agent",
    "智能体",
    "模型微调",
    "向量数据库",
)


def _settings(config: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = dict((config or {}).get("analysis", config or {}))
    result = dict(DEFAULT_ANALYSIS_CONFIG)
    result.update({key: value for key, value in supplied.items() if key != "score_weights"})
    result["score_weights"] = {
        **DEFAULT_ANALYSIS_CONFIG["score_weights"],
        **dict(supplied.get("score_weights") or {}),
    }
    weights = result["score_weights"]
    if not math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-6):
        raise ValueError("analysis.score_weights must sum to 1.0")
    return result


def _as_document(value: ExternalDocument | Mapping[str, object]) -> ExternalDocument:
    return value if isinstance(value, ExternalDocument) else ExternalDocument.model_validate(value)


def _as_evidence(value: Evidence | Mapping[str, object]) -> Evidence:
    return value if isinstance(value, Evidence) else Evidence.model_validate(value)


def _as_observation(value: JobObservation | Mapping[str, object]) -> JobObservation:
    return value if isinstance(value, JobObservation) else JobObservation.model_validate(value)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _observed_at(value: JobObservation) -> datetime:
    return _aware(value.published_at or value.collected_at)


def _monday(value: datetime) -> str:
    """Return the ISO Monday for a timestamp after normalising to UTC."""

    timestamp = _aware(value)
    return (timestamp - timedelta(days=timestamp.weekday())).date().isoformat()


def _snapshot_week_from_metadata(metadata: Mapping[str, Any], collected_at: datetime) -> str:
    """Use a declared snapshot only when it proves consistent with collection.

    A publisher's ``published_at`` describes the age of an advert, not when we
    observed it.  Snapshot continuity must therefore be anchored to
    ``collected_at``.  Sources may additionally provide a weekly snapshot
    label (``2026-W31``) or an ISO-date-bearing snapshot id.  Those labels are
    useful for auditability, but are accepted only when they normalise to the
    same week as the actual collection timestamp; otherwise a malformed or
    stale label cannot fabricate persistence.
    """

    collected_week = _monday(collected_at)

    def parsed_monday(raw: object, *, is_week: bool) -> str | None:
        if isinstance(raw, datetime):
            return _monday(raw)
        if not isinstance(raw, str):
            return None
        value = raw.strip()
        if not value:
            return None
        if is_week:
            match = re.fullmatch(r"(\d{4})-?W(\d{1,2})", value, flags=re.IGNORECASE)
            if match:
                try:
                    return datetime.fromisocalendar(int(match.group(1)), int(match.group(2)), 1).date().isoformat()
                except ValueError:
                    return None
        # Snapshot ids often use a prefix/suffix around an ISO date.  Only an
        # unambiguous YYYY-MM-DD component is considered verifiable.
        match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", value)
        if match:
            try:
                return _monday(datetime.fromisoformat(match.group(1)))
            except ValueError:
                return None
        return None

    for key, is_week in (("snapshot_week", True), ("snapshot_id", False)):
        candidate = parsed_monday(metadata.get(key), is_week=is_week)
        if candidate == collected_week:
            return candidate
    return collected_week


def _window(as_of: datetime, settings: Mapping[str, Any]) -> TrendWindow:
    recent_end = _aware(as_of)
    recent_start = recent_end - timedelta(days=int(settings["recent_days"]))
    baseline_end = recent_start
    baseline_start = baseline_end - timedelta(days=int(settings["baseline_days"]))
    return TrendWindow(
        recent_start=recent_start,
        recent_end=recent_end,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
    )


def _in_half_open(value: datetime, start: datetime, end: datetime) -> bool:
    value = _aware(value)
    return start <= value < end


def _list_value(metadata: Mapping[str, Any], *keys: str) -> list[str]:
    value: Any = None
    for key in keys:
        if key in metadata:
            value = metadata[key]
            break
    if value is None:
        return []
    if isinstance(value, str):
        values = re.split(r"[\n;；]", value)
    elif isinstance(value, Mapping):
        values = list(value.values())
    elif isinstance(value, Iterable):
        values = list(value)
    else:
        values = [value]
    result: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            item = item.get("name") or item.get("value") or item.get("text") or ""
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text and text not in result:
            result.append(text)
    return result


def _structured_skills(metadata: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    required = _list_value(metadata, "required_skills", "skills_required")
    preferred = _list_value(metadata, "preferred_skills", "skills_preferred")
    mentioned = _list_value(metadata, "mentioned_skills")
    # The parser's lossless record adapter stores source columns under
    # metadata.structured_fields.  A plain ``skills`` column represents the
    # job's stated requirements; lines explicitly marked 优先 are classified
    # as preferred instead of required.
    if not required and not preferred and not mentioned:
        flat_skills = _list_value(metadata, "skills", "skills_norm", "skills_raw")
        requirement_lines = _list_value(metadata, "requirements", "requirement", "qualifications")
        for name in flat_skills:
            preferred_context = any(
                normalize_text(name) in normalize_text(line) and "优先" in line
                for line in requirement_lines
            )
            destination = preferred if preferred_context else required
            if name not in destination:
                destination.append(name)
    skills = metadata.get("skills") or []
    if isinstance(skills, Mapping):
        skills = [skills]
    if isinstance(skills, Iterable) and not isinstance(skills, (str, bytes)):
        for item in skills:
            if isinstance(item, Mapping):
                name = str(item.get("name") or item.get("normalized_name") or "").strip()
                role = str(item.get("level") or item.get("role") or "mentioned").casefold()
                destination = required if role == "required" else preferred if role == "preferred" else mentioned
                if name and name not in destination:
                    destination.append(name)
            elif str(item).strip() and str(item).strip() not in mentioned:
                mentioned.append(str(item).strip())
    return required, preferred, mentioned


def _fallback_skills(text: str) -> list[str]:
    compact = normalize_text(text)
    result: list[str] = []
    for skill in _FALLBACK_SKILLS:
        if normalize_text(skill) in compact and skill not in result:
            result.append(skill)
    return result


def _fallback_responsibilities(text: str) -> list[str]:
    lines = [re.sub(r"^[\s\-•*\d.、()（）]+", "", line).strip() for line in text.splitlines()]
    return [line for line in lines if len(line) >= 6 and any(word in line for word in ("负责", "参与", "建设", "开发"))][:12]


def build_job_observations(
    documents: Sequence[ExternalDocument | Mapping[str, object]],
    evidence: Sequence[Evidence | Mapping[str, object]],
    config: Mapping[str, Any] | None = None,
) -> list[JobObservation]:
    """Turn parsed JD documents into immutable, duplicate-aware observations."""

    del config  # reserved for future extraction dictionaries; no hidden defaults here
    parsed_documents = [_as_document(item) for item in documents]
    parsed_evidence = [_as_evidence(item) for item in evidence]
    job_documents = [item for item in parsed_documents if item.source_type == "job" and item.parse_status == "parsed"]
    clustered = cluster_documents(job_documents)
    evidence_by_document: dict[str, list[str]] = defaultdict(list)
    for item in parsed_evidence:
        evidence_by_document[item.document_id].append(item.evidence_id)

    observations: list[JobObservation] = []
    for document in job_documents:
        metadata = dict(document.metadata or {})
        structured_fields = metadata.get("structured_fields")
        if isinstance(structured_fields, Mapping):
            # Explicit top-level extraction/batch output wins over raw parser
            # fields when both exist.
            metadata = {**dict(structured_fields), **metadata}
        responsibilities = _list_value(metadata, "responsibilities", "duties", "job_responsibilities")
        if not responsibilities:
            responsibilities = _fallback_responsibilities(document.text)
        required, preferred, mentioned = _structured_skills(metadata)
        if not required and not preferred and not mentioned:
            mentioned = _fallback_skills(document.text)
        # Keep event-time analytics on published_at where available, but make
        # the emerging-role continuity gate a true collection-snapshot gate.
        # In particular, several old postings collected in one run count as
        # one weekly observation, never as historical weekly persistence.
        monday = _snapshot_week_from_metadata(metadata, document.collected_at)
        assignment = clustered.assignment_for(document.document_id)
        observations.append(
            JobObservation(
                observation_id=stable_id("obs", document.document_id),
                document_id=document.document_id,
                source_name=document.source_name,
                title=document.title,
                normalized_title=normalize_title(str(metadata.get("normalized_title") or document.title)),
                company=document.company,
                industry=document.industry,
                region=document.region,
                published_at=document.published_at,
                collected_at=document.collected_at,
                responsibilities=responsibilities,
                required_skills=required,
                preferred_skills=preferred,
                mentioned_skills=mentioned,
                evidence_ids=sorted(set(evidence_by_document.get(document.document_id, []))),
                exact_cluster_id=assignment.exact_cluster_id,
                near_dup_cluster_id=assignment.near_dup_cluster_id,
                snapshot_week=monday,
            )
        )
    return sorted(observations, key=lambda item: (_aware(item.collected_at), item.observation_id))


def _deduped(rows: Iterable[JobObservation]) -> list[JobObservation]:
    """Count a propagated posting once per source while preserving diversity."""

    selected: dict[tuple[str, str], JobObservation] = {}
    for row in sorted(rows, key=lambda item: (_observed_at(item), item.observation_id)):
        selected.setdefault((row.source_name, row.near_dup_cluster_id), row)
    return list(selected.values())


def _source_normalized_share(
    all_rows: Sequence[JobObservation],
    predicate: Callable[[JobObservation], bool],
) -> float:
    by_source: dict[str, list[JobObservation]] = defaultdict(list)
    for row in _deduped(all_rows):
        by_source[row.source_name].append(row)
    shares = []
    for source_rows in by_source.values():
        denominator = len({row.near_dup_cluster_id for row in source_rows})
        numerator = len({row.near_dup_cluster_id for row in source_rows if predicate(row)})
        if denominator:
            shares.append(numerator / denominator)
    return float(sum(shares) / len(shares)) if shares else 0.0


def _weekly_shares(
    all_rows: Sequence[JobObservation],
    predicate: Callable[[JobObservation], bool],
    start: datetime,
    end: datetime,
) -> list[float]:
    weeks = max(1, math.ceil((end - start).total_seconds() / (7 * 86400)))
    values: list[float] = []
    for index in range(weeks):
        week_start = start + timedelta(days=7 * index)
        week_end = min(end, week_start + timedelta(days=7))
        rows = [row for row in all_rows if _in_half_open(_observed_at(row), week_start, week_end)]
        values.append(_source_normalized_share(rows, predicate))
    return values


def _ewma_slope(values: Sequence[float], alpha: float = 0.35) -> float:
    if len(values) < 2:
        return 0.0
    smoothed = [float(values[0])]
    for value in values[1:]:
        smoothed.append(alpha * float(value) + (1.0 - alpha) * smoothed[-1])
    x = np.arange(len(smoothed), dtype=float)
    return float(np.polyfit(x, np.asarray(smoothed), 1)[0])


def _robust_zscore(recent_values: Sequence[float], baseline_values: Sequence[float]) -> float:
    if not recent_values or not baseline_values:
        return 0.0
    recent = float(np.mean(recent_values))
    baseline = np.asarray(baseline_values, dtype=float)
    median = float(np.median(baseline))
    mad = float(np.median(np.abs(baseline - median)))
    if mad <= 1e-12:
        return 0.0 if math.isclose(recent, median) else (10.0 if recent > median else -10.0)
    return float(max(-10.0, min(10.0, (recent - median) / (1.4826 * mad))))


def _metrics_for(
    observations: Sequence[JobObservation],
    predicate: Callable[[JobObservation], bool],
    window: TrendWindow,
) -> TrendMetrics:
    recent_all = [row for row in observations if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)]
    baseline_all = [row for row in observations if _in_half_open(_observed_at(row), window.baseline_start, window.baseline_end)]
    recent_matches_raw = [row for row in recent_all if predicate(row)]
    baseline_matches_raw = [row for row in baseline_all if predicate(row)]
    recent_matches = _deduped(recent_matches_raw)
    baseline_matches = _deduped(baseline_matches_raw)
    recent_share = _source_normalized_share(recent_all, predicate)
    baseline_share = _source_normalized_share(baseline_all, predicate)
    growth = recent_share / baseline_share if baseline_share > 0 else (float(len(recent_matches)) if recent_matches else 0.0)
    recent_weekly = _weekly_shares(observations, predicate, window.recent_start, window.recent_end)
    baseline_weekly = _weekly_shares(observations, predicate, window.baseline_start, window.baseline_end)
    persistence = sum(value > 0 for value in recent_weekly) / len(recent_weekly) if recent_weekly else 0.0
    distinct_sources = {row.source_name for row in recent_matches}
    return TrendMetrics(
        distinct_job_count=len({row.near_dup_cluster_id for row in recent_matches}),
        previous_distinct_job_count=len({row.near_dup_cluster_id for row in baseline_matches}),
        distinct_company_count=len({normalize_company(row.company) for row in recent_matches if row.company}),
        distinct_source_count=len(distinct_sources),
        distinct_region_count=len({normalize_text(row.region) for row in recent_matches if row.region}),
        recent_share=recent_share,
        baseline_share=baseline_share,
        growth_rate=growth,
        share_delta=recent_share - baseline_share,
        ewma_slope=_ewma_slope([*baseline_weekly, *recent_weekly]),
        robust_zscore=_robust_zscore(recent_weekly, baseline_weekly),
        persistence=persistence,
        source_diversity=min(1.0, len(distinct_sources) / 2.0),
        propagation_count=len(recent_matches_raw),
    )


@dataclass(slots=True)
class _TrendDenominators:
    recent: dict[str, set[str]]
    baseline: dict[str, set[str]]
    recent_weekly: list[dict[str, set[str]]]
    baseline_weekly: list[dict[str, set[str]]]


def _source_cluster_sets(rows: Iterable[JobObservation]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        result[row.source_name].add(row.near_dup_cluster_id)
    return dict(result)


def _weekly_source_cluster_sets(
    rows: Sequence[JobObservation], start: datetime, end: datetime
) -> list[dict[str, set[str]]]:
    weeks = max(1, math.ceil((end - start).total_seconds() / (7 * 86400)))
    result: list[dict[str, set[str]]] = [defaultdict(set) for _ in range(weeks)]
    for row in rows:
        timestamp = _observed_at(row)
        if not _in_half_open(timestamp, start, end):
            continue
        index = min(weeks - 1, int((timestamp - start).total_seconds() // (7 * 86400)))
        result[index][row.source_name].add(row.near_dup_cluster_id)
    return [dict(value) for value in result]


def _trend_denominators(
    observations: Sequence[JobObservation], window: TrendWindow
) -> _TrendDenominators:
    recent = [
        row for row in observations if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)
    ]
    baseline = [
        row for row in observations if _in_half_open(_observed_at(row), window.baseline_start, window.baseline_end)
    ]
    return _TrendDenominators(
        recent=_source_cluster_sets(recent),
        baseline=_source_cluster_sets(baseline),
        recent_weekly=_weekly_source_cluster_sets(observations, window.recent_start, window.recent_end),
        baseline_weekly=_weekly_source_cluster_sets(observations, window.baseline_start, window.baseline_end),
    )


def _share_from_sets(
    matches: Mapping[str, set[str]], denominator: Mapping[str, set[str]]
) -> float:
    shares = [
        len(matches.get(source, set())) / len(clusters)
        for source, clusters in denominator.items()
        if clusters
    ]
    return float(sum(shares) / len(shares)) if shares else 0.0


def _metrics_from_matching_rows(
    matching_rows: Sequence[JobObservation],
    window: TrendWindow,
    denominators: _TrendDenominators,
) -> TrendMetrics:
    recent_raw = [
        row for row in matching_rows if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)
    ]
    baseline_raw = [
        row for row in matching_rows if _in_half_open(_observed_at(row), window.baseline_start, window.baseline_end)
    ]
    recent = _deduped(recent_raw)
    baseline = _deduped(baseline_raw)
    recent_sets = _source_cluster_sets(recent)
    baseline_sets = _source_cluster_sets(baseline)
    recent_share = _share_from_sets(recent_sets, denominators.recent)
    baseline_share = _share_from_sets(baseline_sets, denominators.baseline)
    recent_week_sets = _weekly_source_cluster_sets(
        matching_rows, window.recent_start, window.recent_end
    )
    baseline_week_sets = _weekly_source_cluster_sets(
        matching_rows, window.baseline_start, window.baseline_end
    )
    recent_weekly = [
        _share_from_sets(values, denominators.recent_weekly[index])
        for index, values in enumerate(recent_week_sets)
    ]
    baseline_weekly = [
        _share_from_sets(values, denominators.baseline_weekly[index])
        for index, values in enumerate(baseline_week_sets)
    ]
    distinct_sources = set(recent_sets)
    growth = recent_share / baseline_share if baseline_share > 0 else (float(len(recent)) if recent else 0.0)
    return TrendMetrics(
        distinct_job_count=len({row.near_dup_cluster_id for row in recent}),
        previous_distinct_job_count=len({row.near_dup_cluster_id for row in baseline}),
        distinct_company_count=len({normalize_company(row.company) for row in recent if row.company}),
        distinct_source_count=len(distinct_sources),
        distinct_region_count=len({normalize_text(row.region) for row in recent if row.region}),
        recent_share=recent_share,
        baseline_share=baseline_share,
        growth_rate=growth,
        share_delta=recent_share - baseline_share,
        ewma_slope=_ewma_slope([*baseline_weekly, *recent_weekly]),
        robust_zscore=_robust_zscore(recent_weekly, baseline_weekly),
        persistence=sum(value > 0 for value in recent_weekly) / len(recent_weekly)
        if recent_weekly
        else 0.0,
        source_diversity=min(1.0, len(distinct_sources) / 2.0),
        propagation_count=len(recent_raw),
    )


def _entity_names(observations: Sequence[JobObservation]) -> tuple[dict[str, str], dict[str, str]]:
    roles: dict[str, Counter[str]] = defaultdict(Counter)
    abilities: dict[str, Counter[str]] = defaultdict(Counter)
    for row in observations:
        roles[row.normalized_title][row.title] += 1
        for value in {*row.required_skills, *row.preferred_skills, *row.mentioned_skills}:
            abilities[normalize_text(value)][value] += 1
    role_names = {key: counter.most_common(1)[0][0] for key, counter in roles.items() if key}
    ability_names = {key: counter.most_common(1)[0][0] for key, counter in abilities.items() if key}
    return role_names, ability_names


def _generic_trend_score(metrics: TrendMetrics) -> tuple[float, float]:
    growth = min(1.0, metrics.growth_rate / 2.0) if metrics.baseline_share > 0 else min(1.0, metrics.distinct_job_count / 8.0)
    volume = min(1.0, metrics.distinct_job_count / 8.0)
    zscore = min(1.0, max(0.0, metrics.robust_zscore) / 4.0)
    score = 0.30 * growth + 0.25 * metrics.persistence + 0.20 * metrics.source_diversity + 0.15 * volume + 0.10 * zscore
    confidence = min(1.0, 0.45 * volume + 0.30 * metrics.persistence + 0.25 * metrics.source_diversity)
    return score, confidence


def build_trend_features(
    observations: Sequence[JobObservation],
    evidence: Sequence[Evidence],
    kg_index: KGIndex | None,
    config: Mapping[str, Any] | None,
    as_of: datetime,
) -> list[TrendFeature]:
    settings = _settings(config)
    window = _window(as_of, settings)
    valid_evidence = {item.evidence_id for item in evidence}
    roles, abilities = _entity_names(observations)
    denominators = _trend_denominators(observations, window)
    role_rows: dict[str, list[JobObservation]] = defaultdict(list)
    ability_rows: dict[str, list[JobObservation]] = defaultdict(list)
    for row in observations:
        role_rows[row.normalized_title].append(row)
        for value in {
            normalize_text(value)
            for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
        }:
            if value:
                ability_rows[value].append(row)
    features: list[TrendFeature] = []
    for entity_type, names in (("job_role", roles), ("ability", abilities)):
        for normal, display in sorted(names.items()):
            if entity_type == "job_role":
                predicate = lambda row, key=normal: row.normalized_title == key
                kg_matches = kg_index.search_jobs(display, 1) if kg_index is not None else []
                kg_node_id = kg_matches[0]["node_id"] if kg_matches and kg_matches[0]["score"] >= 0.999 else None
            else:
                predicate = lambda row, key=normal: key in {
                    normalize_text(value)
                    for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
                }
                resolution = kg_index.resolve_ability(display) if kg_index is not None else None
                kg_node_id = (
                    resolution.source_node_id
                    if resolution is not None and resolution.resolution_status in {"exact", "curated_alias"}
                    else None
                )
            matching_rows = role_rows[normal] if entity_type == "job_role" else ability_rows[normal]
            metrics = _metrics_from_matching_rows(matching_rows, window, denominators)
            if metrics.distinct_job_count == 0 and metrics.previous_distinct_job_count == 0:
                continue
            score, confidence = _generic_trend_score(metrics)
            evidence_ids = sorted(
                {
                    identifier
                    for row in matching_rows
                    if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)
                    for identifier in row.evidence_ids
                    if identifier in valid_evidence
                }
            )
            features.append(
                TrendFeature(
                    trend_id=stable_id("trend", entity_type, normal, window.recent_end.isoformat()),
                    entity_type=entity_type,  # type: ignore[arg-type]
                    entity_name=display,
                    kg_node_id=kg_node_id,
                    window=window,
                    metrics=metrics,
                    score=score,
                    confidence=confidence,
                    evidence_ids=evidence_ids,
                )
            )
    return sorted(features, key=lambda item: (-item.score, item.entity_type, item.entity_name))


def _observation_text(row: JobObservation) -> str:
    return " ".join(
        [
            row.title,
            *row.responsibilities,
            *row.required_skills,
            *row.preferred_skills,
            *row.mentioned_skills,
        ]
    )


def _fallback_clusters(rows: Sequence[JobObservation], min_cluster_size: int) -> list[list[JobObservation]]:
    grouped: dict[str, list[JobObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.normalized_title].append(row)
    # Merge very close title variants if they also share an extracted skill.
    keys = sorted(grouped)
    parent = {key: key for key in keys}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)

    skills = {
        key: {
            normalize_text(value)
            for row in grouped[key]
            for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
        }
        for key in keys
    }
    for position, left in enumerate(keys):
        for right in keys[position + 1 :]:
            if left[:2] != right[:2] and right[:2] not in left and left[:2] not in right:
                continue
            similarity = SequenceMatcher(None, left, right, autojunk=False).ratio()
            if similarity >= 0.84 and (skills[left] & skills[right] or similarity >= 0.94):
                union(left, right)
    clusters: dict[str, list[JobObservation]] = defaultdict(list)
    for key in keys:
        clusters[find(key)].extend(grouped[key])
    return [
        sorted(values, key=lambda item: item.observation_id)
        for _, values in sorted(clusters.items())
    ]


def _merge_definition_equivalent_clusters(
    clusters: Sequence[Sequence[JobObservation]],
) -> list[list[JobObservation]]:
    """Merge title aliases whose sourced duties and skills are near-identical."""

    if len(clusters) < 2:
        return [list(cluster) for cluster in clusters]
    parent = list(range(len(clusters)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[max(left, right)] = min(left, right)

    signatures: list[tuple[set[str], set[str]]] = []
    for cluster in clusters:
        responsibilities = {
            normalize_text(value) for row in cluster for value in row.responsibilities if value.strip()
        }
        skills = {
            normalize_text(value)
            for row in cluster
            for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
            if value.strip()
        }
        signatures.append((responsibilities, skills))
    for left in range(len(clusters)):
        for right in range(left + 1, len(clusters)):
            left_responsibilities, left_skills = signatures[left]
            right_responsibilities, right_skills = signatures[right]
            responsibility_union = left_responsibilities | right_responsibilities
            skill_union = left_skills | right_skills
            responsibility_overlap = (
                len(left_responsibilities & right_responsibilities) / len(responsibility_union)
                if responsibility_union
                else 0.0
            )
            skill_overlap = (
                len(left_skills & right_skills) / len(skill_union) if skill_union else 0.0
            )
            if responsibility_overlap >= 0.50 and skill_overlap >= 0.60:
                union(left, right)
    merged: dict[int, list[JobObservation]] = defaultdict(list)
    for index, cluster in enumerate(clusters):
        merged[find(index)].extend(cluster)
    return [
        sorted(values, key=lambda item: item.observation_id)
        for _, values in sorted(merged.items())
    ]


def cluster_unknown_roles(
    observations: Sequence[JobObservation],
    *,
    min_cluster_size: int,
    min_samples: int,
) -> list[list[JobObservation]]:
    """Use HDBSCAN when installed; otherwise use stable title/skill components."""

    if len(observations) < min_cluster_size:
        return []
    try:
        try:
            from sklearn.cluster import HDBSCAN  # type: ignore[attr-defined]
        except ImportError:
            from hdbscan import HDBSCAN  # type: ignore[no-redef]
        from sklearn.feature_extraction.text import HashingVectorizer

        # A fixed-dimensional hash matrix avoids converting an unbounded
        # 2--4-gram vocabulary to dense form for the 10k-JD baseline.
        matrix = HashingVectorizer(
            analyzer="char",
            ngram_range=(2, 4),
            n_features=512,
            alternate_sign=False,
            norm="l2",
        ).transform([_observation_text(row) for row in observations])
        # Dense conversion is bounded to the unknown-role candidates and is
        # required by some hdbscan versions for deterministic Euclidean fit.
        labels = HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            metric="euclidean",
        ).fit_predict(matrix.toarray())
        clusters: dict[int, list[JobObservation]] = defaultdict(list)
        for row, label in zip(observations, labels, strict=True):
            if int(label) >= 0:
                clusters[int(label)].append(row)
        result = [
            sorted(rows, key=lambda item: item.observation_id)
            for _, rows in sorted(clusters.items())
        ]
        # HDBSCAN may label a small, perfectly coherent synthetic/new role as
        # noise; the deterministic fallback prevents an availability-dependent
        # false negative.
        merged = _merge_definition_equivalent_clusters(
            result or _fallback_clusters(observations, min_cluster_size)
        )
        return [
            cluster
            for cluster in merged
            if len({item.near_dup_cluster_id for item in cluster}) >= min_cluster_size
        ]
    except Exception:
        merged = _merge_definition_equivalent_clusters(
            _fallback_clusters(observations, min_cluster_size)
        )
        return [
            cluster
            for cluster in merged
            if len({item.near_dup_cluster_id for item in cluster}) >= min_cluster_size
        ]


def _best_known_role(row: JobObservation, kg_index: KGIndex | None) -> tuple[float, str | None, str | None]:
    if kg_index is None:
        return 0.0, None, None
    values = kg_index.search_jobs(row.title, 5)
    if not values:
        return 0.0, None, None
    observed_skills = {
        normalize_text(value)
        for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
    }
    scored: list[tuple[float, dict[str, Any]]] = []
    for value in values:
        title_score = float(value["score"])
        # An exact canonical title is already a known role even when a new
        # skill is appearing; that change belongs in the skill-update output.
        if title_score >= 0.995:
            score = 1.0
        else:
            prototype_skills = {
                normalize_text(name)
                for name in kg_index.job_ability_names(str(value["node_id"]))
            }
            union = observed_skills | prototype_skills
            skill_overlap = len(observed_skills & prototype_skills) / len(union) if union else 0.0
            # Novel role discovery is based on title+duty+skill composition,
            # not title edit distance alone.  The current graph exposes title
            # and abilities; sourced duties remain in the observation vector.
            score = 0.70 * title_score + 0.30 * skill_overlap
        scored.append((score, value))
    score, result = max(scored, key=lambda item: (item[0], str(item[1]["node_id"])))
    return score, str(result["node_id"]), str(result["canonical_title"])


def _top_values(values: Iterable[str], limit: int) -> list[str]:
    counts = Counter(value.strip() for value in values if value and value.strip())
    return [value for value, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def _frequent_skills(
    rows: Sequence[JobObservation], attribute: str, *, minimum_fraction: float, limit: int
) -> list[str]:
    counts: Counter[str] = Counter()
    displays: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        values = list(getattr(row, attribute))
        keys_seen: set[str] = set()
        for value in values:
            key = normalize_text(value)
            displays[key][value] += 1
            if key and key not in keys_seen:
                counts[key] += 1
                keys_seen.add(key)
    threshold = max(2, math.ceil(len(rows) * minimum_fraction))
    selected = [
        key for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])) if count >= threshold
    ][:limit]
    return [displays[key].most_common(1)[0][0] for key in selected]


def _external_support(
    cluster: Sequence[JobObservation], evidence: Sequence[Evidence]
) -> list[Evidence]:
    query_terms = {
        normalize_text(value)
        for row in cluster
        for value in (row.title, *row.required_skills, *row.preferred_skills, *row.mentioned_skills)
        if len(normalize_text(value)) >= 2
    }
    results: list[Evidence] = []
    for item in evidence:
        if item.source_type == "job":
            continue
        text = normalize_text(item.text)
        matched = sum(term in text for term in query_terms)
        if matched >= 1:
            results.append(item)
    return sorted(results, key=lambda item: item.evidence_id)[:8]


def _ability_for_role(
    name: str,
    role: str,
    rows: Sequence[JobObservation],
    kg_index: KGIndex | None,
    valid_evidence: set[str],
) -> tuple[RoleAbility, AbilityRef | None]:
    evidence_ids = sorted(
        {
            identifier
            for row in rows
            if normalize_text(name)
            in {normalize_text(value) for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)}
            for identifier in row.evidence_ids
            if identifier in valid_evidence
        }
    )
    resolution = kg_index.resolve_ability(name) if kg_index is not None else None
    automatic = resolution is not None and resolution.resolution_status in {"exact", "curated_alias"}
    ability = RoleAbility(
        name=resolution.canonical_name if automatic else name,
        category=resolution.category if resolution is not None else "unknown",
        role=role,  # type: ignore[arg-type]
        kg_node_id=resolution.source_node_id if automatic else None,
        confidence=min(1.0, 0.65 + 0.05 * len(evidence_ids)),
        evidence_ids=evidence_ids,
    )
    return ability, resolution


def discover_emerging_roles(
    observations: Sequence[JobObservation],
    evidence: Sequence[Evidence],
    kg_index: KGIndex | None,
    config: Mapping[str, Any] | None,
    as_of: datetime,
) -> tuple[list[EmergingRole], list[KGLinkDelta]]:
    settings = _settings(config)
    window = _window(as_of, settings)
    # When no/partial external KG is supplied, the historical baseline itself
    # is the local known-role catalogue.  A long-standing role whose skills are
    # changing (for example Java 开发工程师) belongs in skill updates, not in
    # emerging-role discovery merely because no graph node was imported.
    baseline_known_titles = {
        row.normalized_title
        for row in observations
        if _in_half_open(_observed_at(row), window.baseline_start, window.baseline_end)
    }
    eligible = [
        row
        for row in observations
        if _in_half_open(_observed_at(row), window.baseline_start, window.recent_end)
        and row.normalized_title not in baseline_known_titles
        and _best_known_role(row, kg_index)[0] <= float(settings["max_known_role_similarity"])
    ]
    clusters = cluster_unknown_roles(
        eligible,
        min_cluster_size=int(settings["min_cluster_size"]),
        min_samples=int(settings["min_samples"]),
    )
    valid_evidence = {item.evidence_id for item in evidence}
    roles: list[EmergingRole] = []
    deltas: list[KGLinkDelta] = []
    for cluster in clusters:
        member_ids = {row.observation_id for row in cluster}
        predicate = lambda row, ids=member_ids: row.observation_id in ids
        metrics = _metrics_for(observations, predicate, window)
        recent = [row for row in cluster if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)]
        recent_unique = _deduped(recent)
        supporting_jobs = len({row.near_dup_cluster_id for row in recent_unique})
        companies = {normalize_company(row.company) for row in recent_unique if row.company}
        sources = {row.source_name for row in recent_unique}
        weeks = {row.snapshot_week for row in recent_unique}
        if supporting_jobs < int(settings["min_cluster_size"]):
            continue
        if len(companies) < int(settings["min_companies"]):
            continue
        if len(weeks) < int(settings["min_week_snapshots"]):
            continue
        supporting_external = _external_support(cluster, evidence)
        if len(sources) < 2 and not (len(sources) == 1 and supporting_external):
            continue
        if not (
            metrics.baseline_share == 0.0
            or metrics.growth_rate >= float(settings["min_growth_rate"])
        ):
            continue
        known_similarity = max((_best_known_role(row, kg_index)[0] for row in cluster), default=0.0)
        novelty = max(
            0.0,
            min(1.0, 1.0 - known_similarity / max(float(settings["max_known_role_similarity"]), 1e-9)),
        )
        growth = 1.0 if metrics.baseline_share == 0.0 else min(
            1.0, metrics.growth_rate / float(settings["min_growth_rate"])
        )
        persistence = min(1.0, len(weeks) / float(settings["min_week_snapshots"]))
        source_diversity = min(1.0, len(sources) / 2.0 + (0.25 if supporting_external else 0.0))
        recent_evidence_ids = {
            identifier for row in recent_unique for identifier in row.evidence_ids if identifier in valid_evidence
        }
        evidence_coverage = min(1.0, len(recent_evidence_ids) / max(1, supporting_jobs))
        if supporting_external:
            evidence_coverage = min(1.0, evidence_coverage + 0.20)
        components = {
            "novelty": novelty,
            "growth": growth,
            "persistence": persistence,
            "source_diversity": source_diversity,
            "evidence_coverage": evidence_coverage,
        }
        overall = sum(
            float(settings["score_weights"][name]) * value for name, value in components.items()
        )
        if len(sources) == 1:
            overall = min(overall, max(0.0, float(settings["high_confidence_threshold"]) - 1e-6))
        if overall < float(settings["candidate_score_threshold"]):
            continue

        canonical_title = _top_values((row.title for row in recent_unique), 1)[0]
        aliases = [value for value in _top_values((row.title for row in cluster), 8) if value != canonical_title]
        required_names = _frequent_skills(
            recent_unique, "required_skills", minimum_fraction=0.25, limit=12
        )
        preferred_names = _frequent_skills(
            recent_unique, "preferred_skills", minimum_fraction=0.20, limit=8
        )
        # A skill explicitly required somewhere is not duplicated as preferred.
        preferred_names = [value for value in preferred_names if normalize_text(value) not in {normalize_text(v) for v in required_names}]
        abilities_and_resolutions = [
            _ability_for_role(name, "required", recent_unique, kg_index, valid_evidence)
            for name in required_names
        ]
        preferred_and_resolutions = [
            _ability_for_role(name, "preferred", recent_unique, kg_index, valid_evidence)
            for name in preferred_names
        ]
        all_evidence_ids = sorted(
            recent_evidence_ids | {item.evidence_id for item in supporting_external}
        )
        role_id = stable_id("role", normalize_title(canonical_title))
        first_seen = min(_observed_at(row) for row in cluster)
        last_seen = max(_observed_at(row) for row in cluster)
        role = EmergingRole(
            role_id=role_id,
            canonical_title=canonical_title,
            aliases=aliases,
            core_responsibilities=_top_values(
                (value for row in recent_unique for value in row.responsibilities), 8
            ),
            required_skills=[value[0] for value in abilities_and_resolutions],
            preferred_skills=[value[0] for value in preferred_and_resolutions],
            typical_industry_scenarios=_top_values(
                (row.industry for row in recent_unique if row.industry), 5
            ),
            industries=sorted({row.industry for row in recent_unique if row.industry}),
            regions=sorted({row.region for row in recent_unique if row.region}),
            first_seen=first_seen,
            last_seen=last_seen,
            supporting_job_count=supporting_jobs,
            supporting_company_count=len(companies),
            supporting_source_count=len(sources),
            scores=EmergingRoleScores(**components, overall=overall),
            evidence_ids=all_evidence_ids,
            status="candidate" if all_evidence_ids else "needs_review",
            explanation=(
                f"近{settings['recent_days']}天发现{supporting_jobs}个去重岗位，覆盖"
                f"{len(companies)}家企业、{len(sources)}个招聘来源和{len(weeks)}个周快照；"
                f"与已知岗位最高相似度{known_similarity:.3f}，来源归一化增长{metrics.growth_rate:.3f}。"
            ),
        )
        roles.append(role)
        baseline = kg_index.fingerprint if kg_index is not None else "no_baseline_graph"
        deltas.append(
            KGLinkDelta(
                delta_id=stable_id("delta", role_id, "node"),
                baseline_graph_fingerprint=baseline,
                operation="propose_node",
                source_id=role_id,
                evidence_ids=all_evidence_ids,
                resolution_status="unresolved",
                properties={
                    "label": "EmergingRole",
                    "canonical_title": canonical_title,
                    "status": role.status,
                },
            )
        )
        for ability, resolution in [*abilities_and_resolutions, *preferred_and_resolutions]:
            relation = "REQUIRES_SKILL" if ability.role == "required" else "PREFERS_SKILL"
            if resolution is not None and resolution.resolution_status in {"exact", "curated_alias"}:
                operation, target, status = "link_existing", resolution.source_node_id, resolution.resolution_status
            elif resolution is not None and resolution.resolution_status == "review_candidate":
                operation, target, status = "propose_edge", resolution.source_node_id, "review_candidate"
            else:
                ability_id = stable_id("ability", normalize_text(ability.name))
                deltas.append(
                    KGLinkDelta(
                        delta_id=stable_id("delta", ability_id, "node"),
                        baseline_graph_fingerprint=baseline,
                        operation="propose_node",
                        source_id=ability_id,
                        evidence_ids=ability.evidence_ids,
                        resolution_status="unresolved",
                        properties={
                            "label": "Ability",
                            "canonical_name": ability.name,
                            "category": ability.category,
                        },
                    )
                )
                operation, target, status = "propose_edge", ability_id, "unresolved"
            deltas.append(
                KGLinkDelta(
                    delta_id=stable_id("delta", role_id, ability.name, relation),
                    baseline_graph_fingerprint=baseline,
                    operation=operation,  # type: ignore[arg-type]
                    source_id=role_id,
                    target_id=target,
                    relation_type=relation,
                    evidence_ids=ability.evidence_ids,
                    resolution_status=status,  # type: ignore[arg-type]
                    properties={"ability_name": ability.name, "category": ability.category},
                )
            )
    # Multiple emerging roles can cite the same newly proposed ability.  Keep
    # one append-only node proposal and union its evidence deterministically.
    unique_deltas: dict[str, KGLinkDelta] = {}
    for delta in deltas:
        previous = unique_deltas.get(delta.delta_id)
        if previous is None:
            unique_deltas[delta.delta_id] = delta
        else:
            previous.evidence_ids = sorted(set(previous.evidence_ids) | set(delta.evidence_ids))
    return (
        sorted(roles, key=lambda item: (-item.scores.overall, item.role_id)),
        sorted(unique_deltas.values(), key=lambda item: item.delta_id),
    )


def _proportion_p_value(success_recent: int, total_recent: int, success_baseline: int, total_baseline: int) -> float:
    if total_recent <= 0 or total_baseline <= 0:
        return 1.0
    table = [
        [success_recent, max(0, total_recent - success_recent)],
        [success_baseline, max(0, total_baseline - success_baseline)],
    ]
    try:
        from scipy.stats import fisher_exact

        return float(fisher_exact(table, alternative="two-sided").pvalue)
    except Exception:
        first, second = success_recent / total_recent, success_baseline / total_baseline
        pooled = (success_recent + success_baseline) / (total_recent + total_baseline)
        standard_error = math.sqrt(max(0.0, pooled * (1 - pooled) * (1 / total_recent + 1 / total_baseline)))
        if standard_error == 0:
            return 1.0 if math.isclose(first, second) else 0.0
        zscore = abs(first - second) / standard_error
        return math.erfc(zscore / math.sqrt(2.0))


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values in original input order."""

    if not p_values:
        return []
    count = len(p_values)
    order = sorted(range(count), key=lambda index: (p_values[index], index))
    adjusted = [1.0] * count
    running = 1.0
    for rank_from_end, index in enumerate(reversed(order), start=1):
        rank = count - rank_from_end + 1
        running = min(running, max(0.0, min(1.0, float(p_values[index]) * count / rank)))
        adjusted[index] = running
    return adjusted


def _contains_skill(row: JobObservation, skill: str, role: str | None = None) -> bool:
    key = normalize_text(skill)
    if role == "required":
        values = row.required_skills
    elif role == "preferred":
        values = row.preferred_skills
    else:
        values = (*row.required_skills, *row.preferred_skills, *row.mentioned_skills)
    return key in {normalize_text(value) for value in values}


def _cross_source_three_window_decline(
    role_rows: Sequence[JobObservation],
    skill: str,
    as_of: datetime,
    recent_days: int,
    share_delta: float,
) -> bool:
    end = _aware(as_of)
    source_values = sorted({row.source_name for row in role_rows})
    qualifying_sources = 0
    for source in source_values:
        source_rows = [row for row in role_rows if row.source_name == source]
        reference_start = end - timedelta(days=recent_days * 6)
        reference_end = end - timedelta(days=recent_days * 3)
        reference = _deduped(
            row for row in source_rows if _in_half_open(_observed_at(row), reference_start, reference_end)
        )
        if not reference:
            continue
        reference_share = sum(_contains_skill(row, skill) for row in reference) / len(reference)
        if reference_share < share_delta:
            continue
        declined = True
        for window_index in range(3):
            window_end = end - timedelta(days=recent_days * window_index)
            window_start = window_end - timedelta(days=recent_days)
            rows = _deduped(
                row for row in source_rows if _in_half_open(_observed_at(row), window_start, window_end)
            )
            if not rows:
                declined = False
                break
            share = sum(_contains_skill(row, skill) for row in rows) / len(rows)
            if share > max(0.0, reference_share - share_delta):
                declined = False
                break
        if declined:
            qualifying_sources += 1
    return qualifying_sources >= 2


def detect_skill_updates(
    observations: Sequence[JobObservation],
    evidence: Sequence[Evidence],
    kg_index: KGIndex | None,
    config: Mapping[str, Any] | None,
    as_of: datetime,
) -> list[JobSkillUpdate]:
    settings = _settings(config)
    window = _window(as_of, settings)
    valid_evidence = {item.evidence_id for item in evidence}
    role_groups: dict[tuple[str, tuple[str, ...]], list[JobObservation]] = defaultdict(list)
    local_role_names, _ = _entity_names(observations)
    for row in observations:
        score, node_id, canonical = _best_known_role(row, kg_index)
        if score >= float(settings["max_known_role_similarity"]) and node_id and canonical:
            # Keep the observed, human-readable local role name.  Imported
            # legacy graphs can contain encoding-damaged titles; only their
            # immutable node IDs are authoritative for the delta contract.
            key = (local_role_names.get(row.normalized_title, row.title), (node_id,))
        else:
            key = (local_role_names.get(row.normalized_title, row.title), ())
        role_groups[key].append(row)

    proposed: list[dict[str, Any]] = []
    for (role_name, kg_ids), rows in sorted(role_groups.items()):
        recent = _deduped(
            row for row in rows if _in_half_open(_observed_at(row), window.recent_start, window.recent_end)
        )
        baseline = _deduped(
            row for row in rows if _in_half_open(_observed_at(row), window.baseline_start, window.baseline_end)
        )
        if not recent or not baseline:
            continue
        skill_displays: dict[str, Counter[str]] = defaultdict(Counter)
        for row in [*recent, *baseline]:
            for value in (*row.required_skills, *row.preferred_skills, *row.mentioned_skills):
                skill_displays[normalize_text(value)][value] += 1
        for key, displays in skill_displays.items():
            skill = displays.most_common(1)[0][0]
            recent_count = sum(_contains_skill(row, skill) for row in recent)
            baseline_count = sum(_contains_skill(row, skill) for row in baseline)
            recent_share = recent_count / len(recent)
            baseline_share = baseline_count / len(baseline)
            delta = recent_share - baseline_share
            lift = recent_share / baseline_share if baseline_share > 0 else (999.0 if recent_share > 0 else 0.0)
            companies = {
                normalize_company(row.company) for row in recent if row.company and _contains_skill(row, skill)
            }
            p_value = _proportion_p_value(recent_count, len(recent), baseline_count, len(baseline))
            recent_required = sum(_contains_skill(row, skill, "required") for row in recent)
            baseline_required = sum(_contains_skill(row, skill, "required") for row in baseline)
            recent_preferred = sum(_contains_skill(row, skill, "preferred") for row in recent)
            baseline_preferred = sum(_contains_skill(row, skill, "preferred") for row in baseline)
            preferred_to_required = (
                baseline_preferred > baseline_required
                and recent_required > recent_preferred
                and recent_required / len(recent) - baseline_required / len(baseline)
                >= float(settings["skill_min_share_delta"])
            )
            required_to_preferred = (
                baseline_required > baseline_preferred
                and recent_preferred > recent_required
                and recent_preferred / len(recent) - baseline_preferred / len(baseline)
                >= float(settings["skill_min_share_delta"])
            )
            modified = preferred_to_required or required_to_preferred
            if modified:
                p_value = (
                    _proportion_p_value(
                        recent_required, len(recent), baseline_required, len(baseline)
                    )
                    if preferred_to_required
                    else _proportion_p_value(
                        recent_preferred, len(recent), baseline_preferred, len(baseline)
                    )
                )
            proposed.append(
                {
                    "role": role_name,
                    "kg_ids": list(kg_ids),
                    "rows": rows,
                    "recent": recent,
                    "baseline": baseline,
                    "skill": skill,
                    "skill_key": key,
                    "recent_share": recent_share,
                    "baseline_share": baseline_share,
                    "delta": delta,
                    "lift": lift,
                    "companies": companies,
                    "p_value": p_value,
                    "modified": modified,
                }
            )

    q_values = benjamini_hochberg([float(item["p_value"]) for item in proposed])
    changes_by_role: dict[tuple[str, tuple[str, ...]], list[SkillChange]] = defaultdict(list)
    evidence_by_role: dict[tuple[str, tuple[str, ...]], set[str]] = defaultdict(set)
    for item, q_value in zip(proposed, q_values, strict=True):
        delta, lift = float(item["delta"]), float(item["lift"])
        recent_share, baseline_share = float(item["recent_share"]), float(item["baseline_share"])
        companies = item["companies"]
        if q_value > float(settings["significance_q"]):
            continue
        change_type: str | None = None
        if item["modified"] and len(companies) >= int(settings["skill_min_companies"]):
            change_type = "modified"
        elif (
            delta >= float(settings["skill_min_share_delta"])
            and lift >= float(settings["skill_min_relative_lift"])
            and len(companies) >= int(settings["skill_min_companies"])
        ):
            change_type = "added" if baseline_share == 0.0 else "rising"
        elif delta <= -float(settings["skill_min_share_delta"]):
            change_type = "declining"
            if _cross_source_three_window_decline(
                item["rows"],
                item["skill"],
                as_of,
                int(settings["recent_days"]),
                float(settings["skill_min_share_delta"]),
            ):
                change_type = "removal_candidate"
        if change_type is None:
            continue
        resolution = kg_index.resolve_ability(item["skill"]) if kg_index is not None else None
        kg_node_id = (
            resolution.source_node_id
            if resolution is not None and resolution.resolution_status in {"exact", "curated_alias"}
            else None
        )
        evidence_ids = sorted(
            {
                identifier
                for row in [*item["recent"], *item["baseline"]]
                if _contains_skill(row, item["skill"])
                for identifier in row.evidence_ids
                if identifier in valid_evidence
            }
        )
        role_key = (str(item["role"]), tuple(item["kg_ids"]))
        changes_by_role[role_key].append(
            SkillChange(
                skill_name=(
                    resolution.canonical_name
                    if resolution is not None
                    and resolution.resolution_status in {"exact", "curated_alias"}
                    else item["skill"]
                ),
                kg_node_id=kg_node_id,
                change_type=change_type,  # type: ignore[arg-type]
                baseline_share=baseline_share,
                recent_share=recent_share,
                share_delta=delta,
                relative_lift=lift,
                p_value=float(item["p_value"]),
                q_value=q_value,
                supporting_company_count=len(companies),
                evidence_ids=evidence_ids,
            )
        )
        evidence_by_role[role_key].update(evidence_ids)

    updates: list[JobSkillUpdate] = []
    for (role, kg_ids), changes in changes_by_role.items():
        changes.sort(key=lambda item: (-abs(item.share_delta), item.skill_name))
        updates.append(
            JobSkillUpdate(
                update_id=stable_id("skill-update", normalize_title(role), window.recent_end.isoformat()),
                canonical_role=role,
                kg_job_ids=list(kg_ids),
                window=window,
                changes=changes,
                evidence_ids=sorted(evidence_by_role[(role, kg_ids)]),
                status="candidate" if evidence_by_role[(role, kg_ids)] else "needs_review",
                explanation=(
                    f"比较近{settings['recent_days']}天与此前{settings['baseline_days']}天的来源内岗位占比；"
                    f"保留通过 BH 校正(q≤{settings['significance_q']})的{len(changes)}项能力变化。"
                ),
            )
        )
    return sorted(updates, key=lambda item: item.update_id)


def analyze_trends(
    observations: Sequence[JobObservation | Mapping[str, object]],
    evidence: Sequence[Evidence | Mapping[str, object]],
    kg_index: KGIndex | None,
    config: Mapping[str, Any] | None,
    as_of: datetime | None = None,
) -> tuple[
    list[TrendFeature],
    list[EmergingRole],
    list[JobSkillUpdate],
    list[KGLinkDelta],
    dict[str, Any],
]:
    """Run the complete deterministic analysis stage used by the CLI."""

    parsed_observations = [_as_observation(item) for item in observations]
    parsed_evidence = [_as_evidence(item) for item in evidence]
    if as_of is None:
        as_of = (
            max((_observed_at(item) for item in parsed_observations), default=datetime.now(timezone.utc))
            + timedelta(microseconds=1)
        )
    as_of = _aware(as_of)
    features = build_trend_features(parsed_observations, parsed_evidence, kg_index, config, as_of)
    emerging, deltas = discover_emerging_roles(
        parsed_observations, parsed_evidence, kg_index, config, as_of
    )
    updates = detect_skill_updates(parsed_observations, parsed_evidence, kg_index, config, as_of)
    summary = {
        "as_of": as_of.isoformat(),
        "observation_count": len(parsed_observations),
        "unique_near_duplicate_count": len({item.near_dup_cluster_id for item in parsed_observations}),
        "trend_feature_count": len(features),
        "emerging_role_count": len(emerging),
        "job_skill_update_count": len(updates),
        "kg_delta_count": len(deltas),
        "baseline_graph_fingerprint": kg_index.fingerprint if kg_index is not None else None,
    }
    return features, emerging, updates, deltas, summary


__all__ = [
    "DEFAULT_ANALYSIS_CONFIG",
    "analyze_trends",
    "benjamini_hochberg",
    "build_job_observations",
    "build_trend_features",
    "cluster_unknown_roles",
    "detect_skill_updates",
    "discover_emerging_roles",
]
