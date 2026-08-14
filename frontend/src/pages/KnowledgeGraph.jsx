import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, SearchOutlined, ShareAltOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { getKnowledgeGraph, graphRetrieval } from "../api/client";

const { Title, Text } = Typography;

// ── 节点分类与配色（与预构建图谱 label 对应） ──
const CATEGORY_META = {
  Job: { label: "岗位", color: "#3b82f6" },
  Company: { label: "公司", color: "#8b5cf6" },
  Technology: { label: "技术", color: "#10b981" },
  Skill: { label: "技能", color: "#22d3ee" },
  Knowledge: { label: "知识", color: "#f59e0b" },
  TransversalCompetence: { label: "通用能力", color: "#f43f5e" },
  LanguageCompetence: { label: "语言能力", color: "#ec4899" },
  Candidate: { label: "候选人", color: "#a3a3a3" },
  Evidence: { label: "证据", color: "#d4d4d8" },
};

const GRAPH_ID = "kg_prebuilt_v2";
// 默认聚焦"岗位-技能-知识-能力"主干，排除证据/候选人/公司，避免画面杂乱
const DEFAULT_CATEGORIES = Object.keys(CATEGORY_META).filter(
  (k) => k !== "Evidence" && k !== "Candidate" && k !== "Company"
);
const LABEL_TOP_N = 40; // 只给连接度前 N 的节点常显标签

