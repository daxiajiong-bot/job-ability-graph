const state = {
  mode: "panorama",
  matchInputMode: "sample",
  graphView: "all",
  samples: { jds: [], resumes: [] },
  currentGraph: null,
};

const fallbackSamples = {
  jds: [
    {
      id: "jd_llm_rag_001",
      title: "大模型算法工程师",
      seniority: "3-5年",
      text:
        "岗位名称: 大模型算法工程师\n岗位职责:\n1. 负责企业知识库问答场景的大语言模型应用建设, 包括 RAG 检索增强生成、Prompt 优化和效果评估。\n任职要求:\n1. 本科及以上学历, 3 年以上 NLP 或大模型相关经验。\n2. 熟练掌握 Python、PyTorch、Transformer、RAG 和模型部署。"
    },
    {
      id: "jd_backend_platform_001",
      title: "后端开发工程师",
      seniority: "3-6年",
      text:
        "岗位名称: 后端开发工程师\n岗位职责:\n1. 负责招聘业务和企业服务平台的后端开发。\n任职要求:\n1. 本科及以上学历, 3 年以上 Java 或 Python 后端开发经验。\n2. 熟练掌握 Java、Spring Boot、MySQL、Redis、Kafka、Docker 和微服务。"
    }
  ],
  resumes: [
    {
      id: "resume_llm_rag_001",
      name: "候选人A",
      text:
        "姓名: 候选人A\n求职意向: 大模型算法工程师\n教育经历: 某大学 计算机科学与技术 硕士\n工作经历:\n2022.07-至今 算法工程师, 负责企业知识库问答产品的 RAG 链路, 使用 Python、PyTorch、LangChain、Milvus 和 FastAPI 完成模型训练与部署。"
    }
  ]
};

const colorByType = {
  Domain: "#725a9a",
  Job: "#3f6f9f",
  Position: "#3f6f9f",
  JobCategory: "#65736e",
  Capability: "#65736e",
  Level: "#a86b12",
  Skill: "#28755b",
  SkillType: "#b04a42",
  TechStack: "#b04a42",
  Resume: "#3f6f9f",
  Candidate: "#3f6f9f",
  Version: "#a86b12",
  Evidence: "#9fb0aa"
};

const els = {};

window.addEventListener("DOMContentLoaded", async () => {
  bindElements();
  bindEvents();
  await checkHealth();
  await loadSamples();
  setMode("panorama");
  await buildPanorama();
});

