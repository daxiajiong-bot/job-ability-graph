from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from jd_resume_pipeline.job_spec_semantics import authoritative_semantics


JOB_FAMILIES = [
    "cv",
    "nlp_llm",
    "speech",
    "search_recommendation",
    "robotics_control",
    "data_ml",
    "embedded",
    "frontend_mobile",
    "backend_platform",
    "qa_ops",
    "other_algorithm",
    "other_software",
]
JOB_SPEC_SCHEMA_VERSION = "job_spec_v2_1"
JOB_SPEC_CUSTOM_ID_VERSION = "v2_1"

JOB_SPEC_SYSTEM_PROMPT = """你是严谨的中文技术岗位分析器。仅依据输入JD提取岗位规范，不补造JD没有的信息。这是job_spec v2.1。
必须返回一个合法JSON对象，不得输出Markdown或解释。所有数组去重并使用简洁的规范化技术短语。
规则：
1. required_skills只能包含无条件全部必需的技能。
2. 只有原文明确表达“至少一种、至少一门、任一、任选、A或B”等无条件必需候选关系时，才能创建required_skill_group；普通并列清单绝不自动形成any_of。输入的alternative_requirement_evidence只是程序找到的候选证据提示，最终每个组仍必须由原文明确支持。
3. “优先、有经验者优先、优先考虑、加分、了解更佳”等内容只能进入preferred_skills，绝不能进入required_skill_groups或升级为必需项。
4. 不得把同一技术栈的组成部分错误设为候选关系。例如Java、Spring Boot、Spring Cloud即使并列出现，也不是彼此替代的any_of。
5. 不得把语言、框架、数据库、任务场景等不同类型内容混入同一个候选组。专业方向、工作场景、项目类型不能作为技能组，除非原文确实给出明确的无条件必需任选关系。
6. required_skill_groups中mode固定为any_of；skills只列JD在同一证据片段中明确点名的候选技能；min_required写原文实际最低数量；不得补造JD未点名的技能。
7. 每个required_skill_group必须有evidence，逐字复制requirements或jd_text中支持该组的最短完整原文片段，不得概括或改写。evidence必须同时支持候选关系和skills中的每一项。
8. 若“如、例如、包括、等、不限于”等表明候选列表不穷尽，allow_other=true，否则为false。单元素技能组仅在原文是开放示例列表且allow_other=true时允许；单元素封闭组禁止。
9. required_skills与所有required_skill_groups.skills不得重叠；同一候选技能不得在多个组出现；不得把候选项摊平回required_skills。
10. preferred_skills只包含可选或加分技能。
11. experience_requirement必须逐字段原样复制输入的authoritative_experience_requirement；它已由程序按requirements/jd_text优先于experience_metadata的规则计算，禁止改写、补充或用元数据覆盖正文。
12. seniority必须原样复制authoritative_seniority；这是程序按统一规则计算的值，禁止自行判断。
13. decisive_requirements只包含决定胜任的硬条件。对于any_of组，用一条组级描述表达“候选项至少N项”，不得把每个候选项分别写成全部必需。
输出结构必须严格为：
{
  "jd_id": "原样返回",
  "normalized_title": "去除地点、福利、公司和招聘修饰词后的岗位名",
  "job_family": "给定枚举之一",
  "seniority": "原样复制authoritative_seniority",
  "required_skills": ["无条件全部必需的技能"],
  "required_skill_groups": [
    {
      "mode":"any_of",
      "skills":["Django","Flask","FastAPI"],
      "min_required":1,
      "allow_other":false,
      "evidence":"掌握至少一种主流Web框架：Django/Flask/FastAPI"
    }
  ],
  "preferred_skills": ["优先但非必需的技能"],
  "core_tasks": ["核心工作任务"],
  "decisive_requirements": ["决定性要求"],
  "experience_requirement": {
    "min_years": 3,
    "max_years": 5,
    "management_min_years": null,
    "source": "requirements|jd_text|metadata|unspecified之一",
    "metadata_conflict": false,
    "metadata_value": "原始元数据字符串",
    "evidence": ["正文证据"]
  }
}"""

RESUME_SYSTEM_PROMPT = """你是合成训练数据生成器。根据岗位规范一次生成三份完全虚构的中文简历。
只返回合法JSON对象，不输出Markdown或说明。模型不得自行决定关系标签，关系标签由下游程序按slot强制赋值。

硬约束：
1. resumes数组必须恰好有P1、P2、H1各一份，不能有其他slot。
2. 每份resume_text正文总长度为700-1100个字符，包含职业摘要、技能、教育、工作经历、项目经历及年月。
3. P1与P2满足全部decisive_requirements及全部required_skills，但职业路径、项目场景、时间线、措辞与段落组织明显不同，不能简单改写。
   对每个required_skill_groups，从skills明确列出的候选项中分别选择不少于min_required项；allow_other仅表示原JD列表不穷尽，不得据此补造未列技能。除非min_required等于候选项数量，不要掌握组内全部技能。P1与P2优先选择不同候选组合。
4. H1与正样本共享40%-70%的通用技能，同时缺少至少一项决定性能力。把缺失项列入H1的omitted_core_skills。
5. H1的resume_text不得出现omitted_core_skills及明显同义词，也不得出现“不会、不熟悉、缺少、不具备、未接触”等标签泄漏。
6. resume_text中禁止出现P1、P2、H1、positive、negative、匹配、正样本、负样本、硬负等关系或slot标记。
7. resume_text不设置姓名字段，不出现姓名、电话、邮箱、微信、QQ、真实学校或真实公司。教育机构写“某高校”，任职机构写“某科技企业”等匿名表达；正文直接从“职业摘要”开始。
8. slot只能出现在JSON元数据字段中；omitted_core_skills只能出现在JSON元数据中，不得写进正文。
9. 不直接复制JD原句；经历要具体可信、日期连续且工作年限与seniority一致。

输出结构：
{
  "jd_id": "原样返回",
  "resumes": [
    {"slot":"P1","resume_text":"...","omitted_core_skills":[]},
    {"slot":"P2","resume_text":"...","omitted_core_skills":[]},
    {"slot":"H1","resume_text":"...","omitted_core_skills":["至少一项决定性能力"]}
  ]
}"""


