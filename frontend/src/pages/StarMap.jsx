import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import { Typography, Tag, Button, Input, message, Divider } from "antd";
import {
  StarOutlined,
  PlusOutlined,
  EnvironmentOutlined,
  DollarOutlined,
  BookOutlined,
  ThunderboltOutlined,
  AimOutlined,
} from "@ant-design/icons";
import * as THREE from "three";
import ReactECharts from "echarts-for-react";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  REPRESENTATIVE_JDS,
  JD_CATEGORIES,
  classifyJD,
  extractSkillsFromText,
} from "../utils/representativeJDs";
import "../styles/starmap.css";

const { Title, Paragraph } = Typography;
const { TextArea } = Input;

// ── 技能热度颜色梯度 ──
const SKILL_HEAT = ["#6ee7a8", "#d6e85f", "#ffb347", "#ff5f57"];

function heatColor(count, max) {
  if (max <= 0) return SKILL_HEAT[0];
  const ratio = Math.min(count / max, 1);
  const pos = ratio * (SKILL_HEAT.length - 1);
  const idx = Math.floor(pos);
  const next = Math.min(idx + 1, SKILL_HEAT.length - 1);
  const t = pos - idx;
  const ah = parseInt(SKILL_HEAT[idx].slice(1), 16);
  const bh = parseInt(SKILL_HEAT[next].slice(1), 16);
  const r = Math.round(((ah >> 16) & 0xff) * (1 - t) + ((bh >> 16) & 0xff) * t);
  const g = Math.round(((ah >> 8) & 0xff) * (1 - t) + ((bh >> 8) & 0xff) * t);
  const b = Math.round((ah & 0xff) * (1 - t) + (bh & 0xff) * t);
  return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`;
}

// ── 发光粒子球体 Shader（参照 JobCloud） ──
function createGlowMaterial(color) {
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
        vec3 c = uColor * (0.42 + uIntensity * 0.32) + hot * (sparkle * 1.35 + rim * 1.05 + scan * 0.42) * uIntensity;
        float alpha = 0.22 + uIntensity * 0.68 + rim * 0.1 * uIntensity;
        gl_FragColor = vec4(c, alpha);
      }
    `,
    transparent: true,
    depthWrite: true,
    blending: THREE.NormalBlending,
  });
}

// ── Canvas 文字 Sprite ──
function createTextSprite(text, x, y, z, color, fontSize = 40, scale = [8, 2, 1]) {
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
  return sprite;
}

// ── 力导向排斥 ──
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

// ── 布局：为 JD 和技能计算 3D 位置 ──
function layoutNodes(jdNodes, skillNodes, categoryKeys) {
  const catCount = categoryKeys.length;
  const catAngleStep = (Math.PI * 2) / catCount;

  // 类别节点：上层圆环
  const catPositions = {};
  categoryKeys.forEach((key, i) => {
    const angle = catAngleStep * i - Math.PI / 2;
    catPositions[key] = {
      x: Math.cos(angle) * 30,
      y: 16,
      z: Math.sin(angle) * 30,
    };
  });

  // JD 节点：中层，靠近所属类别
  const jdByCategory = {};
  for (const jd of jdNodes) {
    if (!jdByCategory[jd.category]) jdByCategory[jd.category] = [];
    jdByCategory[jd.category].push(jd);
  }

  for (const [cat, jds] of Object.entries(jdByCategory)) {
    const center = catPositions[cat] || { x: 0, y: 0, z: 0 };
    const spread = 12;
    jds.forEach((jd, i) => {
      const angle = (Math.PI * 2 * i) / jds.length + Math.random() * 0.3;
      const r = 6 + Math.random() * spread;
      jd.x = center.x + Math.cos(angle) * r;
      jd.y = 0 + (Math.random() - 0.5) * 5;
      jd.z = center.z + Math.sin(angle) * r;
    });
  }

  // 排斥 JD 节点避免重叠
  repelNodes(jdNodes, 6, 24);

  // 技能节点：下层，按频率排列
  const maxCount = Math.max(...skillNodes.map((s) => s.count), 1);
  skillNodes.sort((a, b) => b.count - a.count);
  const ringCount = 3;
  skillNodes.forEach((skill, i) => {
    const ring = Math.floor(i / (skillNodes.length / ringCount + 1));
    const ringBase = 14 + ring * 10;
    const angle = (Math.PI * 2 * i * 1.618) % (Math.PI * 2); // 黄金角
    skill.x = Math.cos(angle) * ringBase;
    skill.y = -16 + (Math.random() - 0.5) * 3;
    skill.z = Math.sin(angle) * ringBase;
    skill.radius = 0.35 + (skill.count / maxCount) * 0.6;
    skill.color = heatColor(skill.count, maxCount);
  });

  repelNodes(skillNodes, 3, 20);

  return { catPositions };
}

