/**
 * 数据适配器 - 将后端数据转换为前端组件所需格式
 */

/**
 * 将后端 JD 数据转换为 JobGalaxy 所需格式
 * @param {Array} backendData - 后端返回的 JD 数组
 * @returns {Object} { nodes, links, categories }
 */
export function adaptJobDataForGalaxy(backendData) {
  const nodes = [];
  const links = [];
  const categories = [
    { name: "岗位大类" },
    { name: "职位" },
    { name: "技能" },
  ];

  backendData.forEach((jd) => {
    // 岗位节点
    nodes.push({
      id: `job_${jd.job_id}`,
      name: jd.job_title || jd.title,
      category: 1,
      value: jd.skills_norm?.length || 0,
      symbolSize: Math.max(10, (jd.skills_norm?.length || 0) * 3),
    });

    // 技能节点与连线
    jd.skills_norm?.forEach((skill) => {
      const skillId = `skill_${skill}`;
      if (!nodes.find((n) => n.id === skillId)) {
        nodes.push({
          id: skillId,
          name: skill,
          category: 2,
          value: 1,
          symbolSize: 8,
        });
      }
      links.push({
        source: `job_${jd.job_id}`,
        target: skillId,
      });
    });
  });

  return { nodes, links, categories };
}

/**
 * 将后端图谱数据转换为 ECharts graph 格式
 * @param {Array} graphNodes - 后端图谱节点
 * @param {Array} graphEdges - 后端图谱边
 * @returns {Object} ECharts option
 */
export function adaptGraphForECharts(graphNodes, graphEdges) {
  const categories = [
    { name: "岗位" },
    { name: "技能" },
    { name: "知识" },
    { name: "通用能力" },
    { name: "公司" },
  ];

  const categoryMap = {
    Job: 0,
    Skill: 1,
    AbilityEntity: 1,
    Knowledge: 2,
    Company: 4,
  };

  const nodes = graphNodes
    .filter((n) => n.label !== "Evidence")
    .map((node) => ({
      name: node.properties?.name || node.properties?.title || node.node_id,
      category: categoryMap[node.label] ?? 3,
      symbolSize: node.label === "Job" ? 40 : 20,
      value: node.label,
      id: node.node_id,
    }));

  const links = graphEdges
    .filter((e) =>
      ["REQUIRES_SKILL", "HAS_KNOWLEDGE", "HAS_ABILITY"].includes(e.relation_type)
    )
    .map((edge) => ({
      source: edge.source_id,
      target: edge.target_id,
    }));

  return {
    tooltip: {
      formatter: (params) => {
        if (params.dataType === "node") {
          return `<strong>${params.name}</strong><br/>类型：${categories[params.data.category]?.name || "-"}`;
        }
        return `${params.data.source} → ${params.data.target}`;
      },
    },
    legend: {
      data: categories.map((c) => c.name),
      bottom: 10,
      textStyle: { color: "#8b949e" },
    },
    series: [
      {
        type: "graph",
        layout: "force",
        data: nodes,
        links: links,
        categories: categories,
        roam: true,
        draggable: true,
        force: {
          repulsion: 300,
          edgeLength: [80, 200],
          gravity: 0.1,
        },
        label: {
          show: true,
          position: "right",
          color: "#e6edf3",
          fontSize: 11,
        },
        lineStyle: {
          color: "source",
          curveness: 0.15,
          opacity: 0.6,
        },
        emphasis: {
          focus: "adjacency",
          lineStyle: { width: 3 },
        },
      },
    ],
  };
}

/**
 * 从匹配结果中提取技能列表
 * @param {Object} matchResult - 匹配结果
 * @returns {Array} 技能列表
 */
export function extractSkillsFromMatch(matchResult) {
  const skills = [];

  if (matchResult?.details?.matched_skills) {
    matchResult.details.matched_skills.forEach((skill) => {
      skills.push({
        name: typeof skill === "string" ? skill : skill.name || skill.skill,
        category: typeof skill === "object" ? skill.category || "S" : "S",
        level: typeof skill === "object" ? skill.level || "matched" : "matched",
      });
    });
  }

  if (matchResult?.details?.missing_skills) {
    matchResult.details.missing_skills.forEach((skill) => {
      skills.push({
        name: typeof skill === "string" ? skill : skill.name || skill.skill,
        category: typeof skill === "object" ? skill.category || "S" : "S",
        level: "missing",
      });
    });
  }

  return skills;
}

/**
 * 从画像中提取技能列表
 * @param {Object} profile - 候选人画像或岗位画像
 * @returns {Array} 技能列表
 */
export function extractSkillsFromProfile(profile) {
  const skills = [];

  const profileData = profile?.attributes?.resume_profile ||
    profile?.attributes?.jd_profile ||
    profile?.attributes || {};

  if (profileData.skills) {
    profileData.skills.forEach((skill) => {
      if (typeof skill === "string") {
        skills.push({ name: skill, category: "S", level: "intermediate" });
      } else {
        skills.push({
          name: skill.name || skill.skill,
          category: skill.category || "S",
          level: skill.level || "intermediate",
        });
      }
    });
  }

  if (profileData.technical_skills) {
    profileData.technical_skills.forEach((skill) => {
      const name = typeof skill === "string" ? skill : skill.name;
      if (name) {
        skills.push({ name, category: "Tech", level: "intermediate" });
      }
    });
  }

  if (profileData.knowledge) {
    profileData.knowledge.forEach((k) => {
      const name = typeof k === "string" ? k : k.name;
      if (name) {
        skills.push({ name, category: "K", level: "intermediate" });
      }
    });
  }

  return skills;
}

/**
 * 格式化匹配分数为等级
 * @param {number} score - 匹配分数 (0-100)
 * @returns {Object} { level, color, text }
 */
export function formatMatchLevel(score) {
  if (score >= 80) {
    return { level: "high", color: "green", text: "高度匹配" };
  } else if (score >= 60) {
    return { level: "medium", color: "orange", text: "中度匹配" };
  } else {
    return { level: "low", color: "red", text: "低度匹配" };
  }
}

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的大小
 */
export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * 生成唯一 ID
 * @returns {string} 唯一 ID
 */
export function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
}
