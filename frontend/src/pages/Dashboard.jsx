import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Col, Row, Statistic, Typography, Spin, Space } from "antd";
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
  DatabaseOutlined,
  StarOutlined,
} from "@ant-design/icons";
import { getHealth, getCapabilities, listUserDocuments, initUser, getCandidateProfilesByDocuments, getJobProfilesByDocuments } from "../api/client";
import useStore from "../store/useStore";

const { Title, Paragraph } = Typography;

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
  const [stats, setStats] = useState({
    totalMatches: 0,
    avgScore: 0,
    totalDocs: 0,
    uptime: "99.9%",
  });

  const { userId, initUserId } = useStore();

  useEffect(() => {
    initUserId();
    loadAllData();
  }, []);

  async function loadAllData() {
    try {
      const uid = initUserId();

      // 并行加载健康状态、能力、用户初始化、文档列表
      const [healthRes, capRes] = await Promise.allSettled([
        getHealth(),
        getCapabilities(),
        initUser(),
      ]);

      if (healthRes.status === "fulfilled") setHealth(healthRes.value.data);
      if (capRes.status === "fulfilled") setCapabilities(capRes.value.data);

      // 文档和画像加载（不阻塞健康状态显示）
      let docs = [];
      try {
        const docRes = await listUserDocuments(uid || userId, null, 0, 200);
        docs = docRes.data.data.items || [];
      } catch (e) {
        console.warn("加载文档列表失败:", e);
      }

      // 只保留用户上传的文档（过滤掉系统种子数据 sys_ 开头的）
      const userDocs = docs.filter((d) => !d.id.startsWith("sys_") && !d.document_id?.startsWith("sys_"));
      const resumeDocs = userDocs.filter((d) => d.document_type === "resume");
      const jdDocs = userDocs.filter((d) => d.document_type === "jd");

      // 加载画像并构建统计和图谱
      const resumeIds = resumeDocs.map((d) => d.document_id || d.id).filter(Boolean);
      const jdIds = jdDocs.map((d) => d.document_id || d.id).filter(Boolean);

      let allProfiles = [];
      const [candProfilesRes, jobProfilesRes] = await Promise.allSettled([
        resumeIds.length > 0 ? getCandidateProfilesByDocuments(resumeIds) : Promise.resolve({ data: { data: { profiles: {} } } }),
        jdIds.length > 0 ? getJobProfilesByDocuments(jdIds) : Promise.resolve({ data: { data: { profiles: {} } } }),
      ]);

      const candProfiles = candProfilesRes.status === "fulfilled" ? Object.values(candProfilesRes.value.data.data.profiles || {}) : [];
      const jobProfiles = jobProfilesRes.status === "fulfilled" ? Object.values(jobProfilesRes.value.data.data.profiles || {}) : [];
      allProfiles = [...candProfiles, ...jobProfiles];

      // 统计用户数据
      const realProfiles = allProfiles.filter((p) => p.state === "available" && p.implementation !== "mock");
      setStats({
        totalDocs: userDocs.length,
        resumeCount: resumeDocs.length,
        jdCount: jdDocs.length,
        profileCount: realProfiles.length,
      });

    } catch (e) {
      console.warn("加载数据失败:", e);
    } finally {
      setLoading(false);
    }
  }

  // 从 capabilities 数组中按 name 查找状态
  function getCap(name) {
    // capabilities 结构: { data: { capabilities: [...] }, meta: {...} }
    const caps = capabilities?.data?.capabilities;
    if (!Array.isArray(caps)) return null;
    return caps.find((c) => c.name === name) || null;
  }

  // 状态卡片数据（真实数据）
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
      value: getCap("ocr")?.state === "available" ? "可用" : "不可用",
      icon: <FileTextOutlined />,
      color: getCap("ocr")?.state === "available" ? "#4dd6ff" : "#8b949e",
      bg: "linear-gradient(135deg, rgba(77,214,255,0.06) 0%, rgba(77,214,255,0.02) 100%)",
    },
    {
      title: "LLM 抽取",
      value: getCap("structured_extraction")?.state === "available" ? "可用" : "不可用",
      icon: <ThunderboltOutlined />,
      color: getCap("structured_extraction")?.state === "available" ? "#52c41a" : "#faad14",
      bg: "linear-gradient(135deg, rgba(82,196,26,0.06) 0%, rgba(82,196,26,0.02) 100%)",
    },
    {
      title: "人岗匹配",
      value: getCap("matching")?.state === "available" ? "可用" : "不可用",
      icon: <SwapOutlined />,
      color: getCap("matching")?.state === "available" ? "#7b61ff" : "#8b949e",
      bg: "linear-gradient(135deg, rgba(123,97,255,0.06) 0%, rgba(123,97,255,0.02) 100%)",
    },
  ];

  // 统计卡片数据（真实数据）
  const statCards = [
    {
      title: "文档总数",
      value: stats.totalDocs,
      icon: <DatabaseOutlined />,
      color: "#4dd6ff",
      suffix: " 份",
    },
    {
      title: "简历数量",
      value: stats.resumeCount,
      icon: <UserOutlined />,
      color: "#7b61ff",
      suffix: " 份",
    },
    {
      title: "JD 数量",
      value: stats.jdCount,
      icon: <FileTextOutlined />,
      color: "#52c41a",
      suffix: " 份",
    },
    {
      title: "已生成画像",
      value: stats.profileCount,
      icon: <ExperimentOutlined />,
      color: "#faad14",
      suffix: " 个",
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
      icon: <StarOutlined />,
      title: "查看星图",
      desc: "浏览岗位分布星图",
      link: "/starmap",
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
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
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
                  <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                    {card.title}
                  </div>
                </div>
              </Card>
            </Col>
          ))}
        </Row>

        {/* 快速操作 */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col span={24}>
            <Card
              className="gradient-border"
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: "#7b61ff" }} />
                  <span>快速操作</span>
                </Space>
              }
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: 12,
                }}
              >
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
                            color: "var(--text-secondary)",
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
                    color: "var(--text-secondary)",
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