// ── 构建图数据 ──
function buildGraph(jdList) {
  const categoryKeys = [...new Set(jdList.map((jd) => jd.category))];
  const skillCountMap = new Map();

  // 统计技能频率
  for (const jd of jdList) {
    for (const skill of jd.skills_norm) {
      skillCountMap.set(skill, (skillCountMap.get(skill) || 0) + 1);
    }
  }

  // 构建 JD 节点
  const jdNodes = jdList.map((jd, i) => ({
    id: `jd:${jd.job_id}`,
    type: "jd",
    name: jd.job_title,
    category: jd.category,
    company: jd.company_name,
    salary: `${jd.salary_min / 1000}K-${jd.salary_max / 1000}K`,
    experience: jd.experience,
    education: jd.education,
    location: jd.location,
    skills: jd.skills_norm,
    jdText: jd.jd_text,
    radius: 1.2 + Math.random() * 0.4,
    index: i,
    x: 0, y: 0, z: 0, // 布局后赋值
    isNew: jd.isNew || false,
  }));

  // 构建技能节点（去重，按频率排序取前 25）
  const sortedSkills = [...skillCountMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 25);
  const skillNodes = sortedSkills.map(([name, count], i) => ({
    id: `skill:${name}`,
    type: "skill",
    name,
    count,
    x: 0, y: 0, z: 0,
    radius: 0.4,
    index: i,
  }));

  const { catPositions } = layoutNodes(jdNodes, skillNodes, categoryKeys);

  // 构建类别节点
  const catNodes = categoryKeys.map((key, i) => {
    const cat = JD_CATEGORIES[key];
    const pos = catPositions[key];
    return {
      id: `cat:${key}`,
      type: "category",
      name: cat?.label || key,
      category: key,
      color: cat?.color || "#4dd6ff",
      x: pos.x,
      y: pos.y,
      z: pos.z,
      radius: 2.2,
      index: i,
    };
  });

  // 构建连线
  const links = [];
  for (const jd of jdNodes) {
    links.push({ source: jd.id, target: `cat:${jd.category}`, type: "jd-cat" });
    for (const skill of jd.skills) {
      const skillNode = skillNodes.find((s) => s.name === skill);
      if (skillNode) {
        links.push({ source: jd.id, target: skillNode.id, type: "jd-skill" });
      }
    }
  }

  const allNodes = [...catNodes, ...jdNodes, ...skillNodes];
  const nodeMap = new Map(allNodes.map((n) => [n.id, n]));

  return { allNodes, catNodes, jdNodes, skillNodes, links, nodeMap, categoryKeys };
}

