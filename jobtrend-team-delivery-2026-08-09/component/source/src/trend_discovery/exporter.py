"""Build a validated, credential-free, reproducible handoff bundle."""

from __future__ import annotations

import csv
import gzip
import importlib.resources
import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from .io_utils import (
    model_json_schema,
    read_jsonl,
    sha256_file,
    sha256_text,
    write_json,
)
from .review import REVIEW_COLUMNS
from .schemas import (
    ArtifactInfo,
    EmergingRole,
    Evidence,
    ExternalDocument,
    JobSkillUpdate,
    KGLinkDelta,
    RunManifest,
    SourceManifest,
    TrendFeature,
)


REQUIRED_DATA_FILES = (
    "external_documents.jsonl",
    "evidence.jsonl",
    "trend_features.jsonl",
    "emerging_roles.jsonl",
    "job_skill_updates.jsonl",
    "review_queue.csv",
    "kg_link_delta.jsonl",
)
REQUIRED_HANDOFF_FILES = ("README.md",) + REQUIRED_DATA_FILES + ("manifest.json",)

_JSONL_MODELS: dict[str, type[BaseModel]] = {
    "external_documents.jsonl": ExternalDocument,
    "evidence.jsonl": Evidence,
    "trend_features.jsonl": TrendFeature,
    "emerging_roles.jsonl": EmergingRole,
    "job_skill_updates.jsonl": JobSkillUpdate,
    "kg_link_delta.jsonl": KGLinkDelta,
}
_WEIGHT_SUFFIXES = {
    ".ckpt",
    ".gguf",
    ".h5",
    ".onnx",
    ".pb",
    ".pt",
    ".pth",
    ".safetensors",
}
_IGNORED_SOURCE_NAMES = {
    ".git",
    ".coverage",
    ".mypy_cache",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "build",
    "dist",
    "htmlcov",
    # Runtime state is represented by the seven audited public artifacts and
    # must not leak into the source snapshot as duplicate databases/caches.
    "warehouse",
    "qdrant",
    # Real evaluation snapshots keep source-reference-only full text and raw
    # responses under a directory named ``private``.  Git ignore rules do not
    # protect an explicit source-tree copy, so the exporter must enforce this
    # boundary itself.
    "private",
    # Completed evaluation annotations may contain necessary source excerpts
    # and blind-test answers.  They require a separate, explicit rights review
    # instead of being swept into the general handoff source snapshot.
    "annotations",
}
_LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)"
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:authorization\s*:\s*bearer)\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"(?i)\b(?:DASHSCOPE_API_KEY|api[_-]?key)\b\s*[=:]\s*[\"']?"
        r"(?!\$\{|<|YOUR_|REDACTED|NONE\b|NULL\b)[A-Za-z0-9._-]{12,}"
    ),
)


class BundleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handoff_dir: str
    archive_path: str
    archive_sha256: str
    checksum_path: str
    artifact_count: int


def _safe_archive_name(value: str) -> None:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe archive path {value!r}")


def _scan_text(text: str, label: str) -> None:
    if _LOCAL_PATH_PATTERN.search(text):
        raise ValueError(f"{label}: local user absolute path detected")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise ValueError(f"{label}: possible API credential detected")


def _is_probably_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def assert_safe_for_handoff(path: str | Path) -> None:
    """Reject credentials, workstation paths, unsafe archives, and model weights."""

    source = Path(path)
    if source.name == ".env" or source.name.startswith(".env."):
        raise ValueError(f"{source}: environment/credential file is not allowed")
    if source.suffix.lower() in _WEIGHT_SUFFIXES:
        raise ValueError(f"{source}: model weight files are not allowed")
    if not source.is_file():
        raise FileNotFoundError(source)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                _safe_archive_name(info.filename)
                if Path(info.filename).suffix.lower() in _WEIGHT_SUFFIXES:
                    raise ValueError(f"{source}!{info.filename}: model weight is not allowed")
                if info.is_dir() or info.file_size > 5 * 1024 * 1024:
                    continue
                data = archive.read(info)
                if _is_probably_text(data):
                    _scan_text(data.decode("utf-8"), f"{source}!{info.filename}")
        return
    # The handoff artifacts are text-sized.  For optional large binaries, avoid
    # loading them into memory after their file type has already been checked.
    if source.stat().st_size <= 10 * 1024 * 1024:
        data = source.read_bytes()
        if _is_probably_text(data):
            _scan_text(data.decode("utf-8"), str(source))


def _count_and_validate(path: Path, model: type[BaseModel]) -> int:
    count = 0
    for line_number, row in enumerate(read_jsonl(path), start=1):
        try:
            model.model_validate(row)
        except Exception as exc:
            raise ValueError(f"{path}:{line_number}: schema validation failed: {exc}") from exc
        count += 1
    return count


