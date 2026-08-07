from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import load_config
from .evaluation import evaluate_trained, run_baselines
from .io_utils import write_json
from .mining import mine_negatives
from .model_registry import download_models
from .preflight import run_preflight
from .provenance import collect_provenance
from .training import train


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--limit", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jdmatch",
        description="JD/resume embedding and dual-encoder training pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download-models")
    _common(download)

    preflight = subparsers.add_parser("preflight")
    _common(preflight)
    preflight.add_argument("--skip-training-step", action="store_true")

    baseline = subparsers.add_parser("baseline")
    _common(baseline)

    mining = subparsers.add_parser("mine-negatives")
    _common(mining)

    training = subparsers.add_parser("train")
    _common(training)
    training.add_argument("--resume")
    training.add_argument("--max-steps", type=int)

    evaluation = subparsers.add_parser("evaluate")
    _common(evaluation)
    evaluation.add_argument("--adapter-path", type=Path)

    run_all = subparsers.add_parser("run-all")
    _common(run_all)
    run_all.add_argument("--resume")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "download-models":
        result = download_models(config)
    elif args.command == "preflight":
        result = run_preflight(
            config,
            run_training_step=not args.skip_training_step,
        )
        target = Path(config["paths"]["run_dir"]) / "preflight.json"
        write_json(target, result)
    elif args.command == "baseline":
        result = run_baselines(config, limit=args.limit)
    elif args.command == "mine-negatives":
        result = mine_negatives(config, limit=args.limit)
    elif args.command == "train":
        result = train(
            config,
            resume=args.resume,
            max_steps=args.max_steps,
        )
    elif args.command == "evaluate":
        result = evaluate_trained(
            config,
            adapter_path=args.adapter_path,
            limit=args.limit,
        )
    elif args.command == "run-all":
        preflight = run_preflight(config, run_training_step=True)
        write_json(
            Path(config["paths"]["run_dir"]) / "preflight.json",
            preflight,
        )
        baseline = run_baselines(config, limit=args.limit)
        mining = mine_negatives(config, limit=args.limit)
        training = train(config, resume=args.resume)
        evaluation = evaluate_trained(config, limit=args.limit)
        result = {
            "status": "completed",
            "preflight": preflight,
            "baseline": baseline,
            "mining": mining,
            "training": training,
            "evaluation": evaluation,
        }
        write_json(
            Path(config["paths"]["run_dir"]) / "run_manifest.json",
            {
                "schema_version": "jdmatch_run_v1",
                "status": "completed",
                "provenance": collect_provenance(config),
                "stages": result,
            },
        )
    else:
        raise AssertionError(args.command)
    _print(result)


if __name__ == "__main__":
    main()