function bindElements() {
  [
    "apiStatus",
    "apiStatusText",
    "modePanorama",
    "modeMatch",
    "panoramaControls",
    "matchControls",
    "jobSelect",
    "matchJdSelect",
    "matchResumeSelect",
    "buildPanoramaBtn",
    "runMatchBtn",
    "payloadBox",
    "viewAll",
    "viewStack",
    "viewLevel",
    "graphMeta",
    "graphSvg",
    "summaryMetrics",
    "skillList",
    "explanation",
    "modeSample",
    "modeCustom",
    "matchSampleArea",
    "matchCustomArea",
    "customJdText",
    "customResumeText",
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function bindEvents() {
  els.modePanorama.addEventListener("click", () => setMode("panorama"));
  els.modeMatch.addEventListener("click", () => setMode("match"));
  els.buildPanoramaBtn.addEventListener("click", buildPanorama);
  els.runMatchBtn.addEventListener("click", runMatch);
  els.jobSelect.addEventListener("change", updatePayloadPreview);
  els.matchJdSelect.addEventListener("change", updatePayloadPreview);
  els.matchResumeSelect.addEventListener("change", updatePayloadPreview);
  els.modeSample.addEventListener("click", () => setMatchInputMode("sample"));
  els.modeCustom.addEventListener("click", () => setMatchInputMode("custom"));
  els.customJdText.addEventListener("input", updatePayloadPreview);
  els.customResumeText.addEventListener("input", updatePayloadPreview);
  els.viewAll.addEventListener("click", () => setGraphView("all"));
  els.viewStack.addEventListener("click", () => setGraphView("stack"));
  els.viewLevel.addEventListener("click", () => setGraphView("level"));
  window.addEventListener("resize", () => renderGraph(state.currentGraph));
}

async function checkHealth() {
  try {
    await apiGet("/health");
    els.apiStatus.classList.add("ok");
    els.apiStatusText.textContent = "服务正常";
  } catch (error) {
    els.apiStatus.classList.add("error");
    els.apiStatusText.textContent = "离线样例";
  }
}

async function loadSamples() {
  try {
    state.samples = await apiGet("/samples");
  } catch (error) {
    state.samples = fallbackSamples;
  }
  fillSelects();
  fillCustomDefaults();
  updatePayloadPreview();
}

function fillCustomDefaults() {
  if (!els.customJdText.value) {
    const jdSample = state.samples.jds[0];
    if (jdSample) els.customJdText.value = jdSample.text;
  }
  if (!els.customResumeText.value) {
    const resumeSample = state.samples.resumes[0];
    if (resumeSample) els.customResumeText.value = resumeSample.text;
  }
}

function fillSelects() {
  els.jobSelect.innerHTML = "";
  state.samples.jds.forEach((item, index) => {
    const option = new Option(item.title || item.id, item.id);
    option.selected = index < Math.min(4, state.samples.jds.length);
    els.jobSelect.add(option);
  });

  els.matchJdSelect.innerHTML = "";
  state.samples.jds.forEach((item) => els.matchJdSelect.add(new Option(item.title || item.id, item.id)));

  els.matchResumeSelect.innerHTML = "";
  state.samples.resumes.forEach((item) => els.matchResumeSelect.add(new Option(item.name || item.id, item.id)));
}

function setMode(mode) {
  state.mode = mode;
  els.modePanorama.classList.toggle("active", mode === "panorama");
  els.modeMatch.classList.toggle("active", mode === "match");
  els.panoramaControls.classList.toggle("hidden", mode !== "panorama");
  els.matchControls.classList.toggle("hidden", mode !== "match");
  updatePayloadPreview();
}

function setMatchInputMode(mode) {
  state.matchInputMode = mode;
  els.modeSample.classList.toggle("active", mode === "sample");
  els.modeCustom.classList.toggle("active", mode === "custom");
  els.matchSampleArea.classList.toggle("hidden", mode !== "sample");
  els.matchCustomArea.classList.toggle("hidden", mode !== "custom");
  updatePayloadPreview();
}

function setGraphView(view) {
  state.graphView = view;
  els.viewAll.classList.toggle("active", view === "all");
  els.viewStack.classList.toggle("active", view === "stack");
  els.viewLevel.classList.toggle("active", view === "level");
  renderGraph(state.currentGraph);
}

function selectedJobs() {
  const selected = Array.from(els.jobSelect.selectedOptions).map((option) => option.value);
  const ids = selected.length ? selected : state.samples.jds.map((item) => item.id);
  return state.samples.jds.filter((item) => ids.includes(item.id));
}

function selectedJd() {
  if (state.matchInputMode === "custom") {
    const text = els.customJdText.value.trim();
    return text ? { id: "custom_jd", title: "自定义岗位", text } : null;
  }
  return state.samples.jds.find((item) => item.id === els.matchJdSelect.value) || state.samples.jds[0];
}

function selectedResume() {
  if (state.matchInputMode === "custom") {
    const text = els.customResumeText.value.trim();
    return text ? { id: "custom_resume", name: "自定义简历", text } : null;
  }
  return state.samples.resumes.find((item) => item.id === els.matchResumeSelect.value) || state.samples.resumes[0];
}

function updatePayloadPreview() {
  if (state.mode === "panorama") {
    const payload = {
      job_documents: selectedJobs().map((item) => ({
        id: item.id,
        level: item.seniority,
        source_type: "sample_jd",
        text: item.text,
      }))
    };
    els.payloadBox.value = JSON.stringify(payload, null, 2);
  } else {
    const jd = selectedJd();
    const resume = selectedResume();
    if (!jd || !resume) {
      els.payloadBox.value = state.matchInputMode === "custom"
        ? '{"提示": "请输入岗位JD和简历内容"}'
        : JSON.stringify({ jd_text: "", resume_text: "" }, null, 2);
      return;
    }
    els.payloadBox.value = JSON.stringify({ jd_text: jd.text, resume_text: resume.text }, null, 2);
  }
}

async function buildPanorama() {
  state.mode = "panorama";
  updatePayloadPreview();
  try {
    const result = await apiPost("/graph/panorama", JSON.parse(els.payloadBox.value));
    const graph = result.data || result;
    state.currentGraph = graph;
    renderGraph(graph);
    renderPanoramaSummary(graph);
  } catch (error) {
    showError(error);
  }
}

async function runMatch() {
  state.mode = "match";
  updatePayloadPreview();
  const jd = selectedJd();
  const resume = selectedResume();
  if (!jd || !resume) {
    els.graphMeta.textContent = "输入为空";
    els.explanation.textContent = state.matchInputMode === "custom"
      ? "请先输入岗位JD和简历内容"
      : "请选择岗位和简历";
    return;
  }
  try {
    const result = await apiPost("/match", JSON.parse(els.payloadBox.value));
    state.currentGraph = result.graph;
    renderGraph(result.graph);
    renderMatchSummary(result);
  } catch (error) {
    showError(error);
  }
}

function renderPanoramaSummary(graph) {
  const meta = graph.graph_metadata || {};
  els.graphMeta.textContent = `${meta.job_count || 0} 个岗位 · ${meta.skill_count || 0} 个技能`;
  renderMetrics([
    ["岗位", meta.job_count || 0],
    ["技能", meta.skill_count || 0],
    ["节点", graph.nodes?.length || 0],
    ["边", graph.edges?.length || 0],
  ]);
  const skills = (graph.nodes || [])
    .filter((node) => node.type === "Skill")
    .sort((a, b) => (b.properties?.support_count || 0) - (a.properties?.support_count || 0))
    .slice(0, 12)
    .map((node) => ({ name: node.label, value: `${node.properties?.support_count || 0} 岗位`, tone: "green" }));
  renderSkillList(skills);
  els.explanation.textContent = "全景图谱按岗位、技能、技术栈和级别组织，可用于展示新一代信息技术岗位能力分布。";
}

function renderMatchSummary(result) {
  const match = result.match_result || {};
  els.graphMeta.textContent = `${match.final_score || 0} 分 · ${match.matched_skills?.length || 0} 个命中技能`;
  renderMetrics([
    ["匹配分", match.final_score ?? 0],
    ["覆盖率", percent(match.skill_coverage)],
    ["相似度", percent(match.distribution_similarity)],
    ["缺失", match.missing_skills?.length || 0],
  ]);
  const matched = (match.matched_skills || []).slice(0, 8).map((item) => ({
    name: item.name,
    value: item.match_type === "related" ? "相关" : "命中",
    tone: "green",
  }));
  const missing = (match.missing_skills || []).slice(0, 6).map((item) => ({
    name: item.name,
    value: item.priority,
    tone: item.priority === "high" ? "red" : "amber",
  }));
  renderSkillList([...matched, ...missing]);
  els.explanation.textContent = match.explanation || "暂无解释";
}

function renderMetrics(items) {
  els.summaryMetrics.innerHTML = items.map(([label, value]) => (
    `<div class="metric"><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></div>`
  )).join("");
}

function renderSkillList(items) {
  if (!items.length) {
    els.skillList.innerHTML = `<div class="skill-row"><span>暂无技能项</span><small>-</small></div>`;
    return;
  }
  els.skillList.innerHTML = items.map((item) => (
    `<div class="skill-row"><span>${escapeHtml(item.name)}</span><span class="pill ${item.tone}">${escapeHtml(item.value)}</span></div>`
  )).join("");
}

function renderGraph(graph) {
  const svg = els.graphSvg;
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  if (!graph || !graph.nodes || !graph.edges) return;

  const rect = svg.getBoundingClientRect();
  const width = Math.max(640, rect.width || 900);
  const height = Math.max(520, rect.height || 620);
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const { nodes, edges } = filterGraph(graph);
  const positioned = layoutNodes(nodes, width, height);
  const nodeById = new Map(positioned.map((node) => [node.id, node]));

  const edgeGroup = makeSvg("g", {});
  edges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return;
    edgeGroup.appendChild(makeSvg("line", {
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
      class: "edge-line",
      "stroke-width": Math.max(0.8, Math.min(3, Number(edge.weight || 1) * 1.4)),
    }));
  });
  svg.appendChild(edgeGroup);

  const nodeGroup = makeSvg("g", {});
  positioned.forEach((node) => {
    const group = makeSvg("g", {});
    const radius = nodeRadius(node);
    group.appendChild(makeSvg("circle", {
      cx: node.x,
      cy: node.y,
      r: radius,
      fill: colorByType[node.type] || "#65736e",
      class: "node-circle",
    }));
    group.appendChild(makeSvg("text", {
      x: node.x + radius + 4,
      y: node.y + 4,
      class: "node-label",
    }, truncate(node.label, 16)));
    nodeGroup.appendChild(group);
  });
  svg.appendChild(nodeGroup);
}

