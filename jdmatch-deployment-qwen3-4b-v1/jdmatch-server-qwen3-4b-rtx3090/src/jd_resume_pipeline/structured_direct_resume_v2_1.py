from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from jd_resume_pipeline.direct_resume import numbered_requirements
from jd_resume_pipeline.job_spec_semantics import authoritative_semantics
from jd_resume_pipeline.quality import SLOT_ORDER
from jd_resume_pipeline.structured_direct_resume import (
    ALLOWED_DEGREES,
    PreparedStructuredInput,
    StructuredParseFailure,
    StructuredParseResult,
    _response_body,
    _response_content,
    _usage_from_body,
    serialize_structured_resume,
    structured_custom_id_jd_id,
    structured_edges,
    validate_structured_resume_payload,
)


REPAIR_SCHEMA_VERSION = "resume_structured_direct_v2_1"
REPAIR_PROMPT_VERSION = "qwen_plus_structured_resume_v2_1"
REPAIR_MODEL = "qwen-plus"
REPAIR_TEMPERATURE = 0.7
REPAIR_TOP_P = 0.85
REPAIR_MAX_TOKENS = 6000
REPAIR_CUSTOM_ID_RE = re.compile(
    r"^resume-structured-direct-(J\d+)-v2-r1$"
)
FRESH_CUSTOM_ID_RE = re.compile(
    r"^resume-structured-direct-(J\d+)-v2_1$"
)
V2_1_CUSTOM_ID_RE = re.compile(
    r"^resume-structured-direct-(J\d+)-(?:v2-r1|v2_1)$"
)

PREFERRED_RE = re.compile(
    r"优先(?!级)|加分|更佳|可放宽|优先考虑|非必须|不是必须|"
    r"nice\s+to\s+have|optional|bonus",
    re.IGNORECASE,
)
INFORMATIONAL_RE = re.compile(
    r"企业简介|公司简介|关于公司|公司介绍|公司文化|企业文化|"
    r"我们提供|为什么加入|职位福利|福利方面|薪资方面|薪酬待遇|"
    r"工作时间|团队氛围|职业前景|常见问题|发布了|公司研发|"
    r"致力于|估值|融资|五险一金|周末双休|带薪年假|员工旅游|"
    r"办公(?:室|地点)|午休|弹性工作制"
)
HEADING_RE = re.compile(
    r"^[#*_\-•\s]*(?:任职要求|任职资格|岗位要求|职位要求|"
    r"岗位内容|基础资质|核心能力|高端加分项|应聘要求|"
    r"专业要求|工作职责|岗位职责|要求|必备)[：:\s（）()]*$"
)
ALTERNATE_ROLE_HEADING_RE = re.compile(
    r"(?:工程师|架构师|科学家|负责人|研究员)\s*[（(]?\s*\d+\s*人"
)
SECTION_BOUNDARY_RE = re.compile(
    r"^(?:关于公司|常见问题|企业简介|公司简介|我们提供)"
)
SOFT_RE = re.compile(
    r"沟通|团队(?:协作|合作|精神)?|责任心|抗压|学习能力|"
    r"积极主动|执行力|表达能力|协调能力|工作态度|敬业|品德|"
    r"热情|自驱|逻辑(?:清晰|思维)|问题分析|解决问题|独立思考|"
    r"细心|耐心|数据敏感|总结与文档|服从团队|态度踏实|"
    r"人际交往|成熟稳重|认真负责"
)
VAGUE_RE = re.compile(
    r"抽化出|抽象出|实际应用场景|输入输出方式|综合素质|"
    r"相关能力|相关知识|有一定了解|有一定基础"
)
YEAR_REQUIREMENT_RE = re.compile(
    r"(?<!\d)\d{1,2}\s*(?:-|~|～|—|–|至|到)?\s*"
    r"\d{0,2}\s*年(?:以上|及以上|以下|以内|经验)?"
)
PROJECT_RE = re.compile(
    r"项目|落地|上线|生产环境|量产|实战|研发经验|开发经验|"
    r"架构经验|实践经验"
)
EDUCATION_RE = re.compile(r"大专|本科|硕士|博士|学历|相关专业")
ACTION_RE = re.compile(
    r"精通|熟练|掌握|具备|能够|理解|独立完成|主导|搭建|开发|"
    r"设计|部署|调优|仿真|标定"
)

DEGREE_RANK = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}

