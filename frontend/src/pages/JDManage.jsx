import { useState, useCallback, useEffect } from "react";
import {
  Card,
  Typography,
  Upload,
  Button,
  Input,
  Form,
  Select,
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
  FileTextOutlined,
  ExperimentOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  InboxOutlined,
  DeleteOutlined,
} from "@ant-design/icons";
import {
  createDocument,
  createDocumentOCR,
  createJobProfile,
  getJobProfileTask,
  getJobProfile,
  getJobProfilesByDocuments,
  deleteDocument,
  initUser,
  listUserDocuments,
} from "../api/client";
import useStore from "../store/useStore";
import OCRCorrectionModal from "../components/OCRCorrectionModal";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

export default function JDManage() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState([]);
  const [totalDocs, setTotalDocs] = useState(0);
  const [pageOffset, setPageOffset] = useState(0);
  const [profileModal, setProfileModal] = useState(null);
  const [activeTab, setActiveTab] = useState("text");

  const {
    userId, initUserId,
    jobProfileCache, setCachedJobProfile, setCachedJobProfiles,
    removeCachedJobProfile,
  } = useStore();

  const [profiles, setProfiles] = useState({});

  // ── 页面加载时：从缓存恢复画像 + 初始化用户 + 获取文档列表 ──
  useEffect(() => {
    // 从持久化缓存恢复画像（此时 store 已完成 rehydrate）
    console.log("[JDManage] 缓存中的画像:", Object.keys(jobProfileCache).length, "条");
    if (Object.keys(jobProfileCache).length > 0) {
      setProfiles((prev) => ({ ...jobProfileCache, ...prev }));
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
      const res = await listUserDocuments(uid || userId, "jd", offset, 50);
      const data = res.data.data;
      const items = data.items || [];
      if (offset === 0) {
        setDocuments(items);
      } else {
        setDocuments((prev) => [...prev, ...items]);
      }
      setTotalDocs(data.total || 0);
      setPageOffset(offset);
      // 加载已有画像（后端 → 本地 + 缓存）
      const docIds = items.map((d) => d.document_id || d.id).filter(Boolean);
      console.log("[JDManage] 文档 docIds:", docIds);
      console.log("[JDManage] 缓存 keys:", Object.keys(jobProfileCache));
      if (docIds.length > 0) {
        try {
          const profileRes = await getJobProfilesByDocuments(docIds);
          const existingProfiles = profileRes.data.data.profiles || {};
          console.log("[JDManage] 后端返回画像 keys:", Object.keys(existingProfiles));
          setProfiles((prev) => ({ ...prev, ...existingProfiles }));
          // 同步到持久化缓存
          if (Object.keys(existingProfiles).length > 0) {
            setCachedJobProfiles(existingProfiles);
          }
        } catch (e) {
          console.warn("加载画像失败:", e);
        }
      }
      // 兜底：后端没返回的画像，从本地持久化缓存补回
      setProfiles((prev) => {
        const merged = { ...prev };
        let fallbackCount = 0;
        for (const d of items) {
          const docId = d.document_id || d.id;
          if (docId && !merged[docId] && jobProfileCache[docId]) {
            merged[docId] = jobProfileCache[docId];
            fallbackCount++;
          }
        }
        console.log("[JDManage] 缓存兜底补回:", fallbackCount, "条，最终 profiles keys:", Object.keys(merged));
        return merged;
      });
    } catch (e) {
      console.warn("加载文档列表失败:", e);
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

  // ── 文本输入创建 JD ──
  async function handleCreateText(values) {
    setLoading(true);
    try {
      const res = await createDocument({
        document_type: "jd",
        text: values.text,
        source: { source_system: "manual" },
      });
      const doc = res.data.data.document;
      console.log("[JDManage] 文档已创建:", doc.id || doc.document_id);
      message.success("JD 文档创建成功，正在生成画像...");
      form.resetFields();
      // 重新加载文档列表
      await loadDocuments(userId, 0);
      // 自动生成画像
      const docId = doc.id || doc.document_id;
      if (docId) {
        console.log("[JDManage] 自动触发画像生成, docId:", docId);
        handleBuildProfile({ document_id: docId, id: docId });
      }
    } catch (e) {
      console.error("[JDManage] 创建文档失败:", e);
      message.error("创建失败: " + (e.response?.data?.error?.message || e.message));
    } finally {
      setLoading(false);
    }
  }

  // ── OCR 上传（单个文件） ──
  async function handleOCRUpload(file) {
    setLoading(true);
    const formData = new FormData();
    formData.append("document_type", "jd");
    formData.append("file", file);
    try {
      const res = await createDocumentOCR(formData);
      const doc = res.data.data.document;
      // 打开 OCR 校正弹窗
      setOcrCorrection({
        text: doc.text || doc._raw || "",
        confidence: doc.confidence,
        filename: file.name,
        doc,
      });
      message.success("OCR 识别成功，请检查并修正结果");
      await loadDocuments(userId, 0);
    } catch (e) {
      message.error("OCR 失败: " + (e.response?.data?.error?.message || e.message));
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
        document_type: "jd",
        text: correctedText,
        source: { source_system: "ocr_corrected" },
      });
      const doc = res.data.data.document;
      message.success("校正后的 JD 文档已创建，正在生成画像...");
      await loadDocuments(userId, 0);
      // 自动生成画像
      const docId = doc.id || doc.document_id;
      if (docId) {
        handleBuildProfile({ document_id: docId, id: docId });
      }
    } catch (e) {
      message.error("创建失败: " + (e.response?.data?.error?.message || e.message));
    }
    setOcrCorrection(null);
  }

  // ── 批量文件选择 ──
  const handleBatchFileSelect = useCallback((info) => {
    const fileList = info.fileList.map((file) => ({
      uid: file.uid,
      name: file.name,
      size: file.size,
      status: "pending", // pending | uploading | success | error
      file: file.originFileObj,
      result: null,
      error: null,
    }));
    setBatchFiles(fileList);
  }, []);

  // ── 移除批量文件 ──
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

      // 更新文件状态为上传中
      setBatchFiles((prev) =>
        prev.map((f) =>
          f.uid === fileItem.uid ? { ...f, status: "uploading" } : f
        )
      );

      try {
        const formData = new FormData();
        formData.append("document_type", "jd");
        formData.append("file", fileItem.file);

        const res = await createDocumentOCR(formData);
        const doc = res.data.data.document;

        // 更新文件状态为成功
        setBatchFiles((prev) =>
          prev.map((f) =>
            f.uid === fileItem.uid
              ? { ...f, status: "success", result: doc }
              : f
          )
        );

        // 添加到文档列表
        setDocuments((prev) => [{ ...doc, _raw: "(批量OCR)" }, ...prev]);
        successCount++;
      } catch (e) {
        // 更新文件状态为失败
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
  }, [batchFiles, userId]);

  // ── 清空批量文件列表 ──
  const handleClearBatch = useCallback(() => {
    setBatchFiles([]);
    setBatchProgress({ current: 0, total: 0 });
  }, []);

  // ── 生成画像 (异步任务) ──
  async function handleBuildProfile(doc) {
    const docId = doc.document_id || doc.id;
    console.log("[JDManage] handleBuildProfile called, docId:", docId);
    try {
      const res = await createJobProfile(docId);
      const task = res.data.data.task;
      console.log("[JDManage] 画像任务已创建, taskId:", task.task_id);
      setGeneratingTasks((prev) => ({ ...prev, [docId]: task.task_id }));
      message.info("画像生成中，请稍候...");
      pollProfileTask(task.task_id, docId);
    } catch (e) {
      console.error("[JDManage] 画像生成请求失败:", e);
      message.error("画像生成失败: " + (e.response?.data?.error?.message || e.message));
    }
  }

  function pollProfileTask(taskId, docId) {
    console.log("[JDManage] 开始轮询画像任务, taskId:", taskId);
    const interval = setInterval(async () => {
      try {
        const res = await getJobProfileTask(taskId);
        const task = res.data.data.task;
        console.log("[JDManage] 轮询任务状态:", task.status);
        if (task.status === "succeeded") {
          clearInterval(interval);
          setGeneratingTasks((prev) => {
            const next = { ...prev };
            delete next[docId];
            return next;
          });
          if (task.profile) {
            setProfiles((prev) => ({ ...prev, [docId]: task.profile }));
            setCachedJobProfile(docId, task.profile);
            console.log("[JDManage] 画像已缓存, docId:", docId, "implementation:", task.profile.implementation);
          }
          message.success("岗位画像生成成功");
        } else if (task.status === "failed") {
          clearInterval(interval);
          setGeneratingTasks((prev) => {
            const next = { ...prev };
            delete next[docId];
            return next;
          });
          message.error("画像生成失败: " + (task.error || "未知错误"));
        }
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

  // ── 查看画像 ──
  async function handleViewProfile(doc) {
    const docId = doc.document_id || doc.id;
    if (profiles[docId]) {
      setProfileModal(profiles[docId]);
      return;
    }
    setLoading(true);
    try {
      const res = await getJobProfile(docId);
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
      removeCachedJobProfile(docId);
      await loadDocuments(userId, 0);
    } catch (e) {
      message.error("删除失败: " + (e.response?.data?.error?.message || e.message));
    } finally {
      setLoading(false);
    }
  }

  const isSystem = (r) => r.user_id === "system";

  const columns = [
    {
      title: "岗位名称",
      key: "title",
      ellipsis: true,
      width: 220,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        const profileTitle = profile?.attributes?.job?.title || profile?.attributes?.job_title;
        if (isSystem(r)) return profileTitle || r.title || <Text type="secondary">{r.company_name ? `${r.company_name} · 未命名岗位` : "未命名岗位"}</Text>;
        if (!profile) return <Text type="secondary">未生成画像</Text>;
        return profileTitle || "-";
      },
    },
    {
      title: "公司",
      key: "company",
      ellipsis: true,
      width: 150,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        if (isSystem(r)) return profile?.attributes?.company?.name || r.company_name || "-";
        if (!profile) return "-";
        return profile.attributes?.company?.name || "-";
      },
    },
    {
      title: "地点",
      key: "location",
      width: 100,
      ellipsis: true,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        if (isSystem(r)) return profile?.attributes?.company?.location || r.location || "-";
        if (!profile) return "-";
        return profile.attributes?.company?.location || "-";
      },
    },
    {
      title: "薪资",
      key: "salary",
      width: 100,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        const emp = profile?.attributes?.employment || {};
        if (emp.salary_min && emp.salary_max) {
          return <Text type="success">{emp.salary_min}-{emp.salary_max}</Text>;
        }
        if (isSystem(r)) return r.salary_range ? <Text type="success">{r.salary_range}</Text> : "-";
        if (!profile) return "-";
        if (emp.salary_range) return <Text type="success">{emp.salary_range}</Text>;
        return "-";
      },
    },
    {
      title: "经验",
      key: "exp",
      width: 80,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        if (isSystem(r)) return profile?.attributes?.employment?.experience || r.experience || "-";
        if (!profile) return "-";
        return profile.attributes?.employment?.experience || "-";
      },
    },
    {
      title: "学历",
      key: "edu",
      width: 70,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        if (isSystem(r)) return profile?.attributes?.employment?.education || r.education || "-";
        if (!profile) return "-";
        return profile.attributes?.employment?.education || "-";
      },
    },
    {
      title: "技能要求",
      key: "skills",
      width: 200,
      ellipsis: true,
      render: (_, r) => {
        const docId = r.document_id || r.id;
        const profile = profiles[docId];
        const skills = profile?.attributes?.skills || [];
        if (skills.length > 0) {
          return skills.slice(0, 3).map((s, i) => (
            <Tag key={i} style={{ margin: 1, fontSize: 11 }} color="blue">
              {s.name || s}
            </Tag>
          ));
        }
        if (isSystem(r)) {
          const rawSkills = r.skills;
          if (rawSkills && rawSkills.length > 0) {
            return rawSkills.slice(0, 3).map((s, i) => (
              <Tag key={i} style={{ margin: 1, fontSize: 11 }}>
                {s}
              </Tag>
            ));
          }
        }
        return "-";
      },
    },
    {
      title: "来源",
      key: "source",
      width: 80,
      render: (_, r) =>
        r.user_id === "system" ? (
          <Tag color="cyan">系统</Tag>
        ) : (
          <Tag color="purple">用户</Tag>
        ),
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
      width: 220,
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
                : "画像"}
          </Button>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewProfile(record)}
          >
            查看
          </Button>
          {record.user_id !== "system" && (
            <Popconfirm
              title="确定删除该 JD？"
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
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <Title level={3} style={{ marginBottom: 4 }}>
          <FileTextOutlined style={{ marginRight: 8, color: "#4dd6ff" }} />
          JD 管理
        </Title>
        <Paragraph style={{ color: "var(--text-secondary)", margin: 0 }}>
          上传岗位描述（JD），系统将自动解析技能要求并生成岗位画像
        </Paragraph>
      </div>

      <Spin spinning={loading}>
        <Card title="上传岗位描述" style={{ marginBottom: 24 }}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: "text",
                label: "文本输入",
                children: (
                  <Form form={form} onFinish={handleCreateText} layout="vertical">
                    <Form.Item
                      name="text"
                      label="JD 原文"
                      rules={[{ required: true, message: "请输入岗位描述文本" }]}
                    >
                      <TextArea
                        rows={8}
                        placeholder="粘贴岗位描述原文，例如：&#10;&#10;岗位名称：Python 开发工程师&#10;岗位要求：&#10;1. 熟悉 Python、Linux、MySQL&#10;2. 有接口自动化测试经验&#10;3. 具备良好的沟通能力"
                      />
                    </Form.Item>
                    <Form.Item>
                      <Button
                        type="primary"
                        htmlType="submit"
                        icon={<FileTextOutlined />}
                        loading={loading}
                      >
                        创建 JD 文档
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
                        <UploadOutlined style={{ fontSize: 32, color: "#4dd6ff" }} />
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
                      <Badge count={batchFiles.length} style={{ backgroundColor: "#4dd6ff" }} />
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
                        <InboxOutlined style={{ fontSize: 48, color: "#4dd6ff" }} />
                      </p>
                      <p style={{ fontSize: 16 }}>
                        点击或拖拽多个文件到此区域
                      </p>
                      <p type="secondary">
                        支持同时选择多个 PNG、JPG、PDF 文件进行批量 OCR 识别
                      </p>
                    </Upload.Dragger>

                    {/* 批量上传进度 */}
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
                        {/* 整体进度 */}
                        {batchUploading && (
                          <div style={{ marginBottom: 16 }}>
                            <Progress
                              percent={Math.round(
                                (batchProgress.current / batchProgress.total) * 100
                              )}
                              format={() =>
                                `${batchProgress.current}/${batchProgress.total}`
                              }
                              status="active"
                            />
                          </div>
                        )}

                        {/* 文件列表 */}
                        <List
                          size="small"
                          dataSource={batchFiles}
                          renderItem={(item) => (
                            <List.Item
                              actions={[
                                !batchUploading && item.status === "pending" && (
                                  <Tooltip title="移除">
                                    <Button
                                      type="text"
                                      size="small"
                                      icon={<DeleteOutlined />}
                                      onClick={() => handleRemoveBatchFile(item.uid)}
                                    />
                                  </Tooltip>
                                ),
                              ].filter(Boolean)}
                            >
                              <List.Item.Meta
                                avatar={
                                  item.status === "success" ? (
                                    <CheckCircleOutlined
                                      style={{ color: "#52c41a", fontSize: 18 }}
                                    />
                                  ) : item.status === "error" ? (
                                    <CloseCircleOutlined
                                      style={{ color: "#ff4d4f", fontSize: 18 }}
                                    />
                                  ) : item.status === "uploading" ? (
                                    <LoadingOutlined
                                      style={{ color: "#4dd6ff", fontSize: 18 }}
                                    />
                                  ) : (
                                    <FileTextOutlined
                                      style={{ color: "var(--text-secondary)", fontSize: 18 }}
                                    />
                                  )
                                }
                                title={
                                  <Space>
                                    <Text>{item.name}</Text>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
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

        <Card title={`JD 列表 (${totalDocs || documents.length})`}>
          <Table
            dataSource={documents}
            columns={columns}
            rowKey={(r) => r.document_id || r.id}
            size="small"
            pagination={{
              pageSize: 50,
              total: totalDocs,
              onChange: (page) => loadDocuments(userId, (page - 1) * 50),
              showTotal: (total) => `共 ${total} 条`,
            }}
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
        documentType="jd"
      />

      {/* 画像详情弹窗 */}
      <Modal
        title="岗位画像详情"
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
                <Tag color={profileModal.state === "ready" ? "green" : "orange"}>
                  {profileModal.state}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="实现方式">
                {profileModal.implementation || "mock"}
              </Descriptions.Item>
            </Descriptions>

            {profileModal.attributes?.jd_profile && (
              <>
                <Divider>JD 解析结果</Divider>
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
                  {JSON.stringify(profileModal.attributes.jd_profile, null, 2)}
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
