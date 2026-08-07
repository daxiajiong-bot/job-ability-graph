import { useMemo } from "react";
import {
  Card,
  Typography,
  Tag,
  Space,
  Progress,
  Divider,
  List,
  Tooltip,
  Empty,
  Row,
  Col,
} from "antd";
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  AimOutlined,
  RiseOutlined,
  FallOutlined,
  MinusOutlined,
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";

const { Text, Title } = Typography;

/**
 * 解析匹配结果，提取技能差距数据
 */
function parseMatchResult(matchResult) {
  if (!matchResult) return null;

  const score = matchResult.score ?? 0;
  const details = matchResult.details || matchResult.attributes || {};

  // 提取匹配的技能
  const matchedSkills = details.matched_skills || [];
  const missingSkills = details.missing_skills || [];
  const partialSkills = details.partial_skills || [];

  // 提取维度分数
  const dimensions = details.dimensions || details;
  const dimScores = {
    技能匹配: dimensions.skill_score ?? score,
    知识匹配: dimensions.knowledge_score ?? Math.max(0, score - 10),
    经验匹配: dimensions.experience_score ?? Math.max(0, score - 5),
    通用能力: dimensions.ability_score ?? Math.max(0, score - 15),
    综合得分: score,
  };

  return {
    score,
    matchedSkills,
    missingSkills,
    partialSkills,
    dimScores,
    implementation: matchResult.implementation || "mock",
    state: matchResult.state,
  };
}

/**
 * 雷达图配置
 */
function getRadarOption(dimScores) {
  const dims = Object.keys(dimScores).map((name) => ({
    name,
    max: 100,
  }));
  const values = Object.values(dimScores);

  return {
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(13, 17, 23, 0.9)",
      borderColor: "rgba(77, 214, 255, 0.3)",
      textStyle: { color: "#e6edf3" },
    },
    radar: {
      indicator: dims,
      shape: "polygon",
      splitNumber: 5,
      axisName: {
        color: "var(--text-secondary)",
        fontSize: 12,
      },
      splitArea: {
        areaStyle: {
          color: [
            "rgba(77, 214, 255, 0.02)",
            "rgba(77, 214, 255, 0.05)",
            "rgba(77, 214, 255, 0.02)",
            "rgba(77, 214, 255, 0.05)",
            "rgba(77, 214, 255, 0.02)",
          ],
        },
      },
      axisLine: {
        lineStyle: { color: "rgba(77, 214, 255, 0.2)" },
      },
      splitLine: {
        lineStyle: { color: "rgba(77, 214, 255, 0.1)" },
      },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: values,
            name: "匹配度",
            symbol: "circle",
            symbolSize: 6,
            lineStyle: {
              color: "#4dd6ff",
              width: 2,
            },
            areaStyle: {
              color: {
                type: "linear",
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: "rgba(77, 214, 255, 0.3)" },
                  { offset: 1, color: "rgba(77, 214, 255, 0.05)" },
                ],
              },
            },
            itemStyle: {
              color: "#4dd6ff",
              borderColor: "#fff",
              borderWidth: 1,
            },
          },
        ],
      },
    ],
  };
}

/**
 * 技能条形图配置
 */