# Canonical anchors are deliberately narrow. They are used both in the prompt
# contract and by the deterministic post-validator; broad semantic substring
# matching is intentionally avoided.
ANCHOR_DEFINITIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Cursor", re.compile(r"(?<![A-Za-z0-9])Cursor(?![A-Za-z0-9])", re.I)),
    (
        "Claude Code",
        re.compile(r"(?<![A-Za-z0-9])Claude\s+Code(?![A-Za-z0-9])", re.I),
    ),
    ("Copilot", re.compile(r"(?<![A-Za-z0-9])Copilot(?![A-Za-z0-9])", re.I)),
    ("RAG", re.compile(r"(?<![A-Za-z0-9])RAG(?![A-Za-z0-9])|检索增强", re.I)),
    ("向量数据库", re.compile(r"向量数据库|向量存储")),
    ("Embedding", re.compile(r"(?<![A-Za-z0-9])Embedding(?:s)?(?![A-Za-z0-9])", re.I)),
    ("Milvus", re.compile(r"(?<![A-Za-z0-9])Milvus(?![A-Za-z0-9])", re.I)),
    ("Chroma", re.compile(r"(?<![A-Za-z0-9])Chroma(?:DB)?(?![A-Za-z0-9])", re.I)),
    ("Pinecone", re.compile(r"(?<![A-Za-z0-9])Pinecone(?![A-Za-z0-9])", re.I)),
    ("Python", re.compile(r"(?<![A-Za-z0-9])Python(?![A-Za-z0-9])", re.I)),
    ("Java", re.compile(r"(?<![A-Za-z0-9])Java(?!Script|[A-Za-z0-9])", re.I)),
    ("Go", re.compile(r"(?<![A-Za-z0-9])Go(?:lang)?(?![A-Za-z0-9])", re.I)),
    ("C/C++", re.compile(r"(?<![A-Za-z0-9])C(?:/C\+\+|\+\+)(?![A-Za-z0-9])", re.I)),
    ("C语言", re.compile(r"(?<![A-Za-z0-9])C(?:语言)?(?![+#A-Za-z0-9])", re.I)),
    ("Verilog", re.compile(r"(?<![A-Za-z0-9])Verilog(?![A-Za-z0-9])", re.I)),
    ("MATLAB", re.compile(r"(?<![A-Za-z0-9])MATLAB(?![A-Za-z0-9])", re.I)),
    ("PyTorch", re.compile(r"(?<![A-Za-z0-9])PyTorch(?![A-Za-z0-9])", re.I)),
    ("TensorFlow", re.compile(r"(?<![A-Za-z0-9])TensorFlow(?![A-Za-z0-9])", re.I)),
    ("Scikit-learn", re.compile(r"Scikit[- ]?learn", re.I)),
    ("OpenCV", re.compile(r"(?<![A-Za-z0-9])OpenCV(?![A-Za-z0-9])", re.I)),
    ("Linux", re.compile(r"(?<![A-Za-z0-9])Linux(?![A-Za-z0-9])", re.I)),
    ("Windows", re.compile(r"(?<![A-Za-z0-9])Windows(?![A-Za-z0-9])", re.I)),
    ("Docker", re.compile(r"(?<![A-Za-z0-9])Docker(?![A-Za-z0-9])", re.I)),
    ("Kubernetes", re.compile(r"(?<![A-Za-z0-9])Kubernetes|(?<![A-Za-z0-9])K8s(?![A-Za-z0-9])", re.I)),
    ("Git", re.compile(r"(?<![A-Za-z0-9])Git(?!Hub|Lab|[A-Za-z0-9])", re.I)),
    ("CI/CD", re.compile(r"CI\s*/\s*CD", re.I)),
    ("MLflow", re.compile(r"(?<![A-Za-z0-9])MLflow(?![A-Za-z0-9])", re.I)),
    ("Kubeflow", re.compile(r"(?<![A-Za-z0-9])Kubeflow(?![A-Za-z0-9])", re.I)),
    ("Airflow", re.compile(r"(?<![A-Za-z0-9])Airflow(?![A-Za-z0-9])", re.I)),
    ("React", re.compile(r"(?<![A-Za-z0-9])React(?![A-Za-z0-9])", re.I)),
    ("Vue", re.compile(r"(?<![A-Za-z0-9])Vue(?:\.js)?(?![A-Za-z0-9])", re.I)),
    ("Angular", re.compile(r"(?<![A-Za-z0-9])Angular(?![A-Za-z0-9])", re.I)),
    ("Next.js", re.compile(r"(?<![A-Za-z0-9])Next\.?js(?![A-Za-z0-9])", re.I)),
    ("TypeScript", re.compile(r"(?<![A-Za-z0-9])TypeScript(?![A-Za-z0-9])", re.I)),
    ("SpringBoot", re.compile(r"Spring\s*Boot", re.I)),
    ("MyBatis", re.compile(r"(?<![A-Za-z0-9])MyBatis(?![A-Za-z0-9])", re.I)),
    ("SpringCloud", re.compile(r"Spring\s*Cloud", re.I)),
    ("MySQL", re.compile(r"(?<![A-Za-z0-9])MySQL(?![A-Za-z0-9])", re.I)),
    ("Redis", re.compile(r"(?<![A-Za-z0-9])Redis(?![A-Za-z0-9])", re.I)),
    ("MongoDB", re.compile(r"(?<![A-Za-z0-9])MongoDB(?![A-Za-z0-9])", re.I)),
    ("Elasticsearch", re.compile(r"(?<![A-Za-z0-9])Elasticsearch(?![A-Za-z0-9])", re.I)),
    ("FastAPI", re.compile(r"(?<![A-Za-z0-9])FastAPI(?![A-Za-z0-9])", re.I)),
    ("ASR", re.compile(r"(?<![A-Za-z0-9])ASR(?![A-Za-z0-9])|语音识别", re.I)),
    ("TTS", re.compile(r"(?<![A-Za-z0-9])TTS(?![A-Za-z0-9])|语音合成", re.I)),
    ("VAD", re.compile(r"(?<![A-Za-z0-9])VAD(?![A-Za-z0-9])|端点检测", re.I)),
    ("语音处理", re.compile(r"语音(?:处理|交互|后台|服务|技术)")),
    ("信号处理", re.compile(r"信号处理|数字信号")),
    ("雷达算法", re.compile(r"雷达.{0,8}算法|雷达信号")),
    ("通信算法", re.compile(r"通信.{0,8}算法|通信信号")),
    ("AI系统架构", re.compile(r"AI.{0,6}系统架构|AI.{0,6}架构")),
    ("分布式架构", re.compile(r"分布式(?:系统|架构)")),
    ("微服务", re.compile(r"微服务")),
    ("深度学习", re.compile(r"深度学习")),
    ("机器学习", re.compile(r"机器学习")),
    ("大模型", re.compile(r"大模型|LLM", re.I)),
    ("Transformer", re.compile(r"(?<![A-Za-z0-9])Transformer(?![A-Za-z0-9])", re.I)),
    ("LangChain", re.compile(r"(?<![A-Za-z0-9])LangChain(?![A-Za-z0-9])", re.I)),
    ("知识图谱", re.compile(r"知识图谱")),
    ("隐私计算", re.compile(r"隐私计算")),
    ("数据安全合规", re.compile(r"数据安全法|个人信息保护法|数据安全合规")),
    ("医疗数据", re.compile(r"医疗数据|临床数据|公卫数据|医药数据")),
    ("机器人控制", re.compile(r"机器人.{0,8}控制|运动控制")),
    ("PID", re.compile(r"(?<![A-Za-z0-9])PID(?![A-Za-z0-9])", re.I)),
    ("LQR", re.compile(r"(?<![A-Za-z0-9])LQR(?![A-Za-z0-9])", re.I)),
    ("MPC", re.compile(r"(?<![A-Za-z0-9])MPC(?![A-Za-z0-9])", re.I)),
    ("自适应滤波", re.compile(r"自适应滤波")),
    ("FXLMS", re.compile(r"(?<![A-Za-z0-9])F?XLMS(?![A-Za-z0-9])", re.I)),
    ("多麦克风阵列", re.compile(r"多麦克风阵列|麦克风阵列")),
    ("主动降噪", re.compile(r"主动降噪|RNC|ANC", re.I)),
    ("标定", re.compile(r"标定(?:流程|经验|工具|调参)?")),
)
ANCHOR_PATTERN_BY_NAME = dict(ANCHOR_DEFINITIONS)
ALTERNATIVE_ANCHOR_SETS: tuple[tuple[str, ...], ...] = (
    ("Cursor", "Claude Code", "Copilot"),
    ("React", "Vue", "Angular"),
    ("PyTorch", "TensorFlow"),
    ("Python", "Java", "Go", "C/C++", "C语言"),
)


