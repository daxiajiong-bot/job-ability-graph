from __future__ import annotations

from typing import Any

import torch
import torch.nn.functional as F


def grouped_contrastive_loss(
    query_embeddings: torch.Tensor,
    document_embeddings: torch.Tensor,
    document_records: list[dict[str, Any]],
    query_records: list[dict[str, Any]],
    temperature: float,
    h1_margin: float,
    hard_margin: float,
    h1_loss_weight: float,
    hard_loss_weight: float,
) -> tuple[torch.Tensor, dict[str, float]]:
    if len(document_records) != document_embeddings.shape[0]:
        raise ValueError("document metadata/embedding size mismatch")
    if len(query_records) != query_embeddings.shape[0]:
        raise ValueError("query metadata/embedding size mismatch")

    device = query_embeddings.device
    info_indices = [
        index
        for index, record in enumerate(document_records)
        if record["kind"] != "h1"
    ]
    info_embeddings = document_embeddings[info_indices]
    info_records = [document_records[index] for index in info_indices]
    logits = query_embeddings @ info_embeddings.T / temperature

    info_losses: list[torch.Tensor] = []
    positive_scores: list[torch.Tensor] = []
    h1_losses: list[torch.Tensor] = []
    hard_losses: list[torch.Tensor] = []
    masked_count = 0
    for query_index, query in enumerate(query_records):
        query_id = str(query["query_id"])
        mask_ids = set(query.get("do_not_use_as_negative") or [])
        valid = torch.ones(len(info_records), dtype=torch.bool, device=device)
        positive = torch.zeros(
            len(info_records), dtype=torch.bool, device=device
        )
        for index, document in enumerate(info_records):
            document_id = str(document["document_id"])
            if (
                document_id in mask_ids
                and document["source_query_id"] != query_id
            ):
                valid[index] = False
                masked_count += 1
            if (
                document["source_query_id"] == query_id
                and document["kind"] == "positive"
            ):
                positive[index] = True
        if not bool(positive.any()):
            raise ValueError(f"{query_id}: no positive document in batch")
        selected = logits[query_index].masked_fill(~valid, float("-inf"))
        numerator = torch.logsumexp(
            selected.masked_fill(~positive, float("-inf")),
            dim=0,
        )
        denominator = torch.logsumexp(selected, dim=0)
        info_losses.append(-(numerator - denominator))

        own_positive_scores = [
            document_embeddings[index] @ query_embeddings[query_index]
            for index, document in enumerate(document_records)
            if document["source_query_id"] == query_id
            and document["kind"] == "positive"
        ]
        positive_score = torch.stack(own_positive_scores).mean()
        positive_scores.append(positive_score)
        for index, document in enumerate(document_records):
            if document["source_query_id"] != query_id:
                continue
            score = document_embeddings[index] @ query_embeddings[query_index]
            if document["kind"] == "h1":
                h1_losses.append(
                    F.relu(h1_margin - positive_score + score)
                )
            elif document["kind"] == "hard":
                hard_losses.append(
                    F.relu(hard_margin - positive_score + score)
                )

    info_loss = torch.stack(info_losses).mean()
    zero = info_loss.new_zeros(())
    h1_loss = torch.stack(h1_losses).mean() if h1_losses else zero
    hard_loss = torch.stack(hard_losses).mean() if hard_losses else zero
    total = (
        info_loss
        + h1_loss_weight * h1_loss
        + hard_loss_weight * hard_loss
    )
    metrics = {
        "loss": float(total.detach()),
        "info_nce": float(info_loss.detach()),
        "h1_margin_loss": float(h1_loss.detach()),
        "hard_margin_loss": float(hard_loss.detach()),
        "mean_positive_score": float(
            torch.stack(positive_scores).mean().detach()
        ),
        "masked_in_batch_pairs": float(masked_count),
    }
    return total, metrics

