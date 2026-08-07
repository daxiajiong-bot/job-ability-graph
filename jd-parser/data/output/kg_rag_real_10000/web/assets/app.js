(function () {
  const data = window.KG_WEB_DATA;
  if (!data) {
    document.body.innerHTML = "<p>Missing graph data.</p>";
    return;
  }

  const state = {
    view: "top",
    selectedNodeId: null,
    skill: data.topSkills[0]?.name || "",
  };

  const color = {
    Job: "#2563eb",
    Skill: "#059669",
    Evidence: "#64748b",
    Education: "#a855f7",
    ExperienceRequirement: "#ea580c",
    Location: "#0891b2",
    Hub: "#111827",
  };

  const canvas = document.getElementById("graphCanvas");
  const graphTitle = document.getElementById("graphTitle");
  const graphMeta = document.getElementById("graphMeta");
  const details = document.getElementById("nodeDetails");
  const skillInput = document.getElementById("skillSearch");

  function fmt(value) {
    return new Intl.NumberFormat("zh-CN").format(value || 0);
  }

  function pct(value) {
    return `${Math.round((value || 0) * 1000) / 10}%`;
  }

  function nodeLabel(node) {
    const p = node.properties || {};
    return p.title || p.name || p.value || p.text || node.label || node.id;
  }

  function short(value, max = 24) {
    const text = String(value || "");
    return text.length > max ? `${text.slice(0, max - 1)}...` : text;
  }

  function initMetrics() {
    const s = data.summary;
    document.getElementById("metricJobs").textContent = fmt(s.source_profile_count);
    document.getElementById("metricNodes").textContent = fmt(s.graph_node_count);
    document.getElementById("metricEdges").textContent = fmt(s.graph_edge_count);
    document.getElementById("metricCoverage").textContent = pct(s.coverage.jobs_with_skill_edges_ratio);

    const status = document.getElementById("validationStatus");
    status.textContent = data.validation.status.toUpperCase();
    status.classList.toggle("invalid", data.validation.status !== "valid");

    const checks = data.validation.checks;
    const rows = [
      ["悬空边", checks.dangling_edges],
      ["证据缺失", checks.evidence_text_missing_from_raw_text],
      ["重复节点", checks.duplicate_node_ids],
      ["重复关系", checks.duplicate_edge_ids],
      ["无技能岗位", checks.jobs_without_skill_edges],
    ];
    document.getElementById("validationChecks").innerHTML = rows
      .map(([name, value]) => `<div><span>${name}</span><strong>${fmt(value)}</strong></div>`)
      .join("");
  }

  function initSkillOptions() {
    const options = document.getElementById("skillOptions");
    options.innerHTML = data.skills.map((skill) => `<option value="${escapeHtml(skill.name)}"></option>`).join("");
    skillInput.value = state.skill;
    skillInput.addEventListener("change", () => {
      state.skill = skillInput.value.trim() || state.skill;
      state.view = "focus";
      setActiveView();
      render();
    });
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setActiveView() {
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.classList.toggle("active", button.dataset.view === state.view);
    });
  }

  function bindControls() {
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.addEventListener("click", () => {
        state.view = button.dataset.view;
        setActiveView();
        render();
      });
    });
    document.getElementById("resetSelection").addEventListener("click", () => {
      state.selectedNodeId = null;
      details.className = "detail-empty";
      details.textContent = "选择一个节点";
      render();
    });
  }

  function topSkillGraph() {
    const top = data.topSkills.slice(0, 28);
    const nodes = [
      {
        id: "hub",
        label: "Hub",
        properties: { title: "9000 JD", count: data.summary.source_profile_count },
        x: 430,
        y: 290,
        r: 24,
      },
    ];
    const edges = [];
    const radius = 238;
    top.forEach((skill, index) => {
      const angle = -Math.PI / 2 + (index / top.length) * Math.PI * 2;
      const x = 430 + Math.cos(angle) * radius;
      const y = 290 + Math.sin(angle) * radius;
      nodes.push({
        id: `skill:${skill.name}`,
        label: "Skill",
        properties: skill,
        x,
        y,
        r: 10 + Math.sqrt(skill.count) / 10,
      });
      edges.push({ source_id: "hub", target_id: `skill:${skill.name}`, relation_type: "TOP_SKILL", properties: { weight: skill.count } });
    });
    return { nodes, edges, title: "Top 技能关系", meta: `${top.length} 个高频技能，按提及次数缩放节点大小` };
  }

  function sampleGraph() {
    const source = data.sampleGraph;
    const nodes = source.nodes.map((node) => ({ id: node.node_id, label: node.label, properties: node.properties || {} }));
    const edges = source.edges.map((edge) => ({ ...edge }));
    const lanes = { Job: 80, Skill: 360, Education: 360, ExperienceRequirement: 360, Location: 360, Evidence: 690 };
    const counters = {};
    nodes.forEach((node) => {
      const lane = lanes[node.label] || 520;
      counters[node.label] = (counters[node.label] || 0) + 1;
      node.x = lane;
      node.y = 42 + counters[node.label] * 44;
      node.r = node.label === "Job" ? 12 : 9;
    });
    return { nodes, edges, title: "岗位子图", meta: "前 5 个岗位的一跳能力与证据关系" };
  }

  function skillFocusGraph() {
    const skill = data.skillIndex[state.skill] || data.skills[0];
    const jobs = (skill.jobs || []).slice(0, 14);
    const centerId = `skill:${skill.name}`;
    const nodes = [
      { id: centerId, label: "Skill", properties: skill, x: 430, y: 290, r: 22 },
    ];
    const edges = [];
    jobs.forEach((job, index) => {
      const side = index % 2 === 0 ? -1 : 1;
      const row = Math.floor(index / 2);
      const jobId = `job:${job.document_id}`;
      const evId = `evidence:${job.document_id}:${index}`;
      nodes.push({
        id: jobId,
        label: "Job",
        properties: { title: job.title, document_id: job.document_id, location: job.location },
        x: side < 0 ? 120 : 740,
        y: 70 + row * 72,
        r: 10,
      });
      nodes.push({
        id: evId,
        label: "Evidence",
        properties: { text: job.evidence, level: job.level },
        x: side < 0 ? 250 : 610,
        y: 70 + row * 72,
        r: 8,
      });
      edges.push({ source_id: jobId, target_id: centerId, relation_type: relationForLevel(job.level), properties: { level: job.level } });
      edges.push({ source_id: centerId, target_id: evId, relation_type: "SUPPORTED_BY", properties: { level: job.level } });
    });
    return { nodes, edges, title: `${skill.name} 技能聚焦`, meta: `${fmt(skill.count)} 次提及，展示 ${jobs.length} 个岗位样例` };
  }

  function relationForLevel(level) {
    if (level === "required") return "REQUIRES_SKILL";
    if (level === "preferred") return "PREFERS_SKILL";
    return "MENTIONS_SKILL";
  }

  function render() {
    const graph = state.view === "sample" ? sampleGraph() : state.view === "focus" ? skillFocusGraph() : topSkillGraph();
    graphTitle.textContent = graph.title;
    graphMeta.textContent = graph.meta;
    renderSvg(graph);
    renderSkillExamples();
  }

  function renderSvg(graph) {
    const width = 860;
    const height = 590;
    const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
    canvas.setAttribute("viewBox", `0 0 ${width} ${height}`);
    canvas.innerHTML = "";

    const edgeLayer = svg("g", { class: "edge-layer" });
    graph.edges.forEach((edge) => {
      const source = nodeById.get(edge.source_id);
      const target = nodeById.get(edge.target_id);
      if (!source || !target) return;
      const line = svg("line", {
        class: `edge ${edgeClass(edge)}`,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        "stroke-width": Math.min(6, 1 + Math.sqrt((edge.properties || {}).weight || 1) / 22),
      });
      edgeLayer.appendChild(line);
    });
    canvas.appendChild(edgeLayer);

    const nodeLayer = svg("g", { class: "node-layer" });
    graph.nodes.forEach((node) => {
      const group = svg("g", {
        class: `node ${state.selectedNodeId === node.id ? "selected" : ""}`,
        transform: `translate(${node.x}, ${node.y})`,
      });
      const fill = color[node.label] || "#475569";
      if (node.label === "Evidence") {
        group.appendChild(svg("rect", { x: -8, y: -8, width: 16, height: 16, rx: 3, fill }));
      } else {
        group.appendChild(svg("circle", { r: node.r || 10, fill }));
      }
      group.appendChild(svg("text", { x: (node.r || 10) + 8, y: 4 }, short(nodeLabel(node), node.label === "Evidence" ? 22 : 18)));
      group.addEventListener("click", () => {
        state.selectedNodeId = node.id;
        renderDetails(node);
        renderSvg(graph);
      });
      nodeLayer.appendChild(group);
    });
    canvas.appendChild(nodeLayer);
  }

  function edgeClass(edge) {
    if (edge.relation_type === "REQUIRES_SKILL") return "required";
    if (edge.relation_type === "PREFERS_SKILL") return "preferred";
    if (edge.relation_type === "MENTIONS_SKILL") return "mentioned";
    if (edge.relation_type === "SUPPORTED_BY") return "supported";
    return "";
  }

  function svg(name, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs || {}).forEach(([key, value]) => el.setAttribute(key, value));
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function renderDetails(node) {
    const props = node.properties || {};
    const rows = Object.entries(props)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => `<strong>${escapeHtml(key)}</strong><span>${escapeHtml(value)}</span>`)
      .join("");
    details.className = "detail-kv";
    details.innerHTML = `<strong>label</strong><span>${escapeHtml(node.label)}</span><strong>id</strong><span>${escapeHtml(node.id)}</span>${rows}`;
  }

  function renderBars(targetId, rows, colorValue) {
    const target = document.getElementById(targetId);
    const max = Math.max(...rows.map((row) => row.count), 1);
    target.innerHTML = rows
      .map((row) => {
        const width = Math.max(2, (row.count / max) * 100);
        return `<div class="bar-row"><span class="bar-label" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span><span class="bar-track"><span class="bar-fill" style="width:${width}%;background:${colorValue}"></span></span><span class="bar-value">${fmt(row.count)}</span></div>`;
      })
      .join("");
  }

  function renderAnalytics() {
    renderBars("skillBars", data.topSkills.slice(0, 18), "#0f766e");
    const edgeRows = Object.entries(data.summary.edge_counts).map(([name, count]) => ({ name, count }));
    renderBars("edgeBars", edgeRows, "#a855f7");
  }

  function renderSkillExamples() {
    const skill = data.skillIndex[state.skill] || data.skills[0];
    const examples = (skill.jobs || []).slice(0, 6);
    document.getElementById("skillExamples").innerHTML = examples
      .map(
        (job) =>
          `<div class="example"><strong>${escapeHtml(job.title)}</strong><p>${escapeHtml(job.level)} · ${escapeHtml(job.location || "")}</p><p>${escapeHtml(job.evidence)}</p></div>`,
      )
      .join("");
  }

  initMetrics();
  initSkillOptions();
  bindControls();
  renderAnalytics();
  render();
})();

