# v3 API Contract

所有 `/api/v1` 成功响应使用 `data` 与 `meta` 信封；`meta` 包含 `request_id`、`api_version`、`implementation`、`persistence`。错误响应使用 `error.code`、`error.message`、`error.details`。

资源接口包括 documents、candidate-profiles、job-profiles、knowledge-graphs、matches 和 reports；能力接口包括 document-retrievals、graph-retrievals、position-discoveries 和 position-deltas。

当前智能接口均返回 `state: "not_implemented"`，空数组或 `score: null`。这些值不是算法结论，客户端必须依据 `state` 与 `implementation` 决定是否展示。