REPAIR_SYSTEM_PROMPT = """你是 Qwen-Plus 非思考模式下的中文结构化简历生成器。任务是根据唯一权威输入，生成一个可被程序直接解析的 JSON 对象。最终答案只能包含 JSON，不得输出 Markdown、解释、思考过程或代码围栏。

一、指令优先级
1. generation_contract 是程序计算出的最高优先级约束。
2. numbered_requirements 是程序裁剪后的唯一JD要求；core_requirement_ids是核心候选清单，不表示要把其中所有术语堆入skills。
3. preferred_requirement_ids仅为可选项，P1/P2最多自然覆盖少量合理项，不能全部堆砌。
4. previous_invalid_output只用于识别旧错误，不是续写模板；必须重新生成完整JSON。

二、P1/P2硬规则
1. P1和P2都必须在 skills、work_experiences.details 或 projects 中明确体现 generation_contract.positive_evidence_groups：每个内层数组至少出现一个术语。
2. 若 require_work_or_project_evidence=true，不能只把术语放在skills或summary，工作或项目细节中也必须出现。
3. 两人都满足 authoritative_experience_requirement，并自然覆盖与岗位职责直接相关的核心条件。
4. P1与P2的职业路径、行业场景、公司类型、项目名称和技术组合必须明显不同。

三、H1硬规则
1. H1是同领域相邻候选人，但其全部字段都不得出现 generation_contract.h1_forbidden_terms 中任何术语或明显同义表达。
2. H1只能填写 generation_contract.omitted_requirement_id，不得换ID。
3. H1只写做过的事情，禁止出现“未参与、尚未实践、无相关经验、无经验、缺少、不具备、未接触、不了解”等缺失说明。
4. H1也必须满足 authoritative_experience_requirement；程序不会选择与该全局年限规则冲突的遗漏目标。

四、结构、匿名与时间
1. resumes恰好为P1、P2、H1各一份。不得输出resume_text、label、relevance、relation或其他字段。
2. school严格等于“某高校”。company只能是：某科技企业、某互联网企业、某制造企业、某软件企业、某研究机构。
3. 不出现姓名、电话、邮箱、微信、QQ、真实学校、真实公司。
4. summary为60–150个中文字符；skills为8–15项。
5. work_experiences为1–3段，每段details为2–4条；projects为1–2个，每个details为2–4条。
6. 日期使用YYYY-MM；只有工作结束时间可写“至今”。经历按开始时间升序且不重叠。
7. generation_contract.experience_contract给出工作月数边界和推荐连续时间线。为减少算术错误，优先原样使用推荐的单段连续工作时间；若拆成多段，三份仍都必须逐月满足边界。
8. school、company、项目名使用匿名虚构表达；项目名建议以“某”开头。

五、行为示例
若 positive_evidence_groups=[["Docker","Kubernetes"]] 且 h1_forbidden_terms=["Docker","Kubernetes"]：
- P1可以在项目细节明确写Docker；P2可以明确写Kubernetes。
- H1必须选择同领域但使用其他部署方式，所有字段都不能出现Docker或Kubernetes。
- H1不得写“不会Docker”或“缺少Kubernetes”。

六、输出JSON模板
{
  "jd_id":"原样返回",
  "resumes":[
    {
      "slot":"P1",
      "summary":"...",
      "education":{"degree":"本科","major":"...","school":"某高校","start":"2016-09","end":"2020-06"},
      "skills":["..."],
      "work_experiences":[{"start":"2020-07","end":"至今","company":"某科技企业","role":"...","details":["...","..."]}],
      "projects":[{"start":"2022-03","end":"2022-11","name":"某项目","role":"...","technologies":["..."],"details":["...","..."]}],
      "omitted_requirement_ids":[]
    },
    {
      "slot":"P2",
      "summary":"...",
      "education":{"degree":"硕士","major":"...","school":"某高校","start":"2017-09","end":"2020-06"},
      "skills":["..."],
      "work_experiences":[{"start":"2020-07","end":"至今","company":"某软件企业","role":"...","details":["...","..."]}],
      "projects":[{"start":"2021-05","end":"2022-02","name":"某项目","role":"...","technologies":["..."],"details":["...","..."]}],
      "omitted_requirement_ids":[]
    },
    {
      "slot":"H1",
      "summary":"...",
      "education":{"degree":"本科","major":"...","school":"某高校","start":"2016-09","end":"2020-06"},
      "skills":["..."],
      "work_experiences":[{"start":"2020-07","end":"至今","company":"某研究机构","role":"...","details":["...","..."]}],
      "projects":[{"start":"2022-04","end":"2023-01","name":"某项目","role":"...","technologies":["..."],"details":["...","..."]}],
      "omitted_requirement_ids":["generation_contract.omitted_requirement_id"]
    }
  ]
}

输出前在内部逐项核对：JSON可解析、字段齐全、slot唯一、遗漏ID正确、P1/P2证据组齐全、H1禁用词为零、工作月数合规、三份经历不同。不要输出核对过程，只输出最终JSON对象。"""