export default function KnowledgeGraph() {
  const [loading, setLoading] = useState(false);
  const [graph, setGraph] = useState(null);
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [maxNodes, setMaxNodes] = useState(100); // 0 = 全部
  const [layout, setLayout] = useState("force");
  const [search, setSearch] = useState("");
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrieving, setRetrieving] = useState(false);
  const [highlightIds, setHighlightIds] = useState(new Set());
  const [paths, setPaths] = useState([]);

  const loadGraph = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getKnowledgeGraph(GRAPH_ID);
      const g = res.data.data.knowledge_graph;
      setGraph(g);
      message.success(`图谱已加载：${g.nodes.length} 节点 / ${g.edges.length} 边`);
    } catch (e) {
      message.error(`图谱加载失败：${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  const doRetrieval = useCallback(async () => {
    const q = retrievalQuery.trim();
    if (!q) return;
    setRetrieving(true);
    try {
      const res = await graphRetrieval(GRAPH_ID, q);
      const retr = res.data.data.retrieval;
      const ids = Object.keys(retr.entities || {});
      setHighlightIds(new Set(ids));
      setPaths(retr.paths || []);
      message.info(`检索命中 ${ids.length} 个实体 / ${(retr.paths || []).length} 条路径`);
    } catch (e) {
      message.error(`检索失败：${e.message}`);
    } finally {
      setRetrieving(false);
    }
  }, [retrievalQuery]);

  // ── 类别过滤后的全量子图 ──
  const { allNodes, allEdges, degreeMap } = useMemo(() => {
    if (!graph) return { allNodes: [], allEdges: [], degreeMap: {} };
    const byId = {};
    const ns = (graph.nodes || []).filter((n) => categories.includes(n.type || n.label));
    ns.forEach((n) => (byId[n.id] = n));
    const es = (graph.edges || []).filter((e) => byId[e.source] && byId[e.target]);
    const dm = {};
    es.forEach((e) => {
      dm[e.source] = (dm[e.source] || 0) + 1;
      dm[e.target] = (dm[e.target] || 0) + 1;
    });
    return { allNodes: ns, allEdges: es, degreeMap: dm };
  }, [graph, categories]);

  // ── 按连接度取 Top N，避免画面过密 ──
  const { nodes, edges } = useMemo(() => {
    if (maxNodes <= 0) return { nodes: allNodes, edges: allEdges };
    const ranked = [...allNodes].sort(
      (a, b) => (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0)
    );
    const keep = new Set(ranked.slice(0, maxNodes).map((n) => n.id));
    return {
      nodes: allNodes.filter((n) => keep.has(n.id)),
      edges: allEdges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    };
  }, [allNodes, allEdges, degreeMap, maxNodes]);

  const filteredNodes = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return nodes;
    return nodes.filter((n) => String(n.name || n.id).toLowerCase().includes(q));
  }, [nodes, search]);

  const option = useMemo(() => {
    const cats = categories
      .filter((c) => CATEGORY_META[c])
      .map((c) => ({ name: CATEGORY_META[c].label, itemStyle: { color: CATEGORY_META[c].color } }));
    const isSearching = search.trim().length > 0;
    const rankById = {};
    [...nodes]
      .sort((a, b) => (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0))
      .forEach((n, i) => (rankById[n.id] = i));

    return {
      tooltip: {
        formatter: (p) => {
          if (p.dataType !== "node") return p.data?.type || "";
          const props = p.data.properties || {};
          const lines = [
            `<b>${p.data.name}</b>`,
            p.data.type ? `类型：${CATEGORY_META[p.data.type]?.label || p.data.type}` : "",
            p.data.degree ? `关联：${p.data.degree} 条` : "",
            props.company_name ? `公司：${props.company_name}` : "",
            props.industry ? `行业：${props.industry}` : "",
            props.location ? `地点：${props.location}` : "",
            props.education ? `学历：${props.education}` : "",
            props.experience ? `经验：${props.experience}` : "",
          ].filter(Boolean);
          return lines.join("<br/>");
        },
      },
      legend: { data: cats, bottom: 0, textStyle: { color: "#999" }, type: "scroll" },
      series: [
        {
          type: "graph",
          layout,
          roam: true,
          draggable: true,
          force: { repulsion: 180, edgeLength: [40, 110], gravity: 0.06 },
          circular: { rotateLabel: false },
          categories: cats,
          label: {
            show: false,
            fontSize: 10,
            color: "#ddd",
            formatter: (p) => p.data.name,
          },
          emphasis: {
            focus: "adjacency",
            label: { show: true, fontSize: 12, color: "#fff" },
            itemStyle: { shadowBlur: 14, shadowColor: "rgba(255,255,255,0.7)" },
            lineStyle: { width: 3 },
          },
          data: nodes.map((n) => ({
            id: n.id,
            name: n.name,
            value: degreeMap[n.id] || 1,
            degree: degreeMap[n.id] || 0,
            category: CATEGORY_META[n.type || n.label]?.label || (n.type || n.label),
            symbolSize: Math.max(8, Math.min(26, 6 + Math.sqrt(degreeMap[n.id] || 1) * 2.2)),
            label: {
              show: !isSearching && (rankById[n.id] ?? 9999) < LABEL_TOP_N,
            },
            properties: n.properties,
            itemStyle: {
              opacity: isSearching && !String(n.name || n.id).toLowerCase().includes(search.trim().toLowerCase()) ? 0.12 : 1,
            },
          })),
          links: edges.map((e) => ({
            source: e.source,
            target: e.target,
            lineStyle: {
              color: highlightIds.has(e.source) || highlightIds.has(e.target) ? "#facc15" : "rgba(120,130,150,0.45)",
              width: highlightIds.has(e.source) || highlightIds.has(e.target) ? 3 : 0.8,
            },
          })),
          lineStyle: { curveness: 0.12, opacity: 0.6 },
          animationDuration: 400,
        },
      ],
      backgroundColor: "transparent",
    };
  }, [nodes, edges, categories, highlightIds, search, degreeMap, layout]);

  const totalNodes = graph?.nodes?.length || 0;
  const totalEdges = graph?.edges?.length || 0;

  return (
    <div style={{ padding: 16 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 12 }} wrap>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <ShareAltOutlined /> 岗位能力全景图谱
          </Title>
          <Text type="secondary">
            数据源：Neo4j 快照 kg_prebuilt_v2（{totalNodes} 节点 / {totalEdges} 边）
          </Text>
        </Col>
        <Col>
          <Space wrap>
            <Select
              mode="multiple"
              allowClear
              style={{ minWidth: 300 }}
              placeholder="分类筛选"
              value={categories}
              onChange={setCategories}
              options={Object.entries(CATEGORY_META).map(([k, v]) => ({ value: k, label: `${v.label} (${k})` }))}
            />
            <Select
              style={{ width: 150 }}
              value={maxNodes}
              onChange={setMaxNodes}
              options={[
                { value: 60, label: "核心 60 节点" },
                { value: 100, label: "核心 100 节点" },
                { value: 200, label: "200 节点" },
                { value: 0, label: "全部节点" },
              ]}
            />
            <Segmented
              value={layout}
              onChange={setLayout}
              options={[
                { label: "力导向", value: "force" },
                { label: "环形", value: "circular" },
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={loadGraph} loading={loading}>
              刷新
            </Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={5}><Statistic title="图谱节点" value={totalNodes} suffix={`/ 展示 ${nodes.length}`} /></Col>
        <Col span={5}><Statistic title="图谱关系" value={totalEdges} suffix={`/ 展示 ${edges.length}`} /></Col>
        <Col span={4}><Statistic title="分类" value={categories.length} /></Col>
        <Col span={5}><Statistic title="检索命中" value={highlightIds.size} /></Col>
        <Col span={5}>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              prefix={<SearchOutlined />}
              placeholder="节点搜索（如 python）"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              allowClear
            />
          </Space.Compact>
        </Col>
      </Row>

      <Row gutter={12}>
        <Col span={7}>
          <Card size="small" title="语义路径检索（Neo4j）" style={{ minHeight: 320 }}>
            <Space.Compact style={{ width: "100%" }}>
              <Input
                placeholder="如 Agent、python、Java"
                value={retrievalQuery}
                onChange={(e) => setRetrievalQuery(e.target.value)}
                onPressEnter={doRetrieval}
              />
              <Button type="primary" icon={<SearchOutlined />} loading={retrieving} onClick={doRetrieval}>
                检索
              </Button>
            </Space.Compact>
            <div style={{ marginTop: 10 }}>
              {paths.length === 0 ? (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  在 Neo4j 中沿图谱关系检索最多 3 跳路径，命中实体黄色高亮。
                </Text>
              ) : (
                <div style={{ maxHeight: 420, overflow: "auto" }}>
                  {paths.slice(0, 40).map((p, i) => (
                    <div key={p.id || i} style={{ fontSize: 12, marginBottom: 6 }}>
                      <Tag color="gold">#{i + 1}</Tag>
                      {p.nodes.map((n) => n.properties?.name || n.id).join(" → ")}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </Col>
        <Col span={17}>
          <Card size="small" bodyStyle={{ padding: 8 }}>
            <Spin spinning={loading}>
              {nodes.length === 0 ? (
                <Empty description="暂无图谱数据，请刷新或检查后端/Neo4j" style={{ padding: 80 }} />
              ) : (
                <ReactECharts option={option} style={{ height: 640 }} notMerge lazyUpdate />
              )}
            </Spin>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
