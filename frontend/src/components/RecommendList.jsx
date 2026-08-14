import { Card, Tag, Typography, Progress, Space, Empty, Spin, Button, Tooltip } from "antd";
import {
  FileTextOutlined,
  UserOutlined,
  SwapOutlined,
  TrophyOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  BulbOutlined,
} from "@ant-design/icons";

const { Text } = Typography;

// 匹配分数颜色
function getScoreColor(score) {
  if (score == null) return "#8b949e";
  if (score >= 80) return "#52c41a";
  if (score >= 60) return "#1890ff";
  if (score >= 40) return "#faad14";
  return "#ff4d4f";
}

// 匹配决策标签
function getDecisionTag(decision) {
  const map = {
    strong_match: { color: "green", text: "强烈推荐" },
    good_match: { color: "blue", text: "推荐" },
    match: { color: "blue", text: "推荐" },
    partial_match: { color: "orange", text: "部分匹配" },
    moderate_match: { color: "orange", text: "一般" },
    weak_match: { color: "red", text: "不推荐" },
    mismatch: { color: "red", text: "不匹配" },
    no_match: { color: "default", text: "不匹配" },
    not_evaluated: { color: "default", text: "待评估" },
    error: { color: "default", text: "匹配失败" },
  };
  const config = map[decision] || { color: "default", text: decision || "未知" };
  return <Tag color={config.color}>{config.text}</Tag>;
}

export default function RecommendList({
  recommendations = [],
  loading = false,
  type = "jd", // "jd" | "resume"
  onMatchClick,
}) {
  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: "48px 0" }}>
        <Spin size="large" tip="正在智能匹配中，请稍候..." />
      </div>
    );
  }

  if (!recommendations.length) {
    return <Empty description="暂无推荐结果" />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {recommendations.map((item, index) => {
        const doc = item.document || {};
        const match = item.match || {};
        const score = match.score ?? null;
        const skills = doc.skills || [];
        const title = doc.title || (type === "jd" ? "未知岗位" : "未知简历");
        const matchedSkills = item.matched_skills || [];
        const missingSkills = item.missing_skills || [];
        const reasons = item.reasons || [];
        const overlap = item.skill_overlap || 0;

        // 副标题：JD 展示公司/地点/薪资/行业，简历展示目标岗位/学历/经验
        const metaParts = [];
        if (type === "jd") {
          if (doc.company_name) metaParts.push(doc.company_name);
          if (doc.location) metaParts.push(doc.location);
          if (doc.salary_range) metaParts.push(doc.salary_range);
          if (doc.industry) metaParts.push(doc.industry);
          if (doc.experience) metaParts.push(doc.experience);
        } else {
          if (doc.education) metaParts.push(doc.education);
          if (doc.experience) metaParts.push(doc.experience);
          if (doc.location) metaParts.push(doc.location);
        }
        const subtitle = metaParts.join(" · ");

        return (
          <Card
            key={doc.document_id || index}
            hoverable
            style={{ position: "relative" }}
            styles={{ body: { padding: "16px 20px" } }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              {/* 排名 */}
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background:
                    index < 3 ? getScoreColor(score) : "var(--bg-elevated)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 18,
                  fontWeight: 700,
                  color: index < 3 ? "#fff" : "var(--text-secondary)",
                  flexShrink: 0,
                }}
              >
                {index + 1}
              </div>

              {/* 主信息 */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 4,
                    flexWrap: "wrap",
                  }}
                >
                  <Text strong style={{ fontSize: 15 }}>
                    {type === "jd" ? <FileTextOutlined /> : <UserOutlined />}{" "}
                    {title}
                  </Text>
                  {getDecisionTag(match.decision)}
                  {index === 0 && (
                    <Tag color="gold" icon={<TrophyOutlined />}>
                      最佳匹配
                    </Tag>
                  )}
                </div>

                {subtitle && (
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    {subtitle}
                  </Text>
                )}

                {/* 推荐理由 */}
                {reasons.length > 0 && (
                  <div style={{ marginTop: 6 }}>
                    <Space size={[4, 4]} wrap>
                      {reasons.map((reason, i) => (
                        <Tag
                          key={i}
                          icon={<BulbOutlined />}
                          color="processing"
                          style={{ marginRight: 0 }}
                        >
                          {reason}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}

                {/* 技能标签：优先展示匹配/缺失，否则展示文档技能 */}
                {(matchedSkills.length > 0 || missingSkills.length > 0) ? (
                  <div style={{ marginTop: 8 }}>
                    <Space size={[4, 4]} wrap>
                      {matchedSkills.slice(0, 8).map((skill) => (
                        <Tag
                          key={`m-${skill}`}
                          color="green"
                          icon={<CheckCircleOutlined />}
                          style={{ marginRight: 0 }}
                        >
                          {skill}
                        </Tag>
                      ))}
                      {missingSkills.slice(0, 8).map((skill) => (
                        <Tooltip key={`x-${skill}`} title="目标方要求但暂未匹配">
                          <Tag
                            color="red"
                            icon={<CloseCircleOutlined />}
                            style={{ marginRight: 0 }}
                          >
                            {skill}
                          </Tag>
                        </Tooltip>
                      ))}
                      {(matchedSkills.length > 8 || missingSkills.length > 8) && (
                        <Tag>+{matchedSkills.length + missingSkills.length - 8}</Tag>
                      )}
                    </Space>
                  </div>
                ) : (
                  skills.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      {skills.slice(0, 8).map((skill) => (
                        <Tag key={skill} style={{ marginBottom: 4 }}>
                          {skill}
                        </Tag>
                      ))}
                      {skills.length > 8 && <Tag>+{skills.length - 8}</Tag>}
                    </div>
                  )
                )}

                {match.summary && (
                  <Text
                    type="secondary"
                    style={{ fontSize: 12, display: "block", marginTop: 6 }}
                    ellipsis={{ tooltip: match.summary }}
                  >
                    {match.summary}
                  </Text>
                )}
              </div>

              {/* 分数 / 重叠数 */}
              <div style={{ textAlign: "center", flexShrink: 0 }}>
                {score != null ? (
                  <>
                    <Progress
                      type="circle"
                      percent={score}
                      size={64}
                      strokeColor={getScoreColor(score)}
                      format={(p) => (
                        <span
                          style={{
                            fontSize: 18,
                            fontWeight: 700,
                            color: getScoreColor(p),
                          }}
                        >
                          {p}
                        </span>
                      )}
                    />
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        匹配度
                      </Text>
                    </div>
                  </>
                ) : (
                  <>
                    <div
                      style={{
                        width: 64,
                        height: 64,
                        borderRadius: "50%",
                        border: `3px solid ${getScoreColor(score)}22`,
                        background: "var(--bg-elevated)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 20,
                        fontWeight: 800,
                        color: "#4dd6ff",
                      }}
                    >
                      {overlap}
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        技能重叠
                      </Text>
                    </div>
                  </>
                )}
              </div>

              {/* 操作 */}
              {onMatchClick && (
                <Button
                  type="link"
                  icon={<SwapOutlined />}
                  onClick={() => onMatchClick(item)}
                  style={{ flexShrink: 0 }}
                >
                  查看详情
                </Button>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
