from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from trend_discovery.ingest import load_source_manifest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPOSITORY_ROOT / "sources" / "authoritative_sources.yaml"


def test_authoritative_source_manifest_is_strict_and_balanced() -> None:
    """Keep the checked-in public reference list auditable and conservative."""

    manifest = load_source_manifest(MANIFEST_PATH)
    source_ids = [source.source_id for source in manifest.sources]
    policy_or_standard = [
        source
        for source in manifest.sources
        if source.source_type in {"policy", "occupational_standard"}
    ]
    reports = [source for source in manifest.sources if source.source_type == "industry_report"]

    assert manifest.schema_version == "source_manifest_v1"
    assert len(manifest.sources) == 20
    assert len(source_ids) == len(set(source_ids))
    assert len(policy_or_standard) == 10
    assert len(reports) == 10
    assert all(source.enabled is False for source in manifest.sources)
    assert all("ictp.caict.ac.cn" not in source.input for source in reports)

    for source in manifest.sources:
        rights = source.metadata["rights"]
        assert rights["redistribution_allowed"] is False
        assert rights["fulltext_in_handoff"] is False
        assert rights["allowed_output"] == "metadata_hash_and_necessary_evidence_excerpt_only"
        assert rights["terms_review_required"] is True


def test_authoritative_source_manifest_rejects_unknown_source_fields(tmp_path: Path) -> None:
    """The checked-in list is parsed with the same extra-forbid contract as input."""

    raw = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    raw["sources"][0]["unreviewed_field"] = "must-not-be-accepted"
    invalid = tmp_path / "authoritative_sources.invalid.yaml"
    invalid.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValidationError, match="unreviewed_field"):
        load_source_manifest(invalid)
