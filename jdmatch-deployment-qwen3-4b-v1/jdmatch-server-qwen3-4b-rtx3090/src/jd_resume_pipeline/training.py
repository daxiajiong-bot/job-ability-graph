from __future__ import annotations

import json
import math
import random
import shutil
import time
import gc
from pathlib import Path
from typing import Any

import torch
from torch.nn.utils import clip_grad_norm_
from transformers import get_linear_schedule_with_warmup

from .gradcache import gradcache_step
from .io_utils import read_jsonl, write_json
from .losses import grouped_contrastive_loss
from .modeling import (
    TrainableTextEncoder,
    load_trainable_encoder,
    trainable_parameter_summary,
)
from .provenance import collect_provenance
from .runtime_data import load_runtime_data


def _hard_id_buckets(
    group: dict[str, Any],
) -> tuple[list[str], list[str]]:
    same_family: list[str] = []
    fallback: list[str] = []
    for item in group.get("hard_negative_pool") or []:
        if isinstance(item, dict):
            target = same_family if item.get("same_family") else fallback
            target.append(str(item["resume_id"]))
        else:
            fallback.append(str(item))
    return same_family, fallback


def _fallback_groups(
    data: dict[str, Any],
    count: int,
) -> list[dict[str, Any]]:
    train_ids = [
        str(row["id"]) for row in data["jds"] if row["split"] == "train"
    ]
    train_ids = train_ids[: max(count * 3, count + 2)]
    result: list[dict[str, Any]] = []
    for index, query_id in enumerate(train_ids[:count]):
        anchors = {
            str(row["metadata"]["slot"]): str(row["id"])
            for row in data["resumes_by_jd"][query_id]
        }
        other_id = train_ids[(index + count) % len(train_ids)]
        easy_id = train_ids[(index + count + 1) % len(train_ids)]
        other = {
            str(row["metadata"]["slot"]): str(row["id"])
            for row in data["resumes_by_jd"][other_id]
        }
        easy = {
            str(row["metadata"]["slot"]): str(row["id"])
            for row in data["resumes_by_jd"][easy_id]
        }
        result.append(
            {
                "query_id": query_id,
                "positive_ids": [anchors["P1"], anchors["P2"]],
                "near_miss_id": anchors["H1"],
                "hard_negative_pool": [other["P1"], other["P2"]],
                "easy_negative_pool": [easy["P1"]],
                "do_not_use_as_negative": [],
            }
        )
    return result


