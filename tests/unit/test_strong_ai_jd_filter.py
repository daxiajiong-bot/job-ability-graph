from __future__ import annotations

from scripts.rebuild_strong_ai_jd_data import is_strong_ai_ml_related


def make_row(title: str, jd_text: str) -> dict[str, object]:
    return {
        "source_name": "zhaopin",
        "job_title": title,
        "jd_text": jd_text,
        "industry": "软件和信息技术服务",
        "company_name": "测试公司",
        "responsibilities": [],
        "requirements": [],
        "skills_raw": [],
        "skills_norm": [],
    }


def test_accepts_ai_algorithm_and_agent_development_roles() -> None:
    rows = [
        make_row(
            "大模型算法工程师",
            "负责大语言模型训练与LoRA微调，使用PyTorch完成模型优化和vLLM推理部署。",
        ),
        make_row(
            "Agent应用开发工程师",
            "基于LLM、RAG和LangGraph开发智能体，使用Python实现Function Calling与向量检索。",
        ),
        make_row(
            "AI Agent系统架构工程师（OpenClaw深度定制方向）",
            "负责OpenClaw源码级重构，开发多智能体框架、MCP工具调用和RAG知识库。",
        ),
        make_row(
            "高级算法工程师",
            "使用机器学习和PyTorch研发推荐算法，完成排序模型训练与在线推理优化。",
        ),
    ]

    assert all(is_strong_ai_ml_related(row) for row in rows)


def test_rejects_jobs_that_only_use_or_mention_ai() -> None:
    rows = [
        make_row(
            "0penClaw应用（AI养“龙虾”）部署工程师",
            "使用OpenClaw抓取潜在客户，集成CRM，并利用AI模型清洗营销数据。",
        ),
        make_row("营销渠道数据管理专员", "使用AI工具制作渠道分析报告。"),
        make_row("海外指挥中心解决方案专家", "了解AI发展并向客户提供行业解决方案。"),
        make_row("3D资产评测美术（AI数据集方向）", "负责AI数据集的3D资产美术评测。"),
        make_row("视觉调试技术员", "调试视觉设备，了解AI和机器视觉。"),
        make_row("ai动漫制作师", "使用生成式AI工具制作动漫内容。"),
        make_row("AI医疗数据分析师", "使用AI工具完成医疗业务数据统计与分析。"),
        make_row("AI办公助理（熟悉OpenClaw）", "使用OpenClaw完成日常办公自动化。"),
    ]

    assert not any(is_strong_ai_ml_related(row) for row in rows)
