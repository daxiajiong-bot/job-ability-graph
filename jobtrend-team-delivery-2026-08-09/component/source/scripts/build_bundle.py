#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from trend_discovery.exporter import build_handoff_bundle
from trend_discovery.settings import load_config


ROOT = Path(__file__).resolve().parents[1]


def _log(message: str) -> None:
    print(f"[build-bundle] {message}", file=sys.stderr, flush=True)


def _run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {command!r}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def _preflight(wheel: Path) -> dict[str, object]:
    _log("running tests and coverage gate")
    coverage = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=trend_discovery",
            "--cov-report=term",
        ]
    )
    match = re.search(r"(\d+) passed", coverage.stdout)
    with tempfile.TemporaryDirectory(prefix="jobtrend-build-validate-") as temporary:
        temp = Path(temporary)
        venv = temp / "venv"
        _log("creating isolated wheel validation environment")
        _run([sys.executable, "-m", "venv", str(venv)])
        python = venv / "bin" / "python"
        jobtrend = venv / "bin" / "jobtrend"
        _log("installing locked runtime dependencies")
        _run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.lock")])
        _log("installing and smoke-testing wheel")
        _run([str(python), "-m", "pip", "install", "--no-deps", str(wheel)])
        _run([str(jobtrend), "--help"])

        config_payload = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
        config_payload["paths"] = {
            "warehouse": str(temp / "warehouse"),
            "runs": str(temp / "runs"),
            "qdrant": str(temp / "qdrant"),
        }
        config_path = temp / "config.yaml"
        config_path.write_text(
            yaml.safe_dump(config_payload, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        _log("running network-free 120-JD demo from installed wheel")
        demo = _run(
            [
                str(jobtrend),
                "--config",
                str(config_path),
                "run-all",
                "--sources",
                str(ROOT / "data" / "samples" / "sources.yaml"),
                "--output",
                str(temp / "output"),
            ],
            cwd=temp,
        )
        counts = json.loads(demo.stdout)["result"]["analysis"]["counts"]
        if counts["observations"] < 100 or counts["emerging_roles"] < 1 or counts["job_skill_updates"] < 1:
            raise ValueError(f"offline demo acceptance failed: {counts}")
    return {
        "pytest_passed": int(match.group(1)) if match else None,
        "coverage_gate_percent": 60,
        "wheel_install": True,
        "cli_smoke": True,
        "offline_cache_demo": True,
        "offline_demo_counts": counts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output", default=ROOT / "dist", type=Path)
    parser.add_argument("--bundle-name", default="jobtrend-handoff-0.1.0")
    args = parser.parse_args()

    wheel_dir = args.output / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    _log("building wheel")
    _run([sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)])
    wheels = sorted(wheel_dir.glob("trend_discovery_service-*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"expected exactly one wheel, got {wheels}")
    validation = _preflight(wheels[0])
    config = load_config(ROOT / "config" / "default.yaml")
    sources = [
        ROOT / name
        for name in (
            "src",
            "config",
            "schemas",
            "docs",
            "tests",
            "scripts",
            "sources",
            "data",
            "Dockerfile",
            ".dockerignore",
            ".gitignore",
            "pyproject.toml",
            "requirements.lock",
            "README.md",
            "LICENSE",
        )
    ]
    _log("assembling credential-scanned handoff archive")
    result = build_handoff_bundle(
        args.run_dir,
        args.output,
        bundle_name=args.bundle_name,
        config_sha256=config["_sha256"],
        model_ids={key: str(value) for key, value in config["models"].items() if key.endswith("model")},
        prompt_versions={"extraction": "jobtrend_extract_v1", "role_definition": "jobtrend_role_definition_v1"},
        wheel_paths=wheels,
        source_paths=sources,
        local_validation=validation,
    )
    print(json.dumps({**result.model_dump(), "validation": validation}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
