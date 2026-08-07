from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F
from peft import (
    LoraConfig,
    PeftModel,
    get_peft_model,
    prepare_model_for_kbit_training,
)
from torch import nn
from transformers import AutoModel, AutoTokenizer, BitsAndBytesConfig

from .model_registry import resolve_model_source


def resolve_device(
    require_cuda: bool = False,
    required_visible_devices: str | None = None,
) -> torch.device:
    if require_cuda and required_visible_devices is not None:
        actual = os.environ.get("CUDA_VISIBLE_DEVICES")
        if actual != required_visible_devices:
            raise RuntimeError(
                "CUDA_VISIBLE_DEVICES must be exactly "
                f"{required_visible_devices!r}, found {actual!r}"
            )
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    if require_cuda:
        raise RuntimeError(
            "CUDA is required but unavailable. Set CUDA_VISIBLE_DEVICES=0 "
            "and install a CUDA-enabled PyTorch wheel."
        )
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _torch_dtype(name: str, device: torch.device) -> torch.dtype:
    if name == "bfloat16":
        if device.type == "cuda" and not torch.cuda.is_bf16_supported():
            raise RuntimeError("the selected CUDA device does not support BF16")
        return torch.bfloat16
    if name == "float16":
        return torch.float16 if device.type != "cpu" else torch.float32
    if name == "float32":
        return torch.float32
    raise ValueError(f"unsupported dtype: {name}")


def _attention_implementation(config: dict[str, Any]) -> str:
    requested = str(config["hardware"]["attention"])
    fallback = str(config["hardware"]["attention_fallback"])
    if requested == "flash_attention_2":
        if importlib.util.find_spec("flash_attn") is None:
            return fallback
        try:
            importlib.import_module("flash_attn")
        except (ImportError, OSError):
            return fallback
    return requested


def last_token_pool(
    hidden_states: torch.Tensor,
    attention_mask: torch.Tensor,
) -> torch.Tensor:
    left_padding = bool(
        (attention_mask[:, -1].sum() == attention_mask.shape[0]).item()
    )
    if left_padding:
        return hidden_states[:, -1]
    sequence_lengths = attention_mask.sum(dim=1) - 1
    rows = torch.arange(hidden_states.shape[0], device=hidden_states.device)
    return hidden_states[rows, sequence_lengths]


class TrainableTextEncoder(nn.Module):
    def __init__(
        self,
        model: nn.Module,
        tokenizer: Any,
        model_name: str,
        query_instruction: str,
        max_length: int,
        output_dimension: int,
        device: torch.device,
    ) -> None:
        super().__init__()
        self.model = model
        self.tokenizer = tokenizer
        self.model_name = model_name
        self.query_instruction = query_instruction
        self.max_length = max_length
        self.output_dimension = output_dimension
        self.device = device
        self.pooling = (
            "last_token"
            if "qwen" in model_name.lower()
            else "cls"
        )

    def prepare_texts(
        self,
        texts: list[str],
        is_query: bool,
    ) -> list[str]:
        if not is_query or not self.query_instruction:
            return texts
        return [
            f"Instruct: {self.query_instruction}\nQuery:{text}"
            for text in texts
        ]

    def encode_texts(
        self,
        texts: list[str],
        is_query: bool,
    ) -> torch.Tensor:
        prepared = self.prepare_texts(texts, is_query=is_query)
        encoded = self.tokenizer(
            prepared,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        output = self.model(**encoded)
        hidden = output.last_hidden_state
        if self.pooling == "last_token":
            embeddings = last_token_pool(hidden, encoded["attention_mask"])
        else:
            embeddings = hidden[:, 0]
        if self.output_dimension > embeddings.shape[-1]:
            raise ValueError(
                f"output_dimension {self.output_dimension} exceeds hidden "
                f"dimension {embeddings.shape[-1]}"
            )
        embeddings = embeddings[:, : self.output_dimension].float()
        return F.normalize(embeddings, p=2, dim=-1)

    def save_adapter(self, path: str | Path) -> None:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        self.model.save_pretrained(target, safe_serialization=True)
        self.tokenizer.save_pretrained(target)


def load_trainable_encoder(
    config: dict[str, Any],
    adapter_path: str | Path | None = None,
) -> TrainableTextEncoder:
    model_name = str(config["models"]["embedding"])
    model_source = resolve_model_source(config, "embedding")
    hardware = config["hardware"]
    training = config["training"]
    device = resolve_device(
        bool(hardware["require_cuda"]),
        (
            str(hardware["required_cuda_visible_devices"])
            if hardware.get("required_cuda_visible_devices") is not None
            else None
        ),
    )
    dtype = _torch_dtype(str(hardware["dtype"]), device)
    quantization = str(training.get("quantization", "none"))

    tokenizer = AutoTokenizer.from_pretrained(model_source)
    if "qwen" in model_name.lower():
        tokenizer.padding_side = "left"
    load_kwargs: dict[str, Any] = {
        "dtype": dtype,
        "attn_implementation": _attention_implementation(config),
    }
    if quantization == "nf4":
        if device.type != "cuda":
            raise RuntimeError("NF4 QLoRA requires a CUDA device")
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        load_kwargs["device_map"] = {"": 0}

    try:
        base = AutoModel.from_pretrained(model_source, **load_kwargs)
    except (ImportError, OSError, TypeError, ValueError):
        load_kwargs["attn_implementation"] = str(
            hardware["attention_fallback"]
        )
        base = AutoModel.from_pretrained(model_source, **load_kwargs)
    if quantization == "nf4":
        base = prepare_model_for_kbit_training(
            base,
            use_gradient_checkpointing=bool(
                training["gradient_checkpointing"]
            ),
        )
    else:
        base.to(device)

    if hasattr(base.config, "use_cache"):
        base.config.use_cache = False
    if training["gradient_checkpointing"]:
        base.gradient_checkpointing_enable()
        if hasattr(base, "enable_input_require_grads"):
            base.enable_input_require_grads()

    if adapter_path is not None:
        model = PeftModel.from_pretrained(
            base,
            str(adapter_path),
            is_trainable=True,
        )
    else:
        lora = LoraConfig(
            r=int(training["lora_rank"]),
            lora_alpha=int(training["lora_alpha"]),
            lora_dropout=float(training["lora_dropout"]),
            target_modules=list(training["lora_targets"]),
            bias="none",
            task_type="FEATURE_EXTRACTION",
        )
        model = get_peft_model(base, lora)
    model.train()
    return TrainableTextEncoder(
        model=model,
        tokenizer=tokenizer,
        model_name=model_name,
        query_instruction=str(config["models"]["query_instruction"]),
        max_length=int(config["text"]["max_length"]),
        output_dimension=int(config["text"]["output_dimension"]),
        device=device,
    )


def trainable_parameter_summary(model: nn.Module) -> dict[str, Any]:
    total = sum(parameter.numel() for parameter in model.parameters())
    trainable = sum(
        parameter.numel()
        for parameter in model.parameters()
        if parameter.requires_grad
    )
    return {
        "total": total,
        "trainable": trainable,
        "trainable_percent": round(trainable / total * 100, 6),
    }
