import { useRef, useEffect, useState, useMemo } from "react";
import { Card, Typography, Tag, Space, message } from "antd";
import { NodeIndexOutlined } from "@ant-design/icons";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const { Text } = Typography;

// ── 颜色配置 ──
const TYPE_COLORS = {
  job: { main: "#4dd6ff", hex: 0x4dd6ff, emissive: 0x071427, opacity: 1 },
  skill: { main: "#52c41a", hex: 0x52c41a, emissive: 0x0a1a08, opacity: 0.92 },
  knowledge: { main: "#b37feb", hex: 0xb37feb, emissive: 0x1a0f2e, opacity: 0.92 },
  ability: { main: "#faad14", hex: 0xfaad14, emissive: 0x1a1408, opacity: 0.92 },
};

const TYPE_LABELS = { job: "岗位", skill: "技能", knowledge: "知识", ability: "能力" };

const NODE_TYPE_MAP = {
  Job: "job",
  Skill: "skill",
  Knowledge: "knowledge",
  AbilityEntity: "ability",
};

// ── 技能热度颜色 ──
const SKILL_HEAT_COLORS = ["#6ee7a8", "#d6e85f", "#ffb347", "#ff5f57"];

function skillHeatColor(count, maxCount) {
  if (maxCount <= 0) return SKILL_HEAT_COLORS[0];
  const ratio = Math.min(count / maxCount, 1);
  const pos = ratio * (SKILL_HEAT_COLORS.length - 1);
  const idx = Math.floor(pos);
  const next = Math.min(idx + 1, SKILL_HEAT_COLORS.length - 1);
  return interpolateColor(SKILL_HEAT_COLORS[idx], SKILL_HEAT_COLORS[next], pos - idx);
}

function interpolateColor(a, b, t) {
  const ah = parseInt(a.slice(1), 16), bh = parseInt(b.slice(1), 16);
  const r = Math.round(((ah >> 16) & 0xff) * (1 - t) + ((bh >> 16) & 0xff) * t);
  const g = Math.round(((ah >> 8) & 0xff) * (1 - t) + ((bh >> 8) & 0xff) * t);
  const bl = Math.round((ah & 0xff) * (1 - t) + (bh & 0xff) * t);
  return `#${((1 << 24) + (r << 16) + (g << 8) + bl).toString(16).slice(1)}`;
}

