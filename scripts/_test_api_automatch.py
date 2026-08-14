"""API-level test: auto-match should now use hybrid (embedding + SQL) recall."""
from __future__ import annotations

import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8002"

RESUME_TEXT = """个人简介：Python 后端开发工程师，5 年工作经验。
技能：Python、Django、FastAPI、MySQL、Redis、消息队列、Docker、Kubernetes、CI/CD、微服务。
工作经历：负责电商平台核心交易系统开发，主导订单服务微服务化改造，接口 QPS 提升 3 倍。
项目经历：开发分布式任务调度平台，支持每日千万级任务执行；搭建日志采集与监控告警体系。
教育：计算机科学与技术本科，985 高校。"""


def main() -> None:
    # 1. Create a resume document
    r = requests.post(
        f"{BASE}/api/v1/documents",
        json={"document_type": "resume", "text": RESUME_TEXT},
        timeout=30,
    )
    r.raise_for_status()
    doc = r.json()["data"]["document"]
    doc_id = doc["id"]
    print(f"created resume document: {doc_id}", flush=True)

    # 2. Auto-match
    t0 = time.time()
    r = requests.post(
        f"{BASE}/api/v1/auto-match",
        json={"document_id": doc_id, "top_n": 5, "max_per_company": 2},
        timeout=600,
    )
    r.raise_for_status()
    body = r.json()["data"]
    meta = body.get("meta", {})
    print(f"auto_match took {time.time() - t0:.1f}s", flush=True)
    print("meta:", json.dumps(meta, ensure_ascii=False), flush=True)

    print("\ntop recommendations:", flush=True)
    for i, rec in enumerate(body.get("recommendations", []), 1):
        doc = rec.get("document", {})
        match = rec.get("match", {})
        print(
            f"  #{i} {doc.get('title', '')[:40]!r} | score={match.get('score')} "
            f"overlap={rec.get('skill_overlap')} | matched={len(rec.get('matched_skills', []))} "
            f"missing={len(rec.get('missing_skills', []))}",
            flush=True,
        )

    recall = meta.get("recall")
    if recall == "hybrid":
        print("\nRESULT: PASS - semantic embedding recall is ACTIVE (recall=hybrid)", flush=True)
    else:
        print(f"\nRESULT: FAIL - recall={recall!r} (expected 'hybrid')", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
