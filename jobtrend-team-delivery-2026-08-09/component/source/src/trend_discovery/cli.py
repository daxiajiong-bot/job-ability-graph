"""Command-line interface for the standalone job-trend pipeline.

The CLI deliberately exposes files and directories rather than a service API.
Successful commands write one JSON object to stdout.  Runtime and usage errors
write one JSON object to stderr and return a non-zero exit status.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO

from pydantic import BaseModel, ValidationError

from . import __version__
from .batch import (
    ROLE_DEFINITION_PROMPT_VERSION,
    SUBMIT_CONFIRMATION,
    download_batch,
    load_batch_state,
    prepare_extraction_batch,
    prepare_role_definition_batch,
    refresh_batch_status,
    submit_batch,
)
from .dashscope import DashScopeError
from .exporter import build_handoff_bundle
from .ingest import ingest_manifest
from .pipeline import (
    analyze_warehouse,
    import_graph,
    load_rag_candidates,
    mark_latest_success,
    new_local_run_dir,
)
from .review import export_review_queue, import_review_queue
from .settings import load_config, resolve_config_path
from .warehouse import Warehouse


EXIT_RUNTIME = 1
EXIT_USAGE = 2
EXIT_IO = 3
EXIT_PERMISSION = 4
EXIT_CLOUD = 5


class CLIUsageError(ValueError):
    """Raised instead of argparse's plain-text usage termination."""


