import { useState, useMemo, useCallback } from "react";
import {
  Card,
  Typography,
  Button,
  Input,
  message,
  Spin,
  Row,
  Col,
  Tag,
  Select,
  Divider,
  Empty,
  Space,
  List,
  Tooltip,
  Badge,
  Dropdown,
  Statistic,
} from "antd";
import {
  NodeIndexOutlined,
  SearchOutlined,
  ExperimentOutlined,
  HighlightOutlined,
  ClearOutlined,
  DownloadOutlined,
  FilterOutlined,
  ApiOutlined,
  QuestionCircleOutlined,
  ClusterOutlined,
  LinkOutlined,
  StarOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  createKnowledgeGraph,
  getKnowledgeGraph,
  searchRAG,
  answerRAG,
  getDocumentLineage,
} from "../api/client";
import { adaptGraphForECharts } from "../utils/adapters";

const { Title, Paragraph, Text } = Typography;

function buildMockGraphOption(highlightNodes = new Set()) {
  const categories = [
    { name: "岗位", itemStyle: { color: "#4dd6ff" } },
    { name: "技能", itemStyle: { color: "#52c41a" } },
    { name: "知识", itemStyle: { color: "#7b61ff" } },
    { name: "通用能力", itemStyle: { color: "#faad14" } },
  ];

  const baseNodes = [
    { name: "Python开发工程师", category: 0, symbolSize: 55, value: "岗位" },
    { name: "测试工程师", category: 0, symbolSize: 48, value: "岗位" },
    { name: "数据分析师", category: 0, symbolSize: 45, value: "岗位" },
    { name: "AI产品经理", category: 0, symbolSize: 42, value: "岗位" },
    { name: "Python", category: 1, symbolSize: 38, value: "技能" },
    { name: "MySQL", category: 1, symbolSize: 32, value: "技能" },
    { name: "Linux", category: 1, symbolSize: 30, value: "技能" },
    { name: "自动化测试", category: 1, symbolSize: 34, value: "技能" },
    { name: "数据分析", category: 1, symbolSize: 32, value: "技能" },
    { name: "机器学习", category: 2, symbolSize: 30, value: "知识" },
    { name: "软件工程", category: 2, symbolSize: 28, value: "知识" },
    { name: "数据库原理", category: 2, symbolSize: 25, value: "知识" },
    { name: "深度学习", category: 2, symbolSize: 28, value: "知识" },
    { name: "沟通能力", category: 3, symbolSize: 22, value: "通用能力" },
    { name: "团队协作", category: 3, symbolSize: 20, value: "通用能力" },
    { name: "产品设计", category: 1, symbolSize: 30, value: "技能" },
  ];

  const categoryColors = ["#4dd6ff", "#52c41a", "#7b61ff", "#faad14"];

  const nodes = baseNodes.map((node) => {
    const isHighlighted = highlightNodes.has(node.name);
    const color = categoryColors[node.category];
    return {
      ...node,
      itemStyle: {
        color: isHighlighted ? "#ff4d4f" : color,
        borderColor: isHighlighted ? "#ff4d4f" : "rgba(255,255,255,0.2)",
        borderWidth: isHighlighted ? 3 : 1.5,
        shadowBlur: isHighlighted ? 16 : 8,
        shadowColor: isHighlighted ? "rgba(255, 77, 79, 0.6)" : `${color}40`,
      },
      label: {
        show: true,
        position: "right",
        fontSize: isHighlighted ? 13 : 11,
        fontWeight: isHighlighted ? "bold" : "normal",
        color: isHighlighted ? "#ff4d4f" : "#e6edf3",
        formatter: "{b}",
      },
      symbolSize: isHighlighted ? node.symbolSize * 1.3 : node.symbolSize,
    };
  });

  const links = [
    { source: "Python开发工程师", target: "Python" },
    { source: "Python开发工程师", target: "MySQL" },
    { source: "Python开发工程师", target: "Linux" },
    { source: "Python开发工程师", target: "机器学习" },
    { source: "Python开发工程师", target: "沟通能力" },
    { source: "测试工程师", target: "Python" },
    { source: "测试工程师", target: "自动化测试" },
    { source: "测试工程师", target: "Linux" },
    { source: "测试工程师", target: "软件工程" },
    { source: "测试工程师", target: "团队协作" },
    { source: "数据分析师", target: "Python" },
    { source: "数据分析师", target: "MySQL" },
    { source: "数据分析师", target: "数据分析" },
    { source: "数据分析师", target: "数据库原理" },
    { source: "数据分析师", target: "沟通能力" },
    { source: "AI产品经理", target: "产品设计" },
    { source: "AI产品经理", target: "机器学习" },
    { source: "AI产品经理", target: "深度学习" },
    { source: "AI产品经理", target: "沟通能力" },
    { source: "AI产品经理", target: "团队协作" },
  ];

  const linksStyled = links.map((link) => {
    const isSourceHighlighted = highlightNodes.has(link.source);
    const isTargetHighlighted = highlightNodes.has(link.target);
    if (isSourceHighlighted || isTargetHighlighted) {
      return {
        ...link,
        lineStyle: {
          color: "#ff4d4f",
          width: 2.5,
          opacity: 1,
          curveness: 0.2,
        },
      };
    }
    return {
      ...link,
      lineStyle: {
        color: "source",
        opacity: 0.4,
        curveness: 0.15,
      },
    };
  });

  return {
    tooltip: {
      formatter: (params) => {
        if (params.dataType === "node") {
          const isHL = highlightNodes.has(params.name);
          const catName = categories[params.data.category]?.name || "-";
          return `<div style="padding:6px 4px">
            <div style="font-size:15px;font-weight:600;margin-bottom:6px">${params.name}</div>
            <div style="display:flex;align-items:center;gap:6px">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${categoryColors[params.data.category]}"></span>
              <span style="color:#8b949e">类型：${catName}</span>
            </div>
            ${isHL ? '<div style="color:#ff4d4f;margin-top:6px;font-weight:500">★ RAG 检索匹配</div>' : ""}
          </div>`;
        }
        return `<div style="padding:4px">
          <span style="color:#8b949e">${params.data.source}</span>
          <span style="color:#4dd6ff;margin:0 6px">→</span>
          <span style="color:#8b949e">${params.data.target}</span>
        </div>`;
      },
      backgroundColor: "rgba(13, 17, 23, 0.95)",
      borderColor: "rgba(77, 214, 255, 0.2)",
      textStyle: { color: "#e6edf3" },
      extraCssText: "border-radius: 8px; backdrop-filter: blur(8px);",
    },
    legend: {
      data: categories.map((c) => c.name),
      bottom: 10,
      textStyle: { color: "#8b949e", fontSize: 12 },
      itemGap: 24,
      itemWidth: 12,
      itemHeight: 12,
    },
    animationDuration: 1500,
    animationEasingUpdate: "quinticInOut",
    series: [
      {
        type: "graph",
        layout: "force",
        data: nodes,
        links: linksStyled,
        categories,
        roam: true,
        draggable: true,
        force: {
          repulsion: 350,
          edgeLength: [100, 220],
          gravity: 0.08,
          friction: 0.6,
        },
        label: {
          show: true,
          position: "right",
          color: "#e6edf3",
          fontSize: 11,
        },
        lineStyle: {
          color: "source",
          curveness: 0.15,
          opacity: 0.4,
        },
        emphasis: {
          focus: "adjacency",
          lineStyle: { width: 3, opacity: 0.8 },
          itemStyle: {
            shadowBlur: 16,
            shadowColor: "rgba(77, 214, 255, 0.4)",
            borderWidth: 2,
          },
          label: {
            fontSize: 13,
            fontWeight: "bold",
          },
        },
        itemStyle: {
          borderColor: "rgba(255,255,255,0.15)",
          borderWidth: 1.5,
          shadowBlur: 8,
        },
        blur: {
          itemStyle: { opacity: 0.15 },
          lineStyle: { opacity: 0.05 },
        },
      },
    ],
  };
}

