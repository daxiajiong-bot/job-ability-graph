import { useState, useEffect } from "react";
import {
  Card,
  Typography,
  Select,
  Button,
  Space,
  Tag,
  Spin,
  message,
  Row,
  Col,
  InputNumber,
  Input,
  Empty,
  Modal,
  Divider,
  Radio,
  Collapse,
} from "antd";
import {
  StarOutlined,
  FileTextOutlined,
  UserOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
  RocketOutlined,
  FilterOutlined,
  ReloadOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  listUserDocuments,
  autoMatch,
  initUser,
} from "../api/client";
import RecommendList from "../components/RecommendList";
import GapChart from "../components/GapChart";
import LearningAdvice from "../components/LearningAdvice";
import useStore from "../store/useStore";

const { Title, Paragraph, Text } = Typography;

export default function RecommendPage() {
  const {
    userId,
    initUserId,
    user,
    settings,
    recommendCache,
    lastRecommendDocId,
    saveRecommendation,
    setLastRecommendDocId,
  } = useStore();
  const role = user?.role || "job_seeker";

  // 恢复上次查看文档的推荐状态（点击其他页面再回来时直接展示，无需重新生成）
  // 仅恢复与当前缓存版本匹配的结果（逻辑升级后旧结果自动失效）
  const restored =
    lastRecommendDocId && recommendCache[lastRecommendDocId]?.version === 2
      ? recommendCache[lastRecommendDocId]
      : null;

  // ── 状态 ──
  const [loading, setLoading] = useState(false);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(
    restored?.documentId || null
  );
  const [topN, setTopN] = useState(restored?.topN || 5);
  const [direction, setDirection] = useState(
    restored?.direction || (role === "hr" ? "jd_to_resume" : "resume_to_jd")
  );
  const [recommendations, setRecommendations] = useState(
    restored?.recommendations || []
  );
  const [meta, setMeta] = useState(
    restored
      ? { ...(restored.meta || {}), cached: true, cached_at: new Date(restored.savedAt).toISOString() }
      : null
  );
  const [inputDocument, setInputDocument] = useState(
    restored?.inputDocument || null
  );
  const [detailModal, setDetailModal] = useState(null);
  // 筛选条件
  const [filters, setFilters] = useState(
    restored?.filters || {
      location: "",
      industry: "",
      keyword: "",
      salary_min: null,
      max_per_company: 2,
    }
  );

  // ── 页面加载 ──
  useEffect(() => {
    const uid = initUserId();
    async function bootstrap() {
      try {
        await initUser();
      } catch {}
      await loadDocuments(uid);
    }
    bootstrap();
  }, [direction]);

  async function loadDocuments(uid) {
    setDocumentsLoading(true);
    try {
      const docType = direction === "resume_to_jd" ? "resume" : "jd";
      const res = await listUserDocuments(uid || userId, docType, 0, 200);
      const items = res.data.data.items || [];
      // 过滤系统种子数据
      const userDocs = items.filter(
        (d) => !d.id.startsWith("sys_") && !d.document_id?.startsWith("sys_")
      );
      setDocuments(userDocs);
    } catch (e) {
      console.warn("加载文档失败:", e);
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function handleRecommend() {
    if (!selectedDocId) {
      message.warning("请先选择一个文档");
      return;
    }
    setLoading(true);
    setRecommendations([]);
    setMeta(null);
    setInputDocument(null);
    try {
      // 仅传递非空筛选条件
      const activeFilters = {};
      if (filters.location) activeFilters.location = filters.location;
      if (filters.industry) activeFilters.industry = filters.industry;
      if (filters.keyword) activeFilters.keyword = filters.keyword;
      if (filters.salary_min) activeFilters.salary_min = filters.salary_min;

      const res = await autoMatch(
        selectedDocId,
        topN,
        activeFilters,
        filters.max_per_company || 0
      );
      const data = res.data.data;
      setRecommendations(data.recommendations || []);
      setMeta(data.meta || null);
      setInputDocument(data.input_document || null);
      // 保存本次推荐结果（按文档持久化，返回页面/再次查询时免重新生成）
      saveRecommendation(selectedDocId, {
        documentId: selectedDocId,
        direction,
        topN,
        filters,
        maxPerCompany: filters.max_per_company || 0,
        recommendations: data.recommendations || [],
        meta: data.meta || null,
        inputDocument: data.input_document || null,
        savedAt: Date.now(),
      });
      if (!data.recommendations?.length) {
        message.info(data.message || "暂无匹配的推荐结果");
      }
    } catch (e) {
      message.error(
        "智能推荐失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
  }

  function resetFilters() {
    setFilters({
      location: "",
      industry: "",
      keyword: "",
      salary_min: null,
      max_per_company: 2,
    });
    message.info("筛选条件已重置");
  }

  // ── 推荐类型标签 ──
  const recommendType = direction === "resume_to_jd" ? "jd" : "resume";

  // ── 文档选项 ──
  const docOptions = documents.map((d) => {
    const docId = d.document_id || d.id;
    const title =
      d.title ||
      (direction === "resume_to_jd"
        ? "简历文档"
        : "JD 文档");
    return {
      value: docId,
      label: `${title} (${docId.slice(0, 8)}...)`,
      doc: d,
    };
  });

  // ── 匹配分数颜色 ──
  function getScoreColor(score) {
    if (score >= 80) return "#52c41a";
    if (score >= 60) return "#4dd6ff";
    if (score >= 40) return "#faad14";
    return "#ff4d4f";
  }

  // ── 雷达图配置 ──
  function getRadarOption(matchData) {
    if (!matchData) return {};
    const score = matchData.score ?? 0;
    const details = matchData.details || {};
    const dims = [
      { name: "技能匹配", max: 100 },
      { name: "知识匹配", max: 100 },
      { name: "经验匹配", max: 100 },
      { name: "通用能力", max: 100 },
      { name: "综合得分", max: 100 },
    ];
    const values = [
      details.skill_score ?? score,
      details.knowledge_score ?? Math.max(0, score - 10),
      details.experience_score ?? Math.max(0, score - 5),
      details.ability_score ?? Math.max(0, score - 15),
      score,
    ];
    const isDark = settings.theme === "dark";

    return {
      tooltip: { trigger: "item" },
      radar: {
        indicator: dims,
        shape: "polygon",
        splitNumber: 5,
        radius: "60%",
        center: ["50%", "55%"],
        splitArea: {
          areaStyle: {
            color: [
              "rgba(77, 214, 255, 0.02)",
              "rgba(77, 214, 255, 0.04)",
              "rgba(77, 214, 255, 0.02)",
              "rgba(77, 214, 255, 0.04)",
              "rgba(77, 214, 255, 0.02)",
            ],
          },
        },
        axisLine: { lineStyle: { color: "rgba(77, 214, 255, 0.15)" } },
        splitLine: {
          lineStyle: { color: "rgba(77, 214, 255, 0.08)", type: "dashed" },
        },
        axisName: {
          color: isDark ? "#8b949e" : "#666",
          fontSize: 12,
          fontWeight: 500,
        },
      },
      animationDuration: 1200,
      animationEasing: "cubicOut",
      series: [
        {
          type: "radar",
          data: [
            {
              value: values,
              name: "匹配度",
              symbol: "circle",
              symbolSize: 8,
              areaStyle: {
                color: {
                  type: "radial",
                  x: 0.5,
                  y: 0.5,
                  r: 0.5,
                  colorStops: [
                    { offset: 0, color: "rgba(77, 214, 255, 0.3)" },
                    { offset: 1, color: "rgba(123, 97, 255, 0.05)" },
                  ],
                },
              },
              lineStyle: {
                color: "#4dd6ff",
                width: 2.5,
                shadowColor: "rgba(77, 214, 255, 0.4)",
                shadowBlur: 8,
              },
              itemStyle: {
                color: "#4dd6ff",
                borderColor: "#fff",
                borderWidth: 2,
              },
            },
          ],
        },
      ],
    };
  }

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <StarOutlined style={{ marginRight: 8, color: "#faad14" }} />
          智能推荐
        </Title>
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
          基于大模型与知识图谱，智能匹配最适合的
          {direction === "resume_to_jd" ? "岗位" : "候选人"}
        </Paragraph>
      </div>

      {/* 配置区 */}
      <Card className="gradient-border" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          {/* 推荐方向 */}
          <Col xs={24} sm={8} md={6}>
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                推荐方向
              </Text>
            </div>
            <Radio.Group
              value={direction}
              onChange={(e) => {
                setDirection(e.target.value);
                setSelectedDocId(null);
                setRecommendations([]);
                setMeta(null);
                setInputDocument(null);
              }}
              optionType="button"
              buttonStyle="solid"
              size="small"
            >
              <Radio.Button value="resume_to_jd">
                <UserOutlined /> 简历→JD
              </Radio.Button>
              <Radio.Button value="jd_to_resume">
                <FileTextOutlined /> JD→简历
              </Radio.Button>
            </Radio.Group>
          </Col>

          {/* 文档选择 */}
          <Col xs={24} sm={10} md={10}>
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                选择{direction === "resume_to_jd" ? "简历" : "JD"}文档
              </Text>
            </div>
            <Select
              showSearch
              placeholder={`选择一个${direction === "resume_to_jd" ? "简历" : "JD"}文档`}
              style={{ width: "100%" }}
              value={selectedDocId}
              onChange={(id) => {
                setSelectedDocId(id);
                setLastRecommendDocId(id);
                // 该文档若已有保存的推荐结果，直接展示（免重新生成）
                const cached = recommendCache[id];
                if (cached?.version === 2 && cached.direction === direction) {
                  setRecommendations(cached.recommendations || []);
                  setMeta({
                    ...(cached.meta || {}),
                    cached: true,
                    cached_at: new Date(cached.savedAt).toISOString(),
                  });
                  setInputDocument(cached.inputDocument || null);
                  if (cached.topN) setTopN(cached.topN);
                  if (cached.filters) setFilters(cached.filters);
                } else {
                  setRecommendations([]);
                  setMeta(null);
                  setInputDocument(null);
                }
              }}
              loading={documentsLoading}
              options={docOptions}
              filterOption={(input, option) =>
                (option?.label ?? "")
                  .toLowerCase()
                  .includes(input.toLowerCase())
              }
              notFoundContent={
                documentsLoading ? (
                  <Spin size="small" />
                ) : (
                  <Empty
                    description={`暂无${direction === "resume_to_jd" ? "简历" : "JD"}文档，请先上传`}
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  />
                )
              }
            />
          </Col>

          {/* 推荐数量 */}
          <Col xs={12} sm={3} md={4}>
            <div style={{ marginBottom: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                推荐数量
              </Text>
            </div>
            <InputNumber
              min={1}
              max={20}
              value={topN}
              onChange={(v) => setTopN(v || 5)}
              style={{ width: "100%" }}
            />
          </Col>

          {/* 推荐按钮 */}
          <Col xs={12} sm={3} md={4}>
            <div style={{ marginBottom: 4 }}>&nbsp;</div>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={loading}
              disabled={!selectedDocId}
              onClick={handleRecommend}
              style={{
                width: "100%",
                height: 36,
                background: loading
                  ? undefined
                  : "linear-gradient(135deg, #faad14, #ff7a45)",
                border: "none",
                fontWeight: 600,
              }}
            >
              {loading ? "推荐中..." : "开始推荐"}
            </Button>
          </Col>
        </Row>

        {/* 提示 */}
        <div
          style={{
            marginTop: 12,
            padding: "10px 14px",
            background: "linear-gradient(135deg, rgba(250, 173, 20, 0.06) 0%, rgba(123, 97, 255, 0.04) 100%)",
            borderRadius: 8,
            border: "1px solid rgba(250, 173, 20, 0.1)",
          }}
        >
          <Text
            type="secondary"
            style={{ fontSize: 12, lineHeight: 1.8 }}
          >
            <RocketOutlined
              style={{ marginRight: 6, color: "#faad14" }}
            />
            选择一份{direction === "resume_to_jd" ? "简历" : "JD"}文档，系统将自动从已有的
            {direction === "resume_to_jd" ? "JD" : "简历"}库中检索最佳匹配，基于技能重叠度和大模型语义分析生成推荐排名。
          </Text>
        </div>

        {/* 高级筛选 */}
        <Collapse
          ghost
          style={{ marginTop: 8 }}
          items={[
            {
              key: "filters",
              label: (
                <Space size={6}>
                  <FilterOutlined style={{ color: "#4dd6ff" }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    高级筛选
                  </Text>
                </Space>
              ),
              children: (
                <Row gutter={[16, 12]}>
                  <Col xs={24} sm={12} md={6}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      工作地点
                    </Text>
                    <Input
                      size="small"
                      placeholder="如：北京 / 上海"
                      value={filters.location}
                      onChange={(e) =>
                        setFilters({ ...filters, location: e.target.value })
                      }
                      allowClear
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      行业
                    </Text>
                    <Input
                      size="small"
                      placeholder="如：互联网 / 金融"
                      value={filters.industry}
                      onChange={(e) =>
                        setFilters({ ...filters, industry: e.target.value })
                      }
                      allowClear
                    />
                  </Col>
                  <Col xs={24} sm={12} md={6}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      关键词
                    </Text>
                    <Input
                      size="small"
                      placeholder="标题/正文包含"
                      value={filters.keyword}
                      onChange={(e) =>
                        setFilters({ ...filters, keyword: e.target.value })
                      }
                      allowClear
                    />
                  </Col>
                  <Col xs={12} sm={6} md={3}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      最低月薪 (k)
                    </Text>
                    <InputNumber
                      size="small"
                      min={0}
                      max={200}
                      style={{ width: "100%" }}
                      placeholder="如：15"
                      value={filters.salary_min}
                      onChange={(v) =>
                        setFilters({ ...filters, salary_min: v })
                      }
                    />
                  </Col>
                  <Col xs={12} sm={6} md={3}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      每公司上限
                    </Text>
                    <InputNumber
                      size="small"
                      min={0}
                      max={10}
                      style={{ width: "100%" }}
                      placeholder="0=不限"
                      value={filters.max_per_company}
                      onChange={(v) =>
                        setFilters({ ...filters, max_per_company: v || 0 })
                      }
                    />
                  </Col>
                  <Col span={24} style={{ textAlign: "right" }}>
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={resetFilters}
                    >
                      重置筛选
                    </Button>
                  </Col>
                </Row>
              ),
            },
          ]}
        />
      </Card>

      {/* 输入文档摘要 */}
      {inputDocument && (
        <Card
          size="small"
          style={{ marginBottom: 16 }}
          className="fade-in-up"
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: 10,
                background:
                  "linear-gradient(135deg, rgba(250, 173, 20, 0.15), rgba(123, 97, 255, 0.08))",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 18,
                color: "#faad14",
              }}
            >
              {direction === "resume_to_jd" ? (
                <UserOutlined />
              ) : (
                <FileTextOutlined />
              )}
            </div>
            <div style={{ flex: 1 }}>
              <Text strong style={{ fontSize: 14 }}>
                {inputDocument.title || "输入文档"}
              </Text>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  文档 ID: {inputDocument.document_id || inputDocument.id}{" "}
                  · 类型:{" "}
                  {inputDocument.document_type === "resume"
                    ? "简历"
                    : "JD"}
                </Text>
              </div>
            </div>
            <Tag color="gold" icon={<TrophyOutlined />}>
              基准文档
            </Tag>
          </div>
        </Card>
      )}

      {/* 推荐结果 */}
      <Spin spinning={loading}>
        {recommendations.length > 0 ? (
          <Card
            title={
              <Space>
                <StarOutlined style={{ color: "#faad14" }} />
                <span>
                  推荐结果 · 共 {recommendations.length} 个匹配
                </span>
              </Space>
            }
            extra={
              meta && (
                <Space size={4} wrap>
                  {meta.cached !== undefined && (
                    <Tag
                      color={meta.cached ? "cyan" : "green"}
                      icon={
                        meta.cached ? <SaveOutlined /> : <ThunderboltOutlined />
                      }
                    >
                      {meta.cached ? "已保存的推荐" : "本次新生成"}
                    </Tag>
                  )}
                  <Tag color="blue">候选池 {meta.pool_size}</Tag>
                  <Tag color={meta.ranking === "matcher_score" ? "green" : "cyan"}>
                    {meta.ranking === "matcher_score" ? "智能评分排序" : "技能重叠排序"}
                  </Tag>
                  {meta.filters && Object.keys(meta.filters).length > 0 && (
                    <Tag color="gold">已启用筛选</Tag>
                  )}
                  {meta.cached_at && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      生成于 {new Date(meta.cached_at).toLocaleString("zh-CN")}
                    </Text>
                  )}
                </Space>
              )
            }
            className="fade-in-up"
          >
            <RecommendList
              recommendations={recommendations}
              loading={false}
              type={recommendType}
              onMatchClick={(item) => setDetailModal(item)}
            />
          </Card>
        ) : (
          !loading && (
            <Card style={{ marginTop: 0 }}>
              <Empty
                description={
                  <span style={{ color: "var(--text-secondary)" }}>
                    选择文档后点击「开始推荐」查看匹配结果
                  </span>
                }
              />
            </Card>
          )
        )}
      </Spin>

      {/* 详情弹窗 */}
      <Modal
        title={
          <Space>
            <SwapOutlined style={{ color: "#4dd6ff" }} />
            <span>匹配详情</span>
          </Space>
        }
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        {detailModal && (
          <div
            style={{
              maxHeight: "calc(100vh - 230px)",
              overflowY: "auto",
              paddingRight: 8,
            }}
          >
            {/* 匹配摘要 */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  fontSize: 48,
                  fontWeight: 900,
                  background: `linear-gradient(135deg, ${getScoreColor(detailModal.match?.score ?? detailModal.skill_overlap)}, ${getScoreColor(detailModal.match?.score ?? detailModal.skill_overlap)}88)`,
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                  lineHeight: 1,
                }}
              >
                {detailModal.match?.score ?? detailModal.skill_overlap ?? 0}
              </div>
              <div>
                <Text strong style={{ fontSize: 16 }}>
                  {detailModal.document?.title ||
                    (recommendType === "jd" ? "未知岗位" : "未知简历")}
                </Text>
                <div>
                  {detailModal.match?.score != null ? (
                    <Tag
                      color={getScoreColor(detailModal.match.score)}
                      style={{ fontSize: 13, padding: "2px 12px" }}
                    >
                      {detailModal.match.score >= 80
                        ? "🎯 高度匹配"
                        : detailModal.match.score >= 60
                          ? "✅ 较为匹配"
                          : detailModal.match.score >= 40
                            ? "⚠️ 部分匹配"
                            : "❌ 匹配度低"}
                    </Tag>
                  ) : (
                    <Tag color="blue" style={{ fontSize: 13, padding: "2px 12px" }}>
                      技能重叠 {detailModal.skill_overlap || 0} 项
                    </Tag>
                  )}
                </div>
              </div>
            </div>

            {/* 匹配总结 */}
            {detailModal.match?.summary && (
              <Card
                size="small"
                style={{ marginBottom: 16 }}
              >
                <Text
                  style={{
                    fontSize: 13,
                    lineHeight: 1.8,
                    color: "var(--text-secondary)",
                  }}
                >
                  {detailModal.match.summary}
                </Text>
              </Card>
            )}

            <Row gutter={16}>
              {/* 左侧：雷达图 */}
              <Col xs={24} md={12}>
                <Card
                  size="small"
                  title={
                    <Space>
                      <SwapOutlined style={{ color: "#4dd6ff" }} />
                      <span>匹配维度分析</span>
                    </Space>
                  }
                  style={{ marginBottom: 16 }}
                >
                  <ReactECharts
                    option={getRadarOption(detailModal.match)}
                    style={{ height: 260 }}
                    opts={{ renderer: "canvas" }}
                  />
                </Card>
              </Col>

              {/* 右侧：技能差距 */}
              <Col xs={24} md={12}>
                <GapChart matchResult={detailModal.match} />
              </Col>
            </Row>

            {/* 学习建议 */}
            <LearningAdvice matchResult={detailModal.match} />

            {/* JSON 详情 */}
            <Divider />
            <details>
              <summary
                style={{
                  cursor: "pointer",
                  color: "var(--text-secondary)",
                  fontSize: 12,
                }}
              >
                匹配原始数据 (JSON)
              </summary>
              <pre
                style={{
                  background: "var(--accent-subtle)",
                  padding: 16,
                  borderRadius: 8,
                  maxHeight: 300,
                  overflow: "auto",
                  fontSize: 12,
                  marginTop: 8,
                  border: "1px solid var(--border-glass)",
                }}
              >
                {JSON.stringify(detailModal, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </Modal>
    </div>
  );
}