// ── 从后端图谱数据构建节点和边 ──
function buildGraphData(graphNodes, graphEdges) {
  const nodes = [];
  const links = [];
  const nodeMap = new Map();
  const degreeMap = new Map();
  const skillCountMap = new Map();

  const filtered = graphNodes.filter((n) => n.label !== "Evidence" && n.label !== "Company");

  // 统计度数
  for (const edge of graphEdges) {
    degreeMap.set(edge.source_id, (degreeMap.get(edge.source_id) || 0) + 1);
    degreeMap.set(edge.target_id, (degreeMap.get(edge.target_id) || 0) + 1);
  }

  const maxDegree = Math.max(...degreeMap.values(), 1);

  // 统计技能出现次数（用于热度着色）
  const keyRelations = ["REQUIRES_SKILL", "HAS_KNOWLEDGE", "HAS_ABILITY"];
  for (const edge of graphEdges) {
    if (keyRelations.includes(edge.relation_type)) {
      skillCountMap.set(edge.target_id, (skillCountMap.get(edge.target_id) || 0) + 1);
    }
  }
  const maxSkillCount = Math.max(...skillCountMap.values(), 1);

  filtered.forEach((node, index) => {
    const type = NODE_TYPE_MAP[node.label] || "skill";
    const nodeId = node.node_id;
    const name = node.properties?.name || node.properties?.title || nodeId;
    const degree = degreeMap.get(nodeId) || 0;

    // 岗位节点更大，技能节点按度数缩放
    const radiusMap = { job: 1.8, skill: 0.5, knowledge: 0.45, ability: 0.45 };
    const baseRadius = radiusMap[type] || 0.5;
    const radius = type === "skill" ? baseRadius + (degree / maxDegree) * 0.8 : baseRadius;

    // 三层布局：岗位在上，技能在中，知识/能力在下
    const yMap = { job: 14, skill: 0, knowledge: -14, ability: -14 };
    const y = yMap[type] || 0;

    // 技能热度颜色
    const heatColor = type === "skill" ? skillHeatColor(skillCountMap.get(nodeId) || 0, maxSkillCount) : null;

    nodes.push({
      id: nodeId,
      name,
      type,
      radius,
      degree,
      label: node.label,
      properties: node.properties,
      heatColor,
      skillCount: skillCountMap.get(nodeId) || 0,
      x: seededOffset(nodeId, index, 40),
      y: y + seededOffset(`${nodeId}:y`, index, 6),
      z: seededOffset(`${nodeId}:z`, index, 40),
      index,
    });
    nodeMap.set(nodeId, nodes[nodes.length - 1]);
  });

  // 力导向排斥（简单版）
  repelNodes(nodes.filter((n) => n.type === "job"), 5, 20);
  repelNodes(nodes.filter((n) => n.type === "skill"), 2.5, 15);
  repelNodes(nodes.filter((n) => n.type === "knowledge" || n.type === "ability"), 2, 10);

  graphEdges
    .filter((e) => keyRelations.includes(e.relation_type))
    .forEach((edge) => {
      if (nodeMap.has(edge.source_id) && nodeMap.has(edge.target_id)) {
        links.push({
          source: edge.source_id,
          target: edge.target_id,
          type: edge.relation_type,
          confidence: edge.properties?.confidence || 0.8,
        });
      }
    });

  // 构建岗位→技能映射
  const jobSkillsMap = new Map();
  for (const link of links) {
    const srcNode = nodeMap.get(link.source);
    if (srcNode?.type === "job") {
      if (!jobSkillsMap.has(link.source)) jobSkillsMap.set(link.source, []);
      jobSkillsMap.get(link.source).push(link.target);
    }
  }

  return { nodes, links, nodeMap, jobSkillsMap, maxSkillCount };
}

// Stable placement keeps the graph readable across refreshes and data reloads.
function seededOffset(value, index, span) {
  const hash = indexHash(value, index);
  const normalized = (hash % 10000) / 9999;
  return (normalized - 0.5) * span;
}

function indexHash(value, seed = 0) {
  let hash = 2166136261 ^ seed;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function repelNodes(nodes, minDist, rounds) {
  for (let r = 0; r < rounds; r++) {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dz = b.z - a.z;
        const dist = Math.sqrt(dx * dx + dz * dz) || 0.01;
        if (dist < minDist) {
          const push = (minDist - dist) * 0.1;
          const nx = dx / dist, nz = dz / dist;
          a.x -= nx * push; a.z -= nz * push;
          b.x += nx * push; b.z += nz * push;
        }
      }
    }
  }
}

// ── 发光粒子球体 Shader（参照 JobCloud） ──
function createParticleSphereMaterial(color) {
  return new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(color) },
      uTime: { value: 0 },
      uIntensity: { value: 1 },
    },
    vertexShader: `
      uniform float uTime;
      varying vec3 vPosition;
      varying vec3 vNormal;
      void main() {
        vPosition = position;
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uTime;
      uniform float uIntensity;
      varying vec3 vPosition;
      varying vec3 vNormal;
      void main() {
        vec3 normal = normalize(vNormal);
        float rim = pow(1.0 - abs(normal.z), 2.25);
        float latitude = sin((vPosition.y + uTime * 0.24) * 32.0);
        float longitude = sin((atan(vPosition.z, vPosition.x) + uTime * 0.55) * 18.0);
        float sparkle = smoothstep(0.88, 1.0, latitude * longitude);
        float scan = smoothstep(0.035, 0.0, abs(fract(vPosition.y * 2.7 + uTime * 0.45) - 0.5));
        vec3 hot = mix(uColor, vec3(1.0), 0.72);
        vec3 color = uColor * (0.42 + uIntensity * 0.32) + hot * (sparkle * 1.35 + rim * 1.05 + scan * 0.42) * uIntensity;
        float alpha = 0.22 + uIntensity * 0.68 + rim * 0.1 * uIntensity;
        gl_FragColor = vec4(color, alpha);
      }
    `,
    transparent: true,
    depthWrite: true,
    blending: THREE.NormalBlending,
  });
}

