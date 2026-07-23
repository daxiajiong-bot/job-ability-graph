import { useState, useEffect, useRef } from "react";
import {
  Card,
  Typography,
  Button,
  Select,
  Form,
  Input,
  message,
  Spin,
  Row,
  Col,
  Tag,
  Descriptions,
  Divider,
  Progress,
  Empty,
  Space,
  Alert,
  Tabs,
  Collapse,
  Dropdown,
  Tooltip,
} from "antd";
import {
  SwapOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  ThunderboltOutlined,
  RocketOutlined,
  BarChartOutlined,
  TrophyOutlined,
  RiseOutlined,
  FallOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import {
  createDocument,
  createCandidateProfile,
  createJobProfile,
  createMatch,
  getMatch,
  createReport,
} from "../api/client";
import GapChart from "../components/GapChart";
import { exportReportAsText, exportReportAsJSON, exportSkillsAsCSV } from "../utils/pdfGenerator";
import useStore from "../store/useStore";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

// ── 动画计数器组件 ──
function AnimatedCounter({ value, duration = 2000, prefix = "", suffix = "" }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    const start = 0;
    const end = value;
    const startTime = Date.now();

    const animate = () => {
      const now = Date.now();
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(start + (end - start) * eased));

      if (progress < 1) {
        ref.current = requestAnimationFrame(animate);
      }
    };

    ref.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(ref.current);
  }, [value, duration]);

  return <span>{prefix}{display}{suffix}</span>;
}

