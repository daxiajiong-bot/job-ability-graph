"""End-to-end smoke test: encode a resume query and search the built index.

Run after ``scripts/build_embedding_index.py``:

    python scripts/_test_recall.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.infrastructure.embeddings.service import (  # noqa: E402
    EmbeddingService,
    VectorIndex,
    default_index_dir,
    embedding_config_from_env,
)

QUERY = (
    "Python 后端开发工程师，三年以上 Django/FastAPI 后端开发经验，熟悉 MySQL、Redis、消息队列，"
    "掌握 Docker、Kubernetes、CI/CD，具备微服务架构设计能力，计算机相关专业本科及以上学历。"
)


def main() -> None:
    config = embedding_config_from_env()
    print("embed_config:", config, flush=True)

    index_dir = default_index_dir(REPO_ROOT / "data")
    index = VectorIndex.load(index_dir)
    print("index_size:", index.size if index else 0, flush=True)
    if index is None or index.size == 0:
        print("EMPTY INDEX - run scripts/build_embedding_index.py first", flush=True)
        return

    svc = EmbeddingService(**config) if config else None
    if svc is None:
        print("embedding service unavailable", flush=True)
        return

    t0 = time.time()
    vec = svc.encode_texts([QUERY], is_jd=False)
    print(f"query_encode {time.time() - t0:.1f}s device={svc.device}", flush=True)

    hits = svc.search_index(vec[0], index.vectors, index.ids, top_k=5)
    print("top_hits:", flush=True)
    for h in hits:
        print(f"  {h['document_id']}  sim={h['similarity']:.4f}", flush=True)

    conn = sqlite3.connect("file:D:/挑战杯/job-ability-graph/data/app.db?mode=ro", uri=True)
    ids = [h["document_id"] for h in hits]
    ph = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT id, title FROM documents WHERE id IN ({ph})", ids).fetchall()
    for r in rows:
        print(f"  doc: {r[0]} | {r[1]}", flush=True)


if __name__ == "__main__":
    main()
