#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


REQUIRED = (
    "README.md",
    "external_documents.jsonl",
    "evidence.jsonl",
    "trend_features.jsonl",
    "emerging_roles.jsonl",
    "job_skill_updates.jsonl",
    "review_queue.csv",
    "kg_link_delta.jsonl",
    "manifest.json",
    "LOCAL_VALIDATION.json",
)


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def validate(root_or_archive: Path) -> dict[str, object]:
    archive_digest: str | None = None
    sidecar_checked = False
    if root_or_archive.is_file():
        archive_digest = hashlib.sha256(root_or_archive.read_bytes()).hexdigest()
        sidecar = Path(f"{root_or_archive}.sha256")
        if sidecar.exists():
            fields = sidecar.read_text(encoding="ascii").strip().split(maxsplit=1)
            recorded_name = fields[1].lstrip("*") if len(fields) == 2 else ""
            if (
                len(fields) != 2
                or not re.fullmatch(r"[0-9a-f]{64}", fields[0])
                or fields[0] != archive_digest
                or recorded_name != root_or_archive.name
            ):
                raise ValueError("archive SHA-256 sidecar is invalid")
            sidecar_checked = True

    with tempfile.TemporaryDirectory(prefix="jobtrend-handoff-validate-") as temporary:
        temp = Path(temporary)
        if root_or_archive.is_file():
            with tarfile.open(root_or_archive, "r:gz") as archive:
                archive.extractall(temp, filter="data")
            roots = [item for item in temp.iterdir() if item.is_dir()]
            if len(roots) != 1:
                raise ValueError("archive must contain exactly one top-level directory")
            root = roots[0]
        else:
            root = root_or_archive.resolve()

        for candidate in root.rglob("*"):
            if candidate.is_symlink():
                raise ValueError(f"handoff contains a symlink: {candidate.relative_to(root)}")

        missing = [name for name in REQUIRED if not (root / name).is_file()]
        if missing:
            raise FileNotFoundError(f"handoff is missing required files: {missing}")
        wheel_paths = sorted((root / "dist").glob("*.whl"))
        if len(wheel_paths) != 1:
            raise ValueError("handoff must contain exactly one wheel under dist/")

        readme = (root / "README.md").read_text(encoding="utf-8")
        required_readme_terms = (
            "3 分钟安装和离线演示",
            "source/data/samples/sources.yaml",
            "kg_link_delta.jsonl",
            "INTERNAL-ONLY",
        )
        missing_readme_terms = [term for term in required_readme_terms if term not in readme]
        if missing_readme_terms:
            raise ValueError(f"handoff README is incomplete: {missing_readme_terms}")

        manifest_path = root / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != "jobtrend_run_manifest_v1":
            raise ValueError("handoff manifest schema_version is invalid")
        notes = manifest.get("notes") or {}
        if notes.get("handoff_contract") != "jobtrend_handoff_v1":
            raise ValueError("manifest handoff_contract is invalid")
        required_contract = set(REQUIRED) - {"LOCAL_VALIDATION.json"}
        if set(notes.get("required_files") or []) != required_contract:
            raise ValueError("manifest required_files do not match the handoff contract")

        artifact_rows = manifest.get("output_artifacts") or []
        raw_artifact_paths = [str(item.get("path") or "") for item in artifact_rows]
        if len(raw_artifact_paths) != len(set(raw_artifact_paths)):
            raise ValueError("manifest contains duplicate artifact paths")
        artifact_hashes_checked = 0
        artifact_paths: set[str] = set()
        for artifact, raw_relative in zip(artifact_rows, raw_artifact_paths, strict=True):
            relative = PurePosixPath(raw_relative)
            if (
                not raw_relative
                or "\\" in raw_relative
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                raise ValueError(f"manifest contains unsafe artifact path: {raw_relative}")
            artifact_path = root.joinpath(*relative.parts)
            if not artifact_path.is_file():
                raise FileNotFoundError(f"manifest artifact is missing: {relative}")
            if artifact_path.is_symlink():
                raise ValueError(f"manifest artifact must not be a symlink: {relative}")
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if digest != artifact.get("sha256"):
                raise ValueError(f"manifest artifact hash mismatch: {relative}")
            artifact_paths.add(relative.as_posix())
            artifact_hashes_checked += 1

        required_artifacts = required_contract - {"manifest.json"}
        if not required_artifacts <= artifact_paths:
            raise ValueError(
                f"manifest omits required artifacts: {sorted(required_artifacts - artifact_paths)}"
            )

        actual_files: set[str] = set()
        for candidate in root.rglob("*"):
            if candidate.is_symlink():
                raise ValueError(f"handoff contains a symlink: {candidate.relative_to(root)}")
            if candidate.is_file():
                actual_files.add(candidate.relative_to(root).as_posix())
        expected_files = artifact_paths | {"manifest.json", "LOCAL_VALIDATION.json"}
        if actual_files != expected_files:
            raise ValueError(
                "handoff file set does not match manifest; "
                f"unregistered={sorted(actual_files - expected_files)}, "
                f"missing={sorted(expected_files - actual_files)}"
            )

        local_validation = json.loads(
            (root / "LOCAL_VALIDATION.json").read_text(encoding="utf-8")
        )
        if (
            local_validation.get("schema_version") != "jobtrend_local_validation_v1"
            or local_validation.get("valid") is not True
        ):
            raise ValueError("LOCAL_VALIDATION is not a valid successful report")
        if set(local_validation.get("required_files") or []) != required_contract:
            raise ValueError("LOCAL_VALIDATION required_files do not match the handoff contract")
        manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        if local_validation.get("manifest_sha256") != manifest_digest:
            raise ValueError("LOCAL_VALIDATION manifest_sha256 mismatch")

        source = root / "source"
        environment = temp / "venv"
        _run([sys.executable, "-m", "venv", str(environment)])
        python = environment / "bin" / "python"
        jobtrend = environment / "bin" / "jobtrend"
        _run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                str(source / "requirements.lock"),
                "pytest>=8,<10",
            ]
        )
        _run([str(python), "-m", "pip", "install", "--no-deps", str(wheel_paths[0])])
        help_result = _run([str(jobtrend), "--help"])
        if "run-all" not in help_result.stdout:
            raise ValueError("installed wheel CLI does not expose run-all")

        test_result = _run([str(python), "-m", "pytest", "-q", "tests"], cwd=source)
        demo_root = temp / "demo"
        demo_root.mkdir()
        config = source / "config" / "default.yaml"
        demo = _run(
            [
                str(jobtrend),
                "--config",
                str(config),
                "run-all",
                "--sources",
                str(source / "data" / "samples" / "sources.yaml"),
                "--warehouse",
                str(demo_root / "warehouse"),
                "--output",
                str(demo_root / "output"),
            ],
            cwd=demo_root,
        )
        payload = json.loads(demo.stdout)
        counts = payload["result"]["analysis"]["counts"]
        if counts["observations"] < 100 or counts["emerging_roles"] < 1:
            raise ValueError(f"offline demo acceptance failed: {counts}")
        test_match = re.search(r"(\d+ passed(?:, \d+ skipped)?)", test_result.stdout)
        return {
            "valid": True,
            "wheel_install": True,
            "cli_smoke": True,
            "readme": True,
            "artifact_hashes_checked": artifact_hashes_checked,
            "sidecar_checked": sidecar_checked,
            "tests": test_match.group(1) if test_match else "completed",
            "offline_demo_counts": counts,
            "archive_sha256": archive_digest,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.handoff), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
