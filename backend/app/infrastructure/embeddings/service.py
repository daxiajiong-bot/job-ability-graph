"""Qwen3-Embedding-4B semantic retrieval for recommendation recall.

Loads the LoRA-finetuned dual-encoder model (see
``jdmatch-deployment-qwen3-4b-v1``) and provides:
- ``encode``: text → 1024-dim L2-normalized vector (JD side gets the retrieval
  instruction used during training),
- cosine retrieval against a prebuilt document index.

The model is loaded lazily on first use and kept alive process-wide. Any
loading/encoding failure raises :class:`EmbeddingUnavailableError` so callers
can gracefully fall back to keyword-based recall.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Iterable

import numpy as np

logger = logging.getLogger(__name__)

# Instruction used during training for the JD (query) side.
JD_QUERY_INSTRUCTION = (
    "Instruct: Given a job description, retrieve candidate resumes that "
    "satisfy core skills, experience, and education requirements.\nQuery:"
)

TRUNCATE_DIM = 1024
MAX_SEQ_LEN = 512


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding model or index cannot be used."""


class EmbeddingService:
    """Lazy, process-wide Qwen3-Embedding-4B encoder + cosine retriever."""

    def __init__(
        self,
        model_dir: str | Path,
        adapter_dir: str | Path | None = None,
        device: str | None = None,
        jd_instruction: str = JD_QUERY_INSTRUCTION,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.adapter_dir = Path(adapter_dir) if adapter_dir else None
        self.device = device or self._detect_device()
        self.jd_instruction = jd_instruction
        self._model: Any = None
        self._lock = threading.Lock()

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            if torch.cuda.is_available() and torch.cuda.device_count() > 0:
                return "cuda"
        except Exception:  # pragma: no cover - torch is optional at import time
            pass
        return "cpu"

    # ── Model lifecycle ─────────────────────────────────

    @property
    def model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def _load_model(self) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover
            raise EmbeddingUnavailableError(
                "sentence-transformers is not installed; cannot use embedding recall"
            ) from exc

        if not self.model_dir.exists():
            raise EmbeddingUnavailableError(
                f"embedding model directory not found: {self.model_dir}"
            )
        quant_kwargs = self._quantization_kwargs()
        # With quantization requested there is no point falling back to the
        # exact load: the ~8 GB BF16 model does not fit small VRAM anyway.
        attempts: list[dict[str, Any] | None] = [quant_kwargs] if quant_kwargs else [None]
        last_exc: Exception | None = None
        for kwargs in attempts:
            try:
                t0 = _now()
                quant_label = "none" if kwargs is None else "kbit"
                logger.info(
                    "Loading Qwen3-Embedding-4B from %s (device=%s, quant=%s) ...",
                    self.model_dir,
                    self.device,
                    quant_label,
                )
                load_kwargs = dict(kwargs or {})
                if "model_kwargs" not in load_kwargs:
                    # device_map inside model_kwargs makes accelerate control
                    # placement; only pass `device` when it does not.
                    load_kwargs["device"] = self.device
                model = SentenceTransformer(
                    str(self.model_dir),
                    trust_remote_code=True,
                    **load_kwargs,
                )
                # Training used max 512 tokens; enforce it for encode().
                model.max_seq_length = MAX_SEQ_LEN
                if self.adapter_dir is not None and self.adapter_dir.exists():
                    model.load_adapter(str(self.adapter_dir))
                    logger.info("LoRA adapter loaded from %s", self.adapter_dir)
                logger.info("Embedding model ready in %.1fs", _now() - t0)
                return model
            except Exception as exc:  # pragma: no cover - env/device dependent
                last_exc = exc
                logger.warning("Embedding model load failed (%s); trying next load mode", exc)
        raise EmbeddingUnavailableError(f"failed to load embedding model: {last_exc}") from last_exc

    def _quantization_kwargs(self) -> dict[str, Any] | None:
        """Return SentenceTransformer kwargs for k-bit loading.

        ``EMBEDDING_QUANT=none`` (default) keeps the exact BF16 model.
        ``8bit`` / ``4bit`` load with bitsandbytes quantization so the ~8 GB
        BF16 model fits into smaller VRAM (e.g. 8 GB laptop GPUs); the LoRA
        adapter is still applied on top afterwards. Quantization only applies
        on CUDA; on CPU it is ignored. Any missing dependency falls back to
        the unquantized path.
        """
        quant = os.getenv("EMBEDDING_QUANT", "none").strip().lower()
        if quant in ("", "none", "off"):
            return None
        if self.device == "cpu":
            logger.warning("EMBEDDING_QUANT=%s ignored on cpu device", quant)
            return None
        try:
            import torch  # noqa: F401
            import bitsandbytes  # noqa: F401  (import check only)
            from transformers import BitsAndBytesConfig
        except ImportError as exc:
            logger.warning("EMBEDDING_QUANT=%s requested but deps missing: %s", quant, exc)
            return None
        if quant == "8bit":
            config = BitsAndBytesConfig(load_in_8bit=True)
        elif quant == "4bit":
            config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
        else:
            logger.warning("Unknown EMBEDDING_QUANT=%r, ignoring", quant)
            return None
        # device_map="auto" is required by bitsandbytes loading; it must be
        # nested under model_kwargs for SentenceTransformer. ST detects
        # hf_device_map and skips its own .to(device) move afterwards.
        return {"model_kwargs": {"quantization_config": config, "device_map": "auto"}}

    def _encode(self, texts: list[str], is_jd: list[bool]) -> np.ndarray:
        """Encode texts; returns (N, TRUNCATE_DIM) L2-normalized vectors."""
        if not texts:
            return np.zeros((0, TRUNCATE_DIM), dtype=np.float32)
        prompts = [
            self.jd_instruction + text if jd else text
            for text, jd in zip(texts, is_jd)
        ]
        try:
            batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
        except ValueError:  # pragma: no cover
            batch_size = 8
        try:
            raw = np.asarray(
                self.model.encode(
                    prompts,
                    normalize_embeddings=False,
                    batch_size=batch_size,
                ),
                dtype=np.float32,
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(f"embedding encode failed: {exc}") from exc

        truncated = raw[:, :TRUNCATE_DIM]
        norms = np.linalg.norm(truncated, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (truncated / norms).astype(np.float32)

    # ── Public API ──────────────────────────────────────

    def encode_texts(self, texts: list[str], is_jd: bool) -> np.ndarray:
        """Encode a list of texts (all JD-side or all document-side)."""
        return self._encode(texts, [is_jd] * len(texts))

    def similarity_matrix(
        self, query_vectors: np.ndarray, doc_vectors: np.ndarray
    ) -> np.ndarray:
        """Cosine similarity between (M,1024) queries and (N,1024) documents."""
        if query_vectors.shape[1] != doc_vectors.shape[1]:
            raise EmbeddingUnavailableError(
                f"dimension mismatch: {query_vectors.shape[1]} vs {doc_vectors.shape[1]}"
            )
        return query_vectors @ doc_vectors.T

    def search_index(
        self,
        query_vector: np.ndarray,
        index_vectors: np.ndarray,
        index_ids: list[str],
        top_k: int,
        exclude_ids: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Top-k document ids by cosine similarity with a single query vector."""
        exclude = set(exclude_ids or ())
        if index_vectors.shape[0] != len(index_ids):
            raise EmbeddingUnavailableError("index matrix / id list length mismatch")
        scores = self.similarity_matrix(query_vector.reshape(1, -1), index_vectors)[0]
        order = np.argsort(-scores)
        results: list[dict[str, Any]] = []
        for idx in order:
            doc_id = index_ids[int(idx)]
            if doc_id in exclude:
                continue
            results.append({"document_id": doc_id, "similarity": float(scores[int(idx)])})
            if len(results) >= top_k:
                break
        return results


# ── Process-wide singleton + vector index ──────────────


def _now() -> float:
    import time

    return time.monotonic()


_service: EmbeddingService | None = None
_service_lock = threading.Lock()


def get_embedding_service(config: dict[str, Any] | None = None) -> EmbeddingService | None:
    """Return the process-wide embedding service, or None when disabled.

    ``config`` keys: ``model_dir``, ``adapter_dir``, ``device``. When the
    service is unavailable (missing deps/model) a negative result is cached
    so we do not retry loading on every request.
    """
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                config = config or {}
                model_dir = config.get("model_dir")
                if not model_dir:
                    return None
                try:
                    _service = EmbeddingService(
                        model_dir=model_dir,
                        adapter_dir=config.get("adapter_dir"),
                        device=config.get("device"),
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("Embedding service disabled: %s", exc)
                    _service = None
    return _service


class VectorIndex:
    """In-memory document vector index loaded from disk (npy + ids json)."""

    def __init__(self, ids: list[str], vectors: np.ndarray) -> None:
        self.ids = ids
        self.vectors = vectors

    @property
    def size(self) -> int:
        return len(self.ids)

    @classmethod
    def load(cls, index_dir: str | Path) -> "VectorIndex | None":
        index_dir = Path(index_dir)
        npy = index_dir / "vectors.npy"
        ids_file = index_dir / "ids.json"
        if not npy.exists() or not ids_file.exists():
            return None
        import json

        try:
            vectors = np.load(str(npy))
            ids = json.loads(ids_file.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to load embedding index: %s", exc)
            return None
        if vectors.ndim != 2 or len(ids) != vectors.shape[0]:
            logger.warning("Embedding index shape mismatch; ignoring index")
            return None
        return cls(ids, vectors)


def default_index_dir(data_root: str | Path) -> Path:
    return Path(data_root) / "embeddings"


# ── Environment-driven helper (used by wiring) ─────────


def embedding_config_from_env() -> dict[str, Any] | None:
    """Read embedding settings from the environment.

    Returns None when ``EMBEDDING_BACKEND=off`` (or unset and the model dir is
    missing). Model/adapter paths default to the in-repo deployment folder.
    """
    backend = os.getenv("EMBEDDING_BACKEND", "").strip().lower()
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent  # repo root
    default_model_dir = (
        project_root
        / "jdmatch-deployment-qwen3-4b-v1"
        / "Qwen3-Embedding-4B"
    )
    default_adapter_dir = (
        project_root
        / "jdmatch-deployment-qwen3-4b-v1"
        / "jdmatch-server-qwen3-4b-rtx3090"
        / "runs"
        / "qwen3_embedding_4b_rtx3090"
        / "best_adapter"
    )
    model_dir = os.getenv("EMBEDDING_MODEL_DIR", str(default_model_dir))
    if backend == "off":
        return None
    if backend not in ("", "local"):
        logger.warning("Unknown EMBEDDING_BACKEND=%r, treating as local", backend)
    if not Path(model_dir).exists():
        logger.info("Embedding model dir not found (%s); embedding recall disabled", model_dir)
        return None
    return {
        "model_dir": model_dir,
        "adapter_dir": os.getenv("EMBEDDING_ADAPTER_DIR", str(default_adapter_dir)),
        "device": os.getenv("EMBEDDING_DEVICE") or None,
    }
