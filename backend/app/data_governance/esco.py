"""ESCO snapshot index and guarded concept linking."""

from __future__ import annotations

import csv
import json
import re
import zipfile
from dataclasses import asdict, dataclass
from os import getenv
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Iterable

from backend.app.domain.errors import InvalidInputError

if TYPE_CHECKING:
    from backend.app.infrastructure.llm.client import ChatClientProtocol
    from backend.app.infrastructure.llm.settings import LLMSettings


DEFAULT_ESCO_VERSION = "v1.2.1"
LSKT_LABELS = {"K", "S", "T", "L"}


@dataclass(frozen=True)
class EscoConcept:
    esco_uri: str
    concept_type: str
    preferred_label: str
    alt_labels: tuple[str, ...]
    description: str | None
    scope_note: str | None
    skill_type: str | None
    reuse_level: str | None
    broader_uris: tuple[str, ...]
    lskt_label: str
    version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EscoLinkResult:
    concept: EscoConcept | None
    linking_status: str
    linking_confidence: float

    @property
    def normalized_name(self) -> str | None:
        return self.concept.preferred_label if self.concept is not None else None


class EscoIndex:
    def __init__(self, concepts: list[EscoConcept], root: Path, version: str) -> None:
        if not concepts:
            raise InvalidInputError("ESCO index must contain at least one concept")
        self.concepts = concepts
        self.root = root
        self.version = version
        self.by_uri = {concept.esco_uri: concept for concept in concepts}
        self._search_rows = [(concept, _search_text(concept)) for concept in concepts]

    @classmethod
    def from_env(cls) -> "EscoIndex":
        return cls.from_root(
            Path(getenv("ESCO_INDEX_ROOT", "data/esco")),
            version=getenv("ESCO_VERSION", DEFAULT_ESCO_VERSION).strip() or DEFAULT_ESCO_VERSION,
        )

    @classmethod
    def from_root(cls, root: str | Path, version: str = DEFAULT_ESCO_VERSION) -> "EscoIndex":
        index_root = Path(root)
        concepts_path = index_root / "index" / "concepts.jsonl"
        if not concepts_path.exists():
            raise InvalidInputError(
                f"ESCO index was not found at {concepts_path}. "
                "Build it from the official ESCO CSV snapshot before starting the service."
            )
        concepts = [
            _concept_from_dict(json.loads(line))
            for line in concepts_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return cls(concepts, index_root, version)

    def search(self, query: str, top_k: int = 8) -> list[EscoConcept]:
        query_text = _normalize(query)
        if not query_text:
            return []
        tokens = {token for token in re.split(r"[^a-z0-9+#.]+", query_text) if token}
        scored: list[tuple[float, str, EscoConcept]] = []
        for concept, searchable in self._search_rows:
            score = 0.0
            if query_text == concept.preferred_label.casefold():
                score += 20
            if query_text in searchable:
                score += 10
            score += sum(1 for token in tokens if token in searchable)
            if score > 0:
                scored.append((score, concept.preferred_label, concept))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [concept for _, _, concept in scored[:top_k]]

    def search_many(self, queries: Iterable[str], top_k: int = 8) -> list[EscoConcept]:
        by_uri: dict[str, EscoConcept] = {}
        for query in queries:
            for concept in self.search(query, top_k=top_k):
                by_uri.setdefault(concept.esco_uri, concept)
        return list(by_uri.values())[:top_k]

    def exact_label_match(self, value: str) -> EscoConcept | None:
        value_key = _normalize(value)
        if not value_key:
            return None
        for concept in self.concepts:
            labels = [concept.preferred_label, *concept.alt_labels]
            if any(_normalize(label) == value_key for label in labels):
                return concept
        return None


class EscoLinker:
    def __init__(
        self,
        index: EscoIndex,
        chat_client: ChatClientProtocol | None = None,
        settings: LLMSettings | None = None,
        min_confidence: float | None = None,
    ) -> None:
        self.index = index
        self.settings = settings or _llm_settings_from_env()
        self.chat_client = chat_client or _openai_chat_client(self.settings)
        self.min_confidence = min_confidence if min_confidence is not None else _env_float("ESCO_LINK_MIN_CONFIDENCE", 0.55)

    def link(self, surface: str, context: str, lskt_label: str) -> EscoLinkResult:
        exact = self.index.exact_label_match(surface)
        if exact is not None:
            return EscoLinkResult(exact, "linked", 1.0)

        queries = self._expand_queries(surface, context, lskt_label)
        candidates = self.index.search_many(queries, top_k=8)
        if not candidates:
            return EscoLinkResult(None, "unmapped", 0.0)
        choice = self._choose_candidate(surface, context, lskt_label, candidates)
        if choice is None:
            return EscoLinkResult(None, "unmapped", 0.0)
        concept, confidence = choice
        if confidence < self.min_confidence:
            return EscoLinkResult(None, "unmapped", confidence)
        return EscoLinkResult(concept, "linked", confidence)

    def _expand_queries(self, surface: str, context: str, lskt_label: str) -> list[str]:
        if _mostly_ascii(surface):
            return [surface]
        try:
            content = self.chat_client.chat(_query_messages(surface, context, lskt_label))
            payload = _load_json_object(content, expected_keys=("queries",))
        except Exception:
            return [surface]
        queries = payload.get("queries")
        if not isinstance(queries, list):
            return [surface]
        cleaned = [_clean_text(query) for query in queries if _clean_text(query)]
        return cleaned[:5] or [surface]

    def _choose_candidate(
        self,
        surface: str,
        context: str,
        lskt_label: str,
        candidates: list[EscoConcept],
    ) -> tuple[EscoConcept, float] | None:
        allowed = {candidate.esco_uri: candidate for candidate in candidates}
        try:
            content = self.chat_client.chat(_choice_messages(surface, context, lskt_label, candidates))
            payload = _load_json_object(content, expected_keys=("esco_uri",))
        except Exception:
            return None
        uri = _clean_text(payload.get("esco_uri"))
        if uri not in allowed:
            return None
        return allowed[uri], _confidence(payload.get("confidence"))


def build_esco_index(source: str | Path, output_root: str | Path, version: str = DEFAULT_ESCO_VERSION) -> dict[str, Any]:
    source_path = Path(source)
    output = Path(output_root)
    with TemporaryDirectory() as temp_dir:
        input_root = _prepare_source(source_path, Path(temp_dir))
        concepts = _read_official_csv_snapshot(input_root, version)
    index_dir = output / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    concepts_path = index_dir / "concepts.jsonl"
    concepts_path.write_text(
        "\n".join(json.dumps(concept.to_dict(), ensure_ascii=False) for concept in concepts) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "esco-index/v1",
        "version": version,
        "concept_count": len(concepts),
        "source": str(source_path),
        "concepts_path": str(concepts_path),
    }
    (index_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _prepare_source(source: Path, temp_root: Path) -> Path:
    if source.is_dir():
        return source
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            archive.extractall(temp_root)
        return temp_root
    raise InvalidInputError("ESCO source must be a directory or a .zip file")


def _read_official_csv_snapshot(root: Path, version: str) -> list[EscoConcept]:
    skills_csv = _find_csv(root, "skills")
    if skills_csv is None:
        raise InvalidInputError("Could not find an ESCO skills CSV file in the provided source")
    broader = _read_broader_relations(root)
    rows = _read_csv_rows(skills_csv)
    concepts: list[EscoConcept] = []
    for row in rows:
        uri = _first(row, "conceptUri", "concept_uri", "uri")
        preferred = _first(row, "preferredLabel", "preferred_label", "preferred term")
        if not uri or not preferred:
            continue
        skill_type = _first(row, "skillType", "skill_type", "type")
        concept = EscoConcept(
            esco_uri=uri,
            concept_type="skill",
            preferred_label=preferred,
            alt_labels=tuple(_split_labels(_first(row, "altLabels", "alt_labels", "alternativeLabel"))),
            description=_none_if_empty(_first(row, "description")),
            scope_note=_none_if_empty(_first(row, "scopeNote", "scope_note")),
            skill_type=_none_if_empty(skill_type),
            reuse_level=_none_if_empty(_first(row, "reuseLevel", "reuse_level")),
            broader_uris=tuple(broader.get(uri, [])),
            lskt_label=_lskt_from_skill_type(skill_type),
            version=version,
        )
        concepts.append(concept)
    if not concepts:
        raise InvalidInputError("ESCO skills CSV did not produce any concepts")
    return concepts


def _read_broader_relations(root: Path) -> dict[str, list[str]]:
    relation_csv = _find_csv(root, "broaderRelationsSkillPillar")
    if relation_csv is None:
        return {}
    relations: dict[str, list[str]] = {}
    for row in _read_csv_rows(relation_csv):
        source = _first(row, "conceptUri", "concept_uri", "child", "source")
        broader = _first(row, "broaderUri", "broader_uri", "parent", "target")
        if source and broader:
            relations.setdefault(source, []).append(broader)
    return relations


def _find_csv(root: Path, name_fragment: str) -> Path | None:
    fragment = name_fragment.casefold()
    candidates = [path for path in root.rglob("*.csv") if fragment in path.name.casefold()]
    if candidates:
        return sorted(candidates, key=lambda path: len(path.name))[0]
    return None


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    return list(csv.DictReader(text.splitlines(), dialect=dialect))


def _concept_from_dict(item: dict[str, Any]) -> EscoConcept:
    return EscoConcept(
        esco_uri=_clean_text(item.get("esco_uri")),
        concept_type=_clean_text(item.get("concept_type")) or "skill",
        preferred_label=_clean_text(item.get("preferred_label")),
        alt_labels=tuple(_clean_text(label) for label in item.get("alt_labels", []) if _clean_text(label)),
        description=_none_if_empty(item.get("description")),
        scope_note=_none_if_empty(item.get("scope_note")),
        skill_type=_none_if_empty(item.get("skill_type")),
        reuse_level=_none_if_empty(item.get("reuse_level")),
        broader_uris=tuple(_clean_text(uri) for uri in item.get("broader_uris", []) if _clean_text(uri)),
        lskt_label=_label_or_default(item.get("lskt_label")),
        version=_clean_text(item.get("version")) or DEFAULT_ESCO_VERSION,
    )


def _query_messages(surface: str, context: str, lskt_label: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Translate a Chinese competency span into concise English ESCO search queries. Output JSON only."},
        {
            "role": "user",
            "content": (
                '{"queries":["..."]}\n'
                f"span: {surface}\n"
                f"lskt_label: {lskt_label}\n"
                f"context: {context[:600]}"
            ),
        },
    ]


def _choice_messages(surface: str, context: str, lskt_label: str, candidates: list[EscoConcept]) -> list[dict[str, str]]:
    candidate_payload = [
        {
            "esco_uri": candidate.esco_uri,
            "preferred_label": candidate.preferred_label,
            "description": candidate.description or "",
            "lskt_label": candidate.lskt_label,
        }
        for candidate in candidates
    ]
    return [
        {
            "role": "system",
            "content": (
                "Choose the single best ESCO concept for the Chinese competency span. "
                "You must choose only one esco_uri from candidates or return an empty esco_uri. Output JSON only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "span": surface,
                    "lskt_label": lskt_label,
                    "context": context[:800],
                    "candidates": candidate_payload,
                    "output_schema": {"esco_uri": "", "confidence": 0.0},
                },
                ensure_ascii=False,
            ),
        },
    ]


def _search_text(concept: EscoConcept) -> str:
    parts = [
        concept.preferred_label,
        *concept.alt_labels,
        concept.description or "",
        concept.scope_note or "",
        concept.skill_type or "",
    ]
    return _normalize(" ".join(parts))


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _mostly_ascii(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return True
    return sum(1 for char in letters if ord(char) < 128) / len(letters) >= 0.8


def _first(row: dict[str, str], *names: str) -> str:
    lookup = {key.casefold(): value for key, value in row.items()}
    for name in names:
        value = lookup.get(name.casefold())
        if value is not None and value.strip():
            return value.strip()
    return ""


def _split_labels(value: str) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"\n|,|;", value) if part.strip()]


def _lskt_from_skill_type(value: str) -> str:
    key = value.strip().casefold()
    if "language" in key:
        return "L"
    if "knowledge" in key:
        return "K"
    if "transversal" in key:
        return "T"
    return "S"


def _label_or_default(value: object) -> str:
    text = _clean_text(value).upper()
    return text if text in LSKT_LABELS else "S"


def _none_if_empty(value: object) -> str | None:
    text = _clean_text(value)
    return text or None


def _clean_text(value: object) -> str:
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


def _confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(score, 1.0))


def _env_float(name: str, default: float) -> float:
    raw_value = getenv(name)
    if not raw_value:
        return default
    try:
        return max(0.0, min(float(raw_value), 1.0))
    except ValueError:
        return default


def _llm_settings_from_env() -> Any:
    from backend.app.infrastructure.llm.settings import LLMSettings

    return LLMSettings.from_env()


def _openai_chat_client(settings: Any) -> Any:
    from backend.app.infrastructure.llm.client import OpenAICompatibleChatClient

    return OpenAICompatibleChatClient(settings)
