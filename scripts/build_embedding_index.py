"""Build the Qwen3-Embedding-4B vector index for system JD documents.

Usage (from repo root):

    python scripts/build_embedding_index.py --limit 500
    python scripts/build_embedding_index.py            # full index (slow on CPU)

Output: ``data/embeddings/vectors.npy`` + ``ids.json`` + ``meta.json``.

NOTE: encoding 10k+ documents with a 4B model takes many hours on CPU and
several minutes on a GPU. For production, run this on the GPU server
(see README of jdmatch-deployment-qwen3-4b-v1) or a machine with enough RAM,
then copy the ``data/embeddings`` folder to this repo.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.infrastructure.embeddings.service import (  # noqa: E402
    EmbeddingService,
    default_index_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="max documents to index (0 = all)")
    parser.add_argument(
        "--db",
        type=str,
        default=str(REPO_ROOT / "data" / "app.db"),
        help="path to the SQLite database",
    )
    parser.add_argument("--output", type=str, default=None, help="output directory")
    parser.add_argument("--device", type=str, default=None, help="cuda / cpu (auto if unset)")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else default_index_dir(REPO_ROOT / "data")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not Path(args.db).exists():
        print(f"database not found: {args.db}")
        sys.exit(1)

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = (
        "SELECT id, title, text FROM documents "
        "WHERE user_id = 'system' AND document_type = 'jd'"
    )
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = conn.execute(sql).fetchall()
    conn.close()
    if not rows:
        print("no system JD documents found")
        sys.exit(1)

    print(f"indexing {len(rows)} system JDs -> {output_dir}")

    model_dir = (
        REPO_ROOT / "jdmatch-deployment-qwen3-4b-v1" / "Qwen3-Embedding-4B"
    )
    adapter_dir = (
        REPO_ROOT
        / "jdmatch-deployment-qwen3-4b-v1"
        / "jdmatch-server-qwen3-4b-rtx3090"
        / "runs"
        / "qwen3_embedding_4b_rtx3090"
        / "best_adapter"
    )

    service = EmbeddingService(model_dir=model_dir, adapter_dir=adapter_dir, device=args.device)
    texts = [(r["title"] or "") + "\n" + (r["text"] or "") for r in rows]
    ids = [r["id"] for r in rows]

    t0 = time.time()
    batch = 32
    vectors = []
    for start in range(0, len(texts), batch):
        chunk = texts[start : start + batch]
        vec = service.encode_texts(chunk, is_jd=True)
        vectors.append(vec)
        done = min(start + batch, len(texts))
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"  {done}/{len(texts)} ({rate:.1f} docs/s)")
    import numpy as np

    matrix = np.concatenate(vectors, axis=0).astype(np.float32)
    np.save(str(output_dir / "vectors.npy"), matrix)
    (output_dir / "ids.json").write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    meta = {
        "count": len(ids),
        "dim": int(matrix.shape[1]),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": "system_jd_documents",
        "model": "Qwen3-Embedding-4B + LoRA (jdmatch-deployment-qwen3-4b-v1)",
        "total_seconds": round(time.time() - t0, 1),
    }
    (output_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"done: {len(ids)} vectors, {matrix.shape[1]} dims, {meta['total_seconds']}s")
    print(meta)


if __name__ == "__main__":
    main()