function getSkillBarOption(matchedSkills, missingSkills) {
  const categories = [
    ...missingSkills.map((s) => (typeof s === "string" ? s : s.name || s.skill)),
    ...matchedSkills.map((s) => (typeof s === "string" ? s : s.name || s.skill)),
  ];

  const matchedValues = new Array(missingSkills.length).fill(0);
  const missingValues = [
    ...new Array(missingSkills.length).fill(100),
    ...new Array(matchedSkills.length).fill(0),
  ];
  const matchedFilled = [
    ...new Array(missingSkills.length).fill(0),
    ...new Array(matchedSkills.length).fill(100),
  ];

  return {
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(13, 17, 23, 0.9)",
      borderColor: "rgba(77, 214, 255, 0.3)",
      textStyle: { color: "#e6edf3" },
    },
    grid: {
      left: 100,
      right: 30,
      top: 10,
      bottom: 10,
    },
    xAxis: {
      type: "value",
      max: 100,
      show: false,
    },
    yAxis: {
      type: "category",
      data: categories,
      axisLabel: {
        color: "var(--text-secondary)",
        fontSize: 11,
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        name: "已掌握",
        type: "bar",
        stack: "total",
        data: matchedFilled,
        itemStyle: {
          color: "#52c41a",
          borderRadius: [0, 4, 4, 0],
        },
        barWidth: 16,
        label: {
          show: true,
          position: "right",
          formatter: (params) => (params.value > 0 ? "✓" : ""),
          color: "#52c41a",
          fontSize: 14,
        },
      },
      {
        name: "缺失",
        type: "bar",
        stack: "total",
        data: missingValues,
        itemStyle: {
          color: "rgba(255, 77, 79, 0.6)",
          borderRadius: [0, 4, 4, 0],
        },
        barWidth: 16,
        label: {
          show: true,
          position: "right",
          formatter: (params) => (params.value > 0 ? "✗" : ""),
          color: "#ff4d4f",
          fontSize: 14,
        },
      },
    ],
  };
}

/**
 * GapChart 组件 - 技能差距分析图表
 */