@dataclass(frozen=True)
class PreparedRepairInput:
    payload: dict[str, Any]
    requirement_source: str
    hard_requirement: dict[str, str]
    omission_contract: dict[str, Any]


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def scoped_requirements(
    requirements: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
    scoped: list[dict[str, str]] = []
    for requirement in requirements:
        text = _text(requirement.get("text"))
        if scoped and (
            INFORMATIONAL_RE.search(text)
            or ALTERNATE_ROLE_HEADING_RE.search(text)
            or SECTION_BOUNDARY_RE.search(text)
        ):
            break
        scoped.append({"id": str(requirement["id"]), "text": text})
    return scoped


def requirement_anchors(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for name, pattern in ANCHOR_DEFINITIONS:
        match = pattern.search(text)
        if match:
            found.append((match.start(), name))
    found.sort()
    anchors = list(dict.fromkeys(name for _, name in found))
    if "C/C++" in anchors and "C语言" in anchors:
        anchors.remove("C语言")
    return anchors


def positive_evidence_groups(
    text: str,
    anchors: list[str],
) -> list[list[str]]:
    """Build at most three evidence clauses without flattening alternatives."""

    remaining = list(anchors)
    groups: list[list[str]] = []
    has_alternative_wording = bool(
        re.search(r"至少(?:一种|一门)|任一|任选|其中一种|或|/", text)
    )
    if has_alternative_wording:
        for alternatives in ALTERNATIVE_ANCHOR_SETS:
            present = [name for name in alternatives if name in remaining]
            if len(present) >= 2:
                groups.append(present)
                remaining = [
                    name for name in remaining if name not in present
                ]
    groups.extend([[anchor] for anchor in remaining])
    return groups[:3]


def _minimum_degree(text: str) -> str | None:
    matches = [
        (match.start(), degree)
        for degree in DEGREE_RANK
        for match in [re.search(re.escape(degree), text)]
        if match
    ]
    if not matches:
        return None
    return min(matches)[1]


def _education_contract(text: str) -> dict[str, Any] | None:
    degree = _minimum_degree(text)
    if degree is None or DEGREE_RANK[degree] <= DEGREE_RANK["大专"]:
        return None
    return {
        "kind": "education",
        "positive_evidence_groups": [],
        "h1_forbidden_terms": [],
        "education_min_degree": degree,
        "require_work_or_project_evidence": False,
    }


def requirement_contract(
    requirement: dict[str, str],
) -> dict[str, Any] | None:
    text = _text(requirement.get("text"))
    if (
        not text
        or len(re.sub(r"[\W_]", "", text)) < 6
        or len(text) > 180
        or HEADING_RE.fullmatch(text)
        or INFORMATIONAL_RE.search(text)
        or PREFERRED_RE.search(text)
        or YEAR_REQUIREMENT_RE.search(text)
    ):
        return None
    anchors = requirement_anchors(text)
    if SOFT_RE.search(text) and not anchors:
        return None
    if VAGUE_RE.search(text) and len(anchors) < 2:
        return None
    if not anchors:
        if EDUCATION_RE.search(text):
            return _education_contract(text)
        return None

    selected_anchors = anchors[:5]
    groups = positive_evidence_groups(text, selected_anchors)
    return {
        "kind": "technical_or_domain",
        "positive_evidence_groups": groups,
        "h1_forbidden_terms": selected_anchors,
        "education_min_degree": None,
        "require_work_or_project_evidence": bool(PROJECT_RE.search(text)),
    }


def _requirement_rank(
    requirement: dict[str, str],
    contract: dict[str, Any],
    index: int,
) -> tuple[int, int, int, int]:
    text = requirement["text"]
    anchors = contract["h1_forbidden_terms"]
    kind_score = 5 if contract["kind"] == "technical_or_domain" else 3
    reliability = 0
    reliability += 4 if 1 <= len(anchors) <= 4 else 1
    reliability += 3 if 12 <= len(text) <= 100 else 0
    reliability += 2 if ACTION_RE.search(text) else 0
    reliability += 2 if text.count("；") + text.count("。") <= 1 else 0
    reliability += 1 if contract["require_work_or_project_evidence"] else 0
    return (-kind_score, -reliability, len(text), index)


def select_reliable_hard_requirement(
    requirements: Iterable[dict[str, str]],
    *,
    target_requirement_id: str | None = None,
) -> tuple[dict[str, str], dict[str, Any]] | None:
    candidates: list[
        tuple[tuple[int, int, int, int], dict[str, str], dict[str, Any]]
    ] = []
    for index, requirement in enumerate(scoped_requirements(requirements)):
        contract = requirement_contract(requirement)
        if contract is None:
            continue
        candidate = {
            "id": str(requirement["id"]),
            "text": _text(requirement["text"]),
        }
        candidates.append(
            (_requirement_rank(candidate, contract, index), candidate, contract)
        )
    if not candidates:
        return None
    if target_requirement_id is not None:
        matching = [
            item
            for item in candidates
            if item[1]["id"] == target_requirement_id
        ]
        if not matching:
            raise ValueError(
                "target_requirement_id_is_not_a_reliable_atomic_requirement"
            )
        _, requirement, contract = matching[0]
    else:
        _, requirement, contract = min(candidates, key=lambda item: item[0])
    contract = {
        **contract,
        "omitted_requirement_id": requirement["id"],
        "omitted_requirement_text": requirement["text"],
    }
    return requirement, contract


def _requirement_id_groups(
    requirements: Iterable[dict[str, str]],
) -> tuple[list[str], list[str]]:
    required: list[str] = []
    preferred: list[str] = []
    for item in scoped_requirements(requirements):
        text = item["text"]
        if PREFERRED_RE.search(text):
            preferred.append(item["id"])
            continue
        if requirement_contract(item) is not None or YEAR_REQUIREMENT_RE.search(
            text
        ):
            required.append(item["id"])
    return required, preferred


def _month_string(value: int) -> str:
    year, month_index = divmod(value - 1, 12)
    return f"{year:04d}-{month_index + 1:02d}"


def experience_generation_contract(
    experience: dict[str, Any],
) -> dict[str, Any]:
    today = date.today()
    current = today.year * 12 + today.month
    minimum_years = experience.get("min_years")
    maximum_years = experience.get("max_years")
    minimum_months = (
        minimum_years * 12 if isinstance(minimum_years, int) else None
    )
    maximum_months = (
        maximum_years * 12 + 1 if isinstance(maximum_years, int) else None
    )
    if minimum_months is not None and maximum_months is not None:
        target_months = (minimum_months + maximum_months) // 2
    elif minimum_months is not None:
        target_months = minimum_months + 6
    elif maximum_months is not None:
        target_months = max(1, maximum_months - 6)
    else:
        target_months = None
    recommended = (
        {
            "start": _month_string(current - target_months + 1),
            "end": "至今",
            "inclusive_months": target_months,
        }
        if target_months is not None
        else None
    )
    return {
        "reference_current_month": f"{today.year:04d}-{today.month:02d}",
        "work_months_min": minimum_months,
        "work_months_max": maximum_months,
        "recommended_single_continuous_timeline": recommended,
        "counting_rule": "所有工作区间按月份并集计数，起止月份都计入",
    }


def prepare_repair_input(
    record: dict[str, Any],
    *,
    target_requirement_id: str | None = None,
) -> PreparedRepairInput:
    jd_id = _text(record.get("jd_id"))
    job_title = _text(record.get("job_title"))
    jd_text = _text(record.get("jd_text"))
    if not jd_id:
        raise ValueError("missing_jd_id")
    if not job_title or not jd_text:
        raise ValueError("missing_job_title_or_jd_text")
    requirements, source = numbered_requirements(record)
    scoped = scoped_requirements(requirements)
    selection = select_reliable_hard_requirement(
        scoped,
        target_requirement_id=target_requirement_id,
    )
    if selection is None:
        raise ValueError("no_reliable_atomic_hard_requirement")
    hard_requirement, omission_contract = selection
    semantics = authoritative_semantics(record)
    required_ids, preferred_ids = _requirement_id_groups(scoped)
    generation_contract = {
        **omission_contract,
        "experience_contract": experience_generation_contract(
            semantics["experience_requirement"]
        ),
        "core_requirement_ids": required_ids,
        "preferred_requirement_ids": preferred_ids,
        "allowed_companies": [
            "某科技企业",
            "某互联网企业",
            "某制造企业",
            "某软件企业",
            "某研究机构",
        ],
        "summary_chars": [60, 150],
        "skills_count": [8, 15],
        "work_experiences_count": [1, 3],
        "projects_count": [1, 2],
        "details_count": [2, 4],
    }
    payload = {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "prompt_version": REPAIR_PROMPT_VERSION,
        "jd_id": jd_id,
        "job_title": job_title,
        "responsibilities": [
            _text(value) for value in record.get("responsibilities", []) if _text(value)
        ],
        "numbered_requirements": scoped,
        "education_metadata": record.get("education"),
        "authoritative_experience_requirement": semantics[
            "experience_requirement"
        ],
        "authoritative_seniority": semantics["seniority"],
        "h1_omitted_requirement": hard_requirement,
        "generation_contract": generation_contract,
    }
    return PreparedRepairInput(
        payload, source, hard_requirement, generation_contract
    )


def _fallback_omission_target(
    record: dict[str, Any],
    requirements: list[dict[str, str]],
) -> tuple[str, str]:
    candidates: list[tuple[tuple[int, ...], str, str]] = []
    sources = (
        (
            "responsibility",
            [
                _text(value)
                for value in record.get("responsibilities", [])
                if _text(value)
            ],
        ),
        (
            "requirement",
            [
                _text(value.get("text"))
                for value in requirements
                if _text(value.get("text"))
            ],
        ),
    )
    for source_index, (source, values) in enumerate(sources):
        for index, text in enumerate(values):
            if (
                len(re.sub(r"[\W_]", "", text)) < 4
                or HEADING_RE.fullmatch(text)
                or INFORMATIONAL_RE.search(text)
            ):
                continue
            anchors = requirement_anchors(text)
            score = (
                int(bool(anchors)),
                min(len(anchors), 5),
                int(bool(ACTION_RE.search(text))),
                int(bool(PROJECT_RE.search(text))),
                int(source == "responsibility"),
                int(10 <= len(text) <= 120),
                -source_index,
                -index,
            )
            candidates.append((score, source, text))
    if candidates:
        _, source, text = max(candidates, key=lambda item: item[0])
        return source, text[:180]
    job_title = _text(record.get("job_title"))
    if not job_title:
        raise ValueError("missing_fallback_omission_target")
    return "job_title", f"具有“{job_title}”岗位核心业务场景的直接实践经历"


def prepare_repair_input_with_fallback(
    record: dict[str, Any],
) -> PreparedRepairInput:
    """Prepare every usable JD, falling back to an adjacent-profile target."""

    try:
        return prepare_repair_input(record)
    except ValueError as exc:
        if str(exc) != "no_reliable_atomic_hard_requirement":
            raise

    jd_id = _text(record.get("jd_id"))
    job_title = _text(record.get("job_title"))
    jd_text = _text(record.get("jd_text"))
    if not jd_id:
        raise ValueError("missing_jd_id")
    if not job_title or not jd_text:
        raise ValueError("missing_job_title_or_jd_text")

    requirements, original_source = numbered_requirements(record)
    scoped = scoped_requirements(requirements)
    target_source, target_text = _fallback_omission_target(record, scoped)
    hard_requirement = {
        "id": "F1",
        "text": (
            "相邻候选人区分项："
            f"{target_text}"
        ),
    }
    fallback_anchors = requirement_anchors(target_text)[:5]
    omission_contract = {
        "kind": "fallback_adjacent_profile",
        "omitted_requirement_id": "F1",
        "omitted_requirement_text": hard_requirement["text"],
        "positive_evidence_groups": (
            positive_evidence_groups(target_text, fallback_anchors)
            if fallback_anchors
            else []
        ),
        "h1_forbidden_terms": fallback_anchors,
        "education_min_degree": None,
        "require_work_or_project_evidence": bool(fallback_anchors),
        "fallback_target_source": target_source,
        "fallback_reason": "no_reliable_atomic_hard_requirement",
        "fallback_instruction": (
            "P1/P2应体现该核心职责或场景；H1保持同一大领域，"
            "但采用相邻职责、相邻业务场景或相邻技术路径，"
            "不要在正文中解释自己缺少该能力。"
        ),
    }
    semantics = authoritative_semantics(record)
    required_ids, preferred_ids = _requirement_id_groups(scoped)
    generation_contract = {
        **omission_contract,
        "experience_contract": experience_generation_contract(
            semantics["experience_requirement"]
        ),
        "core_requirement_ids": [*required_ids, "F1"],
        "preferred_requirement_ids": preferred_ids,
        "allowed_companies": [
            "某科技企业",
            "某互联网企业",
            "某制造企业",
            "某软件企业",
            "某研究机构",
        ],
        "summary_chars": [60, 150],
        "skills_count": [8, 15],
        "work_experiences_count": [1, 3],
        "projects_count": [1, 2],
        "details_count": [2, 4],
    }
    payload = {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "prompt_version": REPAIR_PROMPT_VERSION,
        "jd_id": jd_id,
        "job_title": job_title,
        "responsibilities": [
            _text(value)
            for value in record.get("responsibilities", [])
            if _text(value)
        ],
        "numbered_requirements": [*scoped, hard_requirement],
        "education_metadata": record.get("education"),
        "authoritative_experience_requirement": semantics[
            "experience_requirement"
        ],
        "authoritative_seniority": semantics["seniority"],
        "h1_omitted_requirement": hard_requirement,
        "generation_contract": generation_contract,
    }
    return PreparedRepairInput(
        payload=payload,
        requirement_source=f"fallback_{target_source}:{original_source}",
        hard_requirement=hard_requirement,
        omission_contract=generation_contract,
    )


def repair_request(
    record: dict[str, Any],
    *,
    failure_reason: str,
    previous_output: Any,
    previous_h1_omitted_requirement: dict[str, str] | None,
    target_requirement_id: str | None = None,
    attempt: int = 1,
    request_kind: str = "repair",
) -> tuple[dict[str, Any], PreparedRepairInput]:
    if attempt != 1:
        raise ValueError("repair v2.1 currently supports attempt=1")
    prepared = prepare_repair_input(
        record,
        target_requirement_id=target_requirement_id,
    )
    previous_text = (
        previous_output
        if isinstance(previous_output, str)
        else (
            json.dumps(
                previous_output,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if previous_output is not None
            else None
        )
    )
    envelope = {
        "task": "generate_or_repair_structured_resume_triplet",
        "request_kind": request_kind,
        "authoritative_input": prepared.payload,
        "repair_context": {
            "failure_reason": failure_reason,
            "previous_h1_omitted_requirement": previous_h1_omitted_requirement,
            "corrected_h1_omitted_requirement": prepared.hard_requirement,
            "previous_invalid_output": previous_text,
            "instruction": (
                "旧输出只用于定位错误。以authoritative_input和"
                "generation_contract为准，从头生成完整JSON。"
            ),
        },
    }
    request = {
        "custom_id": (
            f"resume-structured-direct-{prepared.payload['jd_id']}-v2-r1"
        ),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": REPAIR_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": REPAIR_TEMPERATURE,
            "top_p": REPAIR_TOP_P,
            "max_tokens": REPAIR_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请严格依据以下唯一权威输入生成最终JSON：\n"
                        + json.dumps(
                            envelope,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            ],
        },
    }
    return request, prepared


def fresh_generation_request(
    record: dict[str, Any],
    *,
    target_requirement_id: str | None = None,
) -> tuple[dict[str, Any], PreparedRepairInput]:
    """Build one clean v2.1 request without retry history."""

    prepared = prepare_repair_input(
        record,
        target_requirement_id=target_requirement_id,
    )
    return fresh_generation_request_from_prepared(prepared)


def fresh_generation_request_from_prepared(
    prepared: PreparedRepairInput,
) -> tuple[dict[str, Any], PreparedRepairInput]:
    """Build one clean v2.1 request from an already prepared contract."""

    envelope = {
        "task": "generate_structured_resume_triplet",
        "request_kind": "fresh",
        "authoritative_input": prepared.payload,
        "generation_context": {
            "instruction": (
                "以authoritative_input和generation_contract为唯一依据，"
                "从头生成完整JSON。"
            )
        },
    }
    request = {
        "custom_id": (
            f"resume-structured-direct-{prepared.payload['jd_id']}-v2_1"
        ),
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": REPAIR_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": REPAIR_TEMPERATURE,
            "top_p": REPAIR_TOP_P,
            "max_tokens": REPAIR_MAX_TOKENS,
            "messages": [
                {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "请严格依据以下唯一权威输入生成最终JSON：\n"
                        + json.dumps(
                            envelope,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                },
            ],
        },
    }
    return request, prepared


def request_envelope(request: dict[str, Any]) -> dict[str, Any] | None:
    body = request.get("body")
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list) or len(messages) != 2:
        return None
    user = messages[1]
    content = user.get("content") if isinstance(user, dict) else None
    if not isinstance(content, str) or "\n" not in content:
        return None
    try:
        value = json.loads(content.split("\n", 1)[1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def prepared_from_request(request: dict[str, Any]) -> PreparedRepairInput:
    envelope = request_envelope(request)
    if envelope is None:
        raise ValueError("invalid_repair_request_envelope")
    payload = envelope.get("authoritative_input")
    if not isinstance(payload, dict):
        raise ValueError("missing_authoritative_input")
    hard = payload.get("h1_omitted_requirement")
    contract = payload.get("generation_contract")
    if not isinstance(hard, dict) or not isinstance(contract, dict):
        raise ValueError("missing_repair_contract")
    return PreparedRepairInput(
        payload=payload,
        requirement_source="embedded_repair_request",
        hard_requirement={"id": str(hard["id"]), "text": str(hard["text"])},
        omission_contract=contract,
    )


def validate_repair_requests(
    requests: Iterable[dict[str, Any]],
) -> list[str]:
    values = list(requests)
    errors: list[str] = []
    custom_ids: list[str] = []
    for index, request in enumerate(values, 1):
        prefix = f"line {index}"
        custom_id = request.get("custom_id")
        if not isinstance(custom_id, str) or not V2_1_CUSTOM_ID_RE.fullmatch(
            custom_id
        ):
            errors.append(f"{prefix}:invalid_custom_id")
        else:
            custom_ids.append(custom_id)
        if request.get("method") != "POST":
            errors.append(f"{prefix}:invalid_method")
        if request.get("url") != "/v1/chat/completions":
            errors.append(f"{prefix}:invalid_url")
        body = request.get("body")
        if not isinstance(body, dict):
            errors.append(f"{prefix}:missing_body")
            continue
        expected = {
            "model": REPAIR_MODEL,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "temperature": REPAIR_TEMPERATURE,
            "top_p": REPAIR_TOP_P,
            "max_tokens": REPAIR_MAX_TOKENS,
        }
        for key, value in expected.items():
            if body.get(key) != value:
                errors.append(f"{prefix}:invalid_{key}")
        messages = body.get("messages")
        if (
            not isinstance(messages, list)
            or len(messages) != 2
            or messages[0] != {"role": "system", "content": REPAIR_SYSTEM_PROMPT}
        ):
            errors.append(f"{prefix}:invalid_messages")
            continue
        envelope = request_envelope(request)
        if envelope is None:
            errors.append(f"{prefix}:invalid_envelope")
            continue
        try:
            prepared = prepared_from_request(request)
        except (KeyError, ValueError) as exc:
            errors.append(f"{prefix}:{exc}")
            continue
        expected_jd = v2_1_custom_id_jd_id(custom_id)
        if prepared.payload.get("jd_id") != expected_jd:
            errors.append(f"{prefix}:jd_id_mismatch")
        contract = prepared.omission_contract
        if contract.get("omitted_requirement_id") != prepared.hard_requirement["id"]:
            errors.append(f"{prefix}:omission_id_contract_mismatch")
        if contract.get("kind") == "technical_or_domain":
            groups = contract.get("positive_evidence_groups")
            forbidden = contract.get("h1_forbidden_terms")
            if (
                not isinstance(groups, list)
                or not groups
                or not isinstance(forbidden, list)
                or not forbidden
            ):
                errors.append(f"{prefix}:empty_evidence_contract")
        request_kind = envelope.get("request_kind")
        if request_kind in {"repair", "replacement"}:
            repair_context = envelope.get("repair_context")
            if not isinstance(repair_context, dict) or not _text(
                repair_context.get("failure_reason")
            ):
                errors.append(f"{prefix}:missing_failure_reason")
        elif request_kind == "fresh":
            generation_context = envelope.get("generation_context")
            if not isinstance(generation_context, dict) or not _text(
                generation_context.get("instruction")
            ):
                errors.append(f"{prefix}:missing_generation_instruction")
        else:
            errors.append(f"{prefix}:invalid_request_kind")
        content = "\n".join(
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict)
        )
        if "JSON" not in content and "json" not in content:
            errors.append(f"{prefix}:messages_missing_json_keyword")
    duplicates = sorted(
        custom_id
        for custom_id, count in Counter(custom_ids).items()
        if count > 1
    )
    if duplicates:
        errors.append(f"duplicate_custom_ids:{duplicates}")
    return errors


def v2_1_custom_id_jd_id(custom_id: str) -> str | None:
    match = V2_1_CUSTOM_ID_RE.fullmatch(str(custom_id or ""))
    return match.group(1) if match else None


def _resume_search_text(resume: dict[str, Any], *, evidence_only: bool) -> str:
    values: list[str] = []
    if not evidence_only:
        values.extend(
            [
                str(resume.get("summary") or ""),
                json.dumps(
                    resume.get("education", {}),
                    ensure_ascii=False,
                ),
                *[str(value) for value in resume.get("skills", [])],
            ]
        )
    for work in resume.get("work_experiences", []):
        if isinstance(work, dict):
            values.extend(str(value) for value in work.get("details", []))
            values.append(str(work.get("role") or ""))
    for project in resume.get("projects", []):
        if isinstance(project, dict):
            values.extend(str(value) for value in project.get("details", []))
            values.extend(str(value) for value in project.get("technologies", []))
            values.extend(
                [str(project.get("name") or ""), str(project.get("role") or "")]
            )
    return "\n".join(values)


def anchor_present(anchor: str, text: str) -> bool:
    pattern = ANCHOR_PATTERN_BY_NAME.get(anchor)
    return bool(pattern.search(text)) if pattern else anchor.casefold() in text.casefold()


def validate_repair_payload(
    value: dict[str, Any],
    prepared: PreparedRepairInput,
) -> tuple[dict[str, dict[str, Any]], int, list[str], dict[str, Any]]:
    legacy = PreparedStructuredInput(
        payload={
            "jd_id": prepared.payload["jd_id"],
            "authoritative_experience_requirement": prepared.payload[
                "authoritative_experience_requirement"
            ],
        },
        requirement_source=prepared.requirement_source,
        hard_requirement=prepared.hard_requirement,
    )
    by_slot, ignored, errors, metrics = validate_structured_resume_payload(
        value, legacy
    )
    if set(by_slot) != set(SLOT_ORDER):
        return by_slot, ignored, errors, metrics
    contract = prepared.omission_contract
    semantic_metrics: dict[str, Any] = {}
    if contract.get("kind") == "education":
        minimum = str(contract.get("education_min_degree") or "")
        minimum_rank = DEGREE_RANK.get(minimum)
        if minimum_rank is not None:
            for slot in ("P1", "P2"):
                degree = by_slot[slot].get("education", {}).get("degree")
                if DEGREE_RANK.get(str(degree), 0) < minimum_rank:
                    errors.append(f"{slot}:missing_positive_education_requirement")
            h1_degree = by_slot["H1"].get("education", {}).get("degree")
            if DEGREE_RANK.get(str(h1_degree), 0) >= minimum_rank:
                errors.append("H1:omitted_education_requirement_present")
    else:
        groups = contract.get("positive_evidence_groups", [])
        forbidden = contract.get("h1_forbidden_terms", [])
        require_evidence = bool(contract.get("require_work_or_project_evidence"))
        for slot in ("P1", "P2"):
            all_text = _resume_search_text(by_slot[slot], evidence_only=False)
            missing_groups = [
                group
                for group in groups
                if not any(anchor_present(str(anchor), all_text) for anchor in group)
            ]
            if missing_groups:
                errors.append(f"{slot}:missing_positive_requirement_evidence")
            evidence_hits: list[str] = []
            if require_evidence:
                evidence_text = _resume_search_text(
                    by_slot[slot], evidence_only=True
                )
                evidence_hits = [
                    anchor
                    for anchor in forbidden
                    if anchor_present(str(anchor), evidence_text)
                ]
                if not evidence_hits:
                    errors.append(
                        f"{slot}:requirement_only_in_summary_or_skills"
                    )
            semantic_metrics[slot] = {
                "missing_positive_groups": missing_groups,
                "work_or_project_evidence_hits": evidence_hits,
            }
        h1_text = _resume_search_text(by_slot["H1"], evidence_only=False)
        h1_hits = [
            anchor
            for anchor in forbidden
            if anchor_present(str(anchor), h1_text)
        ]
        semantic_metrics["H1"] = {"forbidden_anchor_hits": h1_hits}
        if h1_hits:
            errors.append("H1:omitted_requirement_evidence_present")
    metrics["semantic_contract"] = semantic_metrics
    return by_slot, ignored, sorted(set(errors)), metrics


def parse_repair_rows(
    result_rows: Iterable[dict[str, Any]],
    requests: Iterable[dict[str, Any]],
) -> StructuredParseResult:
    request_list = list(requests)
    prepared_by_custom_id = {
        str(request["custom_id"]): prepared_from_request(request)
        for request in request_list
    }
    expected = set(prepared_by_custom_id)
    result = StructuredParseResult()
    seen: set[str] = set()
    successful: set[str] = set()
    usage_total: Counter[str] = Counter()
    valid_usage_total: Counter[str] = Counter()
    for row in result_rows:
        custom_id = str(row.get("custom_id") or "")
        jd_id = v2_1_custom_id_jd_id(custom_id)
        if custom_id not in expected:
            result.ignored_unexpected_rows += 1
            continue
        try:
            body = _response_body(row)
        except ValueError:
            pass
        else:
            usage_total.update(_usage_from_body(body))
            result.api_successful_rows += 1
        if not custom_id or custom_id in seen:
            result.failures.append(
                StructuredParseFailure(
                    custom_id, jd_id, "duplicate_or_missing_custom_id"
                )
            )
            continue
        seen.add(custom_id)
        prepared = prepared_by_custom_id[custom_id]
        try:
            value, usage = _response_content(row)
            by_slot, ignored, errors, metrics = validate_repair_payload(
                value, prepared
            )
            result.ignored_model_label_fields += ignored
            result.quality_metrics[str(prepared.payload["jd_id"])] = metrics
            if errors:
                raise ValueError(",".join(errors))
            valid_usage_total.update(usage)
            result.strict_valid_rows += 1
            successful.add(custom_id)
            jd_id = str(prepared.payload["jd_id"])
            for slot in SLOT_ORDER:
                result.resumes.append(
                    {
                        "resume_id": f"{jd_id}-{slot}",
                        "jd_id": jd_id,
                        "slot": slot,
                        "resume_text": serialize_structured_resume(by_slot[slot]),
                        "omitted_requirement_ids": list(
                            by_slot[slot]["omitted_requirement_ids"]
                        ),
                    }
                )
            result.edges.extend(structured_edges(jd_id))
        except ValueError as exc:
            result.failures.append(
                StructuredParseFailure(custom_id, jd_id, str(exc))
            )
    failed = {failure.custom_id for failure in result.failures}
    for custom_id in sorted(expected - successful - failed):
        result.failures.append(
            StructuredParseFailure(
                custom_id,
                v2_1_custom_id_jd_id(custom_id),
                "missing_result",
            )
        )
    rank = {slot: index for index, slot in enumerate(SLOT_ORDER)}
    result.resumes.sort(key=lambda item: (item["jd_id"], rank[item["slot"]]))
    result.edges.sort(
        key=lambda item: (
            item["jd_id"],
            rank[item["resume_id"].rsplit("-", 1)[1]],
        )
    )
    result.usage = dict(usage_total)
    result.valid_usage = dict(valid_usage_total)
    return result
