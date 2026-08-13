import { useState } from "react";
import {
  Card,
  Typography,
  Button,
  Tag,
  Space,
  Divider,
  List,
  Timeline,
  Empty,
  Spin,
  message,
  Alert,
} from "antd";
import {
  RocketOutlined,
  BookOutlined,
  ClockCircleOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  StarOutlined,
  FireOutlined,
  ThunderboltOutlined,
  NodeIndexOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { getLearningAdvice } from "../api/client";

const { Title, Text, Paragraph } = Typography;

const PRIORITY_COLORS = {
  high: "red",
  medium: "orange",
  low: "blue",
};

const PRIORITY_LABELS = {
  high: "高优先",
  medium: "中优先",
  low: "低优先",
};

const RESOURCE_ICONS = {
  book: <BookOutlined />,
  course: <ThunderboltOutlined />,
  documentation: <BookOutlined />,
  practice: <RocketOutlined />,
  tool: <StarOutlined />,
};

export default function LearningAdvice({ matchResult, initialAdvice, onSave }) {
  const [loading, setLoading] = useState(false);
  const [advice, setAdvice] = useState(initialAdvice || null);

  const score = matchResult?.score ?? 0;

  async function handleGenerateAdvice() {
    const matchId = matchResult?.match_id || matchResult?.id;
    if (!matchId) {
      message.warning("匹配结果无效，无法生成学习建议");
      return;
    }
    setLoading(true);
    try {
      const res = await getLearningAdvice(matchId);
      const adviceData = res.data.data.advice;
      setAdvice(adviceData);
      onSave?.(adviceData);
      message.success("学习建议生成成功");
    } catch (e) {
      message.error(
        "生成失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
  }

  if (!matchResult) return null;

  return (
    <Card
      className="gradient-border"
      title={
        <Space>
          <RocketOutlined style={{ color: "#faad14" }} />
          <span>AI 学习建议</span>
          {advice?.implementation && (
            <Tag color={
              advice.implementation === "mock_learning_advisor" ? "warning" :
              advice.implementation === "graph_rag_learning_advisor" ? "cyan" : "green"
            }>
              {advice.implementation === "mock_learning_advisor" ? "Mock" :
               advice.implementation === "graph_rag_learning_advisor" ? "Graph-RAG" : "LLM"}
            </Tag>
          )}
        </Space>
      }
      extra={
        !advice ? (
          <Button
            type="primary"
            icon={<BulbOutlined />}
            onClick={handleGenerateAdvice}
            loading={loading}
            style={{
              background: "linear-gradient(135deg, #faad14, #ff7a45)",
              border: "none",
            }}
          >
            生成学习建议
          </Button>
        ) : null
      }
      style={{ marginTop: 16 }}
    >
      {!advice && !loading && (
        <Empty
          description={
            <span style={{ color: "var(--text-secondary)" }}>
              点击上方按钮生成 AI 学习建议
            </span>
          }
        />
      )}

      <Spin spinning={loading}>
        {advice && (
          <div className="fade-in">
            {/* 总结 */}
            {advice.summary && (
              <Alert
                message={advice.summary}
                type="warning"
                showIcon
                icon={<FireOutlined />}
                style={{ marginBottom: 16 }}
              />
            )}

            {/* 技能差距详情 */}
            {advice.skill_gaps?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <Title level={5} style={{ color: "var(--text-primary)", marginBottom: 12 }}>
                  <ExclamationCircleOutlined style={{ marginRight: 8, color: "#ff4d4f" }} />
                  技能差距分析
                </Title>
                <List
                  dataSource={advice.skill_gaps}
                  renderItem={(gap) => (
                    <Card
                      size="small"
                      style={{
                        marginBottom: 12,
                        background: "var(--accent-subtle)",
                        border: "1px solid var(--border-glass)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <Text strong style={{ color: "var(--text-primary)", fontSize: 15 }}>
                          {gap.skill}
                        </Text>
                        <Tag color={PRIORITY_COLORS[gap.priority] || "default"}>
                          {PRIORITY_LABELS[gap.priority] || gap.priority}
                        </Tag>
                      </div>

                      <div style={{ display: "flex", gap: 16, marginBottom: 12, flexWrap: "wrap" }}>
                        {gap.current_level && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>当前水平</Text>
                            <div>
                              <Tag color="default">{gap.current_level}</Tag>
                            </div>
                          </div>
                        )}
                        {gap.target_level && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>目标水平</Text>
                            <div>
                              <Tag color="success">{gap.target_level}</Tag>
                            </div>
                          </div>
                        )}
                        {gap.estimated_time && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              <ClockCircleOutlined style={{ marginRight: 4 }} />
                              预计时长
                            </Text>
                            <div>
                              <Tag color="blue">{gap.estimated_time}</Tag>
                            </div>
                          </div>
                        )}
                      </div>

                      {gap.learning_steps?.length > 0 && (
                        <div style={{ marginBottom: 8 }}>
                          <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 6 }}>
                            学习步骤：
                          </Text>
                          <ol style={{ margin: 0, paddingLeft: 20 }}>
                            {gap.learning_steps.map((step, i) => (
                              <li key={i} style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.8 }}>
                                {step}
                              </li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {gap.resources?.length > 0 && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                            推荐资源：
                          </Text>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {gap.resources.map((res, i) => (
                              <Tag key={i} color="geekblue" style={{ fontSize: 12 }}>
                                {res}
                              </Tag>
                            ))}
                          </div>
                        </div>
                      )}
                    </Card>
                  )}
                />
              </div>
            )}

            {/* 知识图谱分析 */}
            {advice.graph_context?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <Title level={5} style={{ color: "var(--text-primary)", marginBottom: 12 }}>
                  <NodeIndexOutlined style={{ marginRight: 8, color: "#13c2c2" }} />
                  知识图谱分析依据
                </Title>
                {advice.graph_context.map((ctx, idx) => (
                  <Card
                    key={idx}
                    size="small"
                    style={{
                      marginBottom: 12,
                      background: "var(--accent-subtle)",
                      border: "1px solid var(--border-glass)",
                    }}
                  >
                    <Text strong style={{ color: "var(--text-primary)", fontSize: 14, display: "block", marginBottom: 8 }}>
                      {ctx.skill}
                    </Text>

                    {ctx.co_occurring_skills?.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <NodeIndexOutlined style={{ marginRight: 4 }} />
                          关联技能（岗位共现）：
                        </Text>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                          {ctx.co_occurring_skills.map((s, i) => (
                            <Tag key={i} color="cyan" style={{ fontSize: 12 }}>
                              {s.name} ({s.co_occurrence_count})
                            </Tag>
                          ))}
                        </div>
                      </div>
                    )}

                    {ctx.demanding_jobs?.length > 0 && (
                      <div style={{ marginBottom: 8 }}>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <RocketOutlined style={{ marginRight: 4 }} />
                          需求岗位：
                        </Text>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                          {ctx.demanding_jobs.map((j, i) => (
                            <Tag key={i} color="blue" style={{ fontSize: 12 }}>
                              {j.title}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    )}

                    {ctx.jd_evidence?.length > 0 && (
                      <div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          <FileTextOutlined style={{ marginRight: 4 }} />
                          JD 真实要求：
                        </Text>
                        {ctx.jd_evidence.map((ev, i) => (
                          <div
                            key={i}
                            style={{
                              marginTop: 4,
                              padding: "6px 10px",
                              background: "rgba(19, 194, 194, 0.04)",
                              borderRadius: 6,
                              borderLeft: "3px solid #13c2c2",
                              fontSize: 12,
                              color: "var(--text-secondary)",
                              lineHeight: 1.6,
                            }}
                          >
                            "{ev.quote}"
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}

            {/* 学习计划 */}
            {advice.learning_plan?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <Title level={5} style={{ color: "var(--text-primary)", marginBottom: 12 }}>
                  <BookOutlined style={{ marginRight: 8, color: "#4dd6ff" }} />
                  分阶段学习计划
                </Title>
                <Timeline
                  items={advice.learning_plan.map((phase, index) => ({
                    color: index === 0 ? "red" : index === 1 ? "orange" : "green",
                    children: (
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                          <Text strong style={{ color: "var(--text-primary)", fontSize: 14 }}>
                            {phase.phase}
                          </Text>
                          {phase.duration && (
                            <Tag color="blue" style={{ fontSize: 11 }}>
                              <ClockCircleOutlined style={{ marginRight: 4 }} />
                              {phase.duration}
                            </Tag>
                          )}
                        </div>
                        {phase.goals?.length > 0 && (
                          <div style={{ marginBottom: 8 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>目标：</Text>
                            <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                              {phase.goals.map((goal, i) => (
                                <li key={i} style={{ color: "var(--text-secondary)", fontSize: 13, lineHeight: 1.6 }}>
                                  {goal}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {phase.activities?.length > 0 && (
                          <div>
                            <Text type="secondary" style={{ fontSize: 12 }}>活动：</Text>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                              {phase.activities.map((act, i) => (
                                <Tag key={i} style={{ fontSize: 12 }}>
                                  {act}
                                </Tag>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    ),
                  }))}
                />
              </div>
            )}

            {/* 推荐资源 */}
            {advice.recommended_resources?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <Title level={5} style={{ color: "var(--text-primary)", marginBottom: 12 }}>
                  <StarOutlined style={{ marginRight: 8, color: "#7b61ff" }} />
                  推荐资源
                </Title>
                <List
                  size="small"
                  dataSource={advice.recommended_resources}
                  renderItem={(resource) => (
                    <List.Item style={{ padding: "8px 0", border: "none" }}>
                      <Space>
                        {RESOURCE_ICONS[resource.type] || <BookOutlined />}
                        <div>
                          <Text strong style={{ color: "var(--text-primary)", fontSize: 13 }}>
                            {resource.name}
                          </Text>
                          {resource.description && (
                            <div>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {resource.description}
                              </Text>
                            </div>
                          )}
                        </div>
                        <Tag style={{ fontSize: 11 }}>{resource.type}</Tag>
                      </Space>
                    </List.Item>
                  )}
                />
              </div>
            )}

            {/* 职业建议 */}
            {advice.career_advice && (
              <div>
                <Title level={5} style={{ color: "var(--text-primary)", marginBottom: 12 }}>
                  <BulbOutlined style={{ marginRight: 8, color: "#faad14" }} />
                  职业发展建议
                </Title>
                <div
                  style={{
                    padding: 16,
                    background: "linear-gradient(135deg, rgba(250, 173, 20, 0.06) 0%, rgba(123, 97, 255, 0.04) 100%)",
                    borderRadius: 10,
                    border: "1px solid rgba(250, 173, 20, 0.1)",
                  }}
                >
                  <Paragraph style={{ color: "var(--text-primary)", margin: 0, lineHeight: 1.8, fontSize: 14 }}>
                    {advice.career_advice}
                  </Paragraph>
                </div>
              </div>
            )}
          </div>
        )}
      </Spin>
    </Card>
  );
}
