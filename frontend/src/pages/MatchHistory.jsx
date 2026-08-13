import { useState } from "react";
import {
  Card,
  Typography,
  Table,
  Tag,
  Button,
  Space,
  Popconfirm,
  message,
  Empty,
  Modal,
  Row,
  Col,
  Descriptions,
  Divider,
  Spin,
  Progress,
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  ClearOutlined,
  SwapOutlined,
  DownloadOutlined,
  HistoryOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import useStore from "../store/useStore";
import GapChart from "../components/GapChart";
import LearningAdvice from "../components/LearningAdvice";
import { formatMatchLevel } from "../utils/adapters";

const { Title, Paragraph, Text } = Typography;

/**
 * 从文本中提取技能名称
 */
function extractSkillNamesFromText(text) {
  if (!text) return [];
  const patterns = [
    /[：:]\s*(.+?)(?:。|$)/,
    /(?:缺少|缺失|需要|掌握)\s*(.+?)(?:等|。|$)/,
    /^(.+?)(?:等|。|$)/,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      const skills = match[1]
        .split(/[,，、和\s]+/)
        .map((s) => s.trim())
        .filter((s) => s.length > 1 && s.length < 20 && !/^(技能|技术|能力|岗位|要求)$/.test(s));
      if (skills.length > 0) return skills;
    }
  }
  return [];
}

// 从匹配结果中提取技能数量
function getSkillCounts(matchResult) {
  if (!matchResult) return { matched: 0, missing: 0 };

  const details = matchResult.details || {};
  let matched = details.matched_skills?.length ?? 0;
  let missing = details.missing_skills?.length ?? 0;

  // 兼容旧数据：从 learning_path 和 gaps 中提取
  if (matched === 0 && missing === 0) {
    // learning_path 是最可靠的来源
    const learningPath = matchResult.learning_path || [];
    missing = learningPath.filter((lp) => lp.skill).length;

    // 从 gaps 中提取
    const gaps = matchResult.gaps || [];
    gaps.forEach((g) => {
      if (g.category === "skill" && g.text) {
        const skills = extractSkillNamesFromText(g.text);
        missing += skills.length;
      }
    });

    // 从 strengths 中提取
    const strengths = matchResult.strengths || [];
    strengths.forEach((s) => {
      if (s.category === "skill" && s.text) {
        const skills = extractSkillNamesFromText(s.text);
        matched += skills.length;
      }
    });
  }

  return { matched, missing };
}

