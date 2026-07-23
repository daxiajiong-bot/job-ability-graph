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
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  ClearOutlined,
  SwapOutlined,
  DownloadOutlined,
  HistoryOutlined,
} from "@ant-design/icons";
import useStore from "../store/useStore";
import GapChart from "../components/GapChart";
import { formatMatchLevel } from "../utils/adapters";

const { Title, Paragraph, Text } = Typography;

export default function MatchHistory() {
  const { matchHistory, removeMatchHistory, clearMatchHistory } = useStore();
  const [detailModal, setDetailModal] = useState(null);
  const [compareModal, setCompareModal] = useState(null);
  const [selectedRows, setSelectedRows] = useState([]);

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
      title: "简历摘要",
      key: "resume",
      ellipsis: true,
      render: (_, r) => (
        <Text type="secondary">{r.resumeText?.slice(0, 60) || "-"}...</Text>
      ),
    },
    {
      title: "JD 摘要",
      key: "jd",
      ellipsis: true,
      render: (_, r) => (
        <Text type="secondary">{r.jdText?.slice(0, 60) || "-"}...</Text>
      ),
    },
    {
      title: "实现方式",
      dataIndex: ["matchResult", "implementation"],
      key: "impl",
      width: 100,
      render: (v) => <Tag>{v || "mock"}</Tag>,
    },
    {
      title: "操作",
      key: "action",
      width: 240,
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
        <Paragraph style={{ color: "#8b949e", margin: 0 }}>
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
            getCheckboxProps: (record) => ({
              disabled: selectedRows.length >= 2 && !selectedRows.find((r) => r.timestamp === record.timestamp),
            }),
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
        width={800}
      >
        {detailModal && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="匹配得分">
                <Tag color={formatMatchLevel(detailModal.score ?? 0).color}>
                  {detailModal.score ?? 0}%
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="时间">
                {new Date(detailModal.timestamp).toLocaleString("zh-CN")}
              </Descriptions.Item>
              <Descriptions.Item label="实现方式" span={2}>
                {detailModal.matchResult?.implementation || "mock"}
              </Descriptions.Item>
            </Descriptions>

            {detailModal.matchResult && (
              <>
                <Divider>匹配分析</Divider>
                <GapChart matchResult={detailModal.matchResult} />
              </>
            )}

            {detailModal.report?.content && (
              <>
                <Divider>匹配报告</Divider>
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
                  {detailModal.report.content}
                </div>
              </>
            )}

            <Divider>原始数据</Divider>
            <pre
              style={{
                background: "rgba(77,214,255,0.05)",
                padding: 16,
                borderRadius: 8,
                maxHeight: 300,
                overflow: "auto",
                fontSize: 12,
              }}
            >
              {JSON.stringify(detailModal.matchResult, null, 2)}
            </pre>
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
                    <Descriptions.Item label="实现方式">
                      {record.matchResult?.implementation || "mock"}
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
                      background: "rgba(77,214,255,0.05)",
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
    </div>
  );
}
