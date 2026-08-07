"""LSKT span extraction backed by an official ESCO snapshot index."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from os import getenv
from typing import Any, Protocol

from backend.app.data_governance.esco import EscoIndex, EscoLinkResult, EscoLinker
from backend.app.infrastructure.llm.client import ChatClientProtocol, OpenAICompatibleChatClient
from backend.app.infrastructure.llm.settings import LLMSettings


LSKT_LABELS = {"K", "S", "T", "L"}


@dataclass(frozen=True)
class SpanCandidate:
    surface: str
    normalized_name: str
    category: str | None
    lskt_label: str
    start_char: int
    end_char: int
    confidence: float
    extraction_method: str
    normalization_status: str
    esco_id: str | None = None
    esco_uri: str | None = None
    esco_preferred_label: str | None = None
    esco_version: str | None = None
    linking_status: str = "unmapped"
    linking_confidence: float = 0.0


class SpanExtractor(Protocol):
    def extract(self, text: str) -> list[SpanCandidate]: ...


class EscoBackedLsktSpanExtractor:
    def __init__(
        self,
        index: EscoIndex,
        linker: EscoLinker,
        draft_extractor: SpanExtractor | None = None,
    ) -> None:
        self.index = index
        self.linker = linker
        self.draft_extractor = draft_extractor

    def extract(self, text: str) -> list[SpanCandidate]:
        candidates: list[SpanCandidate] = []
        occupied: list[range] = []
        for draft in self._drafts(text):
            if not validate_candidate(text, draft):
                continue
            linked = self._linked_candidate(text, draft)
            if _occupy(linked, occupied):
                candidates.append(linked)
        return sorted(candidates, key=lambda item: (item.start_char, item.end_char, item.surface))

    def _drafts(self, text: str) -> list[SpanCandidate]:
        drafts: list[SpanCandidate] = []
        if self.draft_extractor is not None:
            drafts.extend(self.draft_extractor.extract(text))
        drafts.extend(LanguageCertificateSpanExtractor().extract(text))
        return drafts

    def _linked_candidate(self, text: str, draft: SpanCandidate) -> SpanCandidate:
        link = self.linker.link(draft.surface, text, draft.lskt_label)
        return _with_link(draft, link)


class LanguageCertificateSpanExtractor:
    def extract(self, text: str) -> list[SpanCandidate]:
        candidates: list[SpanCandidate] = []
        for pattern in _LANGUAGE_PATTERNS:
            for match in pattern.finditer(text):
                surface = _trim_surface(match.group(0))
                if not surface:
                    continue
                start = match.start() + match.group(0).find(surface)
                candidates.append(
                    SpanCandidate(
                        surface=surface,
                        normalized_name=surface,
                        category="language",
                        lskt_label="L",
                        start_char=start,
                        end_char=start + len(surface),
                        confidence=0.9,
                        extraction_method="local_language_certificate",
                        normalization_status="unmapped",
                    )
                )
        return candidates


class OllamaLsktDraftExtractor:
    def __init__(self, chat_client: ChatClientProtocol | None = None, settings: LLMSettings | None = None) -> None:
        self.settings = settings or LLMSettings.from_env()
        self.chat_client = chat_client or OpenAICompatibleChatClient(self.settings)

    def extract(self, text: str) -> list[SpanCandidate]:
        prompt_text = text[: self.settings.max_input_chars]
        try:
            content = self.chat_client.chat(_ollama_messages(prompt_text))
            payload = _load_json_object(content, expected_keys=("spans",))
        except Exception:
            return []
        spans = payload.get("spans")
        if not isinstance(spans, list):
            return []
        candidates: list[SpanCandidate] = []
        for item in spans:
            if not isinstance(item, dict):
                continue
            candidates.extend(_candidates_from_llm_item(text, item))
        return candidates


def build_lskt_span_extractor(
    esco_index: EscoIndex,
    chat_client: ChatClientProtocol | None = None,
) -> SpanExtractor:
    mode = getenv("LSKT_SPAN_BACKEND", "ollama").strip().lower()
    settings = LLMSettings.from_env()
    linker = EscoLinker(esco_index, chat_client=chat_client, settings=settings)
    draft_extractor: SpanExtractor | None = None
    if mode in {"ollama", "hybrid"}:
        draft_extractor = OllamaLsktDraftExtractor(chat_client=chat_client, settings=settings)
    elif mode == "local":
        draft_extractor = None
    return EscoBackedLsktSpanExtractor(esco_index, linker, draft_extractor=draft_extractor)


def validate_candidate(text: str, candidate: SpanCandidate) -> bool:
    if candidate.lskt_label not in LSKT_LABELS:
        return False
    if candidate.start_char < 0 or candidate.end_char <= candidate.start_char:
        return False
    if candidate.end_char > len(text):
        return False
    return text[candidate.start_char : candidate.end_char] == candidate.surface


def _candidates_from_llm_item(text: str, item: dict[str, Any]) -> list[SpanCandidate]:
    surface = _clean_text(item.get("surface") or item.get("span"))
    label = _clean_text(item.get("lskt_label") or item.get("label")).upper()
    if not surface or label not in LSKT_LABELS:
        return []
    start, end = _resolve_offsets(text, surface, item.get("start_char"), item.get("end_char"))
    if start is None or end is None:
        return []
    category = _clean_text(item.get("category")) or None
    confidence = _confidence(item.get("confidence"), default=0.72)
    candidates: list[SpanCandidate] = []
    for trimmed_surface, trimmed_start, trimmed_end in _minimal_surfaces(surface, start):
        candidate = SpanCandidate(
            surface=trimmed_surface,
            normalized_name=trimmed_surface,
            category=category,
            lskt_label=label,
            start_char=trimmed_start,
            end_char=trimmed_end,
            confidence=confidence,
            extraction_method="ollama_draft",
            normalization_status="unmapped",
        )
        if validate_candidate(text, candidate):
            candidates.append(candidate)
    return candidates


def _with_link(candidate: SpanCandidate, link: EscoLinkResult) -> SpanCandidate:
    concept = link.concept
    if concept is None:
        return SpanCandidate(
            **{
                **candidate.__dict__,
                "normalization_status": link.linking_status,
                "linking_status": link.linking_status,
                "linking_confidence": link.linking_confidence,
            }
        )
    return SpanCandidate(
        **{
            **candidate.__dict__,
            "normalized_name": concept.preferred_label,
            "category": concept.skill_type or concept.concept_type,
            "lskt_label": concept.lskt_label or candidate.lskt_label,
            "normalization_status": "esco_linked",
            "esco_id": concept.esco_uri.rsplit("/", 1)[-1],
            "esco_uri": concept.esco_uri,
            "esco_preferred_label": concept.preferred_label,
            "esco_version": concept.version,
            "linking_status": link.linking_status,
            "linking_confidence": link.linking_confidence,
        }
    )


def _resolve_offsets(text: str, surface: str, raw_start: Any, raw_end: Any) -> tuple[int | None, int | None]:
    try:
        start = int(raw_start)
        end = int(raw_end)
    except (TypeError, ValueError):
        start = -1
        end = -1
    if 0 <= start < end <= len(text) and text[start:end] == surface:
        return start, end
    found = text.find(surface)
    if found < 0:
        return None, None
    return found, found + len(surface)


def _confidence(value: Any, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(score, 1.0))


def _occupy(candidate: SpanCandidate, occupied: list[range]) -> bool:
    current = range(candidate.start_char, candidate.end_char)
    if any(_overlaps(current, existing) for existing in occupied):
        return False
    occupied.append(current)
    return True


def _overlaps(left: range, right: range) -> bool:
    return left.start < right.stop and right.start < left.stop


def _trim_surface(value: str) -> str:
    return value.strip(" ，,。、；;：:\n\t")


def _minimal_surfaces(surface: str, start: int) -> list[tuple[str, int, int]]:
    trimmed, offset = _trim_competency_boundary(surface)
    if not trimmed:
        return []
    base_start = start + offset
    parts: list[tuple[str, int, int]] = []
    last = 0
    for match in _COMPOUND_DELIMITER.finditer(trimmed):
        _append_minimal_part(parts, trimmed[last : match.start()], base_start + last)
        last = match.end()
    _append_minimal_part(parts, trimmed[last:], base_start + last)
    return parts or [(trimmed, base_start, base_start + len(trimmed))]


def _append_minimal_part(parts: list[tuple[str, int, int]], value: str, start: int) -> None:
    trimmed, offset = _trim_competency_boundary(value)
    if not trimmed:
        return
    part_start = start + offset
    parts.append((trimmed, part_start, part_start + len(trimmed)))


def _trim_competency_boundary(value: str) -> tuple[str, int]:
    left_trimmed = value
    offset = 0
    while True:
        stripped = left_trimmed.lstrip(" ，,。、；;：:\n\t")
        offset += len(left_trimmed) - len(stripped)
        left_trimmed = stripped
        matched = False
        for prefix in _LEADING_CONTEXT_WORDS:
            if left_trimmed.startswith(prefix):
                left_trimmed = left_trimmed[len(prefix) :]
                offset += len(prefix)
                matched = True
                break
        if not matched:
            break
    right_trimmed = left_trimmed.rstrip(" ，,。、；;：:\n\t")
    while True:
        matched = False
        for suffix in _TRAILING_CONTEXT_WORDS:
            if right_trimmed.endswith(suffix) and len(right_trimmed) > len(suffix):
                right_trimmed = right_trimmed[: -len(suffix)].rstrip(" ，,。、；;：:\n\t")
                matched = True
                break
        if not matched:
            break
    return right_trimmed, offset


def _clean_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _load_json_object(content: str, expected_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        last_payload: dict[str, Any] | None = None
        for match in re.finditer(r"{", content):
            try:
                parsed, _ = decoder.raw_decode(content[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and _has_expected_key(parsed, expected_keys):
                last_payload = parsed
        if last_payload is None:
            raise
        return last_payload
    if not isinstance(payload, dict) or not _has_expected_key(payload, expected_keys):
        raise ValueError("expected JSON object")
    return payload


def _has_expected_key(payload: dict[str, Any], expected_keys: tuple[str, ...]) -> bool:
    return not expected_keys or any(key in payload for key in expected_keys)


def _ollama_messages(text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是中文招聘文本 LSKT 能力 span 标注器。只输出 JSON object。"
                "所有 span 必须逐字来自原文，不要编造。span 应尽量是最小能力名词短语，"
                "不要包含掌握、熟悉、负责、具备、优先等上下文修饰，不要把多个能力合并。"
            ),
        },
        {
            "role": "user",
            "content": (
                "按 LSKT 抽取能力 span：K=知识/理论/标准，S=可执行技能，"
                "T=通用能力，L=语言能力。不要做 ESCO 归一化。输出格式："
                '{"spans":[{"surface":"","lskt_label":"K|S|T|L","start_char":0,'
                '"end_char":0,"category":"","confidence":0.0}]}'
                "\n原文：\n"
                f"{text}"
            ),
        },
    ]


_LANGUAGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:CET[- ]?[四六46]|英语(?:六级|四级)?|商务英语|日语N[1-5]|JLPT ?N[1-5]|HSK ?[1-6]|IELTS|TOEFL)", re.IGNORECASE),
)
_COMPOUND_DELIMITER = re.compile(r"\s*(?:、|，|,|/|；|;|\+|和|与|及)\s*")
_LEADING_CONTEXT_WORDS = (
    "熟练掌握",
    "熟练使用",
    "熟悉掌握",
    "掌握",
    "熟悉",
    "了解",
    "精通",
    "负责",
    "参与",
    "具备较强的",
    "具备良好的",
    "具备",
    "具有",
    "能够",
    "可以",
    "能",
    "会",
    "使用",
    "应用",
    "进行",
    "完成",
    "从事",
)
_TRAILING_CONTEXT_WORDS = ("者优先", "优先", "相关经验", "经验", "相关")
