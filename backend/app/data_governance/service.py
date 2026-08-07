"""Application-facing data governance service."""

from __future__ import annotations

from pathlib import Path
from os import getenv
from typing import Any

from backend.app.data_governance.esco import DEFAULT_ESCO_VERSION, EscoIndex
from backend.app.data_governance.lskt import build_lskt_span_extractor
from backend.app.data_governance.pipeline import DataGovernancePipeline
from backend.app.data_governance.rag import DataGovernanceRag
from backend.app.data_governance.store import DataGovernanceStore


class DataGovernanceService:
    def __init__(
        self,
        root: str | Path = "data",
        esco_index_root: str | Path | None = None,
        esco_version: str | None = None,
        llm_chat_client: Any | None = None,
    ) -> None:
        self.store = DataGovernanceStore(root)
        self.esco_index = EscoIndex.from_root(
            Path(esco_index_root or getenv("ESCO_INDEX_ROOT", "data/esco")),
            version=esco_version or getenv("ESCO_VERSION", DEFAULT_ESCO_VERSION),
        )
        self.span_extractor = build_lskt_span_extractor(self.esco_index, chat_client=llm_chat_client)
        self.pipeline = DataGovernancePipeline(self.store, self.span_extractor)
        self.rag = DataGovernanceRag(self.store)

    def register_upload(
        self,
        *,
        document_type: str,
        content: bytes,
        file_name: str,
        mime_type: str | None,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document = self.store.register_bytes(
            document_type=document_type,
            content=content,
            file_name=file_name,
            mime_type=mime_type,
            source=source,
            metadata=metadata,
        )
        return {"document": document.to_dict()}

    def register_path(
        self,
        *,
        document_type: str,
        path: str,
        source: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        document = self.store.register_path(document_type=document_type, path=path, source=source, metadata=metadata)
        return {"document": document.to_dict()}

    def process_document(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.pipeline.process(doc_id, version)

    def get_document(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.store.document_summary(doc_id, version)

    def lineage(self, doc_id: str, version: int | None = None) -> dict[str, Any]:
        return self.store.lineage(doc_id, version)

    def retrieve(self, query: str, doc_ids: list[str] | None = None, top_k: int = 5) -> dict[str, Any]:
        return self.rag.retrieve(query, doc_ids, top_k)

    def answer(self, query: str, doc_ids: list[str] | None = None, top_k: int = 5) -> dict[str, Any]:
        return self.rag.answer(query, doc_ids, top_k)
