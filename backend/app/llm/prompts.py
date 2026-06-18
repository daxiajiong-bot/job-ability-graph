"""Prompt templates reserved for future LLM-enhanced extraction and explanation."""

from __future__ import annotations


JD_EXTRACTION_PROMPT = """
你是岗位 JD 结构化抽取助手。请只基于输入 JD 原文抽取结构化信息，不要补充原文中没有证据的内容。

输入：
{jd_text}

请以 JSON 输出：
{
  "position_name": "岗位名称",
  "category": "岗位类别",
  "domain": ["行业或业务领域"],
  "required_skills": [{"name": "技能", "level": "required", "evidence": ["原文证据"]}],
  "preferred_skills": [{"name": "技能", "level": "preferred", "evidence": ["原文证据"]}],
  "responsibilities": ["职责条目"],
  "required_level": {"education": "学历要求", "experience_years": "年限要求"},
  "evidence": [{"section": "来源区块", "text": "证据文本"}]
}
约束：技能必须能在 evidence 中找到支撑；不要编造岗位、技能、年限或行业。
""".strip()


RESUME_EXTRACTION_PROMPT = """
你是简历结构化抽取助手。请只基于输入简历原文抽取候选人画像，不要推断没有证据的技能。

输入：
{resume_text}

请以 JSON 输出：
{
  "candidate_name": "候选人姓名或匿名 ID",
  "target_position": "目标岗位",
  "education": "最高学历",
  "experience_years": 0,
  "skills": [{"name": "技能", "proficiency": 0.0, "evidence": ["原文证据"]}],
  "projects": [{"name": "项目名称", "role": "职责", "skills": ["技能"], "evidence": ["原文证据"]}],
  "evidence": [{"section": "来源区块", "text": "证据文本"}],
  "confidence": 0.0
}
约束：所有技能、项目和年限都必须来自原文证据；不输出个人隐私扩展信息。
""".strip()


MATCH_EXPLANATION_PROMPT = """
你是人岗匹配解释助手。请只基于 JD profile、resume profile、match_result 和 evidence 生成解释。

JD profile:
{jd_profile}

Resume profile:
{resume_profile}

Match result:
{match_result}

Evidence:
{evidence_items}

请以 JSON 输出：
{
  "match_reasons": ["匹配理由"],
  "risks": ["风险点"],
  "ability_gaps": ["能力差距"],
  "improvement_suggestions": ["提升建议"],
  "evidence_refs": ["引用证据 ID"]
}
约束：不要编造任何未在输入中出现的经历、技能、学历或项目；解释必须能回溯到 evidence。
""".strip()


EMERGING_POSITION_PROMPT = """
你是新岗位发现助手。请根据多个 JD 的技能组合、职责组合、技术栈和业务场景变化，生成候选新岗位。

输入 JD 集合：
{job_documents}

请以 JSON 输出：
{
  "position_name": "候选新岗位名称",
  "capability_mix": ["能力组合"],
  "core_skills": ["核心技能"],
  "responsibility_patterns": ["职责组合"],
  "scenario_changes": ["场景变化"],
  "evidence": [{"source_id": "来源", "text": "证据"}],
  "confidence": 0.0
}
约束：岗位命名必须由技能组合和职责证据支撑；不输出没有来源证据的新技能。
""".strip()


POSITION_UPDATE_PROMPT = """
你是岗位能力动态更新解释助手。请对比旧版本和新版本岗位画像，说明能力变化。

旧版本岗位画像：
{old_profile}

新版本岗位画像：
{new_profile}

请以 JSON 输出：
{
  "new_skills": ["新增技能"],
  "rising_skills": ["上升技能"],
  "declining_skills": ["下降技能"],
  "change_reasons": ["变化原因"],
  "evidence": [{"skill": "技能", "old_evidence": ["旧证据"], "new_evidence": ["新证据"]}]
}
约束：变化原因必须由两个版本的岗位画像和证据支持；不要引入外部知识作为事实。
""".strip()