def load_training_groups(
    config: dict[str, Any],
    allow_fallback: bool = False,
    fallback_count: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = load_runtime_data(config["paths"]["data_dir"])
    path = (
        Path(config["paths"]["run_dir"])
        / "negative_mining"
        / "train_groups.jsonl"
    )
    if path.is_file():
        groups = list(read_jsonl(path))
    elif allow_fallback:
        count = fallback_count or int(
            config["training"]["global_jd_batch_size"]
        )
        groups = _fallback_groups(data, count)
    else:
        raise ValueError(
            f"negative groups are missing: {path}; run mine-negatives first"
        )
    return data, groups


def build_training_batch(
    groups: list[dict[str, Any]],
    data: dict[str, Any],
    epoch: int,
    seed: int,
    hard_per_step: int,
    easy_per_step: int,
) -> dict[str, Any]:
    query_texts: list[str] = []
    query_records: list[dict[str, Any]] = []
    document_texts: list[str] = []
    document_records: list[dict[str, Any]] = []
    resume_by_id = data["resume_by_id"]
    jd_by_id = data["jd_by_id"]

    for group in groups:
        query_id = str(group["query_id"])
        query_texts.append(str(jd_by_id[query_id]["text"]))
        query_records.append(
            {
                "query_id": query_id,
                "do_not_use_as_negative": list(
                    group.get("do_not_use_as_negative") or []
                ),
            }
        )
        rng = random.Random(f"{seed}:{epoch}:{query_id}")
        same_family_hard_ids, fallback_hard_ids = _hard_id_buckets(group)
        rng.shuffle(same_family_hard_ids)
        rng.shuffle(fallback_hard_ids)
        hard_ids = (same_family_hard_ids + fallback_hard_ids)[
            :hard_per_step
        ]
        easy_ids = [
            str(item) for item in group.get("easy_negative_pool") or []
        ]
        rng.shuffle(easy_ids)
        easy_ids = easy_ids[:easy_per_step]
        typed_ids = [
            *(("positive", str(item)) for item in group["positive_ids"]),
            ("h1", str(group["near_miss_id"])),
            *(("hard", item) for item in hard_ids),
            *(("easy", item) for item in easy_ids),
        ]
        for kind, document_id in typed_ids:
            document = resume_by_id.get(document_id)
            if document is None:
                raise ValueError(
                    f"{query_id}: unknown training resume {document_id}"
                )
            document_texts.append(str(document["text"]))
            document_records.append(
                {
                    "document_id": document_id,
                    "kind": kind,
                    "source_query_id": query_id,
                    "actual_source_jd_id": str(document["source_jd_id"]),
                }
            )
    return {
        "query_texts": query_texts,
        "query_records": query_records,
        "document_texts": document_texts,
        "document_records": document_records,
    }


def _loss_closure(
    config: dict[str, Any],
    batch: dict[str, Any],
):
    training = config["training"]

    def calculate(
        query_embeddings: torch.Tensor,
        document_embeddings: torch.Tensor,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        return grouped_contrastive_loss(
            query_embeddings=query_embeddings,
            document_embeddings=document_embeddings,
            document_records=batch["document_records"],
            query_records=batch["query_records"],
            temperature=float(training["temperature"]),
            h1_margin=float(training["h1_margin"]),
            hard_margin=float(training["hard_margin"]),
            h1_loss_weight=float(training["h1_loss_weight"]),
            hard_loss_weight=float(training["hard_loss_weight"]),
        )

    return calculate


def _optimizer(
    encoder: TrainableTextEncoder,
    config: dict[str, Any],
) -> torch.optim.Optimizer:
    training = config["training"]
    parameters = [
        parameter
        for parameter in encoder.model.parameters()
        if parameter.requires_grad
    ]
    if not parameters:
        raise ValueError("the encoder has no trainable parameters")
    return torch.optim.AdamW(
        parameters,
        lr=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
    )


def _gradcache_with_oom_fallback(
    encoder: TrainableTextEncoder,
    optimizer: torch.optim.Optimizer,
    batch: dict[str, Any],
    config: dict[str, Any],
    microbatch_size: int,
) -> tuple[torch.Tensor, dict[str, float], int]:
    retry_with_one = False
    try:
        loss, metrics = gradcache_step(
            encoder=encoder,
            query_texts=batch["query_texts"],
            document_texts=batch["document_texts"],
            loss_function=_loss_closure(config, batch),
            microbatch_size=microbatch_size,
        )
    except RuntimeError as error:
        retry_with_one = (
            encoder.device.type == "cuda"
            and microbatch_size > 1
            and "out of memory" in str(error).lower()
        )
        if not retry_with_one:
            raise
    if retry_with_one:
        optimizer.zero_grad(set_to_none=True)
        gc.collect()
        torch.cuda.empty_cache()
        loss, metrics = gradcache_step(
            encoder=encoder,
            query_texts=batch["query_texts"],
            document_texts=batch["document_texts"],
            loss_function=_loss_closure(config, batch),
            microbatch_size=1,
        )
        metrics["gradcache_oom_fallback"] = 1.0
        return loss, metrics, 1
    return loss, metrics, microbatch_size


def _checkpoint_number(path: Path) -> int:
    try:
        return int(path.name.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def latest_checkpoint(run_dir: Path) -> Path | None:
    checkpoint_dir = run_dir / "checkpoints"
    candidates = [
        path
        for path in checkpoint_dir.glob("step-*")
        if (path / "trainer_state.json").is_file()
    ]
    return max(candidates, key=_checkpoint_number) if candidates else None


def _save_checkpoint(
    encoder: TrainableTextEncoder,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    run_dir: Path,
    state: dict[str, Any],
) -> Path:
    target = run_dir / "checkpoints" / f"step-{state['global_step']:08d}"
    temporary = target.with_name(target.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    encoder.save_adapter(temporary)
    torch.save(optimizer.state_dict(), temporary / "optimizer.pt")
    torch.save(scheduler.state_dict(), temporary / "scheduler.pt")
    write_json(temporary / "trainer_state.json", state)
    if target.exists():
        shutil.rmtree(target)
    temporary.rename(target)
    return target


def _load_state(
    checkpoint: Path,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    device: torch.device,
) -> dict[str, Any]:
    with (checkpoint / "trainer_state.json").open(
        "r", encoding="utf-8"
    ) as handle:
        state = json.load(handle)
    optimizer.load_state_dict(
        torch.load(
            checkpoint / "optimizer.pt",
            map_location=device,
            weights_only=False,
        )
    )
    scheduler.load_state_dict(
        torch.load(
            checkpoint / "scheduler.pt",
            map_location=device,
            weights_only=False,
        )
    )
    return state


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )


def preflight_training_step(
    config: dict[str, Any],
) -> dict[str, Any]:
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    data, groups = load_training_groups(
        config,
        allow_fallback=True,
        fallback_count=int(config["training"]["global_jd_batch_size"]),
    )
    groups = groups[: int(config["training"]["global_jd_batch_size"])]
    encoder = load_trainable_encoder(config)
    optimizer = _optimizer(encoder, config)
    batch = build_training_batch(
        groups,
        data,
        epoch=0,
        seed=int(config["seed"]),
        hard_per_step=int(config["sampling"]["hard_per_step"]),
        easy_per_step=int(config["sampling"]["easy_per_step"]),
    )
    optimizer.zero_grad(set_to_none=True)
    started = time.time()
    loss, metrics, actual_microbatch = _gradcache_with_oom_fallback(
        encoder,
        optimizer,
        batch,
        config,
        int(config["training"]["gradcache_microbatch_texts"]),
    )
    clip_grad_norm_(
        [
            parameter
            for parameter in encoder.model.parameters()
            if parameter.requires_grad
        ],
        float(config["training"]["max_grad_norm"]),
    )
    optimizer.step()
    if encoder.device.type == "cuda":
        torch.cuda.synchronize()
        allocated_peak_gib = (
            torch.cuda.max_memory_allocated() / 1024**3
        )
        reserved_peak_gib = torch.cuda.max_memory_reserved() / 1024**3
    elif encoder.device.type == "mps":
        torch.mps.synchronize()
        allocated_peak_gib = (
            torch.mps.current_allocated_memory() / 1024**3
        )
        reserved_peak_gib = (
            torch.mps.driver_allocated_memory() / 1024**3
        )
    else:
        allocated_peak_gib = 0.0
        reserved_peak_gib = 0.0
    return {
        "status": "passed",
        "device": str(encoder.device),
        "model": encoder.model_name,
        "parameters": trainable_parameter_summary(encoder.model),
        "queries": len(batch["query_texts"]),
        "documents": len(batch["document_texts"]),
        "microbatch_texts": actual_microbatch,
        "configured_microbatch_texts": int(
            config["training"]["gradcache_microbatch_texts"]
        ),
        "loss": float(loss),
        "metrics": metrics,
        "peak_memory_gib": round(reserved_peak_gib, 4),
        "peak_allocated_memory_gib": round(allocated_peak_gib, 4),
        "peak_reserved_memory_gib": round(reserved_peak_gib, 4),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def train(
    config: dict[str, Any],
    resume: str | None = None,
    max_steps: int | None = None,
) -> dict[str, Any]:
    started = time.time()
    run_dir = Path(config["paths"]["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    data, groups = load_training_groups(config)
    training = config["training"]
    batch_size = int(training["global_jd_batch_size"])
    epochs = int(training["epochs"])
    steps_per_epoch = math.ceil(len(groups) / batch_size)
    total_steps = steps_per_epoch * epochs
    checkpoint: Path | None = None
    if resume == "auto":
        checkpoint = latest_checkpoint(run_dir)
    elif resume:
        checkpoint = Path(resume).expanduser().resolve()
        if not checkpoint.is_dir():
            raise ValueError(f"resume checkpoint does not exist: {checkpoint}")

    encoder = load_trainable_encoder(config, adapter_path=checkpoint)
    optimizer = _optimizer(encoder, config)
    warmup_steps = round(total_steps * float(training["warmup_ratio"]))
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )
    state = {
        "epoch": 0,
        "next_batch_index": 0,
        "global_step": 0,
    }
    if checkpoint is not None:
        state = _load_state(
            checkpoint, optimizer, scheduler, encoder.device
        )

    log_path = run_dir / "train_log.jsonl"
    processed_this_run = 0
    last_checkpoint: Path | None = checkpoint
    actual_microbatch = int(training["gradcache_microbatch_texts"])
    for epoch in range(int(state["epoch"]), epochs):
        ordered = list(groups)
        random.Random(int(config["seed"]) + epoch).shuffle(ordered)
        first_batch = (
            int(state["next_batch_index"])
            if epoch == int(state["epoch"])
            else 0
        )
        for batch_index in range(first_batch, steps_per_epoch):
            selected = ordered[
                batch_index * batch_size : (batch_index + 1) * batch_size
            ]
            if not selected:
                continue
            batch = build_training_batch(
                selected,
                data,
                epoch=epoch,
                seed=int(config["seed"]),
                hard_per_step=int(config["sampling"]["hard_per_step"]),
                easy_per_step=int(config["sampling"]["easy_per_step"]),
            )
            optimizer.zero_grad(set_to_none=True)
            step_started = time.time()
            loss, metrics, actual_microbatch = _gradcache_with_oom_fallback(
                encoder,
                optimizer,
                batch,
                config,
                actual_microbatch,
            )
            gradient_norm = clip_grad_norm_(
                [
                    parameter
                    for parameter in encoder.model.parameters()
                    if parameter.requires_grad
                ],
                float(training["max_grad_norm"]),
            )
            optimizer.step()
            scheduler.step()
            if encoder.device.type == "cuda":
                torch.cuda.synchronize()
            state = {
                "epoch": epoch,
                "next_batch_index": batch_index + 1,
                "global_step": int(state["global_step"]) + 1,
            }
            record = {
                **state,
                **metrics,
                "loss": float(loss),
                "gradient_norm": float(gradient_norm),
                "learning_rate": float(scheduler.get_last_lr()[0]),
                "queries": len(batch["query_texts"]),
                "documents": len(batch["document_texts"]),
                "gradcache_microbatch_texts": actual_microbatch,
                "seconds": round(time.time() - step_started, 3),
            }
            _append_jsonl(log_path, record)
            processed_this_run += 1
            if int(state["global_step"]) % int(training["save_steps"]) == 0:
                last_checkpoint = _save_checkpoint(
                    encoder, optimizer, scheduler, run_dir, state
                )
            if max_steps is not None and processed_this_run >= max_steps:
                last_checkpoint = _save_checkpoint(
                    encoder, optimizer, scheduler, run_dir, state
                )
                partial = {
                    "status": "stopped_at_max_steps",
                    "global_step": state["global_step"],
                    "checkpoint": str(last_checkpoint.resolve()),
                }
                write_json(
                    run_dir / "run_manifest.json",
                    {
                        "schema_version": "jdmatch_run_v1",
                        "status": "stopped_at_max_steps",
                        "provenance": collect_provenance(config),
                        "training": partial,
                    },
                )
                return partial
        state = {
            "epoch": epoch + 1,
            "next_batch_index": 0,
            "global_step": int(state["global_step"]),
        }
        last_checkpoint = _save_checkpoint(
            encoder, optimizer, scheduler, run_dir, state
        )

    best_adapter = run_dir / "best_adapter"
    if best_adapter.exists():
        shutil.rmtree(best_adapter)
    encoder.save_adapter(best_adapter)
    manifest = {
        "schema_version": "jdmatch_run_v1",
        "status": "completed",
        "provenance": collect_provenance(config),
        "parameters": trainable_parameter_summary(encoder.model),
        "groups": len(groups),
        "steps_per_epoch": steps_per_epoch,
        "total_steps": int(state["global_step"]),
        "last_checkpoint": (
            str(last_checkpoint.resolve()) if last_checkpoint else None
        ),
        "best_adapter": str(best_adapter.resolve()),
        "gradcache_microbatch_texts": actual_microbatch,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    write_json(run_dir / "run_manifest.json", manifest)
    return manifest