def job_spec_request(record: dict[str, Any]) -> dict[str, Any]:
    semantics = authoritative_semantics(record)
    payload = {
        "jd_id": record["jd_id"],
        "job_title": record["job_title"],
        "experience_metadata": record.get("experience"),
        "education": record.get("education"),
        "responsibilities": record.get("responsibilities", []),
        "requirements": record.get("requirements", []),
        "jd_text": record["jd_text"],
        "allowed_job_families": JOB_FAMILIES,
        "alternative_requirement_evidence": semantics[
            "alternative_requirement_evidence"
        ],
        "authoritative_experience_requirement": semantics[
            "experience_requirement"
        ],
        "authoritative_seniority": semantics["seniority"],
    }
    return {
        "custom_id": (
            f"job-spec-{record['jd_id']}-{JOB_SPEC_CUSTOM_ID_VERSION}"
        ),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "qwen-plus",
            "enable_thinking": False,
            "temperature": 0.2,
            "top_p": 0.8,
            "max_tokens": 1800,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": JOB_SPEC_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "请将以下岗位解析为JSON格式的job_spec：\n"
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
        },
    }


def resume_request(job_spec: dict[str, Any]) -> dict[str, Any]:
    jd_id = job_spec["jd_id"]
    return {
        "custom_id": f"resume-triplet-{jd_id}-v2",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": "qwen-plus",
            "enable_thinking": False,
            "temperature": 0.8,
            "top_p": 0.9,
            "max_tokens": 5000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": RESUME_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "请基于以下job_spec生成JSON格式的三份简历：\n"
                    + json.dumps(job_spec, ensure_ascii=False, separators=(",", ":")),
                },
            ],
        },
    }


def validate_batch_requests(requests: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    custom_ids: list[str] = []
    for index, request in enumerate(requests, 1):
        prefix = f"line {index}"
        custom_id = request.get("custom_id")
        if not isinstance(custom_id, str) or not custom_id:
            errors.append(f"{prefix}: missing custom_id")
        else:
            custom_ids.append(custom_id)
        if request.get("method") != "POST":
            errors.append(f"{prefix}: method must be POST")
        if request.get("url") != "/v1/chat/completions":
            errors.append(f"{prefix}: invalid url")
        body = request.get("body")
        if not isinstance(body, dict):
            errors.append(f"{prefix}: missing body")
            continue
        if body.get("model") != "qwen-plus":
            errors.append(f"{prefix}: model must be qwen-plus")
        if body.get("enable_thinking") is not False:
            errors.append(f"{prefix}: enable_thinking must be false")
        if body.get("response_format") != {"type": "json_object"}:
            errors.append(f"{prefix}: response_format must request json_object")
        if "json" not in json.dumps(body.get("messages", []), ensure_ascii=False).casefold():
            errors.append(f"{prefix}: messages must mention JSON")
    duplicates = [value for value, count in Counter(custom_ids).items() if count > 1]
    if duplicates:
        errors.append(f"duplicate custom_id values: {duplicates[:5]}")
    return errors


def select_representative_pilot(
    records: list[dict[str, Any]], size: int = 100
) -> list[dict[str, Any]]:
    train_records = [record for record in records if record.get("split") == "train"]
    if len(train_records) < size:
        raise ValueError(f"need {size} train records, only found {len(train_records)}")

    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in train_records:
        by_family[record["job_family_proxy"]].append(record)
    for family_records in by_family.values():
        family_records.sort(key=lambda record: (len(record["jd_text"]), record["jd_id"]))

    family_counts = Counter(record["job_family_proxy"] for record in train_records)
    quotas = {
        family: max(1, round(size * count / len(train_records)))
        for family, count in family_counts.items()
    }
    while sum(quotas.values()) > size:
        family = max(
            (name for name, quota in quotas.items() if quota > 1),
            key=lambda name: (quotas[name], family_counts[name]),
        )
        quotas[family] -= 1
    while sum(quotas.values()) < size:
        family = max(
            quotas,
            key=lambda name: family_counts[name] / quotas[name],
        )
        quotas[family] += 1

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for family, quota in sorted(quotas.items()):
        candidates = by_family[family]
        for offset in range(quota):
            index = min(
                len(candidates) - 1,
                round((offset + 0.5) * len(candidates) / quota - 0.5),
            )
            record = candidates[index]
            if record["jd_id"] not in selected_ids:
                selected.append(record)
                selected_ids.add(record["jd_id"])

    if len(selected) < size:
        remaining = sorted(
            (record for record in train_records if record["jd_id"] not in selected_ids),
            key=lambda record: (record["job_family_proxy"], len(record["jd_text"]), record["jd_id"]),
        )
        selected.extend(remaining[: size - len(selected)])
    return sorted(selected[:size], key=lambda record: record["jd_id"])


def force_edges(jd_id: str) -> list[dict[str, Any]]:
    return [
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-P1",
            "relevance": 2,
            "relation": "positive",
        },
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-P2",
            "relevance": 2,
            "relation": "positive",
        },
        {
            "jd_id": jd_id,
            "resume_id": f"{jd_id}-H1",
            "relevance": 0,
            "relation": "hard_negative",
        },
    ]
