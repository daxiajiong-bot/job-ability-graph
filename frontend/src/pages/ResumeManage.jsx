import { useState, useCallback, useEffect } from "react";
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
  Popconfirm,
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
  getCandidateProfileTask,
  getCandidateProfile,
  getCandidateProfilesByDocuments,
  deleteDocument,
  initUser,
  listUserDocuments,
} from "../api/client";
import useStore from "../store/useStore";
import OCRCorrectionModal from "../components/OCRCorrectionModal";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

export default function ResumeManage() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [profileModal, setProfileModal] = useState(null);
  const [activeTab, setActiveTab] = useState("text");

  const {
    userId, initUserId,
    candidateProfileCache, setCachedCandidateProfile, setCachedCandidateProfiles,
    removeCachedCandidateProfile,
  } = useStore();

  const [profiles, setProfiles] = useState({});

  // ── 页面加载时：从缓存恢复画像 + 初始化用户 + 获取文档列表 ──
  useEffect(() => {
    // 从持久化缓存恢复画像（此时 store 已完成 rehydrate）
    if (Object.keys(candidateProfileCache).length > 0) {
      setProfiles((prev) => ({ ...candidateProfileCache, ...prev }));
    }

    async function bootstrap() {
      const uid = initUserId();
      try {
        await initUser();
      } catch (e) {
        console.warn("用户初始化失败:", e);
      }
      await loadDocuments(uid, 0);
    }
    bootstrap();
  }, []);

  async function loadDocuments(uid, offset = 0) {
    setLoading(true);
    try {
      const res = await listUserDocuments(uid || userId, "resume", offset, 50);
      const data = res.data.data;
      const items = data.items || [];
      if (offset === 0) {
        setDocuments(items);
      } else {
        setDocuments((prev) => [...prev, ...items]);
      }
      // 加载已有画像（后端 → 本地 + 缓存）
      const docIds = items.map((d) => d.document_id || d.id).filter(Boolean);
      if (docIds.length > 0) {
        try {
          const profileRes = await getCandidateProfilesByDocuments(docIds);
          const existingProfiles = profileRes.data.data.profiles || {};
          setProfiles((prev) => ({ ...prev, ...existingProfiles }));
          // 同步到持久化缓存
          if (Object.keys(existingProfiles).length > 0) {
            setCachedCandidateProfiles(existingProfiles);
          }
        } catch (e) {
          console.warn("加载画像失败:", e);
        }
      }
      // 兜底：后端没返回的画像，从本地持久化缓存补回
      setProfiles((prev) => {
        const merged = { ...prev };
        for (const d of items) {
          const docId = d.document_id || d.id;
          if (docId && !merged[docId] && candidateProfileCache[docId]) {
            merged[docId] = candidateProfileCache[docId];
          }
        }
        return merged;
      });
    } catch (e) {
      console.warn("加载简历列表失败:", e);
    } finally {
      setLoading(false);
    }
  }

  // ── OCR 校正状态 ──
  const [ocrCorrection, setOcrCorrection] = useState(null);
  const [generatingTasks, setGeneratingTasks] = useState({}); // { docId: taskId }

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
      message.success("简历文档创建成功，正在生成画像...");
      form.resetFields();
      await loadDocuments(userId, 0);
      // 自动生成画像
      const docId = doc.id || doc.document_id;
      if (docId) {
        handleBuildProfile({ document_id: docId, id: docId });
      }
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
      message.success("校正后的简历文档已创建，正在生成画像...");
      await loadDocuments(userId, 0);
      // 自动生成画像
      const docId = doc.id || doc.document_id;
      if (docId) {
        handleBuildProfile({ document_id: docId, id: docId });
      }
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
      message.success(`批量上传完成：${successCount} 个成功，正在自动生成画像...`);
      await loadDocuments(userId, 0);
      // 自动生成画像：对每个成功上传的文档触发画像生成
      setBatchFiles((prev) => {
        prev
          .filter((f) => f.status === "success" && f.result)
          .forEach((f) => {
            const docId = f.result.document_id || f.result.id;
            if (docId) {
              handleBuildProfile({ document_id: docId, id: docId });
            }
          });
        return prev;
      });
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
    const docId = doc.document_id || doc.id;
    try {
      const res = await createCandidateProfile(docId);
      const task = res.data.data.task;
      setGeneratingTasks((prev) => ({ ...prev, [docId]: task.task_id }));
      message.info("画像生成中，请稍候...");
      pollProfileTask(task.task_id, docId);
    } catch (e) {
      message.error(
        "画像生成失败: " + (e.response?.data?.error?.message || e.message)
      );
    }
  }

  function pollProfileTask(taskId, docId) {
    const interval = setInterval(async () => {
      try {
        const res = await getCandidateProfileTask(taskId);
        const task = res.data.data.task;
        if (task.status === "succeeded") {
          clearInterval(interval);
          setGeneratingTasks((prev) => {
            const next = { ...prev };
            delete next[docId];
            return next;
          });
          if (task.profile) {
            setProfiles((prev) => ({ ...prev, [docId]: task.profile }));
            setCachedCandidateProfile(docId, task.profile);
          }
          message.success("候选人画像生成成功");
        } else if (task.status === "failed") {
          clearInterval(interval);
          setGeneratingTasks((prev) => {
            const next = { ...prev };
            delete next[docId];
            return next;
          });
          message.error("画像生成失败: " + (task.error || "未知错误"));
        }
        // pending/running → keep polling
      } catch (e) {
        clearInterval(interval);
        setGeneratingTasks((prev) => {
          const next = { ...prev };
          delete next[docId];
          return next;
        });
        message.error("轮询失败: " + e.message);
      }
    }, 2000);
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

  async function handleDeleteDocument(doc) {
    const docId = doc.document_id || doc.id;
    setLoading(true);
    try {
      await deleteDocument(docId);
      message.success("删除成功");
      // 清除该文档的画像缓存
      removeCachedCandidateProfile(docId);
      await loadDocuments(userId, 0);
    } catch (e) {
      message.error("删除失败: " + (e.response?.data?.error?.message || e.message));
    } finally {
      setLoading(false);
    }
  }

  const columns = [
    {
      title: "候选人姓名",
      key: "candidate_name",
      ellipsis: true,
      width: 150,
      render: (_, record) => {
        const profile = profiles[record.document_id || record.id];
        if (!profile) return <Text type="secondary">未生成画像</Text>;
        const attrs = profile.attributes || {};
        const candidate = attrs.candidate || attrs.resume_profile?.candidate || {};
        const name = candidate.name || candidate.full_name;
        return <Text strong>{name || "-"}</Text>;
      },
    },
    {
      title: "目标岗位",
      key: "target_position",
      ellipsis: true,
      width: 180,
      render: (_, record) => {
        const profile = profiles[record.document_id || record.id];
        if (!profile) return "-";
        const attrs = profile.attributes || {};
        const intent = attrs.career_intent || attrs.resume_profile?.career_intent || {};
        const target = intent.target_position || attrs.target_position;
        return target ? <Tag color="blue">{target}</Tag> : "-";
      },
    },
    {
      title: "学历",
      key: "education",
      width: 100,
      render: (_, record) => {
        const profile = profiles[record.document_id || record.id];
        if (!profile) return "-";
        const attrs = profile.attributes || {};
        const education = attrs.education || attrs.resume_profile?.education || [];
        if (education.length > 0) {
          const edu = education[0];
          return edu.degree || edu.school || "-";
        }
        return "-";
      },
    },
    {
      title: "工作经验",
      key: "experience",
      width: 100,
      render: (_, record) => {
        const profile = profiles[record.document_id || record.id];
        if (!profile) return "-";
        const attrs = profile.attributes || {};
        const exp = attrs.work_experience || attrs.experience || attrs.resume_profile?.work_experience || [];
        if (exp.length > 0) {
          return <Text>{exp.length} 段经历</Text>;
        }
        const years = attrs.candidate?.years_of_experience;
        return years ? <Text>{years} 年</Text> : "-";
      },
    },
    {
      title: "技能",
      key: "skills",
      width: 200,
      ellipsis: true,
      render: (_, record) => {
        const profile = profiles[record.document_id || record.id];
        if (!profile) return "-";
        const attrs = profile.attributes || {};
        const skills = attrs.skills || attrs.resume_profile?.skills || [];
        if (skills.length > 0) {
          return skills.slice(0, 3).map((s, i) => (
            <Tag key={i} style={{ margin: 1, fontSize: 11 }} color="green">
              {s.name || s}
            </Tag>
          ));
        }
        return "-";
      },
    },
    {
      title: "来源",
      key: "source",
      width: 100,
      render: (_, r) => <Tag>{r.source?.source_system || "manual"}</Tag>,
    },
    {
      title: "画像状态",
      key: "profile_status",
      width: 100,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        if (generatingTasks[docId]) return <Tag color="processing">生成中...</Tag>;
        if (!profile) return <Tag color="default">未生成</Tag>;
        if (profile.state === "available" && profile.implementation !== "mock")
          return <Tag color="success">已完成</Tag>;
        return <Tag color="warning">Mock</Tag>;
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
            icon={generatingTasks[record.document_id || record.id] ? <LoadingOutlined /> : <ExperimentOutlined />}
            onClick={() => handleBuildProfile(record)}
            loading={!!generatingTasks[record.document_id || record.id]}
            disabled={!!generatingTasks[record.document_id || record.id]}
          >
            {generatingTasks[record.document_id || record.id]
              ? "生成中..."
              : profiles[record.document_id || record.id]
                ? "重新生成"
                : "生成画像"}
          </Button>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewProfile(record)}
          >
            查看
          </Button>
          <Popconfirm
            title="确定删除该简历？"
            description="删除后不可恢复，关联的画像也会一并删除。"
            onConfirm={() => handleDeleteDocument(record)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              删除
            </Button>
          </Popconfirm>
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
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
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
                                        color: "var(--text-secondary)",
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
