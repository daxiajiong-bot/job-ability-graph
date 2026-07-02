"""Prompt templates for schema-based resume and JD profile extraction."""

from __future__ import annotations

from backend.app.domain.entities import DocumentType, SourceDocument
from backend.app.domain.profile_schemas import PROFILE_SCHEMA_VERSION


SYSTEM_PROMPT = """你是岗位能力图谱系统的信息抽取器。
任务目标：从 JD 或简历原文中抽取可落盘、可入图、可用于 RAG 和人岗匹配的结构化 Profile。
只输出一个合法 JSON object，不要输出 Markdown、解释、代码块或额外文字。
所有数组条目的 evidence_text 必须从原文连续复制，不得改写、翻译或概括；每段不超过 120 个字符。
不要输出 evidence_ids，不要输出顶层 evidence；后端会根据 evidence_text 自动生成。
所有非空技能、职责、要求、经历、项目、证书、语言和应用场景都必须填写 evidence_text。
如果原文没有某字段，使用 null、空对象或空数组，不要编造。"""


OPTIONS = """候选标签约束:
- skill.category: programming_language, framework, platform, database, tool, algorithm, ai_model, data_processing, testing, devops, domain_knowledge, soft_skill, language, certificate, other
- lskt_label: K(知识/理论/标准), S(可执行技能), T(通用能力), L(语言能力), unknown
- level: beginner, working, proficient, expert, unknown
- importance: required, preferred, unknown
- requirement_type: education, experience, skill, certificate, language, responsibility, domain, other
- employment_type: full_time, internship, contract, part_time, unknown"""


RESUME_SCHEMA = f"""输出 ResumeProfile JSON schema:
{{
  "schema_version": "{PROFILE_SCHEMA_VERSION}",
  "document_type": "resume",
  "candidate": {{"name": null, "current_title": null, "years_of_experience": null, "location": null}},
  "career_intent": {{"target_position": null, "target_industry": null, "target_location": null}},
  "education": [{{"school": "", "degree": "", "major": "", "period": "", "evidence_text": ""}}],
  "work_experience": [{{"company": "", "role": "", "industry": "", "period": "", "description": "", "evidence_text": ""}}],
  "project_experience": [{{"name": "", "role": "", "description": "", "technologies": [], "outcomes": [], "evidence_text": ""}}],
  "skills": [{{"name": "", "raw_name": "", "category": "", "lskt_label": "", "level": "beginner|working|proficient|expert|unknown", "years": null, "evidence_text": ""}}],
  "capabilities": [{{"name": "", "description": "", "level": "beginner|working|proficient|expert|unknown", "evidence_text": ""}}],
  "certificates": [{{"name": "", "issuer": "", "period": "", "evidence_text": ""}}],
  "languages": [{{"name": "", "level": "", "evidence_text": ""}}],
  "achievements": [{{"name": "", "description": "", "evidence_text": ""}}]
}}"""


JD_SCHEMA = f"""输出 JDProfile JSON schema:
{{
  "schema_version": "{PROFILE_SCHEMA_VERSION}",
  "document_type": "jd",
  "job": {{"title": null, "normalized_title": null, "department": null, "seniority": null}},
  "company": {{"name": null, "industry": null, "location": null}},
  "employment": {{"employment_type": "full_time|internship|contract|part_time|unknown", "salary_min": null, "salary_max": null, "published_at": null}},
  "responsibilities": [{{"text": "", "action": "", "object": "", "evidence_text": ""}}],
  "requirements": [{{"text": "", "requirement_type": "education|experience|skill|certificate|language|responsibility|domain|other", "importance": "required|preferred|unknown", "evidence_text": ""}}],
  "skills": [{{"name": "", "raw_name": "", "category": "", "lskt_label": "", "importance": "required|preferred|unknown", "evidence_text": ""}}],
  "capabilities": [{{"name": "", "description": "", "importance": "required|preferred|unknown", "evidence_text": ""}}],
  "application_scenarios": [{{"name": "", "description": "", "evidence_text": ""}}],
  "evaluation_signals": [{{"name": "", "description": "", "evidence_text": ""}}]
}}"""


TASK_INSTRUCTIONS = {
    DocumentType.RESUME: """任务说明:
1. 抽取候选人画像，不做岗位匹配结论。
2. skills 只保留候选人已经具备或项目/经历中明确使用过的技能。
3. capabilities 是从经历和项目中可证据支持的能力概括，不能脱离原文。
4. career_intent 只记录原文中的求职意向或目标岗位。""",
    DocumentType.JD: """任务说明:
1. 抽取岗位画像，不评价候选人。
2. 区分 required 和 preferred；无法判断时填 unknown。
3. skills 颗粒度到技能点，职责和要求保持可追溯。
4. application_scenarios 用于岗位全景图谱和新岗位定义，必须来自原文。""",
}


def extraction_messages(document: SourceDocument, max_input_chars: int) -> list[dict[str, str]]:
    text = document.text.strip()
    truncated = text[:max_input_chars]
    truncation_note = "" if len(text) <= max_input_chars else "\n注意：以下原文因长度限制已截断。"
    schema = RESUME_SCHEMA if document.document_type is DocumentType.RESUME else JD_SCHEMA
    task_instruction = TASK_INSTRUCTIONS[document.document_type]
    user_prompt = f"""文档类型: {document.document_type.value}
{task_instruction}

{OPTIONS}

{schema}
{truncation_note}

原文:
{truncated}"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
