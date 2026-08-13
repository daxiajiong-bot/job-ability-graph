# AI/大模型岗位趋势与新岗位发现

这是一个独立的 Python 3.11 批处理项目：读取招聘 JD、政策、职业标准和行业报告，输出可审核的趋势特征、新岗位候选、已有岗位能力变化和 append-only 知识图谱增量。它只通过 JSONL/CSV 和队友模块交接，不修改对方代码或图谱 ID。

本项目不包含 REST API、前端、简历解析、人岗匹配或实时网站爬虫。

项目另带一个独立、保守限速的真实评测采集脚本；它不属于生产 `jobtrend` CLI，不提供通用爬虫，也不会登录或绕过网站访问控制。

## 5 分钟离线演示

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'

jobtrend --pretty run-all \
  --sources data/samples/sources.yaml \
  --output runs/demo
```

演示数据包含 120 条合成 JD、2 个招聘来源、8 家企业和 2 份外部支持文档。预期得到一个“AI Agent 安全评测工程师”候选，以及“Java 开发工程师”的 RAG、MCP、大模型 API 能力新增。全过程不需要 API key、不访问网络、不产生云费用。

## 输入

`source_manifest_v1` YAML 中每个条目声明：

- `source_type`: `job` / `policy` / `industry_report` / `occupational_standard`
- `input_format`: `jsonl` / `csv` / `pdf` / `html` / `docx` / `txt` / `url` / `auto`
- `source_id`、`source_name`、`publisher`、`published_at`、`collected_at`、`license`

输入可以是本地文件或公开 HTTP(S) URL。URL 仅允许公网主机，禁止 localhost、内网地址和非 HTTP 协议。扫描 PDF 若文本层覆盖不足会标为 `needs_ocr`，首版不进入自动评分。

历史单一来源 JD 的参考清单在 `sources/team_historical.example.yaml`。它只能作为初始语料，不能单独支撑“多源趋势”结论。`sources/authoritative_sources.yaml` 列出 10 个政策/职业标准和 10 个行业报告条目，默认禁用，必须逐条确认许可与访问频率。

## 固定 CLI

### 1. 采集与时序仓库

```bash
jobtrend ingest --sources input/sources.yaml
```

Parquet 是可重建的权威事实源；DuckDB 是查询镜像；JSONL 是公开交换格式。文档以来源 ID 或 SHA-256 产生稳定 ID，同一清单可重复执行。

### 2. 只读导入队友图谱

```bash
jobtrend import-kg \
  --nodes /kg/graph_nodes.jsonl \
  --edges /kg/graph_edges.jsonl \
  --profiles /kg/profiles.jsonl \
  --output runs/kg-index
```

适配器兼容 `jd_kg_v1` 和 `small-raw-lskt-tech/v2`，验证悬空边并记录整个基线指纹。源图谱仅以读方式打开；它的节点 ID 不会被改写。

### 3. 统计、聚类与联合 RAG

```bash
jobtrend analyze \
  --kg-index runs/kg-index \
  --output runs/2026-W32
```

默认使用离线特征哈希 + BM25/RRF 运行可复现检索，Qdrant 以本地持久化模式保存可重建索引。明确加 `--cloud-retrieval` 后才会使用 `text-embedding-v4` 和 `qwen3-rerank`，该选项会产生云调用费用。

### 4. DashScope Batch

```bash
# 只生成本地 Batch JSONL，默认零费用
jobtrend prepare --kind extraction --output runs/batch-extract

# 对已通过统计门槛的新岗位生成定义请求
jobtrend prepare \
  --kind role-definition \
  --analysis-dir runs/2026-W32 \
  --output runs/batch-role

# 不加 --execute 始终是本地 dry-run
jobtrend submit --state runs/batch-role/batch_state.json

# 只有下面的精确双重确认才会付费提交
jobtrend submit \
  --state runs/batch-role/batch_state.json \
  --execute \
  --confirm SUBMIT_JOBTREND_PAID_BATCH