// ── Canvas 文字 Sprite（参照 JobCloud） ──
function addTextLabel(scene, text, x, y, z, color, fontSize = 44, scale = [8, 2, 1]) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = `600 ${fontSize}px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.96,
    depthTest: false,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const sprite = new THREE.Sprite(material);
  sprite.position.set(x, y, z);
  sprite.scale.set(scale[0], scale[1], scale[2]);
  sprite.renderOrder = 10;
  scene.add(sprite);
  return sprite;
}

// ── 参考环（带动画旋转） ──
function addReferenceRings(scene) {
  const rings = [];
  const levels = [
    { y: 14, color: 0x2e6b7c, radius: 28, segments: 128 },
    { y: 0, color: 0x34445e, radius: 24, segments: 96 },
    { y: -14, color: 0x665d45, radius: 28, segments: 128 },
  ];
  for (const level of levels) {
    const curve = new THREE.EllipseCurve(0, 0, level.radius, level.radius, 0, Math.PI * 2);
    const points = curve.getPoints(level.segments).map((p) => new THREE.Vector3(p.x, level.y, p.y));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color: level.color, transparent: true, opacity: 0.22 });
    const line = new THREE.Line(geometry, material);
    scene.add(line);
    rings.push(line);
  }
  return rings;
}

// ── 连线颜色 ──
function edgeColor(type) {
  switch (type) {
    case "REQUIRES_SKILL": return 0x4dd6ff;
    case "HAS_KNOWLEDGE": return 0xb37feb;
    case "HAS_ABILITY": return 0xfaad14;
    default: return 0x30363d;
  }
}

// ── 更新固定 HTML 标签位置（参照 JobCloud 的 updateFixedLabels） ──
function updateFixedLabels(labelLayer, labelData, objectMap, camera, renderer) {
  if (!labelLayer || labelData.length === 0) return;
  const width = renderer.domElement.clientWidth;
  const height = renderer.domElement.clientHeight;
  const projected = new THREE.Vector3();

  for (let i = 0; i < labelData.length; i++) {
    const item = labelData[i];
    const mesh = objectMap.get(item.id);
    const el = labelLayer.querySelector(`[data-node-id="${CSS.escape(item.id)}"]`);
    if (!mesh || !el || !mesh.visible) {
      if (el) el.style.opacity = "0";
      continue;
    }

    projected.copy(mesh.position);
    projected.y += mesh.scale.y * 1.35;
    projected.project(camera);
    const visible = projected.z > -1 && projected.z < 1;
    const x = (projected.x * 0.5 + 0.5) * width;
    const y = (-projected.y * 0.5 + 0.5) * height;
    const stagger = (i % 4) * 16;
    el.style.opacity = visible ? "1" : "0";
    el.style.transform = `translate(${x + 18}px, ${y - 10 + stagger}px)`;
  }
}

/**
 * JobGalaxy 组件 - 3D 岗位技能星图（参照 JobCloud 设计）
 */
export default function JobGalaxy({ graphNodes = [], graphEdges = [], height = 500 }) {
  const mountRef = useRef(null);
  const fixedLabelsRef = useRef(null);
  const fixedLabelDataRef = useRef([]);
  const objectsRef = useRef(new Map());
  const linesRef = useRef([]);
  const ringsRef = useRef([]);
  const selectedRef = useRef(null);
  const graphDataRef = useRef(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [tooltip, setTooltip] = useState(null);

  const graphData = useMemo(() => {
    if (!graphNodes.length) return null;
    return buildGraphData(graphNodes, graphEdges);
  }, [graphNodes, graphEdges]);

  useEffect(() => {
    selectedRef.current = selectedNode;
  }, [selectedNode]);

  useEffect(() => {
    graphDataRef.current = graphData;
  }, [graphData]);

  // ── 更新固定标签（当选中节点变化时） ──
  useEffect(() => {
    const layer = fixedLabelsRef.current;
    if (!layer || !graphData) return;

    const node = selectedNode ? graphData.nodeMap.get(selectedNode.id) : null;
    let labelData = [];

    if (node?.type === "job") {
      // 选中岗位时，显示其关联技能的固定标签
      const skillIds = graphData.jobSkillsMap.get(node.id) || [];
      labelData = skillIds
        .map((id) => graphData.nodeMap.get(id))
        .filter(Boolean)
        .map((skill) => ({ id: skill.id, type: "skill", label: skill.name }));
    }

    fixedLabelDataRef.current = labelData;
    layer.replaceChildren(
      ...labelData.map((item) => {
        const el = document.createElement("div");
        el.className = `galaxy-fixed-label ${item.type}`;
        el.dataset.nodeId = item.id;

        const typeSpan = document.createElement("span");
        typeSpan.textContent = TYPE_LABELS[item.type] || item.type;
        const labelStrong = document.createElement("strong");
        labelStrong.textContent = item.label;
        el.append(typeSpan, labelStrong);
        return el;
      }),
    );
  }, [graphData, selectedNode]);

  // ── 单一 useEffect：场景 + 渲染 + 动画 ──
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !graphData) return undefined;

    // 场景
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x071018);
    scene.fog = new THREE.Fog(0x071018, 80, 180);

    // 相机
    const aspect = mount.clientWidth / mount.clientHeight;
    const camera = new THREE.PerspectiveCamera(48, aspect, 0.1, 320);
    camera.position.set(0, 18, Math.max(52, 52 / aspect));

    // 渲染器
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    mount.appendChild(renderer.domElement);

    // 控制器
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 20;
    controls.maxDistance = 120;
    controls.target.set(0, 0, 0);
    controls.maxPolarAngle = Math.PI * 0.85;

    // 光照
    scene.add(new THREE.AmbientLight(0xffffff, 0.35));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.3);
    keyLight.position.set(20, 40, 30);
    scene.add(keyLight);
    const fillLight = new THREE.PointLight(0x4dd6ff, 1.5, 120);
    fillLight.position.set(-30, 15, 35);
    scene.add(fillLight);
    const backLight = new THREE.PointLight(0xb37feb, 0.8, 80);
    backLight.position.set(20, -10, -30);
    scene.add(backLight);

    // 参考环
    const rings = addReferenceRings(scene);
    ringsRef.current = rings;

    // 星点背景
    const starsGeo = new THREE.BufferGeometry();
    const starsCount = 800;
    const starPos = new Float32Array(starsCount * 3);
    for (let i = 0; i < starsCount; i++) {
      starPos[i * 3] = seededOffset(`star-x-${i}`, i, 200);
      starPos[i * 3 + 1] = seededOffset(`star-y-${i}`, i, 200);
      starPos[i * 3 + 2] = seededOffset(`star-z-${i}`, i, 200);
    }
    starsGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    const starsMat = new THREE.PointsMaterial({
      color: 0x4dd6ff,
      size: 0.12,
      transparent: true,
      opacity: 0.5,
      sizeAttenuation: true,
    });
    scene.add(new THREE.Points(starsGeo, starsMat));

    // ── 创建节点（参照 JobCloud 的 createGraphObjects） ──
    const objectMap = new Map();
    const lineList = [];
    const sphere = new THREE.SphereGeometry(1, 24, 16);
    const categoryLabels = [];

    for (const node of graphData.nodes) {
      const style = TYPE_COLORS[node.type] || TYPE_COLORS.skill;
      // 技能节点使用热度颜色
      const nodeColor = node.heatColor || style.main;
      const nodeHex = node.heatColor ? new THREE.Color(node.heatColor).getHex() : style.hex;

      const material = new THREE.MeshStandardMaterial({
        color: nodeHex,
        emissive: style.emissive,
        roughness: 0.38,
        metalness: node.type === "job" ? 0.2 : 0.05,
        transparent: true,
        opacity: style.opacity,
      });
      const highlightMat = createParticleSphereMaterial(nodeHex);

      const mesh = new THREE.Mesh(sphere, material);
      mesh.position.set(node.x, node.y, node.z);
      mesh.scale.setScalar(node.radius);
      const baseColor = material.color.clone();
      mesh.userData = {
        node,
        baseMaterial: material,
        highlightMaterial: highlightMat,
        baseColor,
        baseOpacity: style.opacity,
        targetRadius: node.radius,
        phase: ((indexHash(node.id) % 1000) / 1000) * Math.PI * 2,
      };
      scene.add(mesh);
      objectMap.set(node.id, mesh);

      // 只给岗位节点加 Canvas 文字标签（参照 JobCloud：category 节点加标签）
      if (node.type === "job") {
        const label = addTextLabel(scene, node.name, node.x, node.y + node.radius + 1.35, node.z, nodeColor, 48, [10, 2.5, 1]);
        categoryLabels.push({ sprite: label, mesh });
      }
    }

    // ── 创建连线 ──
    for (const link of graphData.links) {
      const source = objectMap.get(link.source);
      const target = objectMap.get(link.target);
      if (!source || !target) continue;

      const geometry = new THREE.BufferGeometry().setFromPoints([source.position, target.position]);
      const material = new THREE.LineBasicMaterial({
        color: edgeColor(link.type),
        transparent: true,
        opacity: 0.18,
      });
      const line = new THREE.Line(geometry, material);
      line.userData = { link, source, target, baseOpacity: 0.18 };
      scene.add(line);
      lineList.push(line);
    }

    objectsRef.current = objectMap;
    linesRef.current = lineList;

    // ── 高亮逻辑（参照 JobCloud 的 applyHighlight） ──
    const applyHighlight = (node) => {
      const neighbors = new Set();
      const neighborLinks = new Set();

      for (const line of lineList) {
        const { link } = line.userData;
        if (link.source === node.id || link.target === node.id) {
          neighbors.add(link.source);
          neighbors.add(link.target);
          neighborLinks.add(`${link.source}->${link.target}`);
        }
      }
      // 如果选中的是岗位，也高亮其关联技能
      if (node.type === "job") {
        const skillIds = graphData.jobSkillsMap.get(node.id) || [];
        skillIds.forEach((id) => neighbors.add(id));
      }
      neighbors.add(node.id);

      for (const [id, mesh] of objectMap.entries()) {
        const isActive = neighbors.has(id);
        const nodeType = mesh.userData.node.type;

        if (isActive) {
          mesh.material = mesh.userData.highlightMaterial;
          mesh.userData.highlightMaterial.uniforms.uIntensity.value = 1;
          mesh.userData.targetRadius = mesh.userData.node.radius * 1.4;
        } else {
          mesh.material = mesh.userData.baseMaterial;
          mesh.userData.baseMaterial.emissiveIntensity = 0.08;
          mesh.userData.baseMaterial.opacity = nodeType === "job" ? 0.46 : 0.12;
          mesh.userData.targetRadius = mesh.userData.node.radius * 0.7;
        }
      }

      for (const line of lineList) {
        const { link } = line.userData;
        const active = link.source === node.id || link.target === node.id;
        line.visible = active;
        line.material.opacity = active ? 0.58 : 0.035;
      }
    };

    const resetHighlight = () => {
      for (const [, mesh] of objectMap.entries()) {
        mesh.material = mesh.userData.baseMaterial;
        mesh.userData.baseMaterial.emissiveIntensity = 0.35;
        mesh.userData.baseMaterial.opacity = mesh.userData.baseOpacity;
        mesh.userData.targetRadius = mesh.userData.node.radius;
      }
      for (const line of lineList) {
        line.visible = true;
        line.material.opacity = line.userData.baseOpacity;
      }
    };

    // ── 交互 ──
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let hovered = null;

    const updatePointer = (e) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    };

    const pick = (e) => {
      updatePointer(e);
      raycaster.setFromCamera(pointer, camera);
      const meshes = [...objectMap.values()].filter((m) => m.visible);
      const hits = raycaster.intersectObjects(meshes, false);
      return hits[0]?.object || null;
    };

    const onMove = (e) => {
      const hit = pick(e);
      if (hit !== hovered) {
        hovered = hit;
        renderer.domElement.style.cursor = hit ? "pointer" : "grab";
      }
      if (hit) {
        const node = hit.userData.node;
        setTooltip({
          x: e.clientX,
          y: e.clientY,
          label: node.name,
          type: node.type,
          typeLabel: TYPE_LABELS[node.type] || node.type,
        });
      } else {
        setTooltip(null);
      }
    };

    const onClick = (e) => {
      const hit = pick(e);
      if (hit) {
        const node = hit.userData.node;
        setSelectedNode(node);
        applyHighlight(node);
        message.info(`选中：${node.name}`);
      } else {
        setSelectedNode(null);
        resetHighlight();
      }
    };

    const onLeave = () => { hovered = null; setTooltip(null); };

    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("click", onClick);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    const onResize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    // ── 动画循环（参照 JobCloud 的 animate，使用 lerp 平滑过渡） ──
    let frameId = 0;
    const animate = () => {
      const t = performance.now() / 1000;

      // 节点浮动 + 平滑缩放（参照 JobCloud）
      for (const mesh of objectMap.values()) {
        const { node, phase, targetRadius } = mesh.userData;
        // 平滑位置过渡
        const targetY = node.y + Math.sin(t * 0.8 + phase) * 0.18;
        mesh.position.y = THREE.MathUtils.lerp(mesh.position.y, targetY, 0.085);
        // 平滑缩放过渡
        const currentScale = mesh.scale.x;
        if (Math.abs(currentScale - targetRadius) > 0.01) {
          mesh.scale.setScalar(THREE.MathUtils.lerp(currentScale, targetRadius, 0.12));
        }
        // 更新 shader 时间
        if (mesh.material.uniforms?.uTime) {
          mesh.material.uniforms.uTime.value = t;
        }
      }

      // Canvas 文字标签跟随（参照 JobCloud 的 updateCategoryLabel）
      for (const { sprite, mesh } of categoryLabels) {
        sprite.position.set(mesh.position.x, mesh.position.y + mesh.scale.y + 1.35, mesh.position.z);
        sprite.visible = mesh.visible !== false;
      }

      // 连线更新（参照 JobCloud 的 updateLinePositions）
      for (const line of lineList) {
        const { source, target } = line.userData;
        const positions = line.geometry.attributes.position.array;
        positions[0] = source.position.x;
        positions[1] = source.position.y;
        positions[2] = source.position.z;
        positions[3] = target.position.x;
        positions[4] = target.position.y;
        positions[5] = target.position.z;
        line.geometry.attributes.position.needsUpdate = true;
      }

      // 固定 HTML 标签跟随（参照 JobCloud 的 updateFixedLabels）
      updateFixedLabels(fixedLabelsRef.current, fixedLabelDataRef.current, objectMap, camera, renderer);

      // 参考环缓慢旋转
      for (const ring of rings) {
        ring.rotation.y = t * 0.03;
      }

      controls.update();
      renderer.render(scene, camera);
      frameId = requestAnimationFrame(animate);
    };
    animate();

    // ── 清理 ──
    return () => {
      cancelAnimationFrame(frameId);
      window.removeEventListener("resize", onResize);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      controls.dispose();
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      scene.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (obj.material) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          for (const m of mats) { if (m.map) m.map.dispose(); m.dispose(); }
        }
      });
      objectMap.clear();
      linesRef.current = [];
      ringsRef.current = [];
    };
  }, [graphData]);

  // ── 重置 ──
  const handleReset = () => {
    setSelectedNode(null);
    setTooltip(null);
    for (const [, mesh] of objectsRef.current.entries()) {
      mesh.material = mesh.userData.baseMaterial;
      mesh.userData.baseMaterial.emissiveIntensity = 0.35;
      mesh.userData.baseMaterial.opacity = mesh.userData.baseOpacity;
      mesh.userData.targetRadius = mesh.userData.node.radius;
    }
    for (const line of linesRef.current) {
      line.visible = true;
      line.material.opacity = line.userData.baseOpacity;
    }
  };

  // 无数据
  if (!graphNodes.length) {
    return (
      <Card
        title={<Space><NodeIndexOutlined /><span>3D 岗位技能星图</span></Space>}
        style={{ height }}
        styles={{ body: { display: "flex", alignItems: "center", justifyContent: "center" } }}
      >
        <span style={{ color: "var(--text-secondary)" }}>暂无图谱数据，请先构建知识图谱</span>
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <NodeIndexOutlined />
          <span>3D 岗位技能星图</span>
          {graphData && <Tag color="blue">{graphData.nodes.length} 节点</Tag>}
          {graphData && <Tag color="purple">{graphData.links.length} 关系</Tag>}
        </Space>
      }
      extra={
        <button
          onClick={handleReset}
          style={{
            background: "transparent",
            border: "1px solid #30363d",
            color: "var(--text-secondary)",
            padding: "3px 12px",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 12,
            transition: "all 0.2s",
          }}
          onMouseEnter={(e) => { e.target.style.borderColor = "#4dd6ff"; e.target.style.color = "#4dd6ff"; }}
          onMouseLeave={(e) => { e.target.style.borderColor = "#30363d"; e.target.style.color = "#8b949e"; }}
        >
          重置视角
        </button>
      }
      style={{ height }}
      styles={{ body: { padding: 0, height: "calc(100% - 57px)", position: "relative" } }}
    >
      <div ref={mountRef} style={{ width: "100%", height: "100%", cursor: "grab" }}>
        {/* 图例 */}
        <div
          style={{
            position: "absolute", bottom: 16, left: 16, zIndex: 10,
            background: "rgba(7, 16, 24, 0.88)", padding: "10px 14px", borderRadius: 10,
            border: "1px solid rgba(77, 214, 255, 0.12)", backdropFilter: "blur(12px)",
          }}
        >
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>图例</div>
          <Space size={8} wrap>
            {[
              { label: "岗位", color: "#4dd6ff", shape: "◆" },
              { label: "技能", color: "#52c41a", shape: "●" },
              { label: "知识", color: "#b37feb", shape: "●" },
              { label: "能力", color: "#faad14", shape: "●" },
            ].map((item) => (
              <span key={item.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: item.color }}>
                <span style={{ fontSize: 8 }}>{item.shape}</span>
                {item.label}
              </span>
            ))}
          </Space>
        </div>

        {/* 技能热度图例（参照 JobCloud 的 skill-heat-legend） */}
        <div
          style={{
            position: "absolute", bottom: 70, left: 16, zIndex: 10,
            background: "rgba(7, 16, 24, 0.88)", padding: "8px 12px", borderRadius: 10,
            border: "1px solid rgba(77, 214, 255, 0.12)", backdropFilter: "blur(12px)",
            display: "flex", gap: 8, alignItems: "center",
          }}
        >
          <span style={{ fontSize: 11, color: "var(--text-secondary)", fontWeight: 500 }}>技能热度</span>
          {[
            { label: "低频", color: "#6ee7a8" },
            { label: "中低", color: "#d6e85f" },
            { label: "中高", color: "#ffb347" },
            { label: "高频", color: "#ff5f57" },
          ].map((item) => (
            <span key={item.label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: item.color }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: item.color,
                boxShadow: `0 0 8px ${item.color}80`,
              }} />
              {item.label}
            </span>
          ))}
        </div>

        {/* 固定 HTML 标签层（参照 JobCloud 的 fixed-label-layer） */}
        <div
          ref={fixedLabelsRef}
          style={{
            position: "absolute", inset: 0, zIndex: 4,
            pointerEvents: "none",
          }}
        />

        {/* Tooltip */}
        {tooltip && (
          <div
            style={{
              position: "fixed", left: tooltip.x + 14, top: tooltip.y + 14, zIndex: 100,
              background: "rgba(7, 16, 24, 0.95)", padding: "8px 14px", borderRadius: 8,
              border: "1px solid rgba(77, 214, 255, 0.2)", color: "#e6edf3", fontSize: 13,
              pointerEvents: "none", backdropFilter: "blur(12px)",
              boxShadow: "0 4px 20px rgba(0,0,0,0.5)",
            }}
          >
            <span style={{
              display: "inline-block", width: 8, height: 8, borderRadius: "50%",
              background: TYPE_COLORS[tooltip.type]?.main || "#8b949e", marginRight: 8,
              boxShadow: `0 0 8px ${TYPE_COLORS[tooltip.type]?.main || "#8b949e"}60`,
            }} />
            <span style={{ marginRight: 8 }}>{tooltip.label}</span>
            <span style={{ fontSize: 11, color: TYPE_COLORS[tooltip.type]?.main || "#8b949e", opacity: 0.8 }}>
              [{tooltip.typeLabel}]
            </span>
          </div>
        )}

        {/* 选中节点信息面板 */}
        {selectedNode && (
          <div
            style={{
              position: "absolute", top: 16, right: 16, zIndex: 10,
              background: "rgba(7, 16, 24, 0.94)", padding: 16, borderRadius: 12,
              border: "1px solid rgba(77, 214, 255, 0.2)", maxWidth: 280,
              backdropFilter: "blur(16px)", boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div style={{
                width: 14, height: 14, borderRadius: "50%",
                background: TYPE_COLORS[selectedNode.type]?.main || "#8b949e",
                boxShadow: `0 0 12px ${TYPE_COLORS[selectedNode.type]?.main || "#8b949e"}80`,
              }} />
              <Text strong style={{ color: "#e6edf3", fontSize: 16 }}>{selectedNode.name}</Text>
            </div>
            <Space size={6} wrap>
              <Tag color={
                selectedNode.type === "job" ? "blue" :
                selectedNode.type === "skill" ? "green" :
                selectedNode.type === "knowledge" ? "purple" : "orange"
              }>
                {selectedNode.label}
              </Tag>
              {selectedNode.degree > 0 && (
                <Tag color="cyan">{selectedNode.degree} 条关系</Tag>
              )}
            </Space>
            {/* 选中岗位时显示关联技能列表 */}
            {selectedNode.type === "job" && graphData && (
              <div style={{ marginTop: 12, borderTop: "1px solid rgba(77, 214, 255, 0.12)", paddingTop: 10 }}>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 6 }}>关联技能</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {(graphData.jobSkillsMap.get(selectedNode.id) || [])
                    .map((id) => graphData.nodeMap.get(id))
                    .filter(Boolean)
                    .map((skill) => (
                      <span key={skill.id} style={{
                        display: "inline-flex", alignItems: "center", gap: 4,
                        padding: "3px 8px", borderRadius: 999,
                        border: "1px solid rgba(82, 196, 26, 0.22)",
                        background: "rgba(82, 196, 26, 0.08)",
                        color: "#e9fbf9", fontSize: 11,
                      }}>
                        {skill.name}
                      </span>
                    ))
                  }
                </div>
              </div>
            )}
          </div>
        )}

        {/* 提示 */}
        <div style={{ position: "absolute", bottom: 16, right: 16, zIndex: 10, fontSize: 11, color: "#30363d" }}>
          拖拽旋转 · 滚轮缩放 · 点击节点
        </div>
      </div>

      {/* 固定标签样式 */}
      <style>{`
        .galaxy-fixed-label {
          position: absolute;
          left: 0;
          top: 0;
          max-width: 180px;
          padding: 7px 9px;
          border: 1px solid rgba(255, 255, 255, 0.14);
          border-radius: 8px;
          background: rgba(7, 16, 24, 0.78);
          box-shadow: 0 14px 34px rgba(0, 0, 0, 0.34);
          color: #f7fbff;
          opacity: 0;
          transform: translate(-9999px, -9999px);
          transition: opacity 140ms ease;
          backdrop-filter: blur(12px);
          pointer-events: none;
        }
        .galaxy-fixed-label span {
          display: block;
          margin-bottom: 4px;
          color: #52c41a;
          font-size: 12px;
          font-weight: 800;
        }
        .galaxy-fixed-label strong {
          display: block;
          overflow: hidden;
          font-size: 14px;
          line-height: 1.35;
          text-overflow: ellipsis;
        }
      `}</style>
    </Card>
  );
}