class CommandFailure(RuntimeError):
    """A command completed enough work to attach structured failure details."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.details = dict(details or {})


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIUsageError(message)


def _add_global_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        help="configuration YAML (default: ./config/default.yaml or packaged default)",
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = JSONArgumentParser(
        prog="jobtrend",
        description="Auditable AI/LLM job-trend and emerging-role discovery",
    )
    _add_global_options(parser)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="parse sources.yaml into the warehouse")
    ingest_parser.add_argument("--sources", default="sources.yaml", help="source_manifest_v1 YAML")
    ingest_parser.add_argument("--warehouse", help="override configured warehouse directory")
    ingest_parser.set_defaults(handler=_cmd_ingest)

    kg_parser = subparsers.add_parser("import-kg", help="validate and index a read-only graph export")
    kg_parser.add_argument("--nodes", required=True, help="graph_nodes.jsonl")
    kg_parser.add_argument("--edges", required=True, help="graph_edges.jsonl")
    kg_parser.add_argument("--profiles", help="optional profiles.jsonl")
    kg_parser.add_argument("--output", help="index directory (default: runs/kg-index)")
    kg_parser.set_defaults(handler=_cmd_import_kg)

    prepare_parser = subparsers.add_parser(
        "prepare", help="prepare a local DashScope Batch request without submitting it"
    )
    prepare_parser.add_argument(
        "--kind",
        choices=("extraction", "role-definition"),
        default="extraction",
        help="batch request type",
    )
    prepare_parser.add_argument("--warehouse", help="override configured warehouse directory")
    prepare_parser.add_argument(
        "--analysis-dir", help="completed analysis directory (required for role-definition)"
    )
    prepare_parser.add_argument("--output", help="batch directory under configured runs by default")
    prepare_parser.add_argument("--run-id", help="auditable batch run identifier")
    prepare_parser.add_argument("--model", help="override the configured model")
    prepare_parser.set_defaults(handler=_cmd_prepare)

    submit_parser = subparsers.add_parser("submit", help="optionally submit one prepared paid batch")
    submit_parser.add_argument("--state", required=True, help="batch_state.json")
    submit_parser.add_argument(
        "--execute",
        action="store_true",
        help="perform the paid remote submission; omitted means a network-free dry run",
    )
    submit_parser.add_argument(
        "--confirm",
        help=f"exact paid-operation confirmation: {SUBMIT_CONFIRMATION}",
    )
    submit_parser.set_defaults(handler=_cmd_submit)

    status_parser = subparsers.add_parser("status", help="show or refresh DashScope Batch status")
    status_parser.add_argument("--state", required=True, help="batch_state.json")
    status_parser.add_argument(
        "--local-only", action="store_true", help="read local state without a network request"
    )
    status_parser.set_defaults(handler=_cmd_status)

    download_parser = subparsers.add_parser(
        "download", help="download and validate a completed DashScope Batch"
    )
    download_parser.add_argument("--state", required=True, help="batch_state.json")
    download_parser.add_argument("--destination", help="raw result JSONL destination")
    download_parser.add_argument(
        "--no-validate", action="store_true", help="skip schema and evidence-ID validation"
    )
    download_parser.set_defaults(handler=_cmd_download)

    analyze_parser = subparsers.add_parser(
        "analyze", help="compute time-series features and candidate graph deltas"
    )
    analyze_parser.add_argument("--warehouse", help="override configured warehouse directory")
    analyze_parser.add_argument("--output", help="analysis output directory")
    analyze_parser.add_argument("--kg-index", help="read-only KG index directory")
    analyze_parser.add_argument("--as-of", help="analysis clock in ISO-8601 form")
    analyze_parser.add_argument(
        "--cloud-retrieval",
        action="store_true",
        help="use configured cloud embedding/rerank models (may incur charges)",
    )
    analyze_parser.set_defaults(handler=_cmd_analyze)

    review_export_parser = subparsers.add_parser(
        "review-export", help="regenerate the human review CSV for an analysis run"
    )
    review_export_parser.add_argument("--run-dir", required=True, help="analysis artifact directory")
    review_export_parser.add_argument("--output", help="review CSV path")
    review_export_parser.set_defaults(handler=_cmd_review_export)

    review_import_parser = subparsers.add_parser(
        "review-import", help="apply reviewed decisions to copied artifacts"
    )
    review_import_parser.add_argument("--review", required=True, help="edited review_queue.csv")
    review_import_parser.add_argument("--run-dir", required=True, help="original analysis directory")
    review_import_parser.add_argument("--output", required=True, help="new reviewed output directory")
    review_import_parser.set_defaults(handler=_cmd_review_import)

    export_parser = subparsers.add_parser("export", help="create a validated append-only handoff bundle")
    export_parser.add_argument("--run-dir", required=True, help="analysis artifact directory")
    export_parser.add_argument("--output", help="bundle parent directory (default: project dist)")
    export_parser.add_argument("--bundle-name", default="jobtrend-handoff")
    export_parser.add_argument("--wheel", action="append", default=[], help="wheel to include; repeatable")
    export_parser.add_argument(
        "--source",
        "--source-path",
        dest="source_paths",
        action="append",
        default=[],
        help="explicit safe source file/directory to include; repeatable",
    )
    export_parser.set_defaults(handler=_cmd_export)

    all_parser = subparsers.add_parser(
        "run-all", help="incrementally ingest, optionally import a KG, analyze, and checkpoint"
    )
    all_parser.add_argument("--sources", default="sources.yaml", help="source_manifest_v1 YAML")
    all_parser.add_argument("--warehouse", help="override configured warehouse directory")
    all_parser.add_argument("--output", help="analysis output directory")
    all_parser.add_argument("--kg-index", help="use an already imported read-only KG index")
    all_parser.add_argument("--kg-nodes", help="optionally import graph_nodes.jsonl")
    all_parser.add_argument("--kg-edges", help="optionally import graph_edges.jsonl")
    all_parser.add_argument("--kg-profiles", help="optional profiles.jsonl")
    all_parser.add_argument("--kg-output", help="new KG index directory")
    all_parser.add_argument("--as-of", help="analysis clock in ISO-8601 form")
    all_parser.add_argument(
        "--cloud-retrieval",
        action="store_true",
        help="use cloud embeddings and reranking (may incur charges)",
    )
    all_parser.set_defaults(handler=_cmd_run_all)
    return parser


def _configured_path(config: Mapping[str, Any], key: str, override: str | None) -> Path:
    return Path(override or str(config["paths"][key])).expanduser().resolve()


def _iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise CLIUsageError(f"invalid ISO-8601 datetime for --as-of: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _state_payload(state: BaseModel, **extra: Any) -> dict[str, Any]:
    return {**state.model_dump(mode="json"), **extra}


def _cmd_ingest(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    result = ingest_manifest(
        args.sources,
        _configured_path(config, "warehouse", args.warehouse),
        config,
    )
    if result.get("status") == "failed":
        raise CommandFailure("all enabled sources failed", details={"ingest": result})
    return result


def _cmd_import_kg(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    output = Path(args.output).expanduser().resolve() if args.output else Path(
        str(config["paths"]["runs"])
    ) / "kg-index"
    result = import_graph(
        nodes=args.nodes,
        edges=args.edges,
        profiles=args.profiles,
        output_dir=output,
    )
    return {**result, "index_dir": str(output.resolve())}


def _cmd_prepare(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    runs_root = Path(str(config["paths"]["runs"]))
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else new_local_run_dir(runs_root, f"batch-{args.kind}")
    )
    run_id = args.run_id or output.name
    models = config["models"]
    if args.kind == "extraction":
        warehouse = Warehouse(_configured_path(config, "warehouse", args.warehouse))
        state = prepare_extraction_batch(
            warehouse.load_documents(),
            warehouse.load_evidence(),
            output,
            run_id=run_id,
            model=args.model or str(models["extraction_model"]),
            temperature=float(models.get("temperature", 0.1)),
            enable_thinking=bool(models.get("enable_thinking", False)),
        )
    else:
        if not args.analysis_dir:
            raise CLIUsageError("--analysis-dir is required when --kind=role-definition")
        candidates, evidence = load_rag_candidates(args.analysis_dir)
        state = prepare_role_definition_batch(
            candidates,
            evidence,
            output,
            run_id=run_id,
            model=args.model or str(models["fallback_model"]),
            temperature=float(models.get("temperature", 0.1)),
            enable_thinking=bool(models.get("enable_thinking", False)),
        )
    return _state_payload(
        state,
        dry_run=True,
        paid_request_submitted=False,
        state_path=str((output / "batch_state.json").resolve()),
    )


def _cmd_submit(args: argparse.Namespace, _config: Mapping[str, Any]) -> dict[str, Any]:
    state = submit_batch(
        args.state,
        execute=bool(args.execute),
        confirmation=args.confirm,
    )
    return _state_payload(
        state,
        executed=bool(args.execute),
        dry_run=not bool(args.execute),
        state_path=str(Path(args.state).expanduser().resolve()),
    )


def _cmd_status(args: argparse.Namespace, _config: Mapping[str, Any]) -> dict[str, Any]:
    state = load_batch_state(args.state) if args.local_only else refresh_batch_status(args.state)
    return _state_payload(
        state,
        local_only=bool(args.local_only),
        state_path=str(Path(args.state).expanduser().resolve()),
    )


def _cmd_download(args: argparse.Namespace, _config: Mapping[str, Any]) -> dict[str, Any]:
    state, validation = download_batch(
        args.state,
        destination=args.destination,
        validate=not bool(args.no_validate),
    )
    return _state_payload(
        state,
        validation=validation,
        state_path=str(Path(args.state).expanduser().resolve()),
    )


def _analysis_output(args: argparse.Namespace, config: Mapping[str, Any]) -> Path:
    if args.output:
        return Path(args.output).expanduser().resolve()
    return new_local_run_dir(config["paths"]["runs"])


def _cmd_analyze(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    return analyze_warehouse(
        config=config,
        warehouse_dir=_configured_path(config, "warehouse", args.warehouse),
        output_dir=_analysis_output(args, config),
        kg_index_dir=args.kg_index,
        as_of=_iso_datetime(args.as_of),
        use_cloud_retrieval=bool(args.cloud_retrieval),
    )


def _run_artifact_paths(run_dir: str | Path) -> tuple[Path, Path, Path]:
    root = Path(run_dir).expanduser().resolve()
    return (
        root / "emerging_roles.jsonl",
        root / "job_skill_updates.jsonl",
        root / "kg_link_delta.jsonl",
    )


def _cmd_review_export(args: argparse.Namespace, _config: Mapping[str, Any]) -> dict[str, Any]:
    run_dir = Path(args.run_dir).expanduser().resolve()
    roles, updates, deltas = _run_artifact_paths(run_dir)
    output = Path(args.output).expanduser().resolve() if args.output else run_dir / "review_queue.csv"
    count = export_review_queue(
        output,
        emerging_roles_path=roles,
        job_skill_updates_path=updates,
        kg_link_delta_path=deltas,
    )
    return {"review_queue": str(output), "records": count}


def _cmd_review_import(args: argparse.Namespace, _config: Mapping[str, Any]) -> dict[str, Any]:
    roles, updates, deltas = _run_artifact_paths(args.run_dir)
    return import_review_queue(
        args.review,
        args.output,
        emerging_roles_path=roles,
        job_skill_updates_path=updates,
        kg_link_delta_path=deltas,
    )


def _cmd_export(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else Path(str(config["_root"])) / "dist"
    )
    result = build_handoff_bundle(
        args.run_dir,
        output,
        bundle_name=args.bundle_name,
        config_sha256=str(config.get("_sha256") or ""),
        model_ids={key: str(value) for key, value in config["models"].items() if key.endswith("model")},
        prompt_versions={"role_definition": ROLE_DEFINITION_PROMPT_VERSION},
        wheel_paths=args.wheel,
        source_paths=args.source_paths,
    )
    return result.model_dump(mode="json")


def _cmd_run_all(args: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    if bool(args.kg_nodes) != bool(args.kg_edges):
        raise CLIUsageError("--kg-nodes and --kg-edges must be supplied together")
    warehouse = _configured_path(config, "warehouse", args.warehouse)
    ingest_result = ingest_manifest(args.sources, warehouse, config)
    if ingest_result.get("status") == "failed":
        raise CommandFailure("all enabled sources failed", details={"ingest": ingest_result})

    kg_result: dict[str, Any] | None = None
    kg_index = args.kg_index
    if args.kg_nodes and args.kg_edges:
        kg_output = (
            Path(args.kg_output).expanduser().resolve()
            if args.kg_output
            else Path(str(config["paths"]["runs"])) / "kg-index"
        )
        kg_result = import_graph(
            nodes=args.kg_nodes,
            edges=args.kg_edges,
            profiles=args.kg_profiles,
            output_dir=kg_output,
        )
        kg_index = str(kg_output.resolve())

    analysis_result = analyze_warehouse(
        config=config,
        warehouse_dir=warehouse,
        output_dir=_analysis_output(args, config),
        kg_index_dir=kg_index,
        as_of=_iso_datetime(args.as_of),
        use_cloud_retrieval=bool(args.cloud_retrieval),
    )
    checkpoint = mark_latest_success(config["paths"]["runs"], analysis_result)
    return {
        "status": "completed",
        "ingest": ingest_result,
        "kg_import": kg_result,
        "analysis": analysis_result,
        "latest_success": str(checkpoint),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _emit(value: Mapping[str, Any], *, stream: TextIO, pretty: bool) -> None:
    json.dump(
        dict(value),
        stream,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
        default=_json_default,
    )
    stream.write("\n")


def _error_payload(exc: BaseException, command: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "command": command,
        "error": {"type": type(exc).__name__, "message": str(exc)},
    }
    if isinstance(exc, CommandFailure) and exc.details:
        payload["details"] = exc.details
    return payload


def _exit_code(exc: BaseException) -> int:
    if isinstance(exc, CLIUsageError):
        return EXIT_USAGE
    if isinstance(exc, PermissionError):
        return EXIT_PERMISSION
    if isinstance(exc, (FileNotFoundError, IsADirectoryError, NotADirectoryError, OSError)):
        return EXIT_IO
    if isinstance(exc, DashScopeError):
        return EXIT_CLOUD
    if isinstance(exc, (ValueError, ValidationError)):
        return EXIT_USAGE
    return EXIT_RUNTIME


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return a process-compatible exit status."""

    parser = build_parser()
    args: argparse.Namespace | None = None
    try:
        args = parser.parse_args(argv)
        config = load_config(resolve_config_path(args.config))
        result = args.handler(args, config)
        payload = {"ok": True, "command": args.command, "result": result}
        _emit(payload, stream=sys.stdout, pretty=bool(args.pretty))
        return 0
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        command = getattr(args, "command", None) if args is not None else None
        pretty = bool(getattr(args, "pretty", False)) if args is not None else False
        _emit(_error_payload(exc, command), stream=sys.stderr, pretty=pretty)
        return _exit_code(exc)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