export default function MatchHistory() {
  const { matchHistory, removeMatchHistory, clearMatchHistory, saveLearningAdvice } = useStore();
  const [detailModal, setDetailModal] = useState(null);
  const [compareModal, setCompareModal] = useState(null);
  const [adviceModal, setAdviceModal] = useState(null);
  const [selectedRows, setSelectedRows] = useState([]);

  function handleBatchDelete() {
    if (selectedRows.length === 0) {
      message.warning("请先选择要删除的记录");
      return;
    }
    Modal.confirm({
      title: "确认批量删除",
      content: `确定要删除选中的 ${selectedRows.length} 条匹配记录吗？删除后不可恢复。`,
      okText: "删除",
      cancelText: "取消",
      okButtonProps: { danger: true },
      onOk: () => {
        selectedRows.forEach((record) => {
          removeMatchHistory(record.timestamp);
        });
        setSelectedRows([]);
        message.success(`成功删除 ${selectedRows.length} 条记录`);
      },
    });
  }

  function handleExport(record) {
    const lines = [
      "═══════════════════════════════════════",
      "         人岗匹配分析报告",
      "═══════════════════════════════════════",
      "",
      `生成时间：${new Date(record.timestamp).toLocaleString("zh-CN")}`,
      `匹配得分：${record.score ?? 0}%`,
      `匹配等级：${formatMatchLevel(record.score ?? 0).text}`,
      "",
      "── 简历文本 ──",
      record.resumeText?.slice(0, 500) || "-",
      "",
      "── JD 文本 ──",
      record.jdText?.slice(0, 500) || "-",
      "",
      "── 匹配详情 ──",
      JSON.stringify(record.matchResult, null, 2),
    ];

    if (record.report?.content) {
      lines.push("", "── 匹配报告 ──", record.report.content);
    }

    const blob = new Blob([lines.join("\n")], {
      type: "text/plain;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `匹配报告_${new Date(record.timestamp).toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    message.success("已导出");
  }

  const columns = [
    {
      title: "时间",
      dataIndex: "timestamp",
      key: "time",
      width: 180,
      render: (ts) => new Date(ts).toLocaleString("zh-CN"),
      sorter: (a, b) => a.timestamp - b.timestamp,
    },
    {
      title: "匹配得分",
      dataIndex: "score",
      key: "score",
      width: 120,
      render: (score) => {
        const { text, color } = formatMatchLevel(score ?? 0);
        return (
          <Tag color={color}>
            {score ?? 0}% {text}
          </Tag>
        );
      },
      sorter: (a, b) => (a.score ?? 0) - (b.score ?? 0),
    },
    {
      title: "技能匹配",
      key: "skills",
      width: 120,
      render: (_, r) => {
        const { matched, missing } = getSkillCounts(r.matchResult);
        const total = matched + missing;
        return (
          <Space size={4}>
            <Tag color="success">{matched}</Tag>
            <Text type="secondary">/</Text>
            <Tag>{total}</Tag>
          </Space>
        );
      },
    },
    {
      title: "掌握率",
      key: "mastery",
      width: 140,
      render: (_, r) => {
        const { matched, missing } = getSkillCounts(r.matchResult);
        const total = matched + missing;
        const percent = total > 0 ? Math.round((matched / total) * 100) : 0;
        const color = percent >= 80 ? "#52c41a" : percent >= 50 ? "#faad14" : "#ff4d4f";
        return (
          <Progress
            percent={percent}
            size="small"
            strokeColor={color}
            format={(p) => `${p}%`}
          />
        );
      },
    },
    {
      title: "操作",
      key: "action",
      width: 300,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => setDetailModal(record)}
          >
            详情
          </Button>
          <Button
            size="small"
            icon={<RocketOutlined />}
            onClick={() => setAdviceModal(record)}
            style={{ color: "#faad14", borderColor: "#faad14" }}
          >
            学习建议
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => handleExport(record)}
          >
            导出
          </Button>
          <Popconfirm
            title="确认删除此记录？"
            onConfirm={() => removeMatchHistory(record.timestamp)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <HistoryOutlined style={{ marginRight: 8, color: "#faad14" }} />
          匹配历史
        </Title>
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
          查看历史匹配记录，支持详情查看、导出和对比
        </Paragraph>
      </div>

      <Card
        title={`历史记录 (${matchHistory.length})`}
        extra={
          <Space>
            {selectedRows.length === 2 && (
              <Button
                icon={<SwapOutlined />}
                onClick={() => setCompareModal(selectedRows)}
              >
                对比选中 ({selectedRows.length})
              </Button>
            )}
            {selectedRows.length > 0 && (
              <Popconfirm
                title={`确定删除选中的 ${selectedRows.length} 条记录？`}
                onConfirm={handleBatchDelete}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button danger icon={<DeleteOutlined />}>
                  批量删除 ({selectedRows.length})
                </Button>
              </Popconfirm>
            )}
            {matchHistory.length > 0 && (
              <Popconfirm
                title="确认清空所有历史记录？"
                onConfirm={() => {
                  clearMatchHistory();
                  message.success("已清空");
                }}
              >
                <Button danger icon={<ClearOutlined />}>
                  清空
                </Button>
              </Popconfirm>
            )}
          </Space>
        }
      >
        <Table
          dataSource={matchHistory}
          columns={columns}
          rowKey={(r) => r.timestamp}
          size="small"
          pagination={{ pageSize: 10 }}
          rowSelection={{
            selectedRowKeys: selectedRows.map((r) => r.timestamp),
            onChange: (_, rows) => setSelectedRows(rows),
          }}
          locale={{
            emptyText: <Empty description="暂无匹配历史记录" />,
          }}
        />
      </Card>

      {/* 详情弹窗 */}
      <Modal
        title="匹配详情"
        open={!!detailModal}
        onCancel={() => setDetailModal(null)}
        footer={null}
        width={900}
      >
        {detailModal && (
          <div style={{ maxHeight: "calc(100vh - 230px)", overflowY: "auto", paddingRight: 8 }}>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="匹配得分">
                <Tag color={formatMatchLevel(detailModal.score ?? 0).color}>
                  {detailModal.score ?? 0}%
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="时间">
                {new Date(detailModal.timestamp).toLocaleString("zh-CN")}
              </Descriptions.Item>
            </Descriptions>

            {detailModal.matchResult && (
              <>
                <Divider>匹配分析</Divider>
                <GapChart matchResult={detailModal.matchResult} />
              </>
            )}

            {detailModal.resumeText && (
              <>
                <Divider>候选人简历</Divider>
                <div
                  style={{
                    background: "var(--accent-subtle)",
                    padding: 16,
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.8,
                    whiteSpace: "pre-wrap",
                    border: "1px solid var(--border-glass)",
                  }}
                >
                  {detailModal.resumeText}
                </div>
              </>
            )}

            {detailModal.jdText && (
              <>
                <Divider>岗位描述 (JD)</Divider>
                <div
                  style={{
                    background: "var(--accent-subtle)",
                    padding: 16,
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.8,
                    whiteSpace: "pre-wrap",
                    border: "1px solid var(--border-glass)",
                  }}
                >
                  {detailModal.jdText}
                </div>
              </>
            )}
          </div>
        )}
      </Modal>

      {/* 对比弹窗 */}
      <Modal
        title="匹配结果对比"
        open={!!compareModal}
        onCancel={() => setCompareModal(null)}
        footer={null}
        width={1000}
      >
        {compareModal && compareModal.length === 2 && (
          <Row gutter={24}>
            {compareModal.map((record, idx) => (
              <Col span={12} key={idx}>
                <Card
                  size="small"
                  title={`记录 ${idx + 1} - ${new Date(record.timestamp).toLocaleString("zh-CN")}`}
                >
                  <Descriptions column={1} size="small" bordered>
                    <Descriptions.Item label="匹配得分">
                      <Tag
                        color={formatMatchLevel(record.score ?? 0).color}
                      >
                        {record.score ?? 0}%
                      </Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="已掌握技能">
                      {record.matchResult?.details?.matched_skills?.length ?? 0}{" "}
                      个
                    </Descriptions.Item>
                    <Descriptions.Item label="缺失技能">
                      {record.matchResult?.details?.missing_skills?.length ?? 0}{" "}
                      个
                    </Descriptions.Item>
                  </Descriptions>
                  <pre
                    style={{
                      background: "var(--accent-soft)",
                      padding: 12,
                      borderRadius: 8,
                      maxHeight: 200,
                      overflow: "auto",
                      fontSize: 11,
                      marginTop: 12,
                    }}
                  >
                    {JSON.stringify(record.matchResult?.details, null, 2)}
                  </pre>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Modal>

      {/* 学习建议弹窗 */}
      <Modal
        title="AI 学习建议"
        open={!!adviceModal}
        onCancel={() => setAdviceModal(null)}
        footer={null}
        width={900}
        destroyOnClose
      >
        <div style={{ maxHeight: "calc(100vh - 230px)", overflowY: "auto", paddingRight: 8 }}>
          {adviceModal && (
            <LearningAdvice
              matchResult={adviceModal.matchResult}
              initialAdvice={adviceModal.learningAdvice}
              onSave={(advice) => saveLearningAdvice(adviceModal.timestamp, advice)}
            />
          )}
        </div>
      </Modal>
    </div>
  );
}