export default function MatchResult() {
  const [loading, setLoading] = useState(false);
  const [matchResult, setMatchResult] = useState(null);
  const [report, setReport] = useState(null);

  const { addMatchHistory } = useStore();
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");

  async function handleMatch() {
    if (!resumeText.trim() || !jdText.trim()) {
      message.warning("请输入简历和 JD 文本");
      return;
    }
    setLoading(true);
    try {
      message.loading({ content: "正在创建简历文档...", key: "match" });
      const resumeDocRes = await createDocument({
        document_type: "resume",
        text: resumeText,
        source: { source_system: "manual" },
      });
      const resumeDocId = resumeDocRes.data.data.document.document_id;

      message.loading({ content: "正在创建 JD 文档...", key: "match" });
      const jdDocRes = await createDocument({
        document_type: "jd",
        text: jdText,
        source: { source_system: "manual" },
      });
      const jdDocId = jdDocRes.data.data.document.document_id;

      message.loading({ content: "正在生成候选人画像...", key: "match" });
      const candRes = await createCandidateProfile(resumeDocId);
      const candProfileId = candRes.data.data.profile.profile_id;

      message.loading({ content: "正在生成岗位画像...", key: "match" });
      const jobRes = await createJobProfile(jdDocId);
      const jobProfileId = jobRes.data.data.profile.profile_id;

      message.loading({ content: "正在执行人岗匹配...", key: "match" });
      const matchRes = await createMatch(candProfileId, jobProfileId);
      const matchData = matchRes.data.data.match;
      setMatchResult(matchData);

      message.loading({ content: "正在生成匹配报告...", key: "match" });
      try {
        const reportRes = await createReport(matchData.match_id);
        setReport(reportRes.data.data.report);
      } catch (e) {
        console.warn("报告生成失败", e);
      }

      message.success({ content: "匹配完成！", key: "match" });

      addMatchHistory({
        resumeText: resumeText.slice(0, 200),
        jdText: jdText.slice(0, 200),
        score: matchData.score,
        matchResult: matchData,
        report: report || null,
      });
    } catch (e) {
      message.error({
        content: "匹配失败: " + (e.response?.data?.error?.message || e.message),
        key: "match",
      });
    } finally {
      setLoading(false);
    }
  }

  function getRadarOption() {
    if (!matchResult) return {};
    const score = matchResult.score ?? 0;
    const details = matchResult.details || {};
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

    return {
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(13, 17, 23, 0.95)",
        borderColor: "rgba(77, 214, 255, 0.2)",
        textStyle: { color: "#e6edf3" },
        formatter: (params) => {
          const val = params.value;
          return `<div style="padding:4px">
            <div style="font-weight:600;margin-bottom:8px">${params.name}</div>
            ${dims.map((d, i) => `
              <div style="display:flex;justify-content:space-between;gap:16px;margin:4px 0">
                <span style="color:#8b949e">${d.name}</span>
                <span style="color:${val[i] >= 80 ? '#52c41a' : val[i] >= 60 ? '#faad14' : '#ff4d4f'};font-weight:600">${val[i]}%</span>
              </div>
            `).join("")}
          </div>`;
        },
      },
      radar: {
        indicator: dims,
        shape: "polygon",
        splitNumber: 5,
        radius: "65%",
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
        axisLine: {
          lineStyle: {
            color: "rgba(77, 214, 255, 0.15)",
          },
        },
        splitLine: {
          lineStyle: {
            color: "rgba(77, 214, 255, 0.08)",
            type: "dashed",
          },
        },
        axisName: {
          color: "#8b949e",
          fontSize: 12,
          fontWeight: 500,
        },
      },
      animationDuration: 1500,
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
                shadowColor: "rgba(77, 214, 255, 0.5)",
                shadowBlur: 6,
              },
            },
          ],
        },
      ],
    };
  }

  function handleExportReport(format = "text") {
    if (!matchResult && !report) {
      message.warning("暂无数据可导出");
      return;
    }
    switch (format) {
      case "json":
        exportReportAsJSON(matchResult, report);
        break;
      case "csv":
        exportSkillsAsCSV(matchResult);
        break;
      default:
        exportReportAsText(matchResult, report);
    }
    message.success("报告已导出");
  }

  // 匹配分数颜色
  function getScoreColor(score) {
    if (score >= 80) return "#52c41a";
    if (score >= 60) return "#4dd6ff";
    if (score >= 40) return "#faad14";
    return "#ff4d4f";
  }

  return (
    <div>
      {/* 页面标题 */}
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <SwapOutlined style={{ marginRight: 8, color: "#4dd6ff" }} />
          人岗匹配
        </Title>
        <Paragraph style={{ color: "#8b949e", margin: 0 }}>
          输入候选人简历和岗位描述，系统将自动完成画像提取、技能匹配和差距分析
        </Paragraph>
      </div>

      {/* 输入区域 */}
      <Row gutter={16}>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <FileTextOutlined style={{ color: "#7b61ff" }} />
                <span>候选人简历</span>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <TextArea
              rows={5}
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              placeholder="粘贴候选人简历文本..."
              style={{ resize: "none" }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <FileTextOutlined style={{ color: "#4dd6ff" }} />
                <span>岗位描述 (JD)</span>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <TextArea
              rows={5}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="粘贴岗位描述文本..."
              style={{ resize: "none" }}
            />
          </Card>
        </Col>
      </Row>

      {/* 操作按钮 */}
      <div style={{ textAlign: "center", margin: "16px 0" }}>
        <Space size="large">
          <Button
            type="primary"
            size="large"
            icon={<ThunderboltOutlined />}
            loading={loading}
            onClick={handleMatch}
            disabled={!resumeText.trim() || !jdText.trim()}
            style={{
              height: 48,
              padding: "0 32px",
              fontSize: 15,
              fontWeight: 600,
            }}
          >
            一键匹配
          </Button>
          {matchResult && (
            <Dropdown
              menu={{
                items: [
                  { key: "text", label: "导出为 TXT", onClick: () => handleExportReport("text") },
                  { key: "json", label: "导出为 JSON", onClick: () => handleExportReport("json") },
                  { key: "csv", label: "导出技能 CSV", onClick: () => handleExportReport("csv") },
                ],
              }}
            >
              <Button size="large" icon={<DownloadOutlined />} style={{ height: 48 }}>
                导出报告
              </Button>
            </Dropdown>
          )}
        </Space>
      </div>

      {/* 结果区域 */}
      <Spin spinning={loading}>
        {matchResult && (
          <Row gutter={16} className="fade-in-up">
            {/* 左侧：匹配得分 + 技能差距 */}
            <Col xs={24} lg={10}>
              {/* 匹配得分卡 */}
              <Card
                className="gradient-border"
                style={{ marginBottom: 16, textAlign: "center" }}
              >
                <div style={{ padding: "12px 0" }}>
                  <div
                    style={{
                      fontSize: 13,
                      color: "#8b949e",
                      marginBottom: 12,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 500,
                    }}
                  >
                    <TrophyOutlined style={{ marginRight: 6 }} />
                    匹配得分
                  </div>
                  <div
                    style={{
                      fontSize: 72,
                      fontWeight: 900,
                      background: `linear-gradient(135deg, ${getScoreColor(matchResult.score || 0)}, ${getScoreColor(matchResult.score || 0)}88)`,
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                      backgroundClip: "text",
                      lineHeight: 1,
                      marginBottom: 8,
                      textShadow: `0 0 40px ${getScoreColor(matchResult.score || 0)}30`,
                    }}
                  >
                    <AnimatedCounter value={matchResult.score ?? 0} />
                  </div>
                  <div style={{ fontSize: 16, color: "#8b949e", marginBottom: 12 }}>
                    / 100
                  </div>
                  <Tag
                    color={getScoreColor(matchResult.score || 0)}
                    style={{
                      fontSize: 14,
                      padding: "4px 20px",
                      borderRadius: 20,
                      fontWeight: 600,
                    }}
                  >
                    {(matchResult.score || 0) >= 80
                      ? "🎯 高度匹配"
                      : (matchResult.score || 0) >= 60
                        ? "✅ 较为匹配"
                        : (matchResult.score || 0) >= 40
                          ? "⚠️ 部分匹配"
                          : "❌ 匹配度低"}
                  </Tag>

                  {/* 匹配度说明 */}
                  <div
                    style={{
                      marginTop: 16,
                      padding: "10px 14px",
                      background: "rgba(77, 214, 255, 0.04)",
                      borderRadius: 8,
                      border: "1px solid rgba(77, 214, 255, 0.06)",
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.6 }}>
                      {(matchResult.score || 0) >= 80
                        ? "候选人技能与岗位要求高度契合，推荐进入面试环节"
                        : (matchResult.score || 0) >= 60
                          ? "候选人基本符合岗位要求，建议针对性提升部分技能"
                          : (matchResult.score || 0) >= 40
                            ? "候选人与岗位存在一定差距，需要重点补充相关技能"
                            : "候选人与岗位匹配度较低，建议考虑其他更适合的岗位"}
                    </div>
                  </div>
                </div>
              </Card>

              {/* 技能差距 */}
              <GapChart matchResult={matchResult} />
            </Col>

            {/* 右侧：雷达图 + 详情 */}
            <Col xs={24} lg={14}>
              <Card
                className="gradient-border"
                title={
                  <Space>
                    <BarChartOutlined style={{ color: "#4dd6ff" }} />
                    <span>匹配维度分析</span>
                  </Space>
                }
                style={{ marginBottom: 16 }}
              >
                <ReactECharts
                  option={getRadarOption()}
                  style={{ height: 300 }}
                  opts={{ renderer: "canvas" }}
                />
              </Card>

              <Collapse
                ghost
                items={[
                  {
                    key: "details",
                    label: (
                      <span style={{ color: "#8b949e" }}>
                        匹配详情 (JSON)
                      </span>
                    ),
                    children: (
                      <pre
                        style={{
                          background: "rgba(77,214,255,0.03)",
                          padding: 16,
                          borderRadius: 8,
                          maxHeight: 300,
                          overflow: "auto",
                          fontSize: 12,
                          border: "1px solid rgba(77,214,255,0.06)",
                        }}
                      >
                        {JSON.stringify(matchResult, null, 2)}
                      </pre>
                    ),
                  },
                ]}
              />
            </Col>
          </Row>
        )}

        {/* 报告区域 */}
        {report && (
          <Card
            className="gradient-border"
            title={
              <Space>
                <FileTextOutlined style={{ color: "#7b61ff" }} />
                <span>匹配报告</span>
              </Space>
            }
            style={{ marginTop: 16 }}
            extra={
              <Tag color={report.state === "ready" ? "green" : "orange"}>
                {report.state || "mock"}
              </Tag>
            }
          >
            {report.content && (
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.8,
                  fontSize: 14,
                }}
              >
                {report.content}
              </div>
            )}
            {!report.content && (
              <pre
                style={{
                  background: "rgba(77,214,255,0.03)",
                  padding: 16,
                  borderRadius: 8,
                  maxHeight: 400,
                  overflow: "auto",
                  fontSize: 12,
                  border: "1px solid rgba(77,214,255,0.06)",
                }}
              >
                {JSON.stringify(report, null, 2)}
              </pre>
            )}
          </Card>
        )}

        {/* 空状态 */}
        {!matchResult && !loading && (
          <Card style={{ marginTop: 16 }}>
            <Empty
              description={
                <span style={{ color: "#8b949e" }}>
                  输入简历和 JD 文本后点击「一键匹配」查看结果
                </span>
              }
            />
          </Card>
        )}
      </Spin>
    </div>
  );
}
