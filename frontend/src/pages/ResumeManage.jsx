import { useState, useCallback } from "react";
import {
  Card,
  Typography,
  Upload,
  Button,
  Input,
  Form,
  message,
  Table,
  Tag,
  Space,
  Modal,
  Descriptions,
  Spin,
  Divider,
  Tabs,
  Progress,
  List,
  Badge,
  Tooltip,
} from "antd";
import {
  UploadOutlined,
  UserOutlined,
  ExperimentOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  InboxOutlined,
  DeleteOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import {
  createDocument,
  createDocumentOCR,
  createCandidateProfile,
  getCandidateProfile,
} from "../api/client";
import OCRCorrectionModal from "../components/OCRCorrectionModal";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

export default function ResumeManage() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [profiles, setProfiles] = useState({});
  const [profileModal, setProfileModal] = useState(null);
  const [activeTab, setActiveTab] = useState("text");

  // ── OCR 校正状态 ──
  const [ocrCorrection, setOcrCorrection] = useState(null);

  // ── 批量上传状态 ──
  const [batchFiles, setBatchFiles] = useState([]);
  const [batchUploading, setBatchUploading] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ current: 0, total: 0 });

  async function handleCreateText(values) {
    setLoading(true);
    try {
      const res = await createDocument({
        document_type: "resume",
        text: values.text,
        source: { source_system: "manual" },
      });
      const doc = res.data.data.document;
      setDocuments((prev) => [{ ...doc, _raw: values.text }, ...prev]);
      message.success("简历文档创建成功");
      form.resetFields();
    } catch (e) {
      message.error(
        "创建失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleOCRUpload(file) {
    setLoading(true);
    const formData = new FormData();
    formData.append("document_type", "resume");
    formData.append("file", file);
    try {
      const res = await createDocumentOCR(formData);
      const doc = res.data.data.document;
      setOcrCorrection({
        text: doc.text || doc._raw || "",
        confidence: doc.confidence,
        filename: file.name,
        doc,
      });
      message.success("OCR 识别成功，请检查并修正结果");
    } catch (e) {
      message.error(
        "OCR 失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
    return false;
  }

  // ── OCR 校正确认 ──
  async function handleOCRCorrectionConfirm(correctedText) {
    if (!ocrCorrection?.doc) return;
    try {
      const res = await createDocument({
        document_type: "resume",
        text: correctedText,
        source: { source_system: "ocr_corrected" },
      });
      const doc = res.data.data.document;
      setDocuments((prev) => [{ ...doc, _raw: correctedText }, ...prev]);
      message.success("校正后的简历文档已创建");
    } catch (e) {
      message.error(
        "创建失败: " + (e.response?.data?.error?.message || e.message)
      );
    }
    setOcrCorrection(null);
  }

  // ── 批量文件选择 ──
  const handleBatchFileSelect = useCallback((info) => {
    const fileList = info.fileList.map((file) => ({
      uid: file.uid,
      name: file.name,
      size: file.size,
      status: "pending",
      file: file.originFileObj,
      result: null,
      error: null,
    }));
    setBatchFiles(fileList);
  }, []);

  const handleRemoveBatchFile = useCallback((uid) => {
    setBatchFiles((prev) => prev.filter((f) => f.uid !== uid));
  }, []);

  // ── 批量上传处理 ──
  const handleBatchUpload = useCallback(async () => {
    if (batchFiles.length === 0) {
      message.warning("请先选择文件");
      return;
    }

    setBatchUploading(true);
    setBatchProgress({ current: 0, total: batchFiles.length });

    let successCount = 0;
    let errorCount = 0;

    for (let i = 0; i < batchFiles.length; i++) {
      const fileItem = batchFiles[i];
      setBatchProgress({ current: i + 1, total: batchFiles.length });

      setBatchFiles((prev) =>
        prev.map((f) =>
          f.uid === fileItem.uid ? { ...f, status: "uploading" } : f
        )
      );

      try {
        const formData = new FormData();
        formData.append("document_type", "resume");
        formData.append("file", fileItem.file);

        const res = await createDocumentOCR(formData);
        const doc = res.data.data.document;

        setBatchFiles((prev) =>
          prev.map((f) =>
            f.uid === fileItem.uid
              ? { ...f, status: "success", result: doc }
              : f
          )
        );

        setDocuments((prev) => [{ ...doc, _raw: "(批量OCR)" }, ...prev]);
        successCount++;
      } catch (e) {
        setBatchFiles((prev) =>
          prev.map((f) =>
            f.uid === fileItem.uid
              ? { ...f, status: "error", error: e.message }
              : f
          )
        );
        errorCount++;
      }
    }

    setBatchUploading(false);

    if (successCount > 0) {
      message.success(`批量上传完成：${successCount} 个成功`);
    }
    if (errorCount > 0) {
      message.error(`${errorCount} 个文件上传失败`);
    }
  }, [batchFiles]);

  const handleClearBatch = useCallback(() => {
    setBatchFiles([]);
    setBatchProgress({ current: 0, total: 0 });
  }, []);

  async function handleBuildProfile(doc) {
    setLoading(true);
    try {
      const res = await createCandidateProfile(doc.document_id || doc.id);
      const profile = res.data.data.profile;
      setProfiles((prev) => ({
        ...prev,
        [doc.document_id || doc.id]: profile,
      }));
      message.success("候选人画像生成成功");
    } catch (e) {
      message.error(
        "画像生成失败: " + (e.response?.data?.error?.message || e.message)
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleViewProfile(doc) {
    const docId = doc.document_id || doc.id;
    if (profiles[docId]) {
      setProfileModal(profiles[docId]);
      return;
    }
    setLoading(true);
    try {
      const res = await getCandidateProfile(docId);
      const profile = res.data.data.profile;
      setProfiles((prev) => ({ ...prev, [docId]: profile }));
      setProfileModal(profile);
    } catch (e) {
      message.info("该文档尚未生成画像，请先点击「生成画像」");
    } finally {
      setLoading(false);
    }
  }

  const columns = [
    {
      title: "ID",
      dataIndex: "document_id",
      key: "id",
      ellipsis: true,
      width: 200,
      render: (id) => <Text code>{id?.slice(0, 16)}...</Text>,
    },
    {
      title: "类型",
      dataIndex: "document_type",
      key: "type",
      width: 80,
      render: () => <Tag color="green">简历</Tag>,
    },
    {
      title: "来源",
      key: "source",
      width: 100,
      render: (_, r) => <Tag>{r.source?.source_system || "manual"}</Tag>,
    },
    {
      title: "文本长度",
      key: "length",
      width: 100,
      render: (_, r) => (
        <Text type="secondary">{r.text_length || "-"} 字</Text>
      ),
    },
    {
      title: "操作",
      key: "action",
      width: 240,
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<ExperimentOutlined />}
            onClick={() => handleBuildProfile(record)}
          >
            生成画像
          </Button>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewProfile(record)}
          >
            查看
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <UserOutlined style={{ marginRight: 8, color: "#7b61ff" }} />
          简历管理
        </Title>
        <Paragraph style={{ color: "#8b949e", margin: 0 }}>
          上传候选人简历，系统将自动提取技能、经验等信息生成候选人画像
        </Paragraph>
      </div>

      <Spin spinning={loading}>
        <Card title="上传简历" style={{ marginBottom: 24 }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "text",
                label: "文本输入",
                children: (
                  <Form
                    form={form}
                    onFinish={handleCreateText}
                    layout="vertical"
                  >
                    <Form.Item
                      name="text"
                      label="简历原文"
                      rules={[{ required: true, message: "请输入简历文本" }]}
                    >
                      <TextArea
                        rows={8}
                        placeholder="粘贴简历原文，例如：&#10;&#10;姓名：张三&#10;技能：Python、MySQL、Linux&#10;项目经历：&#10;1. 接口自动化测试平台 - 使用 Python、Pytest 完成..."
                      />
                    </Form.Item>
                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        icon={<UserOutlined />}
                        loading={loading}
                      >
                        创建简历文档
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
              {
                key: "ocr",
                label: "单文件上传 (OCR)",
                children: (
                  <div style={{ padding: "24px 0" }}>
                    <Upload.Dragger
                      accept=".png,.jpg,.jpeg,.pdf,.bmp"
                      beforeUpload={handleOCRUpload}
                      showUploadList={false}
                    >
                      <p style={{ padding: 24 }}>
                        <UploadOutlined
                          style={{ fontSize: 32, color: "#4dd6ff" }}
                        />
                      </p>
                      <p>点击或拖拽图片/PDF 文件上传</p>
                      <p type="secondary">
                        支持 PNG、JPG、PDF 格式，系统将 OCR 识别文本
                      </p>
                    </Upload.Dragger>
                  </div>
                ),
              },
              {
                key: "batch",
                label: (
                  <Space>
                    <span>批量上传</span>
                    {batchFiles.length > 0 && (
                      <Badge
                        count={batchFiles.length}
                        style={{ backgroundColor: "#4dd6ff" }}
                      />
                    )}
                  </Space>
                ),
                children: (
                  <div style={{ padding: "16px 0" }}>
                    <Upload.Dragger
                      multiple
                      accept=".png,.jpg,.jpeg,.pdf,.bmp"
                      beforeUpload={() => false}
                      onChange={handleBatchFileSelect}
                      showUploadList={false}
                      disabled={batchUploading}
                    >
                      <p style={{ padding: 16 }}>
                        <InboxOutlined
                          style={{ fontSize: 48, color: "#4dd6ff" }}
                        />
                      </p>
                      <p style={{ fontSize: 16 }}>
                        点击或拖拽多个文件到此区域
                      </p>
                      <p type="secondary">
                        支持同时选择多个 PNG、JPG、PDF 文件进行批量 OCR 识别
                      </p>
                    </Upload.Dragger>

                    {batchFiles.length > 0 && (
                      <Card
                        size="small"
                        style={{ marginTop: 16 }}
                        title={
                          <Space>
                            <span>待上传文件</span>
                            <Tag color="blue">{batchFiles.length} 个</Tag>
                          </Space>
                        }
                        extra={
                          <Space>
                            <Button
                              size="small"
                              onClick={handleClearBatch}
                              disabled={batchUploading}
                            >
                              清空
                            </Button>
                            <Button
                              type="primary"
                              size="small"
                              icon={<UploadOutlined />}
                              onClick={handleBatchUpload}
                              loading={batchUploading}
                            >
                              开始批量上传
                            </Button>
                          </Space>
                        }
                      >
                        {batchUploading && (
                          <div style={{ marginBottom: 16 }}>
                            <Progress
                              percent={Math.round(
                                (batchProgress.current /
                                  batchProgress.total) *
                                  100
                              )}
                              format={() =>
                                `${batchProgress.current}/${batchProgress.total}`
                              }
                              status="active"
                            />
                          </div>
                        )}

                        <List
                          size="small"
                          dataSource={batchFiles}
                          renderItem={(item) => (
                            <List.Item
                              actions={[
                                !batchUploading &&
                                  item.status === "pending" && (
                                    <Tooltip title="移除">
                                      <Button
                                        type="text"
                                        size="small"
                                        icon={<DeleteOutlined />}
                                        onClick={() =>
                                          handleRemoveBatchFile(item.uid)
                                        }
                                      />
                                    </Tooltip>
                                  ),
                              ].filter(Boolean)}
                            >
                              <List.Item.Meta
                                avatar={
                                  item.status === "success" ? (
                                    <CheckCircleOutlined
                                      style={{
                                        color: "#52c41a",
                                        fontSize: 18,
                                      }}
                                    />
                                  ) : item.status === "error" ? (
                                    <CloseCircleOutlined
                                      style={{
                                        color: "#ff4d4f",
                                        fontSize: 18,
                                      }}
                                    />
                                  ) : item.status === "uploading" ? (
                                    <LoadingOutlined
                                      style={{
                                        color: "#4dd6ff",
                                        fontSize: 18,
                                      }}
                                    />
                                  ) : (
                                    <FileTextOutlined
                                      style={{
                                        color: "#8b949e",
                                        fontSize: 18,
                                      }}
                                    />
                                  )
                                }
                                title={
                                  <Space>
                                    <Text>{item.name}</Text>
                                    <Text
                                      type="secondary"
                                      style={{ fontSize: 12 }}
                                    >
                                      {(item.size / 1024).toFixed(1)} KB
                                    </Text>
                                  </Space>
                                }
                                description={
                                  item.status === "error" && (
                                    <Text type="danger" style={{ fontSize: 12 }}>
                                      {item.error}
                                    </Text>
                                  )
                                }
                              />
                            </List.Item>
                          )}
                        />
                      </Card>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Card>

        <Card title={`已上传简历 (${documents.length})`}>
          <Table
            dataSource={documents}
            columns={columns}
            rowKey={(r) => r.document_id || r.id}
            size="small"
            pagination={{ pageSize: 10 }}
          />
        </Card>
      </Spin>

      {/* OCR 校正弹窗 */}
      <OCRCorrectionModal
        open={!!ocrCorrection}
        onClose={() => setOcrCorrection(null)}
        onConfirm={handleOCRCorrectionConfirm}
        ocrText={ocrCorrection?.text || ""}
        confidence={ocrCorrection?.confidence}
        filename={ocrCorrection?.filename}
        documentType="resume"
      />

      <Modal
        title="候选人画像详情"
        open={!!profileModal}
        onCancel={() => setProfileModal(null)}
        footer={null}
        width={720}
      >
        {profileModal && (
          <div>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="画像 ID" span={2}>
                <Text code>{profileModal.profile_id}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag
                  color={profileModal.state === "ready" ? "green" : "orange"}
                >
                  {profileModal.state}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="实现方式">
                {profileModal.implementation || "mock"}
              </Descriptions.Item>
            </Descriptions>

            {profileModal.attributes?.resume_profile && (
              <>
                <Divider>简历解析结果</Divider>
                <pre
                  style={{
                    background: "rgba(77, 214, 255, 0.05)",
                    padding: 16,
                    borderRadius: 8,
                    maxHeight: 400,
                    overflow: "auto",
                    fontSize: 12,
                  }}
                >
                  {JSON.stringify(
                    profileModal.attributes.resume_profile,
                    null,
                    2
                  )}
                </pre>
              </>
            )}

            {profileModal.warnings?.length > 0 && (
              <>
                <Divider>警告</Divider>
                {profileModal.warnings.map((w, i) => (
                  <Tag key={i} color="orange" style={{ margin: 4 }}>
                    {w}
                  </Tag>
                ))}
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