jobtrend status --state runs/batch-role/batch_state.json
jobtrend download --state runs/batch-role/batch_state.json
```

有费用命令从环境变量读取 `DASHSCOPE_API_KEY`，从不写入日志、manifest 或交付包。Flash 用于普通抽取，Plus 用于定义和失败/冲突样本；thinking 默认关闭。结果必须同时通过 JSON Schema、Pydantic 和证据 ID 白名单。

### 5. 人工审核与交付

```bash
jobtrend review-export --run-dir runs/2026-W32
# 人工填写 decision / reviewer / reviewed_at / edits_json
jobtrend review-import \
  --review runs/2026-W32/review_queue.csv \
  --run-dir runs/2026-W32 \
  --output runs/2026-W32-reviewed

python -m build --wheel
jobtrend export \
  --run-dir runs/2026-W32 \
  --output dist \
  --wheel dist/trend_discovery_service-0.1.0-py3-none-any.whl \
  --source src --source config --source schemas --source docs \
  --source tests --source scripts --source Dockerfile \
  --source pyproject.toml --source requirements.lock --source README.md
```

`review-import` 始终写入新目录，不覆盖原始算法输出。`export` 会扫描本地用户路径、可疑密钥、模型权重和不安全压缩路径，并拒绝包含完整正文的 `source-reference-only` 文档。经人工复核的受限来源最多只允许 3 个带定位、每段不超过 300 字符的必要证据片段，然后生成确定性 `tar.gz`、SHA-256 侧车文件和 `LOCAL_VALIDATION.json`。

## 公开输出契约

| 文件 | 用途 |
|---|---|
| `external_documents.jsonl` | 统一文档与来源元数据 |
| `evidence.jsonl` | 页码/章节/字符范围/原文证据 |
| `trend_features.jsonl` | 岗位/技能时序指标与分项分数 |
| `emerging_roles.jsonl` | 新岗位定义、置信度、证据和审核状态 |
| `job_skill_updates.jsonl` | 新增/上升/修改/下降/删除候选 |
| `review_queue.csv` | 人工批准、驳回或修改入口 |
| `kg_link_delta.jsonl` | 引用原图节点 ID 的 append-only 待审核增量 |
| `manifest.json` | 哈希、图指纹、模型/Prompt、窗口、费用和记录数 |

额外调试产物 `job_observations.jsonl`、`rag_contexts.jsonl` 和 `quality_report.json` 不会修改公开交付契约。

## 判定规则

- 近期窗口 28 天，基线为此前 84 天；各招聘来源先独立计算去重数、来源内份额、增长、EWMA、稳健 z-score、连续性和多样性。
- 新岗位默认要求 8 个去重 JD、3 家企业、2 个真实采集周快照；2 个招聘源，或 1 个招聘源 + 1 个权威文档；已知岗位相似度不高于 0.82；近期份额提升 1.5 倍或零基线达标。`published_at` 仅用于事件时间统计，不能让同一采集批中的历史 JD 满足连续周门槛。
- 新岗位总分固定为新颖度 30%、增长 25%、持续性 20%、来源多样性 15%、证据覆盖 10%，达到 0.65 才输出。
- 已有岗位能力新增/上升要求 5 家企业、10 个百分点、1.5 倍与 BH 多重检验校正。下降只会产生 `removal_candidate`，从不自动删除。
- 纯语义能力映射一律进入审核；只有大小写折叠、人工别名和已批准映射能自动连图。

## Docker

```bash
docker build -t jobtrend:0.1.0 .

docker run --rm \
  -v "$PWD/input:/input:ro" \
  -v "$PWD/kg:/kg:ro" \
  -v "$PWD/output:/output" \
  jobtrend:0.1.0 \
  --config /input/config.yaml run-all \
  --sources /input/sources.yaml \
  --kg-nodes /kg/graph_nodes.jsonl \
  --kg-edges /kg/graph_edges.jsonl \
  --output /output/current
```

容器以非 root 用户运行，工作面只是 `/input`、`/kg`、`/output`。

## 每周运行

首先将每个企业官网的完整快照保存为 `input/jobs/<source>/YYYY-Www.jsonl`，再运行：

```cron
15 3 * * 1 cd /opt/jobtrend && .venv/bin/jobtrend run-all --sources input/sources.yaml >> logs/weekly.log 2>&1
```

`run-all` 将稳定 ID 增量合并到 Parquet，完整重算可审计窗口，只有成功时才更新 `runs/latest_success.json`。

## 真实评测快照

已完成 `2026-08-08` 首个真实快照：腾讯、美团、小米、百度各 32 条，华为 12 条，共 140 条官方招聘 JD；20 条校准、120 条盲测、400 对去重样本。首次离线闭环得到 140 个岗位观测、144 条证据和 110 条趋势特征，结构验证全部通过。

```bash
.venv/bin/python scripts/collect_public_eval.py --keyword 大模型