def _count_review_csv(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: CSV header is missing")
        missing = sorted(set(REVIEW_COLUMNS) - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path}: review CSV missing columns: {missing}")
        return sum(1 for _ in reader)


def _assert_artifact_redistribution_policy(root: Path) -> None:
    """Reject unredacted reference-only source text in a public handoff.

    A source being publicly reachable is not redistribution permission.  A
    reference-only document may be handed off only after its full ``text`` is
    removed.  At most three short, locatable evidence excerpts are allowed for
    reviewer verification; broader sharing requires a separate licensed data
    package outside this exporter.
    """

    documents = {
        item.document_id: item
        for item in (
            ExternalDocument.model_validate(row)
            for row in read_jsonl(root / "external_documents.jsonl")
        )
    }
    restricted = {
        document_id: item
        for document_id, item in documents.items()
        if (item.license or "").casefold() == "source-reference-only"
    }
    full_text_ids = sorted(
        document_id for document_id, item in restricted.items() if item.text.strip()
    )
    if full_text_ids:
        preview = ", ".join(full_text_ids[:3])
        raise ValueError(
            "source-reference-only document text is not allowed in a public handoff; "
            f"redact or use a private evaluation package first: {preview}"
        )

    evidence_by_document: dict[str, list[Evidence]] = {}
    for row in read_jsonl(root / "evidence.jsonl"):
        item = Evidence.model_validate(row)
        if item.document_id in restricted:
            evidence_by_document.setdefault(item.document_id, []).append(item)
    excerpt_violations: list[str] = []
    for document_id, items in evidence_by_document.items():
        locatable = all(
            item.page is not None
            or (item.char_start is not None and item.char_end is not None)
            or bool(item.section)
            for item in items
        )
        if (
            len(items) > 3
            or any(len(item.text) > 300 for item in items)
            or sum(len(item.text) for item in items) > 900
            or not locatable
        ):
            excerpt_violations.append(document_id)
    if excerpt_violations:
        preview = ", ".join(sorted(excerpt_violations)[:3])
        raise ValueError(
            "source-reference-only evidence exceeds the reviewed excerpt allowance "
            f"(3 excerpts, 300 characters each, with a locator): {preview}"
        )


def _write_schemas(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    schemas: Sequence[tuple[str, type[BaseModel]]] = (
        ("source_manifest_v1.schema.json", SourceManifest),
        ("external_document_v1.schema.json", ExternalDocument),
        ("evidence_v1.schema.json", Evidence),
        ("trend_feature_v1.schema.json", TrendFeature),
        ("emerging_role_v1.schema.json", EmergingRole),
        ("job_skill_update_v1.schema.json", JobSkillUpdate),
        ("trend_kg_delta_v1.schema.json", KGLinkDelta),
        ("jobtrend_run_manifest_v1.schema.json", RunManifest),
    )
    paths: list[Path] = []
    for name, model in schemas:
        path = directory / name
        write_json(path, model_json_schema(model))
        paths.append(path)
    review_schema = directory / "review_queue_v1.schema.json"
    write_json(
        review_schema,
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "jobtrend review queue CSV",
            "type": "object",
            "properties": {column: {"type": "string"} for column in REVIEW_COLUMNS},
            "required": REVIEW_COLUMNS,
            "additionalProperties": False,
        },
    )
    paths.append(review_schema)
    return paths


def _write_handoff_readme(directory: Path, counts: Mapping[str, int]) -> Path:
    template = (
        importlib.resources.files("trend_discovery")
        .joinpath("handoff_readme.md")
        .read_text(encoding="utf-8")
    )
    documents = list(read_jsonl(directory / "external_documents.jsonl"))
    licenses = {(str(item.get("license") or "unknown")) for item in documents}
    dataset_label = (
        "可再分发合成演示输出"
        if licenses and licenses <= {"synthetic-test-data"}
        else "经权利门禁检查的分析输出；详情以 manifest.json 为准"
    )
    replacements = {
        "{{DATASET_LABEL}}": dataset_label,
        "{{DOCUMENT_COUNT}}": str(counts.get("external_documents.jsonl", 0)),
        "{{EVIDENCE_COUNT}}": str(counts.get("evidence.jsonl", 0)),
        "{{TREND_COUNT}}": str(counts.get("trend_features.jsonl", 0)),
        "{{ROLE_COUNT}}": str(counts.get("emerging_roles.jsonl", 0)),
        "{{UPDATE_COUNT}}": str(counts.get("job_skill_updates.jsonl", 0)),
        "{{DELTA_COUNT}}": str(counts.get("kg_link_delta.jsonl", 0)),
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    if "{{" in template or "}}" in template:
        raise ValueError("handoff README contains unresolved template markers")
    path = directory / "README.md"
    path.write_text(template, encoding="utf-8")
    assert_safe_for_handoff(path)
    return path


def _copy_file(source: Path, destination: Path) -> None:
    assert_safe_for_handoff(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _copy_source_selection(source: Path, destination_root: Path) -> list[Path]:
    copied: list[Path] = []
    policy_parts = source.parts
    # macOS exposes /var through /private/var.  The system prefix is not an
    # evaluation privacy marker; any later component named private still is.
    if policy_parts[:3] in {("/", "private", "var"), ("/", "private", "tmp")}:
        policy_parts = policy_parts[3:]
    sensitive_parts = {"private", "annotations"} & set(policy_parts)
    if sensitive_parts:
        names = ", ".join(sorted(sensitive_parts))
        raise ValueError(f"sensitive source selection is not allowed ({names}): {source}")
    if source.is_file():
        destination = destination_root / source.name
        if destination.exists():
            raise ValueError(f"source selection name collision: {destination.name}")
        _copy_file(source, destination)
        return [destination]
    if not source.is_dir():
        raise FileNotFoundError(source)
    base = destination_root / source.name
    if base.exists():
        raise ValueError(f"source selection name collision: {base.name}")
    for candidate in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(source)
        if any(
            part in _IGNORED_SOURCE_NAMES or part.endswith(".egg-info")
            for part in relative.parts
        ):
            continue
        if candidate.is_symlink():
            raise ValueError(f"symlinks are not allowed in handoff source: {candidate}")
        if candidate.is_file():
            destination = base / relative
            _copy_file(candidate, destination)
            copied.append(destination)
    return copied


def _existing_manifest(path: Path) -> RunManifest | None:
    if not path.is_file():
        return None
    try:
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        # Never propagate arbitrary fields from a non-conforming input manifest.
        return None


def _tarinfo_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if info.isdir():
        info.mode = 0o755
    else:
        info.mode = 0o644
    return info


def _create_deterministic_tar_gz(source_dir: Path, archive_path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{archive_path.name}.", dir=archive_path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with temporary.open("wb") as raw_handle:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as gzip_handle:
                with tarfile.open(fileobj=gzip_handle, mode="w") as archive:
                    archive.add(
                        source_dir,
                        arcname=source_dir.name,
                        recursive=True,
                        filter=_tarinfo_filter,
                    )
        os.replace(temporary, archive_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_handoff_bundle(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    bundle_name: str = "jobtrend-handoff",
    run_id: str | None = None,
    created_at: datetime | None = None,
    config_sha256: str | None = None,
    baseline_graph_fingerprint: str | None = None,
    model_ids: Mapping[str, str] | None = None,
    prompt_versions: Mapping[str, str] | None = None,
    wheel_paths: Iterable[str | Path] = (),
    source_paths: Iterable[str | Path] = (),
    local_validation: Mapping[str, Any] | None = None,
) -> BundleResult:
    """Create the stable handoff directory, tarball, and SHA-256 sidecar.

    ``wheel_paths`` and ``source_paths`` are explicit selection hooks: nothing
    outside the seven public source artifacts is included implicitly.
    """

    if not bundle_name or Path(bundle_name).name != bundle_name or bundle_name in {".", ".."}:
        raise ValueError("bundle_name must be one safe directory name")
    source = Path(source_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    final_dir = output / bundle_name
    archive_path = output / f"{bundle_name}.tar.gz"
    checksum_path = output / f"{bundle_name}.tar.gz.sha256"
    for target in (final_dir, archive_path, checksum_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing handoff output: {target}")
    missing = [name for name in REQUIRED_DATA_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"handoff source is missing required artifacts: {missing}")

    prior = _existing_manifest(source / "manifest.json")
    staging = Path(tempfile.mkdtemp(prefix=f".{bundle_name}.", dir=output)) / bundle_name
    staging.mkdir()
    try:
        counts: dict[str, int] = {}
        artifacts: list[ArtifactInfo] = []
        for name in REQUIRED_DATA_FILES:
            source_path = source / name
            target = staging / name
            _copy_file(source_path, target)
            count = (
                _count_review_csv(target)
                if name == "review_queue.csv"
                else _count_and_validate(target, _JSONL_MODELS[name])
            )
            counts[name] = count
            artifacts.append(
                ArtifactInfo(path=name, sha256=sha256_file(target), records=count)
            )

        _assert_artifact_redistribution_policy(staging)
        readme_path = _write_handoff_readme(staging, counts)
        artifacts.append(
            ArtifactInfo(path="README.md", sha256=sha256_file(readme_path), records=None)
        )

        schema_paths = _write_schemas(staging / "schemas")
        for path in schema_paths:
            relative = path.relative_to(staging).as_posix()
            artifacts.append(ArtifactInfo(path=relative, sha256=sha256_file(path), records=None))

        selected_paths: list[Path] = []
        for raw in source_paths:
            selected_paths.extend(_copy_source_selection(Path(raw), staging / "source"))
        for raw in wheel_paths:
            wheel = Path(raw)
            if wheel.suffix != ".whl":
                raise ValueError(f"wheel selection must end in .whl: {wheel}")
            destination = staging / "dist" / wheel.name
            if destination.exists():
                raise ValueError(f"wheel name collision: {wheel.name}")
            _copy_file(wheel, destination)
            selected_paths.append(destination)
        for path in sorted(selected_paths, key=lambda item: item.relative_to(staging).as_posix()):
            relative = path.relative_to(staging).as_posix()
            artifacts.append(ArtifactInfo(path=relative, sha256=sha256_file(path), records=None))

        effective_run_id = run_id or (prior.run_id if prior else None)
        if not effective_run_id:
            digest_seed = "\n".join(f"{item.path}:{item.sha256}" for item in artifacts)
            effective_run_id = f"handoff-{sha256_text(digest_seed)[:16]}"
        effective_created_at = created_at or (prior.created_at if prior else datetime.now(timezone.utc))
        manifest = RunManifest(
            run_id=effective_run_id,
            created_at=effective_created_at,
            status="completed",
            config_sha256=config_sha256 or (prior.config_sha256 if prior else sha256_text("unspecified")),
            baseline_graph_fingerprint=(
                baseline_graph_fingerprint
                if baseline_graph_fingerprint is not None
                else (prior.baseline_graph_fingerprint if prior else None)
            ),
            input_artifacts=[],
            output_artifacts=artifacts,
            model_ids=dict(model_ids) if model_ids is not None else (prior.model_ids if prior else {}),
            prompt_versions=(
                dict(prompt_versions)
                if prompt_versions is not None
                else (prior.prompt_versions if prior else {})
            ),
            token_usage=prior.token_usage if prior else {},
            estimated_cost_cny=prior.estimated_cost_cny if prior else 0.0,
            counts=counts,
            notes={
                "handoff_contract": "jobtrend_handoff_v1",
                "required_files": list(REQUIRED_HANDOFF_FILES),
                "source_included": bool(selected_paths),
            },
        )
        write_json(staging / "manifest.json", manifest)

        local_validation = {
            "schema_version": "jobtrend_local_validation_v1",
            "valid": True,
            "validated_at": effective_created_at.isoformat(),
            "required_files": list(REQUIRED_HANDOFF_FILES),
            "counts": counts,
            "manifest_sha256": sha256_file(staging / "manifest.json"),
            "checks": dict(local_validation or {}),
        }
        write_json(staging / "LOCAL_VALIDATION.json", local_validation)

        for candidate in sorted(staging.rglob("*"), key=lambda item: item.as_posix()):
            if candidate.is_symlink():
                raise ValueError(f"symlink unexpectedly present in staging: {candidate}")
            if candidate.is_file():
                assert_safe_for_handoff(candidate)
        RunManifest.model_validate_json((staging / "manifest.json").read_text(encoding="utf-8"))

        os.replace(staging, final_dir)
        _create_deterministic_tar_gz(final_dir, archive_path)
        archive_digest = sha256_file(archive_path)
        checksum_path.write_text(f"{archive_digest}  {archive_path.name}\n", encoding="ascii")
        return BundleResult(
            handoff_dir=str(final_dir),
            archive_path=str(archive_path),
            archive_sha256=archive_digest,
            checksum_path=str(checksum_path),
            artifact_count=len(artifacts) + 2,  # manifest and LOCAL_VALIDATION
        )
    except Exception:
        shutil.rmtree(staging.parent, ignore_errors=True)
        raise
    finally:
        # After os.replace, only the empty temporary parent remains.
        if staging.parent.exists():
            try:
                staging.parent.rmdir()
            except OSError:
                pass


# CLI-oriented aliases.
create_handoff_bundle = build_handoff_bundle
export_bundle = build_handoff_bundle


__all__ = [
    "BundleResult",
    "REQUIRED_DATA_FILES",
    "REQUIRED_HANDOFF_FILES",
    "assert_safe_for_handoff",
    "build_handoff_bundle",
    "create_handoff_bundle",
    "export_bundle",
]
