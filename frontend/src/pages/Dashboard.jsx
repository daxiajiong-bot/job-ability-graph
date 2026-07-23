import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Col, Row, Statistic, Typography, Spin, message, Button, Space, Tooltip, Progress, Tag } from "antd";
import {
  FileTextOutlined,
  UserOutlined,
  SwapOutlined,
  NodeIndexOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  ArrowRightOutlined,
  ThunderboltOutlined,
  RocketOutlined,
  ApiOutlined,
  RiseOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
} from "@ant-design/icons";
import { getHealth, getCapabilities, createKnowledgeGraph } from "../api/client";
import JobGalaxy from "../components/JobGalaxy";

const { Title, Paragraph, Text } = Typography;

// ── 动画数字组件 ──
function AnimatedNumber({ value, duration = 1500, suffix = "" }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    const start = 0;
    const end = value;
    const startTime = Date.now();

    const animate = () => {
      const now = Date.now();
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
      setDisplay(Math.round(start + (end - start) * eased));

      if (progress < 1) {
        ref.current = requestAnimationFrame(animate);
      }
    };

    ref.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(ref.current);
  }, [value, duration]);

  return <span>{display}{suffix}</span>;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [health, setHealth] = useState(null);
  const [capabilities, setCapabilities] = useState(null);
  const [loading, setLoading] = useState(true);
  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [stats, setStats] = useState({
    totalMatches: 0,
    avgScore: 0,
    totalDocs: 0,
    uptime: "99.9%",
  });

  useEffect(() => {
    loadData();
    loadGraphData();
    // 模拟统计数据
    setStats({
      totalMatches: 128,
      avgScore: 76,
      totalDocs: 45,
      uptime: "99.9%",
    });
  }, []);

  async function loadData() {
    try {
      const [healthRes, capRes] = await Promise.allSettled([
        getHealth(),
        getCapabilities(),
      ]);
      if (healthRes.status === "fulfilled") setHealth(healthRes.value.data);
      if (capRes.status === "fulfilled") setCapabilities(capRes.value.data);
    } catch (e) {
      message.error("无法连接后端服务，请确认后端已启动");
    } finally {
      setLoading(false);
    }
  }

  async function loadGraphData() {
    // Dashboard 使用模拟图谱数据展示
    // 实际图谱需要先上传文档后在知识图谱页面构建
    console.log("使用模拟图谱数据");
    setGraphNodes(getMockNodes());
    setGraphEdges(getMockEdges());
  }

  function getMockNodes() {
    return [
      { label: "Job", node_id: "job:1", properties: { title: "Python开发工程师", name: "Python开发工程师" } },
      { label: "Job", node_id: "job:2", properties: { title: "测试工程师", name: "测试工程师" } },
      { label: "Job", node_id: "job:3", properties: { title: "数据分析师", name: "数据分析师" } },
      { label: "Job", node_id: "job:4", properties: { title: "AI产品经理", name: "AI产品经理" } },
      { label: "Skill", node_id: "s:python", properties: { name: "Python", category: "S" } },
      { label: "Skill", node_id: "s:mysql", properties: { name: "MySQL", category: "S" } },
      { label: "Skill", node_id: "s:linux", properties: { name: "Linux", category: "S" } },
      { label: "Skill", node_id: "s:auto_test", properties: { name: "自动化测试", category: "S" } },
      { label: "Skill", node_id: "s:data_analysis", properties: { name: "数据分析", category: "S" } },
      { label: "Skill", node_id: "s:ml", properties: { name: "机器学习", category: "S" } },
      { label: "Skill", node_id: "s:product_design", properties: { name: "产品设计", category: "S" } },
      { label: "Knowledge", node_id: "k:se", properties: { name: "软件工程", category: "K" } },
      { label: "Knowledge", node_id: "k:db", properties: { name: "数据库原理", category: "K" } },
      { label: "Knowledge", node_id: "k:dl", properties: { name: "深度学习", category: "K" } },
      { label: "AbilityEntity", node_id: "a:comm", properties: { name: "沟通能力", category: "A" } },
      { label: "AbilityEntity", node_id: "a:team", properties: { name: "团队协作", category: "A" } },
    ];
  }

  function getMockEdges() {
    return [
      { source_id: "job:1", target_id: "s:python", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:1", target_id: "s:mysql", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:1", target_id: "s:linux", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:1", target_id: "k:se", relation_type: "HAS_KNOWLEDGE" },
      { source_id: "job:1", target_id: "a:comm", relation_type: "HAS_ABILITY" },
      { source_id: "job:2", target_id: "s:python", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:2", target_id: "s:auto_test", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:2", target_id: "s:linux", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:2", target_id: "k:se", relation_type: "HAS_KNOWLEDGE" },
      { source_id: "job:2", target_id: "a:team", relation_type: "HAS_ABILITY" },
      { source_id: "job:3", target_id: "s:python", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:3", target_id: "s:mysql", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:3", target_id: "s:data_analysis", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:3", target_id: "k:db", relation_type: "HAS_KNOWLEDGE" },
      { source_id: "job:3", target_id: "a:comm", relation_type: "HAS_ABILITY" },
      { source_id: "job:4", target_id: "s:product_design", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:4", target_id: "s:ml", relation_type: "REQUIRES_SKILL" },
      { source_id: "job:4", target_id: "k:dl", relation_type: "HAS_KNOWLEDGE" },
      { source_id: "job:4", target_id: "a:comm", relation_type: "HAS_ABILITY" },
    ];
  }

  // 状态卡片数据
  const statusCards = [
    {
      title: "系统状态",
      value: health?.status === "ok" ? "正常运行" : "连接异常",
      icon: <CheckCircleOutlined />,
      color: health?.status === "ok" ? "#52c41a" : "#ff4d4f",
      bg: health?.status === "ok"
        ? "linear-gradient(135deg, rgba(82,196,26,0.08) 0%, rgba(82,196,26,0.02) 100%)"
        : "linear-gradient(135deg, rgba(255,77,79,0.08) 0%, rgba(255,77,79,0.02) 100%)",
      pulse: health?.status === "ok",
    },
    {
      title: "OCR 识别",
      value: capabilities?.capabilities?.ocr?.state === "available" ? "可用" : "不可用",
      icon: <FileTextOutlined />,
      color: capabilities?.capabilities?.ocr?.state === "available" ? "#4dd6ff" : "#8b949e",
      bg: "linear-gradient(135deg, rgba(77,214,255,0.06) 0%, rgba(77,214,255,0.02) 100%)",
    },
    {
      title: "知识图谱",
      value: capabilities?.capabilities?.knowledge_graph?.state === "available" ? "可用" : "Mock",
      icon: <NodeIndexOutlined />,
      color: capabilities?.capabilities?.knowledge_graph?.state === "available" ? "#7b61ff" : "#faad14",
      bg: "linear-gradient(135deg, rgba(123,97,255,0.06) 0%, rgba(123,97,255,0.02) 100%)",
    },
    {
      title: "LLM 抽取",
      value: capabilities?.capabilities?.profile_extraction?.state === "available" ? "可用" : "Mock",
      icon: <ThunderboltOutlined />,
      color: capabilities?.capabilities?.profile_extraction?.state === "available" ? "#52c41a" : "#faad14",
      bg: "linear-gradient(135deg, rgba(82,196,26,0.06) 0%, rgba(82,196,26,0.02) 100%)",
    },
  ];

  // 统计卡片数据
  const statCards = [
    {
      title: "总匹配次数",
      value: stats.totalMatches,
      icon: <SwapOutlined />,
      color: "#4dd6ff",
      suffix: " 次",
    },
    {
      title: "平均匹配度",
      value: stats.avgScore,
      icon: <RiseOutlined />,
      color: "#52c41a",
      suffix: "%",
    },
    {
      title: "文档总数",
      value: stats.totalDocs,
      icon: <DatabaseOutlined />,
      color: "#7b61ff",
      suffix: " 份",
    },
    {
      title: "系统可用性",
      value: 99.9,
      icon: <CloudServerOutlined />,
      color: "#faad14",
      suffix: "%",
    },
  ];

  // 快速操作数据
  const quickActions = [
    {
      icon: <FileTextOutlined />,
      title: "上传 JD",
      desc: "上传岗位描述文件，系统自动解析技能要求",
      link: "/jd",
      color: "#4dd6ff",
    },
    {
      icon: <UserOutlined />,
      title: "上传简历",
      desc: "上传候选人简历，提取技能画像",
      link: "/resume",
      color: "#7b61ff",
    },
    {
      icon: <SwapOutlined />,
      title: "人岗匹配",
      desc: "选择候选人与岗位，生成匹配报告",
      link: "/match",
      color: "#52c41a",
    },
    {
      icon: <NodeIndexOutlined />,
      title: "查看图谱",
      desc: "浏览岗位-技能-知识关系图谱",
      link: "/graph",
      color: "#faad14",
    },
  ];

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <RocketOutlined style={{ marginRight: 8, color: "#4dd6ff" }} />
          数据概览
        </Title>
        <Paragraph style={{ color: "#8b949e", margin: 0 }}>
          新一代信息技术岗位全景图谱系统 — 基于大模型与知识图谱的智能人岗匹配
        </Paragraph>
      </div>

      <Spin spinning={loading}>
        {/* 系统状态卡片 */}
        <Row gutter={[16, 16]}>
          {statusCards.map((card, index) => (
            <Col xs={24} sm={12} lg={6} key={card.title}>
              <Card
                hoverable
                className={`fade-in-up stagger-${index + 1}`}
                style={{
                  background: card.bg,
                  borderColor: `${card.color}15`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <Statistic
                    title={card.title}
                    value={card.value}
                    valueStyle={{ color: card.color, fontSize: 20 }}
                  />
                  <div style={{ position: "relative" }}>
                    <span
                      style={{
                        fontSize: 32,
                        color: card.color,
                        opacity: 0.3,
                      }}
                    >
                      {card.icon}
                    </span>
                    {card.pulse && (
                      <span
                        className="status-dot success"
                        style={{
                          position: "absolute",
                          top: 0,
                          right: 0,
                          width: 8,
                          height: 8,
                          animation: "pulse-glow 2s infinite",
                        }}
                      />
                    )}
                  </div>
                </div>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 统计数据卡片 */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {statCards.map((card, index) => (
            <Col xs={12} sm={6} key={card.title}>
              <Card
                className={`fade-in-up stagger-${index + 1}`}
                style={{
                  background: `linear-gradient(135deg, ${card.color}08 0%, ${card.color}02 100%)`,
                  borderColor: `${card.color}10`,
                }}
              >
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 28, color: card.color, marginBottom: 8 }}>
                    {card.icon}
                  </div>
                  <div
                    style={{
                      fontSize: 32,
                      fontWeight: 800,
                      color: card.color,
                      lineHeight: 1,
                      marginBottom: 4,
                    }}
                  >
                    <AnimatedNumber value={card.value} suffix={card.suffix} />
                  </div>
                  <div style={{ fontSize: 13, color: "#8b949e" }}>
                    {card.title}
                  </div>
                </div>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 星图 + 快速操作 */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={16}>
            <Card
              className="gradient-border"
              title={
                <Space>
                  <ApiOutlined style={{ color: "#4dd6ff" }} />
                  <span>岗位能力 3D 星图</span>
                </Space>
              }
              extra={
                <Space>
                  <Tooltip title="节点数量">
                    <Tag color="blue">{graphNodes.length} 节点</Tag>
                  </Tooltip>
                  <Tooltip title="关系数量">
                    <Tag color="purple">{graphEdges.length} 关系</Tag>
                  </Tooltip>
                </Space>
              }
              style={{ height: 520 }}
            >
              <JobGalaxy
                graphNodes={graphNodes}
                graphEdges={graphEdges}
                height={470}
              />
            </Card>
          </Col>

          <Col xs={24} lg={8}>
            <Card
              className="gradient-border"
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: "#7b61ff" }} />
                  <span>快速操作</span>
                </Space>
              }
              style={{ height: 520 }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {quickActions.map((item, index) => (
                  <Card
                    key={item.title}
                    size="small"
                    hoverable
                    onClick={() => navigate(item.link)}
                    className={`fade-in-up stagger-${index + 1}`}
                    style={{
                      cursor: "pointer",
                      borderColor: `${item.color}10`,
                      transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                    }}
                    styles={{
                      body: {
                        padding: "12px 16px",
                      },
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 14,
                      }}
                    >
                      <div
                        style={{
                          width: 48,
                          height: 48,
                          borderRadius: 12,
                          background: `linear-gradient(135deg, ${item.color}20, ${item.color}08)`,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 22,
                          color: item.color,
                          flexShrink: 0,
                          boxShadow: `0 4px 12px ${item.color}15`,
                        }}
                      >
                        {item.icon}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: 14,
                            marginBottom: 4,
                            color: "#e6edf3",
                          }}
                        >
                          {item.title}
                        </div>
                        <div
                          style={{
                            fontSize: 12,
                            color: "#8b949e",
                            lineHeight: 1.5,
                          }}
                        >
                          {item.desc}
                        </div>
                      </div>
                      <ArrowRightOutlined
                        style={{ color: "#484f58", fontSize: 14 }}
                      />
                    </div>
                  </Card>
                ))}
              </div>

              {/* 底部提示 */}
              <div
                style={{
                  marginTop: 16,
                  padding: "14px 16px",
                  background: "linear-gradient(135deg, rgba(77, 214, 255, 0.06) 0%, rgba(123, 97, 255, 0.04) 100%)",
                  borderRadius: 10,
                  border: "1px solid rgba(77, 214, 255, 0.08)",
                }}
              >
                <div
                  style={{
                    fontSize: 12,
                    color: "#8b949e",
                    lineHeight: 1.8,
                  }}
                >
                  <div style={{ fontWeight: 600, color: "#4dd6ff", marginBottom: 6, fontSize: 13 }}>
                    💡 使用提示
                  </div>
                  先上传 JD 和简历文档，再进行人岗匹配。
                  系统将自动提取技能画像并生成差距分析报告。
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
}
