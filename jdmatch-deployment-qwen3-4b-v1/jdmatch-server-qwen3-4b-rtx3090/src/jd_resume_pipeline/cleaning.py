from __future__ import annotations

import hashlib
import heapq
import re
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable


RESPONSIBILITY_HEADINGS = (
    "岗位职责",
    "工作职责",
    "职位职责",
    "主要职责",
    "职责描述",
    "工作内容",
    "岗位描述",
    "职位描述",
    "你将负责",
)
REQUIREMENT_HEADINGS = (
    "任职要求",
    "岗位要求",
    "职位要求",
    "任职资格",
    "岗位资格",
    "任职条件",
    "招聘要求",
    "岗位条件",
    "基本要求",
    "能力要求",
    "加分要求",
    "加分项",
    "优先条件",
    "优先要求",
    "我们希望",
    "你需要",
)
BENEFIT_HEADINGS = (
    "福利待遇",
    "薪酬福利",
    "薪资福利",
    "福利说明",
    "公司福利",
    "待遇福利",
    "薪资待遇",
)

RESPONSIBILITY_CUES = re.compile(
    r"负责|参与|承担|协助|主导|推进|推动|完成|开发|设计|搭建|优化|维护|研究|跟踪"
)
REQUIREMENT_CUES = re.compile(
    r"熟悉|精通|掌握|具备|具有|本科|硕士|博士|学历|经验|能力|优先|年以上|善于|能够|要求"
)
BENEFIT_CUES = re.compile(
    r"五险|一金|双休|奖金|补贴|团建|年假|节日福利|生日福利|体检|薪资|年终奖|法定节假日"
)

STRONG_TECH_TITLE = re.compile(
    r"算法|软件|开发|研发|程序|架构|机器学习|深度学习|大模型|语言模型|"
    r"自然语言|计算机视觉|机器视觉|图像处理|数据科学|后端|前端|全栈|"
    r"嵌入式|测试开发|测试工程|SRE|DEVOPS|MLOPS|AI工程|人工智能工程|"
    r"智能体|AGENT|NLP|LLM|CV工程|数据工程|云计算|数据库",
    re.IGNORECASE,
)
ALGORITHM_TITLE = re.compile(
    r"算法|机器学习|深度学习|大模型|语言模型|自然语言|计算机视觉|机器视觉|"
    r"图像处理|数据科学|智能体|AGENT|NLP|LLM|推荐|搜索|语音识别|"
    r"语音合成|OCR|强化学习",
    re.IGNORECASE,
)
NON_TECH_TITLE = re.compile(
    r"销售|商务|市场|运营|主播|文案|剪辑|客服|行政|财务|会计|人事|招聘|"
    r"教师|老师|讲师|助教|教研|课程顾问|产品经理|项目经理|设计师|美工|"
    r"媒介|采购|仓库|渠道|投标|咨询顾问|猎头|标注员|审核员|数据标注|"
    r"实习生助理|管培生",
    re.IGNORECASE,
)
EXPLICIT_TECH_ROLE = re.compile(
    r"算法(?:工程师|研发|研究|专家)|软件(?:工程师|开发|研发|架构)|"
    r"(?:开发|研发|测试开发)工程师|架构师|程序员|研究员|科学家|"
    r"机器学习工程师|深度学习工程师|大模型工程师|AI(?:应用)?开发",
    re.IGNORECASE,
)
HARDWARE_ONLY_TITLE = re.compile(
    r"机构设计|结构设计|机械设计|机械工程|电气工程|电气设计|工艺工程|"
    r"制冷|暖通|液冷|水冷|机柜|钣金|模具|硬件工程|射频工程|光学工程|"
    r"芯片设计|集成电路设计|版图设计",
    re.IGNORECASE,
)
GENERIC_TECH_ROLE = re.compile(
    r"工程师|研究员|科学家|技术总监|技术负责人|技术专家|架构师", re.IGNORECASE
)

