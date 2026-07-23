import { useMemo } from "react";
import { Card, Typography, Tag, Space, Empty, Tooltip } from "antd";
import { BranchesOutlined, ApartmentOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";

const { Text } = Typography;

// ── 技能分类颜色 ──
const CATEGORY_COLORS = {
  L: "#4dd6ff", // 语言能力
  S: "#52c41a", // 专业技能
  K: "#9254de", // 知识领域
  T: "#fa8c16", // 工具使用
  Tech: "#ff4d4f", // 技术栈
};

const CATEGORY_NAMES = {
  L: "语言能力",
  S: "专业技能",
  K: "知识领域",
  T: "工具使用",
  Tech: "技术栈",
};

/**
 * 从技能列表构建 DAG 数据
 */
function buildDagData(skills) {
  if (!skills || skills.length === 0) return null;

  const nodes = [];
  const links = [];
  const categoryGroups = {};

  // 按分类分组
  skills.forEach((skill, index) => {
    const name = typeof skill === "string" ? skill : skill.name || skill.skill;
    const category = typeof skill === "object" ? skill.category || "S" : "S";
    const level = typeof skill === "object" ? skill.level || "intermediate" : "intermediate";

    if (!categoryGroups[category]) {
      categoryGroups[category] = [];
    }
    categoryGroups[category].push({ name, category, level, index });
  });

  // 创建分类节点
  Object.keys(categoryGroups).forEach((category) => {
    nodes.push({
      name: CATEGORY_NAMES[category] || category,
      category: category,
      symbolSize: 40,
      value: categoryGroups[category].length,
      itemStyle: {
        color: CATEGORY_COLORS[category] || "#4dd6ff",
        borderColor: "#fff",
        borderWidth: 2,
      },
      label: {
        show: true,
        position: "inside",
        formatter: CATEGORY_NAMES[category] || category,
        fontSize: 10,
        color: "#fff",
      },
    });

    // 创建技能节点
    categoryGroups[category].forEach((skill) => {
      nodes.push({
        name: skill.name,
        category: skill.category,
        symbolSize: 20 + skill.level.length * 3,
        value: skill.level,
        itemStyle: {
          color: CATEGORY_COLORS[skill.category] || "#4dd6ff",
          opacity: 0.8,
        },
        label: {
          show: true,
          position: "right",
          fontSize: 11,
          color: "#e6edf3",
        },
      });

      // 分类 -> 技能 连线
      links.push({
        source: CATEGORY_NAMES[skill.category] || skill.category,
        target: skill.name,
        lineStyle: {
          color: CATEGORY_COLORS[skill.category] || "#4dd6ff",
          opacity: 0.5,
          curveness: 0.2,
        },
      });
    });
  });

  return { nodes, links };
}

/**
 * SkillDag 组件 - 技能 DAG 图
 */
export default function SkillDag({ skills, title = "技能 DAG 图", height = 400, style }) {
  const dagData = useMemo(() => buildDagData(skills), [skills]);

  if (!dagData) {
    return (
      <Card title={title} style={style}>
        <Empty description="暂无技能数据" />
      </Card>
    );
  }

  const option = {
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(13, 17, 23, 0.9)",
      borderColor: "rgba(77, 214, 255, 0.3)",
      textStyle: { color: "#e6edf3" },
      formatter: (params) => {
        if (params.dataType === "node") {
          const category = params.data.category;
          const categoryName = CATEGORY_NAMES[category] || category;
          if (params.data.value && typeof params.data.value === "string") {
            return `<strong>${params.name}</strong><br/>分类：${categoryName}<br/>水平：${params.data.value}`;
          }
          return `<strong>${params.name}</strong><br/>包含 ${params.data.value} 项技能`;
        }
        return "";
      },
    },
    legend: {
      data: Object.keys(CATEGORY_NAMES).map((key) => ({
        name: CATEGORY_NAMES[key],
        icon: "circle",
      })),
      bottom: 10,
      textStyle: { color: "#8b949e" },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        data: dagData.nodes,
        links: dagData.links,
        roam: true,
        draggable: true,
        force: {
          repulsion: 200,
          edgeLength: [60, 150],
          gravity: 0.1,
        },
        lineStyle: {
          opacity: 0.6,
          curveness: 0.2,
        },
        emphasis: {
          focus: "adjacency",
          lineStyle: { width: 3 },
        },
        edgeSymbol: ["none", "arrow"],
        edgeSymbolSize: 8,
      },
    ],
  };

  return (
    <Card
      title={
        <Space>
          <BranchesOutlined />
          <span>{title}</span>
          <Tag color="blue">{skills.length} 项技能</Tag>
        </Space>
      }
      style={style}
    >
      <ReactECharts
        option={option}
        style={{ height }}
        opts={{ renderer: "canvas" }}
        onEvents={{
          click: (params) => {
            if (params.dataType === "node") {
              // 可以添加节点点击事件
            }
          },
        }}
      />
      <div style={{ marginTop: 8, textAlign: "center" }}>
        <Space size={16}>
          {Object.entries(CATEGORY_COLORS).map(([key, color]) => (
            <Tooltip key={key} title={CATEGORY_NAMES[key]}>
              <Tag
                color={color}
                style={{ cursor: "pointer" }}
              >
                {CATEGORY_NAMES[key]}
              </Tag>
            </Tooltip>
          ))}
        </Space>
      </div>
    </Card>
  );
}
