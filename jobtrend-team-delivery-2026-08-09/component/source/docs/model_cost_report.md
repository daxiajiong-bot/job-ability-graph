# 模型调用与费用报告

## 本次交付演示

- DashScope Batch 提交：0
- 云 embedding/rerank 调用：0
- 云输入/输出 token：0 / 0
- 估算费用：0 元
- 检索后端：离线特征哈希 + BM25/RRF + Qdrant local

这一结果记录在演示 `manifest.json` 的 `notes.cloud_calls_executed=false`。

## 生产运行记录方式

`prepare` 只写本地 JSONL，费用为 0。`submit` 只有在 `--execute --confirm SUBMIT_JOBTREND_PAID_BATCH` 同时存在时才上传。`download` 会从返回的 usage 累计 token，最终写入 manifest 的 `token_usage` 和 `estimated_cost_cny`。

费用估算必须使用运行当日的阿里云官方计价，不把过期单价硬编码进项目。建议答辩前导出下表：

| 模型 | 请求数 | 输入量 | 输出量 | 当日单价 | 费用 |
|---|---:|---:|---:|---:|---:|
| Flash 抽取 |  |  |  |  |  |
| Plus 失败/冲突和岗位定义 |  |  |  |  |  |
| text-embedding-v4 |  |  | — |  |  |
| qwen3-rerank |  |  | — |  |  |

任何表格记录都不得包含 API key。
