/**
 * 代表性 JD 数据 — 用于 3D 星图初始展示
 * 精选 8 个覆盖 AI 各方向的岗位
 */

// ── JD 分类定义 ──
export const JD_CATEGORIES = {
  infra: { label: "AI Infra", color: "#4dd6ff", emissive: 0x0a1a2e },
  algorithm: { label: "算法研究", color: "#b37feb", emissive: 0x1a0f2e },
  agent: { label: "AI Agent", color: "#52c41a", emissive: 0x0a1a08 },
  vision: { label: "CV/视觉", color: "#faad14", emissive: 0x1a1408 },
  llm: { label: "大模型", color: "#ff7875", emissive: 0x1a0a0a },
  engineer: { label: "AI 工程", color: "#36cfc9", emissive: 0x0a1a1a },
  app: { label: "AI 应用", color: "#ffc53d", emissive: 0x1a1608 },
};

// ── 代表性 JD 数据 ──
export const REPRESENTATIVE_JDS = [
  {
    job_id: "40962326802",
    job_title: "AI Infra 工程师-算法性能部署方向",
    company_name: "申通快递",
    location: "上海 青浦 重固",
    salary_min: "20001",
    salary_max: "35000",
    experience: "3-5年",
    education: "本科",
    skills_norm: ["模型部署", "Python", "C++", "深度学习", "CUDA", "TensorRT"],
    category: "infra",
    jd_text:
      "负责AI算法模型的性能优化与部署，包括模型压缩、量化、推理加速等；参与AI基础设施建设，优化GPU集群调度和资源管理。",
  },
  {
    job_id: "40867387609",
    job_title: "AI算法工程师/技术顾问",
    company_name: "北京中博世达专利商标代理有限公司",
    location: "北京 海淀 北下关",
    salary_min: "20001",
    salary_max: "30000",
    experience: "5-10年",
    education: "本科",
    skills_norm: [
      "大模型算法",
      "PyTorch",
      "TRANSFORMERS",
      "HUGGINGFACE",
      "Python",
      "C++",
      "DEEPSEEK",
      "LLAMA",
    ],
    category: "algorithm",
    jd_text:
      "设计和实现高效的算法，推进公司AI大模型的构建与完善。利用数学、统计学和机器学习分析海量数据并进行建模。优化算法实现，保证代码的可扩展性和可维护性。",
  },
  {
    job_id: "40858449607",
    job_title: "实在智能 RPA&AI Agent 开发专员",
    company_name: "许昌佳瑞发制品有限公司",
    location: "郑州 管城 圃田",
    salary_min: "4001",
    salary_max: "5000",
    experience: "1-3年",
    education: "本科",
    skills_norm: ["Java", "Python", "JS", "RPA", "AI Agent", "自动化"],
    category: "agent",
    jd_text:
      "负责基于实在智能RPA/IPA/Agent平台的自动化项目，从需求调研、流程设计、开发测试到部署上线全流程管理。根据电商、财务、供应链等业务需求开发自动化流程。",
  },
  {
    job_id: "40911483608",
    job_title: "视觉工程师",
    company_name: "上海实极机器人自动化有限公司",
    location: "上海 嘉定 南翔",
    salary_min: "12001",
    salary_max: "18000",
    experience: "3-5年",
    education: "本科",
    skills_norm: [
      "机器人",
      "图像识别",
      "OpenCV",
      "HALCON",
      "C#",
      "C语言",
      "机器视觉",
    ],
    category: "vision",
    jd_text:
      "设备视觉软件及模块的需求分析、方案设计、编程实现。制定机器视觉系统方案及选型，编写图像处理相关算法，实现对目标的各种检测与测量。",
  },
  {
    job_id: "40863631807",
    job_title: "多模态大模型/智能体工程师",
    company_name: "湖南鼎一致远科技发展股份有限公司",
    location: "深圳 宝安 航城",
    salary_min: "10001",
    salary_max: "15000",
    experience: "经验不限",
    education: "硕士",
    skills_norm: [
      "深度学习",
      "多模态算法",
      "大模型算法",
      "Llama",
      "Qwen",
      "RAG",
    ],
    category: "llm",
    jd_text:
      "基于开源大模型（如Llama、Qwen等）构建行业专属AI智能体。负责RAG系统的构建，整合企业和行业知识库。设计多模态交互能力，支持图文和语音混合输入。",
  },
  {
    job_id: "40862150714",
    job_title: "2026-AI工程专家",
    company_name: "鼎桥技术有限公司",
    location: "成都 双流 华阳",
    salary_min: "25001",
    salary_max: "50000",
    experience: "3-5年",
    education: "本科",
    skills_norm: [
      "AI",
      "架构设计",
      "多Agent协作",
      "代码质量",
      "自动化测试",
    ],
    category: "engineer",
    jd_text:
      "负责AI编码工具链的架构设计与优化，构建Rule/Skill/Spec体系实现编码约束自动化。设计多Agent协作框架，支持复杂任务分解与编排。",
  },
  {
    job_id: "40859489210",
    job_title: "AI 大模型应用开发工程师",
    company_name: "台州拜亚进出口有限公司",
    location: "上海 徐汇 虹梅路",
    salary_min: "15001",
    salary_max: "25000",
    experience: "1-3年",
    education: "大专",
    skills_norm: ["Flask", "Django", "MySQL", "Redis", "Cursor", "Claude"],
    category: "app",
    jd_text:
      "用Cursor、Claude Code等AI Coding Agent重组日常开发流程。工程师的核心价值是把模糊业务问题转成Agent可执行的任务，为Agent准备上下文、拆任务、设检查点。",
  },
  {
    job_id: "40812462813",
    job_title: "Python后端开发工程师(RAG知识库)",
    company_name: "浙江浩越贸易有限公司",
    location: "杭州 萧山 盈丰",
    salary_min: "7001",
    salary_max: "12000",
    experience: "3-5年",
    education: "本科",
    skills_norm: [
      "Python",
      "RAG",
      "向量数据库",
      "大模型",
      "智能体",
      "MCP",
    ],
    category: "app",
    jd_text:
      "以RAG知识库构建为核心，结合千亿参数大模型、智能体、MCP等技术，打造智能化的标书生成、语义检索等关键场景。主导构建面向招投标垂直领域的智能知识库系统。",
  },
];

