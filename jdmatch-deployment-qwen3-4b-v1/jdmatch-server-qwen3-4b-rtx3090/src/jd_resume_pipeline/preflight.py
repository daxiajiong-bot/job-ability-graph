from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
from typing import Any

import torch

from .runtime_data import load_runtime_data
from .training import preflight_training_step


def _version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_preflight(
    config: dict[str, Any],
    run_training_step: bool = True,
) -> dict[str, Any]:
    hardware = config["hardware"]
    require_cuda = bool(hardware["require_cuda"])
    required_visible = hardware.get("required_cuda_visible_devices")
    actual_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if (
        require_cuda
        and required_visible is not None
        and actual_visible != str(required_visible)
    ):
        raise RuntimeError(
            "CUDA_VISIBLE_DEVICES must be exactly "
            f"{required_visible!r}, found {actual_visible!r}; "
            "this protects the jobs running on GPU 7"
        )
    if require_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required but torch.cuda.is_available() is false")
    visible_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    expected_count = int(hardware.get("expected_visible_device_count", 1))
    if require_cuda and visible_count != expected_count:
        raise RuntimeError(
            f"expected exactly {expected_count} visible CUDA device, "
            f"found {visible_count}; launch with CUDA_VISIBLE_DEVICES=0"
        )
    gpu_name = (
        torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    )
    expected_name = hardware.get("expected_gpu_name")
    if expected_name and gpu_name and str(expected_name) not in gpu_name:
        raise RuntimeError(
            f"expected GPU {expected_name!r}, found {gpu_name!r}"
        )
    if (
        require_cuda
        and str(hardware["dtype"]) == "bfloat16"
        and not torch.cuda.is_bf16_supported()
    ):
        raise RuntimeError("selected GPU does not support BF16")
    data = load_runtime_data(config["paths"]["data_dir"])
    report: dict[str, Any] = {
        "status": "passed",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "cuda_visible_devices_environment": actual_visible,
        "visible_cuda_devices": visible_count,
        "gpu_name": gpu_name,
        "bf16_supported": (
            torch.cuda.is_bf16_supported()
            if torch.cuda.is_available()
            else False
        ),
        "flash_attention_2_available": (
            importlib.util.find_spec("flash_attn") is not None
        ),
        "versions": {
            name: _version(name)
            for name in (
                "transformers",
                "sentence-transformers",
                "peft",
                "accelerate",
                "bitsandbytes",
            )
        },
        "data": {
            "jds": len(data["jds"]),
            "resumes": len(data["resumes"]),
            "contracts": len(data["contracts"]),
        },
    }
    if run_training_step:
        training = preflight_training_step(config)
        report["training_step"] = training
        maximum = float(hardware["max_peak_memory_gib"])
        if training["peak_memory_gib"] > maximum:
            raise RuntimeError(
                f"preflight peak memory {training['peak_memory_gib']:.2f} GiB "
                f"exceeds configured maximum {maximum:.2f} GiB"
            )
    return report