.venv/bin/python scripts/validate_real_eval.py \
  data/real_eval/snapshots/2026-08-08 \
  --warehouse runs/real-eval-2026-08-08/warehouse \
  --analysis runs/real-eval-2026-08-08/analysis
```

完整 JD、原始响应和本地外部文档仓库均为 `source-reference-only`，只留在忽略的 `private/` / `runs/` 中；交接包只包含无正文的参考索引。当前只有一个真实采集周，所以不能宣称完成时序趋势精度或新岗位 P@10。详见 `data/real_eval/README.md` 和 `docs/real_evaluation.md`。

## 生成组内完整交接包

标准 `jobtrend export` 面向可安全转发的组件，故意排除真实 JD 全文和标注答案。需要把真实评测数据一并交给组员时，先构建并验证标准组件，再用独立的 `INTERNAL-ONLY` 外层打包器：

```bash
# 1. 以 120 条合成样例生成可复现缓存输出
jobtrend --pretty --config config/default.yaml run-all \
  --sources data/samples/sources.yaml \
  --warehouse runs/team-handoff/warehouse \
  --output runs/team-handoff/analysis

# 2. 构建包含源码、wheel、README 和离线演示的安全组件
.venv/bin/python scripts/build_bundle.py \
  --run-dir runs/team-handoff/analysis \
  --output dist/team-component \
  --bundle-name jobtrend-trend-discovery-component-0.1.0

# 3. 组内包再显式加入真实快照、真实运行输出和脱敏历史 JD
.venv/bin/python scripts/build_team_delivery.py \
  --component dist/team-component/jobtrend-trend-discovery-component-0.1.0 \
  --snapshot data/real_eval/snapshots/2026-08-08 \
  --analysis-dir runs/real-eval-2026-08-08/analysis \
  --historical-jd /path/to/jd_raw.jsonl \
  --output dist/team-delivery
```

完整包包含 120 条合成 JD、5 家官网的 140 条真实 JD、清除 5 条联系方式后保留的 10,510 条智联历史 JD、20 份权威政策/报告的 URL 与解析审计索引、标注模板以及首周真实分析输出。它不包含原始 HTTP 响应、政策/报告全文、API key、warehouse/DuckDB/Qdrant、模型权重或队友知识图谱。

外层归档仅限项目组内部使用，不得上传公开仓库或公开网盘。解压后先阅读顶层 `README.md`，并在归档根目录运行 `shasum -a 256 -c MANIFEST.sha256`；只需对外展示组件时，仅发送内层标准组件归档。

## 测试与诚信验收

```bash
pytest
pytest --cov=trend_discovery --cov-report=term-missing
```

当前自动测试覆盖解析、稳定 ID、去重、Parquet/DuckDB、两套图谱 Schema、聚类与时序统计、证据检索、Batch 失败/重试/限流/断点/非法 JSON、审核、CLI 和交付安全。

合成 fixture 只证明程序可复现，不冒充真实业务精度。赛题的字段/技能 P/R/F1、近重 Precision、RAG Recall@20、新岗位 P@10 和技能变化 F1 必须在两人独立标注、仲裁及真实周快照完成后才能填写。详见 `docs/annotation_guide.md` 和 `docs/acceptance_status.md`。

## 更多文档

- `docs/architecture.md`：与图谱/RAG/人工审核的责任边界。
- `docs/data_sources.md`：周快照、时间语义、许可和再分发。
- `docs/annotation_guide.md`：双人标注、仲裁与时间切分。
- `docs/acceptance_status.md`：自动验证与必须由团队完成的真实验收项。
- `docs/test_report.md`：测试、覆盖率、wheel 安装和图谱适配验证。
- `docs/model_cost_report.md`：云调用计数、演示费用与生产计费记录方法。
- `docs/real_evaluation.md`：真实官网采集结果、评测拆分、外部证据状态与可声称边界。
