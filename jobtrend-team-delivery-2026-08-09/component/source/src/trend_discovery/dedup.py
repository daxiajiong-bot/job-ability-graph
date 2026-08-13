"""Deterministic exact and near-duplicate grouping.

The functions in this module deliberately return *assignments* instead of a
shortened list of documents.  A duplicated advertisement is still an
observation (and is useful for propagation/source-diversity reporting); the
cluster identifiers only control how downstream counts are de-biased.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .io_utils import sha256_text, stable_id
from .schemas import ExternalDocument


_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"from", "ref", "source", "spm", "track", "tracking_id"}


def _as_document(value: ExternalDocument | Mapping[str, object]) -> ExternalDocument:
    return value if isinstance(value, ExternalDocument) else ExternalDocument.model_validate(value)


def normalize_text(value: str | None) -> str:
    """Normalise text for comparison without changing the stored document."""

    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[\s\u3000]+", " ", value).strip()
    return value


def normalize_title(value: str | None) -> str:
    value = normalize_text(value)
    # Punctuation and common bracketed recruiting decorations are not part of
    # the role name.  Seniority words are intentionally retained.
    value = re.sub(r"[（(][^()（）]{0,24}(?:急聘|双休|福利|招聘|base)[^()（）]{0,24}[)）]", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff+#./]+", "", value)
    return value


def normalize_company(value: str | None) -> str:
    """Conservative company-name key for duplicate blocking."""

    value = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalize_text(value))
    return re.sub(r"(?:股份有限|有限责任|集团有限|有限|股份|集团)?公司$", "", value)


def canonical_url(value: str | None) -> str | None:
    """Return a conservative canonical URL suitable for exact matching."""

    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return normalize_text(value)
    if not parsed.scheme or not parsed.netloc:
        return normalize_text(value)
    host = parsed.hostname.casefold() if parsed.hostname else parsed.netloc.casefold()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return normalize_text(value)
    default_port = 80 if parsed.scheme.casefold() == "http" else 443 if parsed.scheme.casefold() == "https" else None
    if port and port != default_port:
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING_QUERY_KEYS
        and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
    ]
    query.sort()
    return urlunsplit(((parsed.scheme or "https").casefold(), host, path, urlencode(query), ""))


class _DisjointSet:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        # This stable tie break makes results independent of input order.
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root


@dataclass(frozen=True, slots=True)
class DedupAssignment:
    document_id: str
    exact_cluster_id: str
    near_dup_cluster_id: str
    exact_duplicate_of: str | None
    propagation_count: int


@dataclass(frozen=True, slots=True)
class DedupResult:
    """Duplicate assignments plus every original document, in input order."""

    documents: tuple[ExternalDocument, ...]
    assignments: Mapping[str, DedupAssignment]
    exact_clusters: Mapping[str, tuple[str, ...]]
    near_clusters: Mapping[str, tuple[str, ...]]

    def assignment_for(self, document_id: str) -> DedupAssignment:
        return self.assignments[document_id]

    def __iter__(self) -> Iterator[ExternalDocument]:
        return iter(self.documents)

    def __len__(self) -> int:
        return len(self.documents)


def _char_ngrams(value: str, size: int = 3) -> set[str]:
    compact = re.sub(r"\s+", "", normalize_text(value))
    if len(compact) <= size:
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def near_duplicate_similarity(left: ExternalDocument, right: ExternalDocument) -> float:
    """Similarity used by :func:`cluster_documents` (0..1).

    Company is a hard block because otherwise generic advertisements such as
    "Java 开发工程师" from unrelated employers collapse into one observation.
    Region is a soft constraint: an empty region never creates a match, while
    two explicit and different regions substantially lower the score.
    """

    left_company, right_company = normalize_company(left.company), normalize_company(right.company)
    if not left_company or not right_company or left_company != right_company:
        return 0.0
    left_title, right_title = normalize_title(left.title), normalize_title(right.title)
    title_score = SequenceMatcher(None, left_title, right_title, autojunk=False).ratio()
    if title_score < 0.70:
        return 0.0
    left_region, right_region = normalize_text(left.region), normalize_text(right.region)
    if left_region and right_region:
        region_score = 1.0 if left_region == right_region else SequenceMatcher(
            None, left_region, right_region, autojunk=False
        ).ratio()
    else:
        region_score = 0.5
    text_score = _jaccard(_char_ngrams(left.text), _char_ngrams(right.text))
    return 0.50 * title_score + 0.40 * text_score + 0.10 * region_score


def cluster_documents(
    documents: Sequence[ExternalDocument | Mapping[str, object]],
    *,
    near_threshold: float = 0.86,
) -> DedupResult:
    """Create exact and near-duplicate clusters without dropping observations.

    Exact duplicates are connected when either their canonical URL or their
    raw/content SHA-256 matches.  Near-duplicate comparison occurs between
    exact-cluster representatives and is blocked by normalised company name.
    """

    parsed = tuple(_as_document(document) for document in documents)
    identifiers = [document.document_id for document in parsed]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("document_id values must be unique before duplicate clustering")
    if not 0.0 <= near_threshold <= 1.0:
        raise ValueError("near_threshold must be between 0 and 1")

    by_id = {document.document_id: document for document in parsed}
    exact_sets = _DisjointSet(identifiers)
    seen_keys: dict[str, str] = {}
    for document in sorted(parsed, key=lambda item: item.document_id):
        if document.source_type == "job" and document.company:
            raw_scope = "\x1f".join(
                (
                    normalize_company(document.company),
                    normalize_title(document.title),
                    normalize_text(document.region),
                    document.raw_sha256.casefold(),
                )
            )
            keys = {f"job-sha:{sha256_text(raw_scope)}"}
        else:
            keys = {f"sha:{document.raw_sha256.casefold()}"}
        url = canonical_url(document.uri)
        if url:
            keys.add(f"url:{url}")
        # Some importers hash the whole JSON record rather than its body.  A
        # body key catches exact copies, but for a JD it must include the
        # recruiting entity/title/location.  Many companies reuse boilerplate
        # verbatim, so body-only matching would incorrectly collapse distinct
        # employers into one job.
        if document.text:
            if document.source_type != "job":
                keys.add(f"text:{sha256_text(normalize_text(document.text))}")
            elif document.company:
                scoped_body = "\x1f".join(
                    (
                        normalize_company(document.company),
                        normalize_title(document.title),
                        normalize_text(document.region),
                        normalize_text(document.text),
                    )
                )
                keys.add(f"job-text:{sha256_text(scoped_body)}")
        for key in sorted(keys):
            if key in seen_keys:
                exact_sets.union(document.document_id, seen_keys[key])
            else:
                seen_keys[key] = document.document_id

    exact_members_by_root: dict[str, list[str]] = {}
    for identifier in sorted(identifiers):
        exact_members_by_root.setdefault(exact_sets.find(identifier), []).append(identifier)

    exact_cluster_ids: dict[str, str] = {}
    exact_clusters: dict[str, tuple[str, ...]] = {}
    representatives: dict[str, ExternalDocument] = {}
    for members in exact_members_by_root.values():
        members = sorted(members)
        representative = members[0]
        cluster_id = stable_id("exact", representative)
        exact_clusters[cluster_id] = tuple(members)
        representatives[cluster_id] = by_id[representative]
        for identifier in members:
            exact_cluster_ids[identifier] = cluster_id

    near_sets = _DisjointSet(exact_clusters)
    company_blocks: dict[str, list[str]] = {}
    for cluster_id, document in representatives.items():
        company = normalize_company(document.company)
        if company:
            company_blocks.setdefault(company, []).append(cluster_id)
    for cluster_ids in company_blocks.values():
        cluster_ids = sorted(cluster_ids)
        for index, left_id in enumerate(cluster_ids):
            for right_id in cluster_ids[index + 1 :]:
                if near_duplicate_similarity(representatives[left_id], representatives[right_id]) >= near_threshold:
                    near_sets.union(left_id, right_id)

    near_exact_groups: dict[str, list[str]] = {}
    for cluster_id in sorted(exact_clusters):
        near_exact_groups.setdefault(near_sets.find(cluster_id), []).append(cluster_id)

    near_cluster_ids: dict[str, str] = {}
    near_clusters: dict[str, tuple[str, ...]] = {}
    for exact_group in near_exact_groups.values():
        member_ids = sorted(
            identifier for cluster_id in exact_group for identifier in exact_clusters[cluster_id]
        )
        near_cluster_id = stable_id("near", member_ids[0])
        near_clusters[near_cluster_id] = tuple(member_ids)
        for identifier in member_ids:
            near_cluster_ids[identifier] = near_cluster_id

    assignments: dict[str, DedupAssignment] = {}
    for document in parsed:
        exact_id = exact_cluster_ids[document.document_id]
        exact_members = exact_clusters[exact_id]
        near_id = near_cluster_ids[document.document_id]
        assignments[document.document_id] = DedupAssignment(
            document_id=document.document_id,
            exact_cluster_id=exact_id,
            near_dup_cluster_id=near_id,
            exact_duplicate_of=exact_members[0] if document.document_id != exact_members[0] else None,
            propagation_count=len(near_clusters[near_id]),
        )

    return DedupResult(
        documents=parsed,
        assignments=assignments,
        exact_clusters=dict(sorted(exact_clusters.items())),
        near_clusters=dict(sorted(near_clusters.items())),
    )


__all__ = [
    "DedupAssignment",
    "DedupResult",
    "canonical_url",
    "cluster_documents",
    "near_duplicate_similarity",
    "normalize_company",
    "normalize_text",
    "normalize_title",
]
