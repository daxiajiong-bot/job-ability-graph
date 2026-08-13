from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

import scripts.validate_handoff as validator


README = """# jobtrend 交接包

## 3 分钟安装和离线演示

样例清单位于 `source/data/samples/sources.yaml`。
图谱增量输出为 `kg_link_delta.jsonl`。
包含真实数据的外层包仅限 `INTERNAL-ONLY` 组内使用。
"""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_valid_handoff(root: Path) -> Path:
    root.mkdir()
    required_contract = set(validator.REQUIRED) - {"LOCAL_VALIDATION.json"}

    for name in sorted(required_contract - {"manifest.json", "README.md"}):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n", encoding="utf-8")
    (root / "README.md").write_text(README, encoding="utf-8")
    wheel = root / "dist" / "trend_discovery_service-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True)
    wheel.write_bytes(b"placeholder wheel")

    artifact_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    )
    manifest = {
        "schema_version": "jobtrend_run_manifest_v1",
        "notes": {
            "handoff_contract": "jobtrend_handoff_v1",
            "required_files": sorted(required_contract),
        },
        "output_artifacts": [
            {"path": relative, "sha256": _sha256(root / relative)}
            for relative in artifact_paths
        ],
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    local_validation = {
        "schema_version": "jobtrend_local_validation_v1",
        "valid": True,
        "required_files": sorted(required_contract),
        "manifest_sha256": _sha256(manifest_path),
    }
    (root / "LOCAL_VALIDATION.json").write_text(
        json.dumps(local_validation, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return root


@pytest.fixture
def handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _write_valid_handoff(tmp_path / "handoff")

    def fail_if_execution_starts(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight failure must not execute venv, pip, tests, or demo")

    monkeypatch.setattr(validator, "_run", fail_if_execution_starts)
    return root


def test_rejects_incomplete_readme_before_execution(handoff: Path) -> None:
    (handoff / "README.md").write_text("# incomplete\n", encoding="utf-8")

    with pytest.raises(ValueError, match="README is incomplete"):
        validator.validate(handoff)


def test_rejects_tampered_artifact_hash_before_execution(handoff: Path) -> None:
    (handoff / "evidence.jsonl").write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="artifact hash mismatch: evidence.jsonl"):
        validator.validate(handoff)


def test_rejects_unregistered_file_before_execution(handoff: Path) -> None:
    (handoff / "not-in-manifest.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"unregistered=\['not-in-manifest.txt'\]"):
        validator.validate(handoff)


def test_rejects_stale_local_validation_manifest_hash_before_execution(
    handoff: Path,
) -> None:
    local_path = handoff / "LOCAL_VALIDATION.json"
    local = json.loads(local_path.read_text(encoding="utf-8"))
    local["manifest_sha256"] = "0" * 64
    local_path.write_text(json.dumps(local), encoding="utf-8")

    with pytest.raises(ValueError, match="LOCAL_VALIDATION manifest_sha256 mismatch"):
        validator.validate(handoff)


@pytest.mark.parametrize("unsafe_path", ["../escape", "/absolute", r"source\\escape"])
def test_rejects_unsafe_manifest_artifact_path_before_execution(
    handoff: Path, unsafe_path: str
) -> None:
    manifest_path = handoff / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_artifacts"][0]["path"] = unsafe_path
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe artifact path"):
        validator.validate(handoff)


def test_rejects_invalid_archive_sidecar_before_extract_or_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _write_valid_handoff(tmp_path / "handoff")
    archive_path = tmp_path / "handoff.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(root, arcname=root.name)
    Path(f"{archive_path}.sha256").write_text(
        f"{'0' * 64}  {archive_path.name}\n", encoding="ascii"
    )

    def fail_if_archive_is_opened(*args: object, **kwargs: object) -> None:
        raise AssertionError("invalid sidecar must fail before archive extraction")

    monkeypatch.setattr(tarfile, "open", fail_if_archive_is_opened)
    monkeypatch.setattr(validator, "_run", fail_if_archive_is_opened)

    with pytest.raises(ValueError, match="archive SHA-256 sidecar is invalid"):
        validator.validate(archive_path)


def test_archive_rejects_symlink_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "symlink.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        directory = tarfile.TarInfo("handoff")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        link = tarfile.TarInfo("handoff/README.md")
        link.type = tarfile.SYMTYPE
        link.linkname = "elsewhere"
        archive.addfile(link, io.BytesIO())

    def fail_if_execution_starts(*args: object, **kwargs: object) -> None:
        raise AssertionError("symlink preflight failure must not execute commands")

    monkeypatch.setattr(validator, "_run", fail_if_execution_starts)

    with pytest.raises((tarfile.TarError, ValueError, FileNotFoundError)):
        validator.validate(archive_path)
