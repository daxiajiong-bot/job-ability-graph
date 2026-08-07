# JD Parser

独立的 JD 结构化解析项目，只处理 Raw JD 到结构化 JSON、校验结果和固定模板序列化文本。

本项目不依赖旧项目代码、旧 Schema、旧知识图谱、简历解析、人岗匹配、Embedding 或 FAISS。基础抽取不依赖 RAG；当前额外提供本地 RAG 增强模块，用于候选技能召回，并通过原文证据门控防止无依据补全。

## Scope

Pipeline:

```text
Raw JD
-> deterministic cleaning
-> JD fact extraction
-> JD Profile JSON
-> validation
-> deterministic serialization
```

## Outputs

Batch output directory contains:

- `profiles.jsonl`
- `validation_results.jsonl`
- `serialized.jsonl`
- `errors.jsonl`
- `cleaned.jsonl`
- `raw_model_outputs.jsonl`
- `summary.json`

## Commands

Run unit tests:

```bash
cd jd-parser
python -m unittest discover -s tests
```

Prepare the real JD input from a zip and sampled job id list:

```bash
cd jd-parser
python scripts/prepare_real_jd.py ^
  --zip "D:\xwechat_files\wxid_r9xfhwvpziry22_1cbc\msg\file\2026-07\jd_raw_10000.zip" ^
  --exclude-ids "D:\xwechat_files\wxid_r9xfhwvpziry22_1cbc\msg\file\2026-07\jd_1000_job_ids.txt" ^
  --target-count 9000 ^
  --output data/input/jd_remaining_9000.jsonl
```

Run batch extraction:

```bash
cd jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli batch --input data/input/jd_remaining_9000.jsonl --output data/output/real_9000
```

Build the knowledge graph from extracted profiles:

```bash
cd jd-parser
$env:PYTHONPATH = "src"
python -m jd_parser.cli kg --profiles data/output/real_9000/profiles.jsonl --output data/output/kg_real_9000
```

Build the static web visualization:

```bash
cd jd-parser
python scripts/build_kg_web.py
```

Evaluate extraction quality and RAG need:

```bash
cd jd-parser
python scripts/evaluate_extraction.py
```

Run local RAG augmentation with evidence gating:

```bash
cd jd-parser
python scripts/run_rag_augmentation.py
```

Generate sample review report:

```bash
cd jd-parser
$env:PYTHONPATH = "src"
python scripts/run_sample.py
```

## Schema

The minimum profile schema is `jd_profile_v1`:

- `document_id`
- `document_type = "job"`
- `title`
- `responsibilities`
- `requirements`
- `preferred`
- `skills[]` with `name`, `level`, `evidence`
- `constraints.education`
- `constraints.experience_years`
- `constraints.location`
- `raw_text`

Skill level is restricted to `required`, `preferred`, and `mentioned`.

## Knowledge Graph

The KG output uses JSONL files:

- `graph_nodes.jsonl`
- `graph_edges.jsonl`
- `graph_summary.json`
- `validation_report.json`
- `top_skills.csv`
- `sample_subgraph_first_5.html`

Node labels:

- `Job`
- `Skill`
- `Evidence`
- `Education`
- `ExperienceRequirement`
- `Location`

Relation types:

- `REQUIRES_SKILL`
- `PREFERS_SKILL`
- `MENTIONS_SKILL`
- `SUPPORTED_BY`
- `REQUIRES_EDUCATION`
- `REQUIRES_EXPERIENCE`
- `LOCATED_IN`

## Hallucination Control

- Extract only text-supported facts.
- Every skill must include evidence copied from the JD.
- Constraint evidence must exist when the constraint value is non-empty.
- Unknown fields use `null` or `[]`.
- Skill names are not normalized in this stage.