EVIDENCE_PATTERNS = (
    re.compile(
        r"\bPython\b|\bJava\b|\bC\+\+\b|\bC#\b|\bGo\b|\bGolang\b|"
        r"\bJavaScript\b|\bTypeScript\b|\bSQL\b|\bRust\b|\bScala\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"PyTorch|TensorFlow|Transformers|LangChain|LlamaIndex|Spring|"
        r"\.NET|Django|Flask|FastAPI|React|Vue|Kubernetes|Docker|Linux",
        re.IGNORECASE,
    ),
    re.compile(
        r"机器学习|深度学习|神经网络|大模型|语言模型|计算机视觉|自然语言处理|"
        r"目标检测|推荐系统|搜索算法|强化学习|模型训练|模型部署|模型微调|"
        r"向量数据库|RAG|智能体|数据结构|操作系统|分布式|微服务|数据库",
        re.IGNORECASE,
    ),
    re.compile(
        r"软件开发|代码|编码|接口开发|系统设计|架构设计|自动化测试|性能优化|"
        r"服务端|客户端|前端|后端|嵌入式软件|CI/CD|版本控制",
        re.IGNORECASE,
    ),
)

FAMILY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cv", re.compile(r"计算机视觉|机器视觉|图像|目标检测|分割|OCR|视觉算法", re.I)),
    ("nlp_llm", re.compile(r"大模型|语言模型|NLP|自然语言|RAG|智能体|Agent|Prompt", re.I)),
    ("speech", re.compile(r"语音|ASR|TTS|声学|音频算法", re.I)),
    ("search_recommendation", re.compile(r"推荐|搜索|广告算法|召回|排序", re.I)),
    ("robotics_control", re.compile(r"机器人|自动驾驶|规划算法|控制算法|运动控制|电机控制|SLAM", re.I)),
    ("data_ml", re.compile(r"机器学习|数据科学|数据挖掘|预测模型|风控算法", re.I)),
    ("embedded", re.compile(r"嵌入式|单片机|MCU|RTOS|驱动开发", re.I)),
    ("frontend_mobile", re.compile(r"前端|Web开发|Android|iOS|客户端开发", re.I)),
    ("backend_platform", re.compile(r"后端|服务端|Java开发|Go开发|Python开发|云原生|平台开发", re.I)),
    ("qa_ops", re.compile(r"测试开发|测试工程|运维|SRE|DevOps|MLOps", re.I)),
)

SENIORITY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("expert", re.compile(r"首席|资深专家|科学家|研究员|总监|负责人")),
    ("senior", re.compile(r"高级|资深|Senior|专家", re.I)),
    ("lead", re.compile(r"主管|经理|组长|Leader|架构师", re.I)),
    ("junior", re.compile(r"初级|助理|应届|校招|实习", re.I)),
)