// ── 主组件 ──
export default function StarMap() {
  const mountRef = useRef(null);
  const sceneRef = useRef(null);
  const cameraRef = useRef(null);
  const rendererRef = useRef(null);
  const controlsRef = useRef(null);
  const objectMapRef = useRef(new Map());
  const linesRef = useRef([]);
  const animFrameRef = useRef(0);
  const graphRef = useRef(null);

  const [jdList, setJdList] = useState(() => REPRESENTATIVE_JDS.map((jd) => ({ ...jd })));
  const [inputText, setInputText] = useState("");
  const [selectedNode, setSelectedNode] = useState(null);
  const [tooltip, setTooltip] = useState(null);
  const [isAdding, setIsAdding] = useState(false);

  // 构建图数据
  const graph = useMemo(() => buildGraph(jdList), [jdList]);

  const skillDistribution = useMemo(() => {
    const groups = new Map([
      ["开发与工程", 0],
      ["数据与 AI", 0],
      ["测试与运维", 0],
      ["通用能力", 0],
    ]);
    const classifySkill = (skill) => {
      const text = skill.toLowerCase();
      if (/python|java|javascript|typescript|react|vue|go|c\+\+|pytorch|tensorflow|sql|mysql|算法|模型|机器学习|深度学习|数据/.test(text)) return "数据与 AI";
      if (/测试|pytest|selenium|linux|docker|k8s|运维|jenkins|监控/.test(text)) return "测试与运维";
      if (/沟通|协作|管理|表达|项目|产品|需求|业务/.test(text)) return "通用能力";
      return "开发与工程";
    };
    for (const skill of graph.skillNodes) groups.set(classifySkill(skill.name), groups.get(classifySkill(skill.name)) + skill.count);
    const colors = ["#4dd6ff", "#b37feb", "#52c41a", "#faad14"];
    return [...groups.entries()].map(([name, value], index) => ({ name, value, color: colors[index] }));
  }, [graph]);

  const relatedJobs = useMemo(() => {
    if (!selectedNode) return jdList.slice(0, 5);
    if (selectedNode.type === "skill") return jdList.filter((job) => job.skills_norm.includes(selectedNode.name));
    return jdList.filter((job) => job.category === selectedNode.category);
  }, [jdList, selectedNode]);

  const topSkills = useMemo(() => graph.skillNodes.slice(0, 6), [graph]);

  const skillPieOption = useMemo(() => ({
    tooltip: {
      trigger: "item",
      formatter: "{b}<br/>{c} 次 · {d}%",
      backgroundColor: "rgba(7, 16, 24, 0.96)",
      borderColor: "rgba(77, 214, 255, 0.2)",
      textStyle: { color: "#e6edf3" },
    },
    series: [{
      type: "pie",
      radius: ["54%", "78%"],
      center: ["50%", "50%"],
      minAngle: 5,
      padAngle: 2,
      itemStyle: { borderRadius: 4, borderColor: "#0d1117", borderWidth: 2 },
      label: { show: false },
      emphasis: { scaleSize: 7 },
      data: skillDistribution.map((item) => ({ value: item.value, name: item.name, itemStyle: { color: item.color } })),
    }],
    graphic: [{
      type: "text",
      left: "center",
      top: "42%",
      style: { text: `${graph.skillNodes.length}\n技能`, fill: "#e6edf3", fontSize: 14, fontWeight: 700, textAlign: "center", lineHeight: 20 },
    }],
  }), [graph.skillNodes.length, skillDistribution]);

  // ── 初始化 Three.js 场景 ──
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    // 场景
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x071018);
    scene.fog = new THREE.Fog(0x071018, 100, 220);
    sceneRef.current = scene;

    // 相机
    const aspect = mount.clientWidth / mount.clientHeight;
    const camera = new THREE.PerspectiveCamera(48, aspect, 0.1, 320);
    camera.position.set(0, 22, Math.max(65, 65 / aspect));
    cameraRef.current = camera;

    // 渲染器
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(mount.clientWidth, mount.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    mount.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 控制器
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 25;
    controls.maxDistance = 150;
    controls.target.set(0, 0, 0);
    controls.maxPolarAngle = Math.PI * 0.85;
    controlsRef.current = controls;

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

    // 星点背景
    const starsGeo = new THREE.BufferGeometry();
    const starsCount = 1000;
    const starPos = new Float32Array(starsCount * 3);
    for (let i = 0; i < starsCount; i++) {
      starPos[i * 3] = (Math.random() - 0.5) * 250;
      starPos[i * 3 + 1] = (Math.random() - 0.5) * 250;
      starPos[i * 3 + 2] = (Math.random() - 0.5) * 250;
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

    // 参考环
    const rings = [];
    const ringLevels = [
      { y: 16, color: 0x2e6b7c, radius: 32 },
      { y: 0, color: 0x34445e, radius: 28 },
      { y: -16, color: 0x665d45, radius: 32 },
    ];
    for (const level of ringLevels) {
      const curve = new THREE.EllipseCurve(0, 0, level.radius, level.radius, 0, Math.PI * 2);
      const points = curve.getPoints(128).map((p) => new THREE.Vector3(p.x, level.y, p.y));
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      const mat = new THREE.LineBasicMaterial({ color: level.color, transparent: true, opacity: 0.18 });
      const line = new THREE.Line(geo, mat);
      scene.add(line);
      rings.push(line);
    }

    // 层标签
    const layerLabels = [
      { text: "岗位层", y: 16, color: "#4dd6ff44" },
      { text: "技能层", y: -16, color: "#52c41a44" },
    ];
    for (const lbl of layerLabels) {
      const sprite = createTextSprite(lbl.text, 0, lbl.y + 2, 0, lbl.color, 32, [6, 1.5, 1]);
      scene.add(sprite);
    }

    // 动画循环
    const animate = () => {
      const t = performance.now() / 1000;

      for (const [, mesh] of objectMapRef.current.entries()) {
        const ud = mesh.userData;
        if (!ud) continue;
        // 浮动
        const targetY = ud.baseY + Math.sin(t * 0.8 + ud.phase) * 0.18;
        mesh.position.y = THREE.MathUtils.lerp(mesh.position.y, targetY, 0.085);
        // 缩放
        const cur = mesh.scale.x;
        if (Math.abs(cur - ud.targetRadius) > 0.01) {
          mesh.scale.setScalar(THREE.MathUtils.lerp(cur, ud.targetRadius, 0.12));
        }
        // shader 时间
        if (mesh.material.uniforms?.uTime) {
          mesh.material.uniforms.uTime.value = t;
        }
      }

      // 连线跟随
      for (const line of linesRef.current) {
        const { source, target } = line.userData;
        const arr = line.geometry.attributes.position.array;
        arr[0] = source.position.x; arr[1] = source.position.y; arr[2] = source.position.z;
        arr[3] = target.position.x; arr[4] = target.position.y; arr[5] = target.position.z;
        line.geometry.attributes.position.needsUpdate = true;
      }

      // 参考环旋转
      for (const ring of rings) ring.rotation.y = t * 0.03;

      controls.update();
      renderer.render(scene, camera);
      animFrameRef.current = requestAnimationFrame(animate);
    };
    animate();

    // 响应式
    const onResize = () => {
      const w = mount.clientWidth, h = mount.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(animFrameRef.current);
      window.removeEventListener("resize", onResize);
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
      objectMapRef.current.clear();
      linesRef.current = [];
    };
  }, []);

  // ── 同步图数据到 Three.js 场景 ──
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    graphRef.current = graph;

    // 清理旧对象
    for (const [, mesh] of objectMapRef.current.entries()) {
      scene.remove(mesh);
      if (mesh.geometry) mesh.geometry.dispose();
      if (mesh.material) {
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        for (const m of mats) { if (m.map) m.map.dispose(); m.dispose(); }
      }
    }
    objectMapRef.current.clear();
    for (const line of linesRef.current) {
      scene.remove(line);
      line.geometry.dispose();
      line.material.dispose();
    }
    linesRef.current = [];

    const sphere = new THREE.SphereGeometry(1, 24, 16);
    const objectMap = new Map();

    // ── 创建类别节点 ──
    for (const cat of graph.catNodes) {
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(cat.color),
        emissive: new THREE.Color(cat.color).multiplyScalar(0.3),
        roughness: 0.3,
        metalness: 0.2,
        transparent: true,
        opacity: 1,
      });
      const glowMat = createGlowMaterial(cat.color);
      const mesh = new THREE.Mesh(sphere, material);
      mesh.position.set(cat.x, cat.y, cat.z);
      mesh.scale.setScalar(cat.radius);
      mesh.userData = {
        node: cat,
        baseMaterial: material,
        highlightMaterial: glowMat,
        baseY: cat.y,
        targetRadius: cat.radius,
        phase: Math.random() * Math.PI * 2,
      };
      scene.add(mesh);
      objectMap.set(cat.id, mesh);

      // 类别标签
      const sprite = createTextSprite(
        cat.name, cat.x, cat.y + cat.radius + 1.5, cat.z, cat.color, 44, [10, 2.5, 1]
      );
      scene.add(sprite);
      mesh.userData.labelSprite = sprite;
    }

    // ── 创建 JD 节点 ──
    for (const jd of graph.jdNodes) {
      const cat = JD_CATEGORIES[jd.category];
      const color = cat?.color || "#4dd6ff";
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(color),
        emissive: 0x071427,
        roughness: 0.38,
        metalness: 0.05,
        transparent: true,
        opacity: 0.88,
      });
      const glowMat = createGlowMaterial(color);
      const mesh = new THREE.Mesh(sphere, material);
      mesh.position.set(jd.x, jd.y, jd.z);
      mesh.scale.setScalar(jd.isNew ? 0.01 : jd.radius); // 新 JD 从小开始动画
      mesh.userData = {
        node: jd,
        baseMaterial: material,
        highlightMaterial: glowMat,
        baseY: jd.y,
        targetRadius: jd.radius,
        phase: Math.random() * Math.PI * 2,
      };
      scene.add(mesh);
      objectMap.set(jd.id, mesh);

      // 新 JD 的飞入动画
      if (jd.isNew) {
        // 从相机方向飞入
        const cam = cameraRef.current;
        if (cam) {
          mesh.position.set(cam.position.x, cam.position.y, cam.position.z - 10);
        }
        // 脉冲效果
        setTimeout(() => {
          mesh.userData.targetRadius = jd.radius * 1.6;
          setTimeout(() => {
            mesh.userData.targetRadius = jd.radius;
          }, 400);
        }, 300);
      }
    }

    // ── 创建技能节点 ──
    for (const skill of graph.skillNodes) {
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(skill.color),
        emissive: 0x17120c,
        roughness: 0.38,
        metalness: 0.05,
        transparent: true,
        opacity: 0.8,
      });
      const mesh = new THREE.Mesh(sphere, material);
      mesh.position.set(skill.x, skill.y, skill.z);
      mesh.scale.setScalar(skill.radius);
      mesh.userData = {
        node: skill,
        baseMaterial: material,
        highlightMaterial: createGlowMaterial(skill.color),
        baseY: skill.y,
        targetRadius: skill.radius,
        phase: Math.random() * Math.PI * 2,
      };
      scene.add(mesh);
      objectMap.set(skill.id, mesh);
    }

    // ── 创建连线 ──
    const lineList = [];
    const lineColorMap = { "jd-cat": 0x4dd6ff, "jd-skill": 0x52c41a };
    for (const link of graph.links) {
      const source = objectMap.get(link.source);
      const target = objectMap.get(link.target);
      if (!source || !target) continue;
      const geo = new THREE.BufferGeometry().setFromPoints([source.position, target.position]);
      const mat = new THREE.LineBasicMaterial({
        color: lineColorMap[link.type] || 0x30363d,
        transparent: true,
        opacity: link.type === "jd-cat" ? 0.12 : 0.08,
      });
      const line = new THREE.Line(geo, mat);
      line.userData = { link, source, target, baseOpacity: link.type === "jd-cat" ? 0.12 : 0.08 };
      scene.add(line);
      lineList.push(line);
    }

    objectMapRef.current = objectMap;
    linesRef.current = lineList;

    // ── 交互事件 ──
    const renderer = rendererRef.current;
    const camera = cameraRef.current;
    if (!renderer || !camera) return;

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
        let label = node.name;
        let extra = "";
        if (node.type === "jd") {
          extra = `${node.company} · ${node.salary}`;
        } else if (node.type === "skill") {
          extra = `出现 ${node.count} 次`;
        }
        setTooltip({ x: e.clientX, y: e.clientY, label, extra, type: node.type });
      } else {
        setTooltip(null);
      }
    };

    const applyHighlight = (node) => {
      const neighbors = new Set();
      neighbors.add(node.id);

      for (const line of lineList) {
        const { link } = line.userData;
        if (link.source === node.id || link.target === node.id) {
          neighbors.add(link.source);
          neighbors.add(link.target);
        }
      }

      for (const [id, mesh] of objectMap.entries()) {
        const isActive = neighbors.has(id);
        if (isActive) {
          mesh.material = mesh.userData.highlightMaterial;
          mesh.userData.highlightMaterial.uniforms.uIntensity.value = 1;
          mesh.userData.targetRadius = mesh.userData.node.radius * 1.35;
        } else {
          mesh.material = mesh.userData.baseMaterial;
          mesh.userData.baseMaterial.opacity = 0.15;
          mesh.userData.targetRadius = mesh.userData.node.radius * 0.7;
        }
        // 标签也跟随
        if (mesh.userData.labelSprite) {
          mesh.userData.labelSprite.material.opacity = isActive ? 1 : 0.15;
        }
      }

      for (const line of lineList) {
        const { link } = line.userData;
        const active = link.source === node.id || link.target === node.id;
        line.material.opacity = active ? 0.5 : 0.02;
      }
    };

    const resetHighlight = () => {
      for (const [, mesh] of objectMap.entries()) {
        mesh.material = mesh.userData.baseMaterial;
        mesh.userData.baseMaterial.opacity = mesh.userData.node.type === "category" ? 1 : mesh.userData.node.type === "jd" ? 0.88 : 0.8;
        mesh.userData.targetRadius = mesh.userData.node.radius;
        if (mesh.userData.labelSprite) {
          mesh.userData.labelSprite.material.opacity = 1;
        }
      }
      for (const line of lineList) {
        line.material.opacity = line.userData.baseOpacity;
      }
    };

    const onClick = (e) => {
      const hit = pick(e);
      if (hit) {
        const node = hit.userData.node;
        setSelectedNode(node);
        applyHighlight(node);
      } else {
        setSelectedNode(null);
        resetHighlight();
      }
    };

    const onLeave = () => { hovered = null; setTooltip(null); };

    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("click", onClick);
    renderer.domElement.addEventListener("pointerleave", onLeave);

    return () => {
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
    };
  }, [graph]);

  // ── 添加新 JD ──
  const handleAddJD = useCallback(() => {
    const text = inputText.trim();
    if (!text) {
      message.warning("请输入 JD 文本");
      return;
    }

    setIsAdding(true);

    // 简单解析：从文本中提取信息
    const lines = text.split("\n").filter((l) => l.trim());
    const title = lines[0]?.replace(/^(职位名称|岗位名称|岗位|职位)[：:]\s*/, "").trim() || "新岗位";

    // 提取技能
    const skills = extractSkillsFromText(text);
    if (skills.length === 0) {
      skills.push("AI", "Python"); // 默认技能
    }

    const category = classifyJD(title);
    const jobId = `custom_${Date.now()}`;

    const newJD = {
      job_id: jobId,
      job_title: title,
      company_name: "用户输入",
      location: "-",
      salary_min: "0",
      salary_max: "0",
      experience: "-",
      education: "-",
      skills_norm: skills.slice(0, 6),
      category,
      jd_text: text.slice(0, 200),
      isNew: true,
    };

    setJdList((prev) => [...prev, newJD]);
    setInputText("");
    message.success(`已添加：${title}（${JD_CATEGORIES[category]?.label || category}）`);

    // 3 秒后移除 isNew 标记
    setTimeout(() => {
      setJdList((prev) =>
        prev.map((jd) => (jd.job_id === jobId ? { ...jd, isNew: false } : jd))
      );
    }, 3000);

    setIsAdding(false);
  }, [inputText]);

  // ── 定位到某个 JD ──
  const handleFocusJD = useCallback((jd) => {
    const node = objectMapRef.current.get(`jd:${jd.job_id}`);
    if (!node) return;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;

    // 平滑移动相机到该节点附近
    const target = node.position.clone();
    const offset = new THREE.Vector3(8, 5, 8);
    const newPos = target.clone().add(offset);

    // 简单动画
    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    let progress = 0;
    const animMove = () => {
      progress += 0.03;
      if (progress > 1) progress = 1;
      const t = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      camera.position.lerpVectors(startPos, newPos, t);
      controls.target.lerpVectors(startTarget, target, t);
      controls.update();
      if (progress < 1) requestAnimationFrame(animMove);
    };
    animMove();

    // 高亮
    setSelectedNode(node.userData.node);
  }, []);

  // ── 重置视角 ──
  const handleReset = useCallback(() => {
    setSelectedNode(null);
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) return;
    camera.position.set(0, 22, 65);
    controls.target.set(0, 0, 0);
    controls.update();
  }, []);

  return (
    <div className="starmap-container">
      {/* ── 3D 星图 ── */}
      <div className="starmap-canvas-wrap">
        <div ref={mountRef} className="starmap-canvas" />

        {/* 图例 */}
        <div className="starmap-legend">
          <div className="starmap-legend-title">图例</div>
          <div className="starmap-legend-items">
            {Object.entries(JD_CATEGORIES).map(([key, cat]) => (
              <span key={key} className="starmap-legend-item" style={{ color: cat.color }}>
                <span className="starmap-legend-dot" style={{ background: cat.color }} />
                {cat.label}
              </span>
            ))}
            <span className="starmap-legend-item" style={{ color: "var(--text-secondary)" }}>
              <span className="starmap-legend-dot" style={{ background: "#8b949e" }} />
              技能
            </span>
          </div>
        </div>

        {/* 统计信息 */}
        <div className="starmap-stats">
          <Tag color="blue">{graph.jdNodes.length} 岗位</Tag>
          <Tag color="purple">{graph.skillNodes.length} 技能</Tag>
          <Tag color="cyan">{graph.categoryKeys.length} 方向</Tag>
        </div>

        {/* 悬浮 Tooltip */}
        {tooltip && (
          <div
            className="starmap-tooltip"
            style={{ left: tooltip.x + 16, top: tooltip.y - 10 }}
          >
            <div className="starmap-tooltip-label">{tooltip.label}</div>
            {tooltip.extra && <div className="starmap-tooltip-extra">{tooltip.extra}</div>}
          </div>
        )}

        {/* 重置按钮 */}
        <Button
          className="starmap-reset-btn"
          icon={<AimOutlined />}
          onClick={handleReset}
          size="small"
        >
          重置视角
        </Button>
      </div>

      {/* ── 右侧面板 ── */}
      <div className="starmap-panel">
        <div className="starmap-panel-header">
          <StarOutlined style={{ color: "#4dd6ff", fontSize: 18 }} />
          <Title level={5} style={{ margin: 0, color: "#e6edf3" }}>
            岗位星图
          </Title>
        </div>

        <div className="starmap-insights">
          <div className="starmap-insights-heading">
            <div><span>岗位技能分析</span><strong>{selectedNode?.name || "全局视图"}</strong></div>
            <Tag color={selectedNode ? "cyan" : "default"}>{selectedNode ? "动态筛选" : "全部数据"}</Tag>
          </div>
          <div className="starmap-insight-summary">
            <div><strong>{graph.jdNodes.length}</strong><span>岗位</span></div>
            <div><strong>{graph.skillNodes.length}</strong><span>技能</span></div>
            <div><strong>{graph.links.length}</strong><span>关联</span></div>
          </div>
          <div className="starmap-analysis-grid">
            <div className="starmap-pie-panel">
              <div className="starmap-metric-title">技能分类占比</div>
              <ReactECharts option={skillPieOption} style={{ height: 150 }} opts={{ renderer: "canvas" }} />
            </div>
            <div className="starmap-pie-legend">
              {skillDistribution.map((item) => (
                <div key={item.name}><i style={{ background: item.color }} /><span>{item.name}</span><b>{item.value}</b></div>
              ))}
            </div>
          </div>
          <div className="starmap-metric-title">高频技能</div>
          <div className="starmap-skill-ranking">
            {topSkills.map((skill, index) => (
              <button key={skill.id} type="button">
                <span><b>{index + 1}</b>{skill.name}</span>
                <i><em style={{ width: `${Math.max(12, skill.count / topSkills[0].count * 100)}%` }} /></i>
                <strong>{skill.count}</strong>
              </button>
            ))}
          </div>
          <div className="starmap-related-title">{selectedNode ? `${selectedNode.name} · 关联职业` : "热门关联职业"}<span>{relatedJobs.length} 个结果</span></div>
          <div className="starmap-related-jobs">
            {relatedJobs.length > 0 ? relatedJobs.slice(0, 5).map((job) => (
              <button key={job.job_id} type="button" onClick={() => handleFocusJD(job)}>
                <i style={{ background: JD_CATEGORIES[job.category]?.color || "#4dd6ff" }} />
                <span><strong>{job.job_title}</strong><small>{job.company_name || JD_CATEGORIES[job.category]?.label}</small></span>
                <em>{job.skills_norm.length} 技能</em>
              </button>
            )) : <span className="starmap-muted">暂无关联职业</span>}
          </div>
        </div>

        {/* 输入区 */}
        <div className="starmap-input-section">
          <div className="starmap-section-title">
            <PlusOutlined /> 添加新 JD
          </div>
          <TextArea
            className="starmap-textarea"
            placeholder={"粘贴 JD 文本，例如：\nAI算法工程师\n负责大模型训练与优化\n要求：Python, PyTorch, 深度学习"}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            rows={4}
            style={{ resize: "none" }}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAddJD}
            loading={isAdding}
            block
            style={{
              background: "linear-gradient(135deg, #4dd6ff22, #7b61ff22)",
              borderColor: "#4dd6ff44",
              color: "#4dd6ff",
              fontWeight: 600,
            }}
          >
            添加到星图
          </Button>
        </div>

        <Divider style={{ margin: "12px 0", borderColor: "rgba(77,214,255,0.08)" }} />

        {/* JD 列表 */}
        <div className="starmap-section-title">
          <ThunderboltOutlined /> 已有岗位 ({jdList.length})
        </div>
        <div className="starmap-jd-list">
          {jdList.map((jd) => {
            const cat = JD_CATEGORIES[jd.category];
            return (
              <div
                key={jd.job_id}
                className={`starmap-jd-card ${selectedNode?.id === `jd:${jd.job_id}` ? "active" : ""}`}
                onClick={() => handleFocusJD(jd)}
              >
                <div className="starmap-jd-card-title">
                  <span
                    className="starmap-jd-dot"
                    style={{ background: cat?.color || "#4dd6ff" }}
                  />
                  {jd.job_title}
                </div>
                <div className="starmap-jd-card-meta">
                  {jd.company_name !== "用户输入" && (
                    <span>{jd.company_name}</span>
                  )}
                  {jd.salary_max !== "0" && (
                    <span style={{ color: "#52c41a" }}>
                      {Number(jd.salary_min) / 1000}K-{Number(jd.salary_max) / 1000}K
                    </span>
                  )}
                </div>
                <div className="starmap-jd-card-skills">
                  {jd.skills_norm.slice(0, 4).map((s) => (
                    <Tag key={s} className="starmap-skill-tag" color="default">
                      {s}
                    </Tag>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* 选中详情 */}
        {selectedNode && selectedNode.type === "jd" && (
          <>
            <Divider style={{ margin: "12px 0", borderColor: "rgba(77,214,255,0.08)" }} />
            <div className="starmap-detail">
              <div className="starmap-section-title">
                <BookOutlined /> 岗位详情
              </div>
              <div className="starmap-detail-title">{selectedNode.name}</div>
              <div className="starmap-detail-row">
                <EnvironmentOutlined /> {selectedNode.location || "-"}
              </div>
              {selectedNode.salary !== "0K-0K" && (
                <div className="starmap-detail-row">
                  <DollarOutlined /> {selectedNode.salary}
                </div>
              )}
              <div className="starmap-detail-row">
                <BookOutlined /> {selectedNode.experience} · {selectedNode.education}
              </div>
              {selectedNode.jdText && (
                <Paragraph
                  className="starmap-detail-text"
                  ellipsis={{ rows: 3, expandable: true, symbol: "展开" }}
                >
                  {selectedNode.jdText}
                </Paragraph>
              )}
              <div className="starmap-detail-skills">
                {selectedNode.skills?.map((s) => (
                  <Tag key={s} color="blue">
                    {s}
                  </Tag>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
