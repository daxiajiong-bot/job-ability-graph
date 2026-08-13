# INTERNAL-ONLY — JobTrend 组内完整交付包

本归档由“安全组件包”和“受限真实评测数据”组成。不得将整个归档公开上传或提交 Git；如果需要
对外演示，只分发 `component/`，不要分发 `datasets/`。

## 内容

- `component/`：已经通过 `LOCAL_VALIDATION.json` 的组件、源码、wheel、合成演示输出和文档。
- `datasets/real_eval_2026-08-08/`：2026-08-08 首周 140 条真实 JD、标注模板与审计索引。
- `MANIFEST.sha256`：除自身外，归档中每个文件的 SHA-256。
- `INTERNAL-ONLY.txt`：组内使用标记。

注意：`component/` 根目录的趋势、新岗位和能力更新文件是合成演示产物，不是真实趋势结论。
真实数据目前只有一个采集周，出现 0 个新岗位候选是预期结果。

## 安装与 5 分钟演示

需要 Python 3.11 或更高版本。下列依赖安装通常需要联网；安装完成后的合成演示不访问网络、
不需要 `DASHSCOPE_API_KEY`，也不会产生云费用。

```bash
cd component/source
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps ../dist/trend_discovery_service-0.1.0-py3-none-any.whl

jobtrend --pretty run-all \
  --sources data/samples/sources.yaml \
  --warehouse runs/demo/warehouse \
  --output runs/demo/analysis
```

合成演示预期至少产生 120 个岗位观测、1 个新岗位候选和 1 个岗位能力更新。始终使用独立
`--warehouse`，不要把合成演示与真实数据混入同一仓库。

## 运行真实评测数据

仍在 `component/source` 目录中执行：

```bash
jobtrend ingest \
  --sources ../../datasets/real_eval_2026-08-08/sources.yaml \
  --warehouse runs/real-eval-2026-08-08/warehouse

jobtrend analyze \
  --warehouse runs/real-eval-2026-08-08/warehouse \
  --output runs/real-eval-2026-08-08/analysis
```

## 导入智联历史 JD

历史数据由单一智联来源的 10515 条原始记录清洗得到；过滤 5 条含
联系方式的记录后保留 10510 条。它只能作为历史基线语料，不能作为
多源或真实多周趋势证据。

```bash
jobtrend ingest \
  --sources ../../datasets/historical_zhaopin/sources.yaml \
  --warehouse runs/historical-zhaopin/warehouse
```

请不要将这个 warehouse 与合成演示或真实周快照共用；如果需要联合分析，应先由负责人明确
数据边界和运行配置。历史记录里的旧 `publish_date` 不能替代同批 `scrape_time` 采集周。


图谱始终只读导入；本组件只输出 `kg_link_delta.jsonl`，由图谱负责人审核后合并。云检索必须显式
添加 `--cloud-retrieval`；付费 Batch 还要求 `--execute --confirm SUBMIT_JOBTREND_PAID_BATCH`。

## 校验文件

解压后可在归档根目录校验逐文件哈希：

```bash
shasum -a 256 -c MANIFEST.sha256
```

数据使用限制与标注说明见 `datasets/real_eval_2026-08-08/DATASET_CARD.md` 和
`component/source/docs/annotation_guide.md`。
