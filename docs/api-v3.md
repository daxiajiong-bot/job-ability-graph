# v3 API Contract

所有 `/api/v1` 成功响应使用 `data` 与 `meta` 信封；`meta` 包含 `request_id`、`api_version`、`implementation`、`persistence`。错误响应使用 `error.code`、`error.message`、`error.details`。

资源接口包括 documents、candidate-profiles、job-profiles、knowledge-graphs、matches 和 reports；能力接口包括 document-retrievals、graph-retrievals、position-discoveries 和 position-deltas。

`POST /api/v1/documents/ocr` 接收 `multipart/form-data`，必填字段为 `document_type` 与 `file`，可选字段包括 `lang`、`source_system`、`external_id`、`uri`、`published_at`、`metadata_json` 以及 PaddleOCR 参数 `use_doc_orientation_classify`、`use_doc_unwarping`、`use_textline_orientation`、`text_det_limit_side_len`、`text_det_limit_type`、`text_det_thresh`、`text_det_box_thresh`、`text_det_unclip_ratio`、`text_rec_score_thresh`。接口支持常见图片与 PDF，识别出的全文只写入文档资源，不在响应中回显。

OCR 能力使用 `implementation: "paddleocr"`。除 OCR 和文档仓储外，当前智能接口仍返回 `state: "not_implemented"`，空数组或 `score: null`。这些值不是算法结论，客户端必须依据 `state` 与 `implementation` 决定是否展示。
