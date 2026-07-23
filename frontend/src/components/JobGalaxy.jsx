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

const NODE_TYPE_MAP = {
  Job: "job",
  Skill: "skill",
  Knowledge: "knowledge",
  AbilityEntity: "ability",
};

// ── 从后端图谱数据构建节点和边 ──
function buildGraphData(graphNodes, graphEdges) {
  const nodes = [];
  const links = [];
  const nodeMap = new Map();
  const degreeMap = new Map();

  const filtered = graphNodes.filter((n) => n.label !== "Evidence" && n.label !== "Company");

  // 统计度数
  for (const edge of graphEdges) {
    degreeMap.set(edge.source_id, (degreeMap.get(edge.source_id) || 0) + 1);
    degreeMap.set(edge.target_id, (degreeMap.get(edge.target_id) || 0) + 1);
  }

  const maxDegree = Math.max(...degreeMap.values(), 1);

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

    nodes.push({
      id: nodeId,
      name,
      type,
      radius,
      degree,
      label: node.label,
      properties: node.properties,
      x: (Math.random() - 0.5) * 40,
      y: y + (Math.random() - 0.5) * 6,
      z: (Math.random() - 0.5) * 40,
      index,
    });
    nodeMap.set(nodeId, nodes[nodes.length - 1]);
  });

  // 力导向排斥（简单版）
  repelNodes(nodes.filter((n) => n.type === "job"), 5, 20);
  repelNodes(nodes.filter((n) => n.type === "skill"), 2.5, 15);
  repelNodes(nodes.filter((n) => n.type === "knowledge" || n.type === "ability"), 2, 10);

  const keyRelations = ["REQUIRES_SKILL", "HAS_KNOWLEDGE", "HAS_ABILITY"];
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

  return { nodes, links };
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

// ── Canvas 文字 Sprite ──
function addTextLabel(scene, text, x, y, z, color) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = "600 44px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = color;
  ctx.shadowColor = color;
  ctx.shadowBlur = 12;
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.9,
    depthTest: false,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.position.set(x, y, z);
  sprite.scale.set(8, 2, 1);
  sprite.renderOrder = 10;
  scene.add(sprite);
  return sprite;
}

// ── 参考环（带动画旋转） ──
function addReferenceRings(scene) {
  const rings = [];
  const levels = [
    { y: 14, color: 0x1a3a4a, radius: 28, segments: 128 },
    { y: 0, color: 0x1a2a3a, radius: 24, segments: 96 },
    { y: -14, color: 0x2a2a1a, radius: 28, segments: 128 },
  ];
  for (const level of levels) {
    const curve = new THREE.EllipseCurve(0, 0, level.radius, level.radius, 0, Math.PI * 2);
    const points = curve.getPoints(level.segments).map((p) => new THREE.Vector3(p.x, level.y, p.y));
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color: level.color, transparent: true, opacity: 0.35 });
    const line = new THREE.Line(geometry, material);
    scene.add(line);
    rings.push(line);

    // 内圈虚线
    const innerCurve = new THREE.EllipseCurve(0, 0, level.radius * 0.6, level.radius * 0.6, 0, Math.PI * 2);
    const innerPoints = innerCurve.getPoints(64).map((p) => new THREE.Vector3(p.x, level.y, p.y));
    const innerGeo = new THREE.BufferGeometry().setFromPoints(innerPoints);
    const innerMat = new THREE.LineDashedMaterial({
      color: level.color,
      transparent: true,
      opacity: 0.15,
      dashSize: 1,
      gapSize: 1.5,
    });
    const innerLine = new THREE.Line(innerGeo, innerMat);
    innerLine.computeLineDistances();
    scene.add(innerLine);
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

/**
 * JobGalaxy 组件 - 3D 岗位技能星图
 */