export default function GapChart({ matchResult, style }) {
  const gapData = useMemo(
    () => parseMatchResult(matchResult),
    [matchResult]
  );

  if (!gapData) {
    return (
      <Card title="技能差距分析" style={style}>
        <Empty description="暂无匹配数据，请先执行人岗匹配" />
      </Card>
    );
  }

  const {
    score,
    matchedSkills,
    missingSkills,
    partialSkills,
    dimScores,
    implementation,
    state,
  } = gapData;

  // 判断是否为 mock 数据
  const isMock = implementation === "mock" || state === "mock";

  return (
    <div style={style}>
      {/* 匹配得分概览 */}
      <Card
        title={
          <Space>
            <AimOutlined />
            <span>匹配得分</span>
          </Space>
        }
        size="small"
        style={{ marginBottom: 16 }}
      >
        <div style={{ textAlign: "center", padding: "16px 0" }}>
          <Progress
            type="dashboard"
            percent={Math.round(score)}
            format={(p) => (
              <span style={{ color: "#e6edf3", fontSize: 24 }}>{p}%</span>
            )}
            strokeColor={{
              "0%": "#ff4d4f",
              "50%": "#faad14",
              "100%": "#52c41a",
            }}
            size={140}
          />
          <div style={{ marginTop: 12 }}>
            <Tag
              color={score >= 80 ? "green" : score >= 60 ? "orange" : "red"}
              style={{ fontSize: 14, padding: "2px 12px" }}
            >
              {score >= 80 ? "高度匹配" : score >= 60 ? "中度匹配" : "低度匹配"}
            </Tag>
          </div>
          {isMock && (
            <Tag color="warning" style={{ marginTop: 8 }}>
              Mock 数据（后端使用模拟数据）
            </Tag>
          )}
        </div>
      </Card>

      {/* 维度雷达图 */}
      <Card
        title="匹配维度分析"
        size="small"
        style={{ marginBottom: 16 }}
      >
        <ReactECharts
          option={getRadarOption(dimScores)}
          style={{ height: 280 }}
          opts={{ renderer: "canvas" }}
        />
      </Card>

      {/* 技能差距详情 */}
      <Card title="技能差距详情" size="small">
        {/* 技能统计概览 */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-around",
            marginBottom: 20,
            padding: "12px 0",
            background: "rgba(77, 214, 255, 0.02)",
            borderRadius: 8,
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#52c41a" }}>
              {matchedSkills.length}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>已掌握</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#ff4d4f" }}>
              {missingSkills.length}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>缺失</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#faad14" }}>
              {partialSkills.length}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>部分匹配</div>
          </div>
        </div>

        {/* 已掌握技能 */}
        {matchedSkills.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ color: "#52c41a", fontSize: 13 }}>
              <CheckCircleOutlined style={{ marginRight: 6 }} />
              已掌握技能 ({matchedSkills.length})
            </Text>
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {matchedSkills.map((skill, index) => {
                const name = typeof skill === "string" ? skill : skill.name || skill.skill;
                return (
                  <Tag
                    key={index}
                    color="success"
                    style={{
                      marginBottom: 4,
                      padding: "3px 12px",
                      borderRadius: 6,
                    }}
                  >
                    <RiseOutlined style={{ marginRight: 4, fontSize: 11 }} />
                    {name}
                  </Tag>
                );
              })}
            </div>
          </div>
        )}

        {/* 缺失技能 */}
        {missingSkills.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ color: "#ff4d4f", fontSize: 13 }}>
              <CloseCircleOutlined style={{ marginRight: 6 }} />
              缺失技能 ({missingSkills.length})
            </Text>
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {missingSkills.map((skill, index) => {
                const name = typeof skill === "string" ? skill : skill.name || skill.skill;
                const importance = typeof skill === "object" ? skill.importance : null;
                return (
                  <Tooltip
                    key={index}
                    title={importance ? `重要性: ${importance}` : "建议补充此技能"}
                  >
                    <Tag
                      color="error"
                      style={{
                        marginBottom: 4,
                        padding: "3px 12px",
                        borderRadius: 6,
                      }}
                    >
                      <FallOutlined style={{ marginRight: 4, fontSize: 11 }} />
                      {name}
                      {importance && (
                        <span style={{ marginLeft: 4, fontSize: 10, opacity: 0.7 }}>
                          ({importance})
                        </span>
                      )}
                    </Tag>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        )}

        {/* 部分匹配技能 */}
        {partialSkills.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong style={{ color: "#faad14", fontSize: 13 }}>
              <ExclamationCircleOutlined style={{ marginRight: 6 }} />
              部分匹配 ({partialSkills.length})
            </Text>
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {partialSkills.map((skill, index) => {
                const name = typeof skill === "string" ? skill : skill.name || skill.skill;
                const level = typeof skill === "object" ? skill.level : null;
                return (
                  <Tooltip
                    key={index}
                    title={level ? `当前水平: ${level}` : "需要进一步提升"}
                  >
                    <Tag
                      color="warning"
                      style={{
                        marginBottom: 4,
                        padding: "3px 12px",
                        borderRadius: 6,
                      }}
                    >
                      <MinusOutlined style={{ marginRight: 4, fontSize: 11 }} />
                      {name}
                      {level && (
                        <span style={{ marginLeft: 4, fontSize: 10, opacity: 0.7 }}>
                          ({level})
                        </span>
                      )}
                    </Tag>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        )}

        {/* 无技能数据时显示维度条形图 */}
        {matchedSkills.length === 0 &&
          missingSkills.length === 0 &&
          partialSkills.length === 0 && (
            <div>
              <Divider style={{ margin: "16px 0" }}>
                <span style={{ color: "var(--text-secondary)", fontSize: 12 }}>维度得分</span>
              </Divider>
              {Object.entries(dimScores).map(([name, value]) => (
                <div key={name} style={{ marginBottom: 12 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginBottom: 6,
                    }}
                  >
                    <Text style={{ color: "var(--text-secondary)", fontSize: 13 }}>{name}</Text>
                    <Text
                      style={{
                        color: value >= 80 ? "#52c41a" : value >= 60 ? "#faad14" : "#ff4d4f",
                        fontWeight: 600,
                      }}
                    >
                      {Math.round(value)}%
                    </Text>
                  </div>
                  <Progress
                    percent={Math.round(value)}
                    showInfo={false}
                    strokeColor={
                      value >= 80
                        ? "#52c41a"
                        : value >= 60
                        ? "#faad14"
                        : "#ff4d4f"
                    }
                    trailColor="rgba(77, 214, 255, 0.06)"
                    size="small"
                  />
                </div>
              ))}
            </div>
          )}

        {/* 无任何数据 */}
        {matchedSkills.length === 0 &&
          missingSkills.length === 0 &&
          partialSkills.length === 0 &&
          Object.keys(dimScores).length === 0 && (
            <Empty
              description="暂无详细差距数据"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
      </Card>
    </div>
  );
}
