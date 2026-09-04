import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tabs,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  BulbOutlined,
  CheckOutlined,
  CloseOutlined,
  DatabaseOutlined,
  EditOutlined,
  ExperimentOutlined,
  EyeOutlined,
  RiseOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  generateRoleDefinition,
  getEmergingRoles,
  getSkillUpdates,
  getTrendFeatures,
  getTrendSummary,
  reviewRoleDefinition,
  reviewSkillUpdate,
  saveRoleDefinition,
} from "../api/client";

const { Title, Text } = Typography;

const CHANGE_META = {
  added: { label: "新增", color: "green" },
  rising: { label: "上升", color: "blue" },
  modified: { label: "修改", color: "orange" },
  declining: { label: "下降", color: "red" },
  removal_candidate: { label: "待移除", color: "volcano" },
};

const STATUS_META = {
  candidate: { label: "候选", color: "gold" },
  needs_review: { label: "待审核", color: "orange" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
};

// 既有岗位技能更新的审核状态（逐条决策聚合而来）
const UPDATE_STATUS_META = {
  candidate: { label: "待审核", color: "gold" },
  partial: { label: "部分通过", color: "orange" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
};

// 每条技能变化的审核决策
const DECISION_META = {
  pending: { label: "待审核", color: "default" },
  approved: { label: "已通过", color: "green" },
  rejected: { label: "已驳回", color: "red" },
};

const DEF_SOURCE_META = {
  llm: { label: "大模型生成", color: "purple" },
  human_edit: { label: "人工优化", color: "blue" },
  mock: { label: "规则生成", color: "cyan" },
};

export default function DiscoverPage() {
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState([]);
  const [updates, setUpdates] = useState([]);
  const [features, setFeatures] = useState([]);
  const [summary, setSummary] = useState({});
  const [editingRole, setEditingRole] = useState(null); // 编辑弹窗
  const [generatingId, setGeneratingId] = useState(null); // 生成定义中的 role_id
  const [reviewBusy, setReviewBusy] = useState(new Set()); // 技能更新审核中的 key: updateId::skillName / updateId::*
  const [form] = Form.useForm();

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [r1, r2, r3, r5] = await Promise.all([
        getEmergingRoles(),
        getSkillUpdates(),
        getTrendFeatures(),
        getTrendSummary(),
      ]);
      setRoles(r1.data.data.emerging_roles || []);
      setUpdates(r2.data.data.skill_updates || []);
      setFeatures(r3.data.data.features || []);
      setSummary(r5.data.data || {});
    } catch (e) {
      message.error(`加载失败：${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // 只刷新「既有岗位技能更新」，供审核后更新审核状态/图谱结果
  const refreshUpdates = useCallback(async () => {
    try {
      const r2 = await getSkillUpdates();
      setUpdates(r2.data.data.skill_updates || []);
    } catch (e) {
      message.error(`加载技能更新失败：${e.message}`);
    }
  }, []);

  const patchRole = (roleId, patch) => {
    setRoles((prev) => prev.map((r) => (r.role_id === roleId ? { ...r, ...patch } : r)));
  };

  // ── 生成岗位定义（LLM / 兜底） ──
  const handleGenerate = async (role) => {
    setGeneratingId(role.role_id);
    try {
      const res = await generateRoleDefinition(role.role_id);
      const data = res.data.data;
      patchRole(role.role_id, {
        generated_definition: data.definition,
        definition_source: data.source,
        status: data.status,
        updated_at: data.updated_at,
      });
      message.success(
        data.source === "llm"
          ? "已基于原文证据生成岗位定义（大模型）"
          : "已生成岗位定义（当前为本地规则兜底，可配置 LLM 升级）"
      );
    } catch (e) {
      message.error(`生成失败：${e.message}`);
    } finally {
      setGeneratingId(null);
    }
  };

  // ── 人工优化（编辑定义） ──
  const openEdit = (role) => {
    const def = role.generated_definition || {};
    form.setFieldsValue({
      canonical_title: def.canonical_title || role.canonical_title || "",
      core_responsibilities: (def.core_responsibilities || role.core_responsibilities || []).join("\n"),
      required_skills: (def.required_skills || role.required_skills || []).map((s) => s.name || s),
      preferred_skills: (def.preferred_skills || role.preferred_skills || []).map((s) => s.name || s),
      typical_industry_scenarios: (
        def.typical_industry_scenarios || role.typical_industry_scenarios || []
      ).join("\n"),
    });
    setEditingRole(role);
  };

  const handleSaveEdit = async () => {
    if (!editingRole) return;
    try {
      const values = await form.validateFields();
      const definition = {
        canonical_title: values.canonical_title,
        core_responsibilities: (values.core_responsibilities || "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        required_skills: (values.required_skills || []).map((name) => ({ name })),
        preferred_skills: (values.preferred_skills || []).map((name) => ({ name })),
        typical_industry_scenarios: (values.typical_industry_scenarios || "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      const res = await saveRoleDefinition(editingRole.role_id, definition, "needs_review");
      const data = res.data.data;
      patchRole(editingRole.role_id, {
        generated_definition: data.definition,
        definition_source: data.source,
        status: data.status,
        updated_at: data.updated_at,
      });
      message.success("岗位定义已保存，状态更新为待审核");
      setEditingRole(null);
    } catch (e) {
      if (e?.errorFields) return; // 表单校验错误
      message.error(`保存失败：${e.message}`);
    }
  };

  // ── 审核（通过 → 新岗位入库，供求职者参考） ──
  const handleReview = async (role, decision) => {
    try {
      const res = await reviewRoleDefinition(role.role_id, decision);
      const data = res.data.data;
      patchRole(role.role_id, {
        status: data.status,
        review: data.review,
        updated_at: data.updated_at,
        publish: data.publish || null,
      });
      const pub = data.publish;
      if (decision === "approved") {
        if (pub?.published) {
          message.success(
            `已通过并入库：新岗位「${pub.title}」已添加到岗位库（文档 ${pub.document_id}），求职者可在智能推荐/匹配中参考`
          );
        } else if (pub && pub.published === false) {
          message.warning(`已通过，但入库失败：${pub.reason || "未知原因"}`);
        } else {
          message.success("已通过：该岗位纳入图谱动态更新");
        }
      } else if (pub?.published) {
        message.warning("已驳回（该岗位此前已入库，现有发布记录予以保留）");
      } else {
        message.success("已驳回：请修改后重新提交");
      }
    } catch (e) {
      message.error(`操作失败：${e.message}`);
    }
  };

  // ── 既有岗位技能更新：审核并写回知识图谱 ──
  const pendingSkillNames = (update) =>
    (update.changes || [])
      .filter((c) => (c.decision || "pending") === "pending")
      .map((c) => c.skill_name);

  const handleReviewUpdate = async (update, decision, skillNames) => {
    const label = decision === "approved" ? "通过" : "驳回";
    const key =
      skillNames && skillNames.length === 1
        ? `${update.update_id}::${skillNames[0]}`
        : `${update.update_id}::*`;
    if (reviewBusy.has(key)) return;
    setReviewBusy((prev) => new Set(prev).add(key));
    try {
      const res = await reviewSkillUpdate(update.update_id, decision, skillNames);
      const data = res.data.data;
      await refreshUpdates();
      const g = data.graph_apply;
      if (g) {
        const matchedJobs = g.matched_jobs || [];
        if (g.applied) {
          const titles = matchedJobs
            .slice(0, 3)
            .map((j) => j.title || j.id)
            .join("、");
          const addNames = (g.additions || [])
            .map((a) => a.skill_name)
            .join("、");
          const removedCount = (g.removals || []).reduce(
            (n, r) => n + (r.edges_deleted || 0),
            0
          );
          message.success(
            `已通过并更新知识图谱：命中 ${matchedJobs.length} 个既有岗位` +
              (titles ? `（${titles}）` : "") +
              (addNames ? `，新增技能要求：${addNames}` : "") +
              (removedCount > 0 ? `，移除技能要求 ${removedCount} 条` : "")
          );
        } else if (g.reason) {
          message.warning(
            g.backend !== "neo4j"
              ? `已${label}（图谱后端未启用：${g.reason}）`
              : `已${label}，但未写入图谱：${g.reason}`
          );
        } else {
          message.warning(`已${label}，但未写入图谱`);
        }
      } else {
        message.success(`已${label}`);
      }
    } catch (e) {
      message.error(`${label}失败：${e.response?.data?.error?.message || e.message}`);
    } finally {
      setReviewBusy((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  // 每条技能变化行的「通过 / 驳回」操作
  const renderDecisionActions = (update, change) => {
    const d = change.decision || "pending";
    const key = `${update.update_id}::${change.skill_name}`;
    const busy = reviewBusy.has(key);
    const removalHint =
      change.change_type === "removal_candidate"
        ? "通过 = 从图谱移除该技能要求"
        : change.change_type === "declining"
          ? "下降仅记录，不改动图谱；如需移除请走离线增量"
          : null;
    return (
      <Space size={4}>
        <Button
          size="small"
          type={d === "approved" ? "primary" : "default"}
          icon={<CheckOutlined />}
          loading={busy && d !== "approved"}
          disabled={d === "approved" || busy}
          onClick={() => handleReviewUpdate(update, "approved", [change.skill_name])}
        >
          通过
        </Button>
        <Button
          size="small"
          danger
          icon={<CloseOutlined />}
          loading={busy && d !== "rejected"}
          disabled={d === "rejected" || busy}
          onClick={() => handleReviewUpdate(update, "rejected", [change.skill_name])}
        >
          驳回
        </Button>
        {removalHint && (
          <Tooltip title={removalHint}>
            <Text type="secondary" style={{ fontSize: 11, cursor: "help" }}>
              提示
            </Text>
          </Tooltip>
        )}
      </Space>
    );
  };

  // 「既有岗位技能更新」表格列（含审核状态与操作）
  const renderUpdateColumns = (update) => [
    { title: "技能", dataIndex: "skill_name", key: "skill_name" },
    {
      title: "变更",
      dataIndex: "change_type",
      key: "change_type",
      render: (v) => {
        const meta = CHANGE_META[v] || { label: v, color: "default" };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "占比（基线→近期）",
      key: "share",
      render: (_, r) =>
        `${((r.baseline_share || 0) * 100).toFixed(1)}% → ${((r.recent_share || 0) * 100).toFixed(1)}%`,
    },
    {
      title: "占比变化",
      dataIndex: "share_delta",
      key: "share_delta",
      render: (v) => `${((v || 0) * 100).toFixed(1)}pp`,
      sorter: (a, b) => (a.share_delta || 0) - (b.share_delta || 0),
    },
    {
      title: "相对提升",
      dataIndex: "relative_lift",
      key: "relative_lift",
      render: (v) => (v >= 999 ? "∞" : Number(v || 0).toFixed(1)),
    },
    { title: "公司数", dataIndex: "supporting_company_count", key: "cc" },
    {
      title: "证据",
      dataIndex: "evidence_ids",
      key: "evidence",
      render: (v) => (Array.isArray(v) ? v.length : 0),
    },
    {
      title: "审核",
      key: "decision",
      width: 90,
      render: (_, r) => {
        const d = r.decision || "pending";
        const meta = DECISION_META[d] || DECISION_META.pending;
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "操作",
      key: "action",
      width: 175,
      render: (_, r) => renderDecisionActions(update, r),
    },
  ];

  // 更新整体审核状态（逐条决策聚合，展示用）
  const renderUpdateStatus = (update) => {
    const meta = UPDATE_STATUS_META[update.status || "candidate"] || {
      label: update.status || "待审核",
      color: "default",
    };
    return <Tag color={meta.color}>{meta.label}</Tag>;
  };

  const featureColumns = useMemo(
    () => [
      {
        title: "类型",
        dataIndex: "entity_type",
        key: "entity_type",
        render: (v) =>
          v === "job_role" ? (
            <Tag color="blue">岗位角色</Tag>
          ) : (
            <Tag color="cyan">能力</Tag>
          ),
      },
      { title: "实体", dataIndex: "entity_name", key: "entity_name" },
      {
        title: "评分",
        dataIndex: "score",
        key: "score",
        render: (v) => v.toFixed(3),
        sorter: (a, b) => a.score - b.score,
        defaultSortOrder: "descend",
      },
      {
        title: "增长率",
        dataIndex: ["metrics", "growth_rate"],
        key: "growth",
        render: (v) => (v >= 99 ? "∞" : v.toFixed(1)),
      },
      {
        title: "持续性",
        dataIndex: ["metrics", "persistence"],
        key: "pers",
        render: (v) => `${(v * 100).toFixed(0)}%`,
      },
      {
        title: "来源多样性",
        dataIndex: ["metrics", "source_diversity"],
        key: "div",
        render: (v) => `${(v * 100).toFixed(0)}%`,
      },
    ],
    []
  );

  const renderDefinition = (role) => {
    const def = role.generated_definition;
    if (!def) {
      return (
        <div style={{ margin: "4px 0 8px" }}>
          <Text type="secondary">尚未生成岗位定义。点击"生成定义"自动生成五要素，或"编辑优化"人工填写。</Text>
        </div>
      );
    }
    const sourceMeta = DEF_SOURCE_META[role.definition_source] || DEF_SOURCE_META.mock;
    return (
      <Descriptions
        size="small"
        column={1}
        bordered
        style={{ marginBottom: 8 }}
        title={
          <Space size={4}>
            <RobotOutlined />
            岗位定义
            <Tag color={sourceMeta.color} style={{ marginLeft: 4 }}>
              {sourceMeta.label}
            </Tag>
          </Space>
        }
      >
        <Descriptions.Item label="岗位名称">{def.canonical_title || "—"}</Descriptions.Item>
        <Descriptions.Item label="核心职责">
          {(def.core_responsibilities || []).map((c) => (
            <div key={c}>· {c}</div>
          ))}
        </Descriptions.Item>
        <Descriptions.Item label="必备技能">
          {(def.required_skills || []).map((s) => (
            <Tag key={s.name} color="blue" style={{ marginBottom: 4 }}>
              {s.name}
            </Tag>
          ))}
        </Descriptions.Item>
        <Descriptions.Item label="加分技能">
          {(def.preferred_skills || []).map((s) => (
            <Tag key={s.name} color="green" style={{ marginBottom: 4 }}>
              {s.name}
            </Tag>
          ))}
        </Descriptions.Item>
        <Descriptions.Item label="典型行业应用场景">
          {(def.typical_industry_scenarios || []).join(" / ") || "—"}
        </Descriptions.Item>
      </Descriptions>
    );
  };

  const renderRoleActions = (role) => {
    const status = role.status || "candidate";
    const hasDef = !!role.generated_definition;
    return (
      <Space wrap size={4} style={{ marginTop: 4 }}>
        {!hasDef && (
          <Button
            size="small"
            type="primary"
            ghost
            icon={<RobotOutlined />}
            loading={generatingId === role.role_id}
            onClick={() => handleGenerate(role)}
          >
            生成定义
          </Button>
        )}
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(role)}>
          编辑优化
        </Button>
        {status !== "approved" && (
          <Popconfirm
            title="确认通过该岗位？"
            description="通过后该岗位将纳入图谱动态更新。"
            okText="通过"
            cancelText="取消"
            onConfirm={() => handleReview(role, "approved")}
          >
            <Button size="small" type="primary" icon={<CheckOutlined />}>
              通过
            </Button>
          </Popconfirm>
        )}
        {status !== "rejected" && (
          <Popconfirm
            title="确认驳回该岗位？"
            description="驳回后请编辑优化定义，重新提交审核。"
            okText="驳回"
            cancelText="取消"
            onConfirm={() => handleReview(role, "rejected")}
          >
            <Button size="small" danger icon={<CloseOutlined />}>
              驳回
            </Button>
          </Popconfirm>
        )}
      </Space>
    );
  };

  const pendingCount = roles.filter((r) => (r.status || "candidate") === "needs_review").length;

  return (
    <div style={{ padding: 16 }}>
      <Row justify="space-between" align="middle" style={{ marginBottom: 12 }} wrap>
        <Col>
          <Title level={4} style={{ margin: 0 }}>
            <BulbOutlined /> 新岗位发现与能力演化
          </Title>
          <Text type="secondary">
            数据源：JobTrend 离线分析组件（JD + 政策/报告 + 知识图谱）→ 生成定义 → 人工优化 →{" "}
            审核通过后入库（求职者可在智能推荐 / 人岗匹配中参考新岗位）→ 图谱演化
          </Text>
        </Col>
        <Col>
          <Button icon={<ThunderboltOutlined />} onClick={loadAll} loading={loading}>
            刷新
          </Button>
        </Col>
      </Row>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Statistic title="新岗位候选" value={summary.emerging_roles ?? roles.length} prefix={<RiseOutlined />} />
        </Col>
        <Col span={6}>
          <Statistic title="既有岗位技能更新" value={summary.skill_updates ?? updates.length} prefix={<ExperimentOutlined />} />
        </Col>
        <Col span={6}>
          <Statistic title="趋势特征" value={summary.features ?? features.length} />
        </Col>
        <Col span={6}>
          <Statistic title="待审核岗位" value={pendingCount} prefix={<EyeOutlined />} />
        </Col>
      </Row>

      <Spin spinning={loading}>
        <Tabs
          defaultActiveKey="roles"
          items={[
            {
              key: "roles",
              label: `新岗位候选（${roles.length}）`,
              children: (
                <Row gutter={[12, 12]}>
                  {roles.length === 0 ? (
                    <Col span={24}><Empty description="暂无新岗位候选（需≥2 个采集周 + 多源证据）" /></Col>
                  ) : (
                    roles.map((role) => {
                      const scores = role.scores || {};
                      return (
                        <Col xs={24} md={12} xl={8} key={role.role_id}>
                          <Card
                            size="small"
                            title={
                              <Space wrap>
                                <span>{role.canonical_title}</span>
                                <Tag color={(STATUS_META[role.status] || {}).color || "default"}>
                                  {(STATUS_META[role.status] || { label: role.status }).label}
                                </Tag>
                                {role.publish?.published && (
                                  <Tooltip
                                    title={`已入库文档：${role.publish.document_id}，求职者可检索参考`}
                                  >
                                    <Tag color="geekblue">
                                      <DatabaseOutlined /> 已入库
                                    </Tag>
                                  </Tooltip>
                                )}
                                {role.review?.reviewed_at && (
                                  <Text type="secondary" style={{ fontSize: 12 }}>
                                    {role.review.reviewed_at?.slice(0, 10)}
                                  </Text>
                                )}
                              </Space>
                            }
                            extra={<Text type="secondary" style={{ fontSize: 12 }}>{role.role_id?.slice(0, 18)}</Text>}
                          >
                            {renderDefinition(role)}
                            <div style={{ marginBottom: 4 }}>
                              <Text type="secondary">
                                支撑：{role.supporting_job_count} 岗位 / {role.supporting_company_count} 公司 /{" "}
                                {role.supporting_source_count} 来源 / {(role.evidence_ids || []).length} 证据
                              </Text>
                            </div>
                            <Progress
                              percent={Math.round((scores.overall || 0) * 100)}
                              size="small"
                              status="active"
                              format={() => `综合分 ${(scores.overall || 0).toFixed(2)}`}
                            />
                            <div style={{ marginTop: 4, fontSize: 12, color: "#999" }}>
                              新颖 {(scores.novelty || 0).toFixed(2)} · 增长 {(scores.growth || 0).toFixed(2)} · 持续{" "}
                              {(scores.persistence || 0).toFixed(2)} · 多样 {(scores.source_diversity || 0).toFixed(2)} · 证据{" "}
                              {(scores.evidence_coverage || 0).toFixed(2)}
                            </div>
                            {renderRoleActions(role)}
                          </Card>
                        </Col>
                      );
                    })
                  )}
                </Row>
              ),
            },
            {
              key: "updates",
              label: `既有岗位技能更新（${updates.length}）`,
              children:
                updates.length === 0 ? (
                  <Empty description="暂无技能更新" />
                ) : (
                  updates.map((u) => {
                    const pending = pendingSkillNames(u);
                    const busyAll = reviewBusy.has(`${u.update_id}::*`);
                    const changes = u.changes || [];
                    const decidedCount = changes.filter(
                      (c) => c.decision && c.decision !== "pending"
                    ).length;
                    const g = u.graph_apply;
                    return (
                      <Card
                        size="small"
                        key={u.update_id}
                        style={{ marginBottom: 12 }}
                        title={
                          <Space wrap>
                            <Tag color="purple">{u.canonical_role}</Tag>
                            {renderUpdateStatus(u)}
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {u.window?.recent_start?.slice(0, 10)} ~{" "}
                              {u.window?.recent_end?.slice(0, 10)} 对比基线{" "}
                              {u.window?.baseline_start?.slice(0, 10)} ~{" "}
                              {u.window?.baseline_end?.slice(0, 10)}
                            </Text>
                          </Space>
                        }
                        extra={
                          <Space wrap size={4}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              已审 {decidedCount}/{changes.length}
                            </Text>
                            <Button
                              size="small"
                              type="primary"
                              ghost
                              icon={<CheckOutlined />}
                              loading={busyAll}
                              disabled={pending.length === 0 && !busyAll}
                              onClick={() => {
                                if (pending.length === 0) {
                                  message.info("没有待审核的变化项");
                                  return;
                                }
                                handleReviewUpdate(u, "approved", pending);
                              }}
                            >
                              全部通过
                            </Button>
                            <Button
                              size="small"
                              danger
                              icon={<CloseOutlined />}
                              loading={busyAll}
                              disabled={pending.length === 0 || busyAll}
                              onClick={() => handleReviewUpdate(u, "rejected", pending)}
                            >
                              全部驳回
                            </Button>
                          </Space>
                        }
                      >
                        {u.explanation && (
                          <Text
                            type="secondary"
                            style={{ display: "block", marginBottom: 8, fontSize: 12 }}
                          >
                            {u.explanation}
                          </Text>
                        )}
                        {g && (
                          <div style={{ marginBottom: 8 }}>
                            {g.applied ? (
                              <Text type="success" style={{ fontSize: 12 }}>
                                已写入知识图谱（快照 {g.snapshot}）：命中{" "}
                                {g.matched_job_count || 0} 个既有岗位
                                {(g.additions || []).length > 0
                                  ? `，技能要求边 ${g.additions.length} 条`
                                  : ""}
                                {(g.removals || []).some((r) => (r.edges_deleted || 0) > 0)
                                  ? "，含移除操作"
                                  : ""}
                              </Text>
                            ) : (
                              <Text type="warning" style={{ fontSize: 12 }}>
                                图谱未更新：{g.reason || "未在图谱中找到既有岗位"}
                              </Text>
                            )}
                          </div>
                        )}
                        <Table
                          rowKey={(r) =>
                            `${r.skill_name}#${r.change_type || "unknown"}`
                          }
                          columns={renderUpdateColumns(u)}
                          dataSource={changes}
                          size="small"
                          pagination={false}
                        />
                      </Card>
                    );
                  })
                ),
            },
            {
              key: "features",
              label: `趋势特征（${features.length}）`,
              children:
                features.length === 0 ? (
                  <Empty description="暂无趋势特征" />
                ) : (
                  <Table rowKey="trend_id" columns={featureColumns} dataSource={features} size="small" />
                ),
            },
          ]}
        />
      </Spin>

      {/* 人工优化弹窗 */}
      <Modal
        title={
          <Space>
            <EditOutlined />
            编辑优化岗位定义{editingRole ? `：${editingRole.canonical_title}` : ""}
          </Space>
        }
        open={!!editingRole}
        onOk={handleSaveEdit}
        onCancel={() => setEditingRole(null)}
        okText="保存并提交审核"
        cancelText="取消"
        width={720}
        destroyOnClose
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item
            name="canonical_title"
            label="岗位名称"
            rules={[{ required: true, message: "请输入岗位名称" }]}
          >
            <Input placeholder="如：AI Agent 安全评测工程师" />
          </Form.Item>
          <Form.Item
            name="core_responsibilities"
            label="核心职责（每行一条）"
            rules={[{ required: true, message: "请输入至少一条核心职责" }]}
          >
            <Input.TextArea rows={3} placeholder={"设计智能体工具调用与越权测试\n建立大模型幻觉与安全评测集"} />
          </Form.Item>
          <Form.Item
            name="required_skills"
            label="必备技能"
            rules={[{ required: true, message: "请至少填写一项必备技能" }]}
          >
            <Select
              mode="tags"
              placeholder="输入后回车添加，如：Agent、LLM评测、Python"
              tokenSeparators={[",", "，", "\n"]}
              open={false}
              suffixIcon={null}
            />
          </Form.Item>
          <Form.Item name="preferred_skills" label="加分技能（可空）">
            <Select
              mode="tags"
              placeholder="如：MCP、红队测试"
              tokenSeparators={[",", "，", "\n"]}
              open={false}
              suffixIcon={null}
            />
          </Form.Item>
          <Form.Item
            name="typical_industry_scenarios"
            label="典型行业应用场景（每行一条）"
            rules={[{ required: true, message: "请输入至少一个应用场景" }]}
          >
            <Input.TextArea rows={2} placeholder={"人工智能\n智能智造\n金融科技"} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
