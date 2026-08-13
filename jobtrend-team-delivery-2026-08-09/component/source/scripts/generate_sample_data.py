#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "data" / "samples"
AS_OF = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def jd_row(
    *,
    index: int,
    source: str,
    company: str,
    title: str,
    date: datetime,
    responsibilities: list[str],
    required: list[str],
    preferred: list[str] | None = None,
    industry: str = "人工智能",
    location: str = "北京",
) -> dict:
    preferred = preferred or []
    requirement_lines = [f"熟练掌握{skill}" for skill in required]
    preferred_lines = [f"具备{skill}经验者优先" for skill in preferred]
    text = "岗位职责：\n" + "\n".join(responsibilities)
    text += "\n任职要求：\n" + "\n".join(requirement_lines + preferred_lines)
    return {
        "source_type": "job_platform",
        "source_name": source,
        "job_id": f"SYN-{source}-{index:04d}",
        "job_title": title,
        "company_name": company,
        "industry": industry,
        "location": location,
        "publish_date": date.isoformat(),
        "scrape_time": (date + timedelta(hours=6)).isoformat(),
        "jd_text": text,
        "responsibilities": responsibilities,
        "requirements": requirement_lines + preferred_lines,
        "skills_raw": required + preferred,
        "skills_norm": required + preferred,
        "url": f"https://careers.example.org/{source}/{index}",
        "license": "synthetic-test-data",
    }


def build_rows() -> list[dict]:
    companies = [
        "甲辰科技",
        "乙木智能",
        "丙火数据",
        "丁巳软件",
        "戊云科技",
        "己土机器人",
        "庚金智造",
        "辛云安全",
    ]
    sources = ["enterprise-careers-a", "enterprise-careers-b"]
    rows: list[dict] = []
    index = 1

    # Baseline Java and conventional AI jobs: 60 records in the 84-day baseline window.
    for offset in range(40):
        rows.append(
            jd_row(
                index=index,
                source=sources[offset % 2],
                company=companies[offset % len(companies)],
                title="Java开发工程师",
                date=AS_OF - timedelta(days=35 + offset % 70),
                responsibilities=["负责企业服务后端开发", "负责微服务性能优化"],
                required=["Java", "Spring Boot", "MySQL"],
                preferred=["Docker"],
                industry="软件服务",
                location=["北京", "上海", "杭州"][offset % 3],
            )
        )
        index += 1
    for offset in range(20):
        rows.append(
            jd_row(
                index=index,
                source=sources[offset % 2],
                company=companies[offset % len(companies)],
                title="机器学习算法工程师",
                date=AS_OF - timedelta(days=40 + offset % 60),
                responsibilities=["负责机器学习模型训练", "负责模型评估与部署"],
                required=["Python", "机器学习", "PyTorch"],
                preferred=["Docker"],
            )
        )
        index += 1

    # Recent Java records contain an observable skill shift toward Agent integration.
    for offset in range(30):
        rows.append(
            jd_row(
                index=index,
                source=sources[offset % 2],
                company=companies[offset % len(companies)],
                title="Java开发工程师",
                date=AS_OF - timedelta(days=2 + offset % 24),
                responsibilities=["负责企业服务后端开发", "接入大模型与智能体工作流"],
                required=["Java", "Spring Boot", "MySQL", "大模型API", "RAG"],
                preferred=["MCP", "Docker"],
                industry="软件服务",
                location=["北京", "上海", "杭州"][offset % 3],
            )
        )
        index += 1

    # A deliberately discoverable emerging role spanning companies, sources and weeks.
    for offset in range(24):
        rows.append(
            jd_row(
                index=index,
                source=sources[offset % 2],
                company=companies[offset % len(companies)],
                title=["AI Agent安全评测工程师", "智能体安全测试工程师", "大模型智能体评测工程师"][offset % 3],
                date=AS_OF - timedelta(days=1 + offset % 26),
                responsibilities=["设计智能体工具调用与越权测试", "建设大模型幻觉和安全评测集", "分析智能体全链路风险"],
                required=["LLM评测", "Agent", "Python", "提示注入测试", "RAG"],
                preferred=["MCP", "红队测试"],
                industry=["人工智能", "金融科技", "智能制造"][offset % 3],
                location=["北京", "上海", "深圳"][offset % 3],
            )
        )
        index += 1

    for offset in range(6):
        rows.append(
            jd_row(
                index=index,
                source=sources[offset % 2],
                company=companies[offset],
                title="数据分析师",
                date=AS_OF - timedelta(days=3 + offset),
                responsibilities=["负责业务数据分析"],
                required=["SQL", "Python"],
            )
        )
        index += 1
    return rows


def main() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    for source in ("enterprise-careers-a", "enterprise-careers-b"):
        output = SAMPLE_DIR / f"{source}.jsonl"
        with output.open("w", encoding="utf-8") as handle:
            for row in rows:
                if row["source_name"] == source:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    (SAMPLE_DIR / "policy_agent_security.txt").write_text(
        "人工智能安全治理应加强智能体工具调用、提示注入、幻觉输出和全生命周期审计能力建设，培养生成式人工智能系统测试与安全评测人才。\n",
        encoding="utf-8",
    )
    (SAMPLE_DIR / "report_agent_engineering.txt").write_text(
        "行业智能体从问答应用走向工具调用和多智能体协同，企业开始设置智能体安全评测、红队测试和MCP权限治理相关岗位。\n",
        encoding="utf-8",
    )
    print(json.dumps({"records": len(rows), "output_dir": str(SAMPLE_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