@dataclass(frozen=True)
class ParseResult:
    responsibilities: list[str]
    requirements: list[str]
    benefits: list[str]
    unclassified: list[str]
    parse_method: str


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.size = [1] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.size[left_root] < self.size[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.size[left_root] += self.size[right_root]


def normalize_compact(value: str) -> str:
    value = value.casefold()
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9+#.]+", value))


def canonical_title(value: str) -> str:
    value = re.sub(r"[\(（【\[].*?[\)）】\]]", "", value)
    value = re.sub(r"\b(?:junior|senior|jr|sr)\b", "", value, flags=re.I)
    value = re.sub(r"初级|中级|高级|资深|专家|急聘|双休|五险一金|高薪|校招|社招", "", value)
    value = re.sub(r"[\-/·|_]+", "", value)
    return normalize_compact(value)


def _heading_pattern(headings: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(map(re.escape, sorted(headings, key=len, reverse=True)))
    return re.compile(
        rf"^\s*[【\[(（]?\s*(?:第?[一二三四五六七八九十0-9]+[、.．:：)）]?\s*)?"
        rf"(?:{alternatives})\s*[】\])）]?\s*(?:[:：\-—]\s*)?(.*)$",
        re.IGNORECASE,
    )


RESPONSIBILITY_HEADING_RE = _heading_pattern(RESPONSIBILITY_HEADINGS)
REQUIREMENT_HEADING_RE = _heading_pattern(REQUIREMENT_HEADINGS)
BENEFIT_HEADING_RE = _heading_pattern(BENEFIT_HEADINGS)
ALL_HEADING_TEXT = (
    *RESPONSIBILITY_HEADINGS,
    *REQUIREMENT_HEADINGS,
    *BENEFIT_HEADINGS,
)


def _prepare_lines(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    heading_alt = "|".join(map(re.escape, sorted(ALL_HEADING_TEXT, key=len, reverse=True)))
    text = re.sub(
        rf"(?<!\n)(?=[【\[(（]?\s*(?:第?[一二三四五六七八九十0-9]+[、.．]?\s*)?"
        rf"(?:{heading_alt})\s*[】\])）]?\s*[:：])",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    output: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            continue
        pieces = re.split(r"(?<!\d)(?=\s*[1-9][0-9]?\s*[、.．)）]\s*)", line)
        output.extend(piece.strip() for piece in pieces if piece.strip())
    return output


def _strip_item_prefix(line: str) -> str:
    line = re.sub(
        r"^\s*(?:第?[一二三四五六七八九十]+[、.．)）]|[（(]?[0-9]{1,2}[）)、.．])\s*",
        "",
        line,
    )
    return line.strip(" \t:：;-—")


def parse_jd_text(text: str) -> ParseResult:
    buckets: dict[str, list[str]] = {
        "responsibilities": [],
        "requirements": [],
        "benefits": [],
        "unclassified": [],
    }
    current: str | None = None
    heading_hits = 0

    for line in _prepare_lines(text):
        matched = False
        for name, pattern in (
            ("responsibilities", RESPONSIBILITY_HEADING_RE),
            ("requirements", REQUIREMENT_HEADING_RE),
            ("benefits", BENEFIT_HEADING_RE),
        ):
            match = pattern.match(line)
            if match:
                current = name
                heading_hits += 1
                inline = _strip_item_prefix(match.group(1))
                if inline:
                    buckets[name].append(inline)
                matched = True
                break
        if matched:
            continue

        item = _strip_item_prefix(line)
        if not item:
            continue
        target = current
        if target is None:
            if BENEFIT_CUES.search(item):
                target = "benefits"
            else:
                responsibility_score = len(RESPONSIBILITY_CUES.findall(item))
                requirement_score = len(REQUIREMENT_CUES.findall(item))
                if requirement_score > responsibility_score:
                    target = "requirements"
                elif responsibility_score:
                    target = "responsibilities"
                else:
                    target = "unclassified"
        buckets[target].append(item)

    if not buckets["requirements"]:
        still_responsibilities: list[str] = []
        for item in buckets["responsibilities"]:
            if REQUIREMENT_CUES.search(item) and not RESPONSIBILITY_CUES.search(item):
                buckets["requirements"].append(item)
            else:
                still_responsibilities.append(item)
        buckets["responsibilities"] = still_responsibilities

    method = "section_headings" if heading_hits else "line_cues"
    return ParseResult(
        responsibilities=_dedupe_items(buckets["responsibilities"]),
        requirements=_dedupe_items(buckets["requirements"]),
        benefits=_dedupe_items(buckets["benefits"]),
        unclassified=_dedupe_items(buckets["unclassified"]),
        parse_method=method,
    )


def _dedupe_items(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = normalize_compact(item)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def technical_filter(title: str, jd_text: str) -> tuple[bool, str]:
    title = title.strip()
    combined = f"{title}\n{jd_text}"
    evidence_count = sum(bool(pattern.search(combined)) for pattern in EVIDENCE_PATTERNS)
    strong = bool(STRONG_TECH_TITLE.search(title))
    algorithmic = bool(ALGORITHM_TITLE.search(title))

    if NON_TECH_TITLE.search(title) and not EXPLICIT_TECH_ROLE.search(title):
        return False, "non_technical_title"
    if HARDWARE_ONLY_TITLE.search(title) and not (
        algorithmic or re.search(r"软件|嵌入式|开发|编程", title, re.I)
    ):
        return False, "hardware_or_mechanical_title"
    if len(normalize_compact(jd_text)) < 80:
        return False, "jd_text_too_short"
    if algorithmic:
        return True, "algorithm_or_ai_role"
    if strong and evidence_count >= 1:
        return True, "software_technical_role"
    if GENERIC_TECH_ROLE.search(title) and evidence_count >= 2:
        return True, "generic_technical_role_with_evidence"
    return False, "insufficient_technical_evidence"


def infer_family(title: str, text: str) -> str:
    combined = f"{title}\n{text[:1600]}"
    for family, pattern in FAMILY_RULES:
        if pattern.search(combined):
            return family
    if ALGORITHM_TITLE.search(title):
        return "other_algorithm"
    return "other_software"


def infer_seniority_proxy(title: str, experience: str) -> str:
    for level, pattern in SENIORITY_RULES:
        if pattern.search(title):
            return level
    years = [int(value) for value in re.findall(r"\d+", experience or "")]
    if years:
        minimum = min(years)
        if minimum >= 8:
            return "expert"
        if minimum >= 5:
            return "senior"
        if minimum >= 3:
            return "mid"
        return "junior"
    return "unspecified"


def _shingle_hashes(title: str, text: str, shingle_size: int = 4) -> set[int]:
    normalized = normalize_compact(f"{title}{title}{text}")
    if len(normalized) <= shingle_size:
        return {zlib.crc32(normalized.encode("utf-8")) & 0xFFFFFFFF}
    return {
        zlib.crc32(normalized[index : index + shingle_size].encode("utf-8")) & 0xFFFFFFFF
        for index in range(len(normalized) - shingle_size + 1)
    }


def bottom_k_sketch(title: str, text: str, size: int = 32) -> tuple[int, ...]:
    hashes = _shingle_hashes(title, text)
    return tuple(heapq.nsmallest(size, hashes))


def sketch_similarity(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    denominator = max(1, min(len(left), len(right)))
    return len(set(left).intersection(right)) / denominator


def title_similarity(left: str, right: str) -> float:
    left_norm = canonical_title(left)
    right_norm = canonical_title(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm, autojunk=False).ratio()


def build_candidate_pairs(
    records: list[dict[str, Any]],
    sketches: list[tuple[int, ...]],
    max_bucket_size: int = 180,
) -> set[tuple[int, int]]:
    candidates: set[tuple[int, int]] = set()
    title_buckets: dict[str, list[int]] = defaultdict(list)
    sketch_buckets: dict[int, list[int]] = defaultdict(list)

    for index, (record, sketch) in enumerate(zip(records, sketches)):
        title_buckets[canonical_title(record["job_title"])].append(index)
        for value in sketch:
            sketch_buckets[value].append(index)

    for indexes in title_buckets.values():
        if len(indexes) > 1:
            for offset, left in enumerate(indexes):
                for right in indexes[offset + 1 :]:
                    candidates.add((left, right))

    shared_counts: Counter[tuple[int, int]] = Counter()
    for indexes in sketch_buckets.values():
        if len(indexes) < 2 or len(indexes) > max_bucket_size:
            continue
        for offset, left in enumerate(indexes):
            for right in indexes[offset + 1 :]:
                shared_counts[(left, right)] += 1
    candidates.update(pair for pair, count in shared_counts.items() if count >= 2)
    return candidates


def find_duplicate_components(
    records: list[dict[str, Any]],
    sketches: list[tuple[int, ...]],
    candidates: set[tuple[int, int]],
    near_threshold: float = 0.82,
) -> tuple[UnionFind, dict[tuple[int, int], tuple[float, float]]]:
    union_find = UnionFind(len(records))
    pair_scores: dict[tuple[int, int], tuple[float, float]] = {}
    for left, right in candidates:
        length_left = len(normalize_compact(records[left]["jd_text"]))
        length_right = len(normalize_compact(records[right]["jd_text"]))
        length_ratio = min(length_left, length_right) / max(1, max(length_left, length_right))
        if length_ratio < 0.60:
            continue
        title_score = title_similarity(records[left]["job_title"], records[right]["job_title"])
        if title_score < 0.50:
            continue
        content_score = sketch_similarity(sketches[left], sketches[right])
        pair_scores[(left, right)] = (content_score, title_score)
        if content_score >= near_threshold and (
            title_score >= 0.72 or canonical_title(records[left]["job_title"]) == canonical_title(records[right]["job_title"])
        ):
            union_find.union(left, right)
    return union_find, pair_scores


def select_component_representatives(
    records: list[dict[str, Any]], union_find: UnionFind
) -> tuple[list[int], dict[int, list[int]]]:
    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        components[union_find.find(index)].append(index)

    representatives: list[int] = []
    for indexes in components.values():
        representative = max(
            indexes,
            key=lambda index: (
                bool(records[index]["requirements"]),
                bool(records[index]["responsibilities"]),
                min(len(records[index]["jd_text"]), 2500),
                -index,
            ),
        )
        representatives.append(representative)
    representatives.sort()
    return representatives, components


def build_leakage_clusters(
    records: list[dict[str, Any]],
    representative_indexes: list[int],
    pair_scores: dict[tuple[int, int], tuple[float, float]],
    leakage_threshold: float = 0.56,
) -> dict[int, int]:
    local_index = {original: local for local, original in enumerate(representative_indexes)}
    union_find = UnionFind(len(representative_indexes))
    for (left, right), (content_score, title_score) in pair_scores.items():
        if left not in local_index or right not in local_index:
            continue
        if content_score >= leakage_threshold and title_score >= 0.62:
            union_find.union(local_index[left], local_index[right])

    roots = sorted({union_find.find(index) for index in range(len(representative_indexes))})
    root_to_number = {root: number for number, root in enumerate(roots, 1)}
    return {
        original: root_to_number[union_find.find(local)]
        for original, local in local_index.items()
    }


def assign_cluster_splits(
    cluster_ids: Iterable[int],
    ratios: dict[str, float] | None = None,
) -> dict[int, str]:
    ratios = ratios or {"train": 0.8, "validation": 0.1, "test": 0.1}
    members: dict[int, int] = Counter(cluster_ids)
    total = sum(members.values())
    targets = {name: total * ratio for name, ratio in ratios.items()}
    assigned = {name: 0 for name in ratios}
    output: dict[int, str] = {}

    def stable_tie(cluster_id: int) -> str:
        return hashlib.sha256(f"jd-cluster-v1:{cluster_id}".encode()).hexdigest()

    for cluster_id, size in sorted(members.items(), key=lambda item: (-item[1], stable_tie(item[0]))):
        split = max(
            ratios,
            key=lambda name: (
                (targets[name] - assigned[name]) / max(targets[name], 1),
                -assigned[name],
            ),
        )
        output[cluster_id] = split
        assigned[split] += size
    return output


def clean_raw_records(
    raw_records: list[dict[str, Any]],
    near_threshold: float = 0.82,
    leakage_threshold: float = 0.56,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stats: dict[str, Any] = {
        "raw_records": len(raw_records),
        "invalid_required_fields": 0,
        "exact_duplicates_removed": 0,
        "filtered_non_technical": 0,
        "filter_reasons": Counter(),
        "near_duplicates_removed": 0,
    }
    parsed_records: list[dict[str, Any]] = []
    exact_seen: set[str] = set()

    for raw_index, raw in enumerate(raw_records):
        title = str(raw.get("job_title") or "").strip()
        text = str(raw.get("jd_text") or "").strip()
        if not title or not text or raw.get("job_id") in (None, ""):
            stats["invalid_required_fields"] += 1
            continue
        exact_key = hashlib.sha256(
            f"{normalize_compact(title)}|{normalize_compact(text)}".encode("utf-8")
        ).hexdigest()
        if exact_key in exact_seen:
            stats["exact_duplicates_removed"] += 1
            continue
        exact_seen.add(exact_key)

        keep, reason = technical_filter(title, text)
        if not keep:
            stats["filtered_non_technical"] += 1
            stats["filter_reasons"][reason] += 1
            continue

        parsed = parse_jd_text(text)
        parsed_records.append(
            {
                "_raw_index": raw_index,
                "source_job_id": str(raw["job_id"]),
                "source_name": raw.get("source_name"),
                "job_title": title,
                "jd_text": text,
                "responsibilities": parsed.responsibilities,
                "requirements": parsed.requirements,
                "benefits": parsed.benefits,
                "unclassified": parsed.unclassified,
                "parse_method": parsed.parse_method,
                "location": raw.get("location"),
                "experience": raw.get("experience"),
                "education": raw.get("education"),
                "industry": raw.get("industry"),
                "publish_date": raw.get("publish_date"),
                "job_family_proxy": infer_family(title, text),
                "seniority_proxy": infer_seniority_proxy(title, str(raw.get("experience") or "")),
            }
        )

    sketches = [
        bottom_k_sketch(record["job_title"], record["jd_text"]) for record in parsed_records
    ]
    candidates = build_candidate_pairs(parsed_records, sketches)
    union_find, pair_scores = find_duplicate_components(
        parsed_records, sketches, candidates, near_threshold=near_threshold
    )
    representative_indexes, components = select_component_representatives(
        parsed_records, union_find
    )
    stats["near_duplicates_removed"] = len(parsed_records) - len(representative_indexes)
    stats["near_duplicate_components"] = sum(len(indexes) > 1 for indexes in components.values())
    stats["candidate_pairs_compared"] = len(pair_scores)

    cluster_by_original = build_leakage_clusters(
        parsed_records,
        representative_indexes,
        pair_scores,
        leakage_threshold=leakage_threshold,
    )
    split_by_cluster = assign_cluster_splits(cluster_by_original.values())

    clean_records: list[dict[str, Any]] = []
    for sequence, original_index in enumerate(representative_indexes, 1):
        record = dict(parsed_records[original_index])
        record.pop("_raw_index", None)
        cluster_number = cluster_by_original[original_index]
        record = {
            "jd_id": f"J{sequence:05d}",
            **record,
            "near_dup_cluster_id": f"C{cluster_number:05d}",
            "split": split_by_cluster[cluster_number],
        }
        clean_records.append(record)

    stats["clean_records"] = len(clean_records)
    stats["retention_rate"] = round(len(clean_records) / max(1, len(raw_records)), 6)
    stats["leakage_clusters"] = len(set(cluster_by_original.values()))
    stats["multi_member_leakage_clusters"] = sum(
        size > 1 for size in Counter(cluster_by_original.values()).values()
    )
    stats["split_counts"] = dict(Counter(record["split"] for record in clean_records))
    stats["parse_method_counts"] = dict(
        Counter(record["parse_method"] for record in clean_records)
    )
    stats["missing_parsed_responsibilities"] = sum(
        not record["responsibilities"] for record in clean_records
    )
    stats["missing_parsed_requirements"] = sum(
        not record["requirements"] for record in clean_records
    )
    stats["filter_reasons"] = dict(stats["filter_reasons"])
    stats["near_duplicate_threshold"] = near_threshold
    stats["leakage_cluster_threshold"] = leakage_threshold
    return clean_records, stats