/**
 * 根据标题关键词对 JD 进行分类
 */
export function classifyJD(jobTitle) {
  const title = jobTitle.toLowerCase();
  if (title.includes("infra") || title.includes("基础") || title.includes("平台"))
    return "infra";
  if (title.includes("算法") || title.includes("研究") || title.includes("scientist"))
    return "algorithm";
  if (title.includes("agent") || title.includes("智能体"))
    return "agent";
  if (title.includes("视觉") || title.includes("cv") || title.includes("nlp") || title.includes("自然语言"))
    return "vision";
  if (title.includes("大模型") || title.includes("llm") || title.includes("预训练") || title.includes("微调"))
    return "llm";
  if (title.includes("工程") && (title.includes("ai") || title.includes("智能")))
    return "engineer";
  return "app";
}

/**
 * 从 JD 文本中提取技能关键词
 */
const SKILL_KEYWORDS = [
  "Python", "Java", "C++", "Go", "Rust", "JavaScript", "TypeScript",
  "PyTorch", "TensorFlow", "Keras", "JAX", "PaddlePaddle",
  "Transformer", "BERT", "GPT", "LLaMA", "Qwen", "DeepSeek", "ChatGLM",
  "NLP", "CV", "RAG", "LLM", "Agent", "MCP",
  "机器学习", "深度学习", "强化学习", "大模型", "多模态",
  "计算机视觉", "自然语言处理", "知识图谱", "推荐系统",
  "Docker", "Kubernetes", "CUDA", "TensorRT", "ONNX",
  "Spark", "Flink", "Hadoop", "Hive",
  "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch", "向量数据库",
  "Flask", "Django", "FastAPI", "Spring",
  "OpenCV", "HALCON", "ROS",
  "Git", "Linux", "Shell",
  "模型部署", "模型压缩", "量化", "蒸馏", "微调", "LoRA", "SFT",
  "Prompt Engineering", "Function Calling", "RPA",
  "数据标注", "特征工程", "A/B测试",
];

export function extractSkillsFromText(text) {
  if (!text) return [];
  const found = [];
  const lower = text.toLowerCase();
  for (const skill of SKILL_KEYWORDS) {
    if (lower.includes(skill.toLowerCase())) {
      found.push(skill);
    }
  }
  return [...new Set(found)];
}