function extractRelevantNodes(ragResults) {
  const nodes = new Set();
  if (!ragResults) return nodes;

  const keywords = [
    "Python", "MySQL", "Linux", "机器学习", "数据分析",
    "自动化测试", "软件工程", "数据库原理", "沟通能力", "团队协作",
    "产品设计", "模型训练", "深度学习", "Java", "Go", "Docker",
    "Python开发工程师", "测试工程师", "数据分析师",
  ];

  if (ragResults.citations) {
    ragResults.citations.forEach((citation) => {
      if (citation.quote) {
        keywords.forEach((kw) => {
          if (citation.quote.includes(kw)) nodes.add(kw);
        });
      }
    });
  }

  if (ragResults.answer) {
    keywords.forEach((kw) => {
      if (ragResults.answer.includes(kw)) nodes.add(kw);
    });
  }

  return nodes;
}

export default function KnowledgeGraph() {
  const [loading, setLoading] = useState(false);
  const [graphData, setGraphData] = useState(null);
  const [graphId, setGraphId] = useState(null);
  const [ragQuery, setRagQuery] = useState("");
  const [ragResults, setRagResults] = useState(null);
  const [highlightedNodes, setHighlightedNodes] = useState(new Set());
  const [filterCategory, setFilterCategory] = useState(null);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [ragWarning, setRagWarning] = useState(null);

  async function handleBuildGraph() {
    setLoading(true);
    try {
      const res = await createKnowledgeGraph({
        document_ids: [],
        candidate_profile_ids: [],
        job_profile_ids: [],
      });
      const data = res.data.data.knowledge_graph;
      setGraphData(data);
      setGraphId(data.graph_id);
      message.success("知识图谱构建成功");
    } catch (e) {
      message.info("使用模拟图谱数据展示");
      setGraphData({ mock: true });
    } finally {
      setLoading(false);
    }
  }

  async function handleRAGSearch() {
    if (!ragQuery.trim()) {
      message.warning("请输入检索问题");
      return;
    }
    setLoading(true);
    setRagWarning(null);
    try {
      // RAG 检索使用数据治理文档 ID，不是知识图谱 ID
      // 传空数组表示搜索所有已处理的治理文档 chunks
      const res = await answerRAG(ragQuery, [], 5);
      const answerData = res.data.data.answer;
      setRagResults(answerData);
      const relevantNodes = extractRelevantNodes(answerData);
      setHighlightedNodes(relevantNodes);
      if (relevantNodes.size > 0) {
        message.success(`检索完成，已高亮 ${relevantNodes.size} 个相关节点`);
      } else if (answerData.citations?.length === 0) {
        setRagWarning("未检索到任何证据。请先在「JD 管理」或「简历管理」页面上传文档，然后通过数据治理接口注册并处理文档。");
      } else {
        message.success("检索完成");
      }
    } catch (e) {
      message.error(
        "检索失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
  }

  function handleClearHighlight() {
    setHighlightedNodes(new Set());
    setRagResults(null);
    setRagQuery("");
    setRagWarning(null);
    message.info("已清除高亮");
  }

  const chartOption = useMemo(() => {
    let option;

    if (graphData && !graphData.mock && graphData.nodes && graphData.edges) {
      option = adaptGraphForECharts(graphData.nodes, graphData.edges);
    } else {
      option = buildMockGraphOption(highlightedNodes);
    }

    if (searchKeyword && option.series?.[0]) {
      const keyword = searchKeyword.toLowerCase();
      const filteredNodes = option.series[0].data.filter((n) =>
        n.name?.toLowerCase().includes(keyword)
      );
      const nodeNames = new Set(filteredNodes.map((n) => n.name || n.id));
      const filteredLinks = option.series[0].links.filter(
        (l) => nodeNames.has(l.source) || nodeNames.has(l.target)
      );
      option.series[0].data = filteredNodes;
      option.series[0].links = filteredLinks;
    }

    if (filterCategory !== null && option.series?.[0]) {
      option.series[0].data = option.series[0].data.filter(
        (n) => n.category === filterCategory
      );
      const nodeNames = new Set(
        option.series[0].data.map((n) => n.name || n.id)
      );
      option.series[0].links = option.series[0].links.filter(
        (l) => nodeNames.has(l.source) && nodeNames.has(l.target)
      );
    }

    return option;
  }, [graphData, highlightedNodes, searchKeyword, filterCategory]);

  const handleExportGraph = useCallback(
    (type) => {
      if (type === "json") {
        const data = graphData?.mock
          ? { nodes: "mock", edges: "mock" }
          : graphData;
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `知识图谱_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        message.success("图谱数据已导出");
      } else if (type === "csv") {
        const rows = [["节点ID", "名称", "类型"]];
        (graphData?.nodes || []).forEach((n) => {
          rows.push([
            n.node_id || "",
            n.properties?.name || n.properties?.title || "",
            n.label || "",
          ]);
        });
        const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
        const blob = new Blob(["﻿" + csv], {
          type: "text/csv;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `知识图谱_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
        message.success("图谱数据已导出为 CSV");
      }
    },
    [graphData]
  );

  const categoryOptions = [
    { label: "全部", value: null },
    { label: "岗位", value: 0 },
    { label: "技能", value: 1 },
    { label: "知识", value: 2 },
    { label: "通用能力", value: 3 },
  ];

  const exportMenuItems = [
    { key: "json", label: "导出为 JSON", onClick: () => handleExportGraph("json") },
    { key: "csv", label: "导出为 CSV", onClick: () => handleExportGraph("csv") },
  ];

  // 图例说明数据
  const legendItems = [
    { tag: "岗位", color: "#4dd6ff", desc: "新一代信息技术岗位" },
    { tag: "技能", color: "#52c41a", desc: "专业技能、技术栈" },
    { tag: "知识", color: "#7b61ff", desc: "理论知识、领域知识" },
    { tag: "通用能力", color: "#faad14", desc: "软技能、迁移能力" },
  ];

  // 图谱统计信息
  const graphStats = useMemo(() => {
    if (!chartOption?.series?.[0]) return null;
    const data = chartOption.series[0].data || [];
    const links = chartOption.series[0].links || [];
    return {
      nodes: data.length,
      edges: links.length,
      categories: new Set(data.map((n) => n.category)).size,
    };
  }, [chartOption]);

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <ApiOutlined style={{ marginRight: 8, color: "#7b61ff" }} />
          知识图谱
        </Title>
        <Paragraph style={{ color: "#8b949e", margin: 0 }}>
          展示岗位-技能-知识-能力的关系图谱，支持图谱 RAG 检索
        </Paragraph>
      </div>

      <Spin spinning={loading}>
        {/* 图谱统计 */}
        {graphStats && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={8}>
              <Card size="small" style={{ background: "rgba(77, 214, 255, 0.04)" }}>
                <Statistic
                  title={<span style={{ color: "#8b949e", fontSize: 12 }}>节点数量</span>}
                  value={graphStats.nodes}
                  prefix={<ClusterOutlined style={{ color: "#4dd6ff" }} />}
                  valueStyle={{ color: "#4dd6ff", fontSize: 24 }}
                />
              </Card>
            </Col>
            <Col xs={8}>
              <Card size="small" style={{ background: "rgba(82, 196, 26, 0.04)" }}>
                <Statistic
                  title={<span style={{ color: "#8b949e", fontSize: 12 }}>关系数量</span>}
                  value={graphStats.edges}
                  prefix={<LinkOutlined style={{ color: "#52c41a" }} />}
                  valueStyle={{ color: "#52c41a", fontSize: 24 }}
                />
              </Card>
            </Col>
            <Col xs={8}>
              <Card size="small" style={{ background: "rgba(123, 97, 255, 0.04)" }}>
                <Statistic
                  title={<span style={{ color: "#8b949e", fontSize: 12 }}>分类数量</span>}
                  value={graphStats.categories}
                  prefix={<StarOutlined style={{ color: "#7b61ff" }} />}
                  valueStyle={{ color: "#7b61ff", fontSize: 24 }}
                />
              </Card>
            </Col>
          </Row>
        )}

        <Row gutter={16}>
          {/* 左侧：图谱可视化 */}
          <Col xs={24} lg={16}>
            <Card
              className="gradient-border"
              title={
                <Space>
                  <NodeIndexOutlined style={{ color: "#4dd6ff" }} />
                  <span>岗位-能力关系图谱</span>
                  {highlightedNodes.size > 0 && (
                    <Badge
                      count={`${highlightedNodes.size} 个高亮`}
                      style={{
                        backgroundColor: "#ff4d4f",
                        fontSize: 11,
                        boxShadow: "0 0 8px rgba(255,77,79,0.3)",
                      }}
                    />
                  )}
                </Space>
              }
              extra={
                <Space>
                  <Input
                    placeholder="搜索节点..."
                    prefix={<SearchOutlined style={{ color: "#484f58" }} />}
                    value={searchKeyword}
                    onChange={(e) => setSearchKeyword(e.target.value)}
                    style={{ width: 150 }}
                    size="small"
                    allowClear
                  />
                  <Select
                    value={filterCategory}
                    onChange={setFilterCategory}
                    options={categoryOptions}
                    style={{ width: 100 }}
                    size="small"
                    placeholder="分类"
                  />
                  {highlightedNodes.size > 0 && (
                    <Button
                      icon={<ClearOutlined />}
                      onClick={handleClearHighlight}
                      size="small"
                    >
                      清除
                    </Button>
                  )}
                  <Dropdown menu={{ items: exportMenuItems }}>
                    <Button icon={<DownloadOutlined />} size="small">
                      导出
                    </Button>
                  </Dropdown>
                  <Button
                    type="primary"
                    icon={<ExperimentOutlined />}
                    onClick={handleBuildGraph}
                    loading={loading}
                    size="small"
                  >
                    构建图谱
                  </Button>
                </Space>
              }
              style={{ height: 620 }}
            >
              {chartOption?.series?.[0]?.data?.length > 0 ? (
                <ReactECharts
                  option={chartOption}
                  style={{ height: 540 }}
                  opts={{ renderer: "canvas" }}
                  onEvents={{
                    click: (params) => {
                      if (params.dataType === "node") {
                        const isHL = highlightedNodes.has(params.name);
                        message.info(
                          `选中节点：${params.name} (${params.data.value})${isHL ? " ★ RAG 匹配" : ""}`
                        );
                      }
                    },
                  }}
                />
              ) : (
                <Empty
                  description={
                    <span style={{ color: "#8b949e" }}>
                      无匹配节点，请调整筛选条件
                    </span>
                  }
                  style={{ paddingTop: 200 }}
                />
              )}
            </Card>
          </Col>

          {/* 右侧：RAG 检索 + 说明 */}
          <Col xs={24} lg={8}>
            {/* RAG 检索 */}
            <Card
              className="gradient-border"
              title={
                <Space>
                  <SearchOutlined style={{ color: "#7b61ff" }} />
                  <span>图谱 RAG 检索</span>
                </Space>
              }
              style={{ marginBottom: 16 }}
            >
              <Space.Compact style={{ width: "100%" }}>
                <Input
                  value={ragQuery}
                  onChange={(e) => setRagQuery(e.target.value)}
                  placeholder="输入问题，例如：Python 开发需要哪些技能？"
                  onPressEnter={handleRAGSearch}
                />
                <Button
                  type="primary"
                  icon={<SearchOutlined />}
                  onClick={handleRAGSearch}
                  loading={loading}
                >
                  检索
                </Button>
              </Space.Compact>

              {ragWarning && (
                <div style={{ marginTop: 12 }}>
                  <div
                    style={{
                      padding: "10px 14px",
                      background: "rgba(250, 173, 20, 0.06)",
                      borderRadius: 8,
                      border: "1px solid rgba(250, 173, 20, 0.15)",
                      fontSize: 12,
                      color: "#faad14",
                      lineHeight: 1.8,
                    }}
                  >
                    ⚠️ {ragWarning}
                  </div>
                </div>
              )}

              {ragResults && (
                <div style={{ marginTop: 16 }} className="fade-in">
                  <Divider style={{ margin: "12px 0" }}>
                    <span style={{ color: "#8b949e", fontSize: 12 }}>检索结果</span>
                  </Divider>

                  {ragResults.answer && (
                    <div
                      style={{
                        marginBottom: 12,
                        padding: 14,
                        background: "linear-gradient(135deg, rgba(77, 214, 255, 0.06) 0%, rgba(123, 97, 255, 0.04) 100%)",
                        borderRadius: 10,
                        border: "1px solid rgba(77, 214, 255, 0.1)",
                      }}
                    >
                      <Text
                        strong
                        style={{ color: "#4dd6ff", fontSize: 12, display: "block", marginBottom: 8 }}
                      >
                        💡 回答
                      </Text>
                      <div
                        style={{
                          whiteSpace: "pre-wrap",
                          lineHeight: 1.8,
                          fontSize: 13,
                          color: "#e6edf3",
                        }}
                      >
                        {ragResults.answer}
                      </div>
                    </div>
                  )}

                  {ragResults.citations?.length > 0 && (
                    <div style={{ marginBottom: 12 }}>
                      <Text
                        strong
                        style={{ color: "#8b949e", fontSize: 12, display: "block", marginBottom: 8 }}
                      >
                        📚 引用来源
                      </Text>
                      <List
                        size="small"
                        dataSource={ragResults.citations}
                        renderItem={(item) => (
                          <List.Item style={{ padding: "6px 0", border: "none" }}>
                            <Text code style={{ fontSize: 11 }}>
                              {item.doc_id}
                            </Text>
                            <Text
                              type="secondary"
                              style={{ marginLeft: 8, fontSize: 12 }}
                            >
                              {item.quote?.slice(0, 60)}...
                            </Text>
                          </List.Item>
                        )}
                      />
                    </div>
                  )}

                  {highlightedNodes.size > 0 && (
                    <div>
                      <Divider style={{ margin: "12px 0" }}>
                        <span style={{ color: "#ff4d4f", fontSize: 12 }}>
                          <HighlightOutlined /> 高亮节点
                        </span>
                      </Divider>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {Array.from(highlightedNodes).map((node) => (
                          <Tag
                            key={node}
                            color="error"
                            style={{
                              fontSize: 12,
                              padding: "2px 10px",
                              borderRadius: 6,
                            }}
                          >
                            {node}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Card>

            {/* 图谱说明 */}
            <Card
              title={
                <Space>
                  <QuestionCircleOutlined style={{ color: "#faad14" }} />
                  <span>图谱说明</span>
                </Space>
              }
            >
              <div style={{ fontSize: 13, lineHeight: 2 }}>
                {legendItems.map((item) => (
                  <div
                    key={item.tag}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      padding: "4px 0",
                    }}
                  >
                    <div
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: "50%",
                        background: item.color,
                        marginRight: 10,
                        boxShadow: `0 0 8px ${item.color}40`,
                      }}
                    />
                    <Tag
                      color={item.color}
                      style={{ margin: 0, minWidth: 60, textAlign: "center" }}
                    >
                      {item.tag}
                    </Tag>
                    <span style={{ color: "#8b949e", marginLeft: 8 }}>
                      {item.desc}
                    </span>
                  </div>
                ))}
                <Divider style={{ margin: "12px 0" }} />
                <div
                  style={{
                    color: "#484f58",
                    fontSize: 12,
                    lineHeight: 2.2,
                  }}
                >
                  <p>🎯 节点可拖拽，点击高亮相邻节点</p>
                  <p>🔗 连线表示岗位要求该技能/知识/能力</p>
                  <p>🔍 使用搜索框和分类筛选过滤节点</p>
                  <p>✨ RAG 检索可高亮相关节点</p>
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
