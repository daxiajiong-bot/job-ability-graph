from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import torch

from .modeling import TrainableTextEncoder


@dataclass
class RNGState:
    cpu: torch.Tensor
    cuda: torch.Tensor | None


@dataclass
class CachedChunk:
    start: int
    end: int
    texts: list[str]
    is_query: bool
    rng: RNGState


def _capture_rng(device: torch.device) -> RNGState:
    cuda_state = (
        torch.cuda.get_rng_state(device)
        if device.type == "cuda"
        else None
    )
    return RNGState(cpu=torch.get_rng_state(), cuda=cuda_state)


def _restore_rng(state: RNGState, device: torch.device) -> None:
    torch.set_rng_state(state.cpu)
    if state.cuda is not None:
        torch.cuda.set_rng_state(state.cuda, device)


def _cache_embeddings(
    encoder: TrainableTextEncoder,
    texts: list[str],
    is_query: bool,
    microbatch_size: int,
) -> tuple[torch.Tensor, list[CachedChunk]]:
    values: list[torch.Tensor] = []
    chunks: list[CachedChunk] = []
    for start in range(0, len(texts), microbatch_size):
        chunk_texts = texts[start : start + microbatch_size]
        rng = _capture_rng(encoder.device)
        with torch.no_grad():
            embeddings = encoder.encode_texts(
                chunk_texts, is_query=is_query
            )
        end = start + len(chunk_texts)
        values.append(embeddings)
        chunks.append(
            CachedChunk(
                start=start,
                end=end,
                texts=chunk_texts,
                is_query=is_query,
                rng=rng,
            )
        )
    return torch.cat(values, dim=0), chunks


def gradcache_step(
    encoder: TrainableTextEncoder,
    query_texts: list[str],
    document_texts: list[str],
    loss_function: Callable[
        [torch.Tensor, torch.Tensor],
        tuple[torch.Tensor, dict[str, float]],
    ],
    microbatch_size: int,
) -> tuple[torch.Tensor, dict[str, float]]:
    if microbatch_size <= 0:
        raise ValueError("microbatch_size must be positive")
    query_values, query_chunks = _cache_embeddings(
        encoder, query_texts, True, microbatch_size
    )
    document_values, document_chunks = _cache_embeddings(
        encoder, document_texts, False, microbatch_size
    )
    query_leaf = query_values.detach().requires_grad_(True)
    document_leaf = document_values.detach().requires_grad_(True)
    loss, metrics = loss_function(query_leaf, document_leaf)
    loss.backward()
    query_gradient = query_leaf.grad
    document_gradient = document_leaf.grad
    if query_gradient is None or document_gradient is None:
        raise RuntimeError("GradCache loss produced no embedding gradients")

    for chunk in query_chunks + document_chunks:
        _restore_rng(chunk.rng, encoder.device)
        replay = encoder.encode_texts(
            chunk.texts, is_query=chunk.is_query
        )
        gradient = (
            query_gradient[chunk.start : chunk.end]
            if chunk.is_query
            else document_gradient[chunk.start : chunk.end]
        )
        surrogate = torch.sum(replay * gradient)
        surrogate.backward()
    return loss.detach(), metrics


def direct_step(
    encoder: TrainableTextEncoder,
    query_texts: list[str],
    document_texts: list[str],
    loss_function: Callable[
        [torch.Tensor, torch.Tensor],
        tuple[torch.Tensor, dict[str, float]],
    ],
) -> tuple[torch.Tensor, dict[str, float]]:
    queries = encoder.encode_texts(query_texts, is_query=True)
    documents = encoder.encode_texts(document_texts, is_query=False)
    loss, metrics = loss_function(queries, documents)
    loss.backward()
    return loss.detach(), metrics