function filterGraph(graph) {
  if (state.graphView === "all") {
    return { nodes: graph.nodes, edges: graph.edges };
  }
  const keepTypes = state.graphView === "stack"
    ? new Set(["Domain", "Job", "Position", "Skill", "SkillType", "TechStack", "Capability"])
    : new Set(["Domain", "Job", "Position", "Resume", "Candidate", "Skill", "Level"]);
  const nodes = graph.nodes.filter((node) => keepTypes.has(node.type));
  const ids = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  return { nodes, edges };
}

function layoutNodes(nodes, width, height) {
  const groups = groupBy(nodes, (node) => node.type);
  const order = ["Domain", "Version", "Job", "Position", "Resume", "Candidate", "JobCategory", "Capability", "TechStack", "Level", "Skill", "SkillType", "Evidence"];
  const lanes = order.filter((type) => groups[type]?.length);
  const laneWidth = width / Math.max(1, lanes.length);
  const result = [];

  lanes.forEach((type, laneIndex) => {
    const items = groups[type].slice().sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
    items.forEach((node, itemIndex) => {
      const count = items.length;
      const x = laneWidth * laneIndex + laneWidth / 2;
      const y = count === 1 ? height / 2 : 48 + itemIndex * ((height - 96) / Math.max(1, count - 1));
      result.push({ ...node, x, y });
    });
  });
  return result;
}

function nodeRadius(node) {
  if (node.type === "Domain") return 15;
  if (node.type === "Job" || node.type === "Resume" || node.type === "Position" || node.type === "Candidate") return 12;
  if (node.type === "Skill") return Math.min(12, 7 + (node.properties?.support_count || 1));
  return 8;
}

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`${path}: ${message}`);
  }
  return response.json();
}

function makeSvg(tag, attrs, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs || {}).forEach(([key, value]) => element.setAttribute(key, value));
  if (text) element.textContent = text;
  return element;
}

function groupBy(items, getKey) {
  return items.reduce((acc, item) => {
    const key = getKey(item);
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
}

function percent(value) {
  if (value === undefined || value === null) return "0%";
  return `${Math.round(Number(value) * 100)}%`;
}

function truncate(text, limit) {
  const source = String(text || "");
  return source.length > limit ? `${source.slice(0, limit - 1)}…` : source;
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function showError(error) {
  els.graphMeta.textContent = "请求失败";
  els.explanation.textContent = error.message;
}
