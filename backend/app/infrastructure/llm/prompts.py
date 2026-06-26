"""Prompt templates for resume and JD extraction."""

from __future__ import annotations

from backend.app.domain.entities import DocumentType, SourceDocument


SYSTEM_PROMPT = """你是岗位能力图谱系统的信息抽取器。
只输出一个合法 JSON object，不要输出 Markdown、解释、代码块或额外文字。
所有结论必须尽量关联 evidence_ids；证据片段必须来自原文，且每段不超过 120 个字符。
如果原文没有某字段，使用 null 或空数组，不要编造。"""


RESUME_SCHEMA = """输出 JSON schema:
{
  "document_type": "resume",
  "candidate": {"name": null, "target_position": null},
  "education": [{"school": "", "degree": "", "major": "", "period": "", "evidence_ids": []}],
  "experience": [{"company": "", "role": "", "period": "", "description": "", "evidence_ids": []}],
  "projects": [{"name": "", "role": "", "description": "", "technologies": [], "evidence_ids": []}],
  "skills": [{"name": "", "category": "", "level": "", "evidence_ids": []}],
  "capabilities": [{"name": "", "description": "", "evidence_ids": []}],
  "responsibilities": [],
  "requirements": [],
  "evidence": [{"id": "ev_001", "field": "skills", "text": ""}]
}"""


JD_SCHEMA = """输出 JSON schema:
{
  "document_type": "jd",
  "candidate": {"name": null, "target_position": null},
  "job": {"title": null, "department": null, "seniority": null},
  "education": [],
  "experience": [],
  "projects": [],
  "skills": [{"name": "", "category": "", "importance": "required|preferred|unknown", "evidence_ids": []}],
  "capabilities": [{"name": "", "description": "", "evidence_ids": []}],
  "responsibilities": [{"text": "", "evidence_ids": []}],
  "requirements": [{"text": "", "importance": "required|preferred|unknown", "evidence_ids": []}],
  "evidence": [{"id": "ev_001", "field": "requirements", "text": ""}]
}"""


def extraction_messages(document: SourceDocument, max_input_chars: int) -> list[dict[str, str]]:
    text = document.text.strip()
    truncated = text[:max_input_chars]
    truncation_note = "" if len(text) <= max_input_chars else "\n注意：以下原文因长度限制已截断。"
    schema = RESUME_SCHEMA if document.document_type is DocumentType.RESUME else JD_SCHEMA
    user_prompt = f"""文档类型: {document.document_type.value}
{schema}
{truncation_note}

原文:
{truncated}"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