export default function JobGalaxy({ graphNodes = [], graphEdges = [], height = 500 }) {
  const mountRef = useRef(null);
  const objectsRef = useRef(new Map());
  const linesRef = useRef([]);
  const ringsRef = useRef([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [tooltip, setTooltip] = useState(null);

  const graphData = useMemo(() => {
    if (!graphNodes.length) return null;
    return buildGraphData(graphNodes, graphEdges);
  }, [graphNodes, graphEdges]);

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
    const starSizes = new Float32Array(starsCount);
    for (let i = 0; i < starsCount; i++) {
      starPos[i * 3] = (Math.random() - 0.5) * 200;
      starPos[i * 3 + 1] = (Math.random() - 0.5) * 200;
      starPos[i * 3 + 2] = (Math.random() - 0.5) * 200;
      starSizes[i] = Math.random() * 0.15 + 0.03;
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

    // ── 创建节点 ──
    const objectMap = new Map();
    const lineList = [];
    const sphere = new THREE.SphereGeometry(1, 32, 24);
    const categoryLabels = [];

    for (const node of graphData.nodes) {
      const style = TYPE_COLORS[node.type] || TYPE_COLORS.skill;
      // 基础材质
      const baseMaterial = new THREE.MeshStandardMaterial({
        color: style.hex,
        emissive: style.emissive,
        roughness: 0.35,
        metalness: node.type === "job" ? 0.15 : 0.05,
        transparent: true,
        opacity: style.opacity,
      });
      // 高亮材质（粒子发光）
      const highlightMat = createParticleSphereMaterial(style.hex);

      const mesh = new THREE.Mesh(sphere, baseMaterial);
      mesh.position.set(node.x, node.y, node.z);
      mesh.scale.setScalar(node.radius);
      mesh.userData = {
        node,
        baseMaterial,
        highlightMaterial: highlightMat,
        baseColor: new THREE.Color(style.hex),
        baseOpacity: style.opacity,
        targetRadius: node.radius,
        phase: Math.random() * Math.PI * 2,
      };
      scene.add(mesh);
      objectMap.set(node.id, mesh);

      // 岗位节点加文字标签
      if (node.type === "job") {
        const label = addTextLabel(scene, node.name, node.x, node.y + node.radius + 1.5, node.z, style.main);
        categoryLabels.push({ sprite: label, mesh });
      }
    }

    // ── 创建连线（带弧度） ──
    for (const link of graphData.links) {
      const source = objectMap.get(link.source);
      const target = objectMap.get(link.target);
      if (!source || !target) continue;

      // 带弧度的连线
      const mid = new THREE.Vector3().lerpVectors(source.position, target.position, 0.5);
      mid.y += 1.5;
      const curve = new THREE.QuadraticBezierCurve3(source.position, mid, target.position);
      const points = curve.getPoints(20);
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material = new THREE.LineBasicMaterial({
        color: edgeColor(link.type),
        transparent: true,
        opacity: 0.2,
      });
      const line = new THREE.Line(geometry, material);
      line.userData = { link, source, target, baseOpacity: 0.2, curve, isCurve: true };
      scene.add(line);
      lineList.push(line);
    }

    objectsRef.current = objectMap;
    linesRef.current = lineList;

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

    const highlightNode = (node) => {
      const neighbors = new Set();
      for (const line of lineList) {
        if (line.userData.link.source === node.id) neighbors.add(line.userData.link.target);
        if (line.userData.link.target === node.id) neighbors.add(line.userData.link.source);
      }
      neighbors.add(node.id);

      for (const [id, mesh] of objectMap.entries()) {
        if (neighbors.has(id)) {
          mesh.material = mesh.userData.highlightMaterial;
          mesh.userData.highlightMaterial.uniforms.uIntensity.value = 1;
          mesh.scale.setScalar(mesh.userData.targetRadius * 1.4);
        } else {
          mesh.material = mesh.userData.baseMaterial;
          mesh.userData.baseMaterial.emissiveIntensity = 0.08;
          mesh.userData.baseMaterial.opacity = 0.15;
          mesh.scale.setScalar(mesh.userData.targetRadius * 0.7);
        }
      }
      for (const line of lineList) {
        const active = line.userData.link.source === node.id || line.userData.link.target === node.id;
        line.visible = active;
        line.material.opacity = active ? 0.6 : 0.02;
      }
    };

    const resetHighlight = () => {
      for (const [, mesh] of objectMap.entries()) {
        mesh.material = mesh.userData.baseMaterial;
        mesh.userData.baseMaterial.emissiveIntensity = 0.35;
        mesh.userData.baseMaterial.opacity = mesh.userData.baseOpacity;
        mesh.scale.setScalar(mesh.userData.targetRadius);
      }
      for (const line of lineList) {
        line.visible = true;
        line.material.opacity = line.userData.baseOpacity;
      }
    };

    const onMove = (e) => {
      const hit = pick(e);
      if (hit !== hovered) {
        hovered = hit;
        renderer.domElement.style.cursor = hit ? "pointer" : "grab";
      }
      if (hit) {
        setTooltip({ x: e.clientX, y: e.clientY, label: hit.userData.node.name, type: hit.userData.node.type });
      } else {
        setTooltip(null);
      }
    };

    const onClick = (e) => {
      const hit = pick(e);
      if (hit) {
        const node = hit.userData.node;
        setSelectedNode(node);
        highlightNode(node);
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

    // ── 动画循环 ──
    let frameId = 0;
    const animate = () => {
      const t = performance.now() / 1000;

      // 节点浮动
      for (const mesh of objectMap.values()) {
        const { node, phase, targetRadius } = mesh.userData;
        mesh.position.y = node.y + Math.sin(t * 0.7 + phase) * 0.25;
        // 平滑缩放
        const cs = mesh.scale.x;
        const ts = targetRadius;
        if (Math.abs(cs - ts) > 0.01) {
          // 只在未选中时平滑回弹
        }
        // 更新 shader 时间
        if (mesh.material.uniforms?.uTime) {
          mesh.material.uniforms.uTime.value = t;
        }
      }

      // 文字标签跟随
      for (const { sprite, mesh } of categoryLabels) {
        sprite.position.set(mesh.position.x, mesh.position.y + mesh.scale.y + 1.5, mesh.position.z);
        sprite.visible = mesh.visible;
      }

      // 连线更新（弧线跟随节点浮动）
      for (const line of lineList) {
        const { source, target, curve } = line.userData;
        if (line.userData.isCurve && curve) {
          const sp = source.position, tp = target.position;
          curve.v0.copy(sp);
          curve.v2.copy(tp);
          curve.v1.set((sp.x + tp.x) / 2, (sp.y + tp.y) / 2 + 1.5, (sp.z + tp.z) / 2);
          const pts = curve.getPoints(20);
          line.geometry.setFromPoints(pts);
        }
      }

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
      mesh.scale.setScalar(mesh.userData.targetRadius);
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
        <span style={{ color: "#8b949e" }}>暂无图谱数据，请先构建知识图谱</span>
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
            color: "#8b949e",
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
          <div style={{ fontSize: 11, color: "#8b949e", marginBottom: 6, fontWeight: 500 }}>图例</div>
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
            {tooltip.label}
          </div>
        )}

        {/* 选中节点 */}
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
          </div>
        )}

        {/* 提示 */}
        <div style={{ position: "absolute", bottom: 16, right: 16, zIndex: 10, fontSize: 11, color: "#30363d" }}>
          拖拽旋转 · 滚轮缩放 · 点击节点
        </div>
      </div>
    </Card>
  );
}
