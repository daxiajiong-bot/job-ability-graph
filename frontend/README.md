# 前端使用指南

> 岗位能力图谱 · 智能人岗匹配系统前端

---

## 一、环境要求

| 依赖    | 版本要求 |
| ------- | -------- |
| Node.js | >= 18.0  |
| npm     | >= 9.0   |

---

## 二、安装与启动

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

启动后访问 **http://localhost:5173**

### 3. 其他命令

| 命令                | 说明                            |
| ------------------- | ------------------------------- |
| `npm run dev`     | 启动开发服务器（热更新）        |
| `npm run build`   | 构建生产版本（输出到`dist/`） |
| `npm run preview` | 预览生产构建                    |
| `npm run lint`    | 代码检查（oxlint）              |

---

## 三、后端依赖

前端通过 Vite 代理将 API 请求转发到后端：

```
前端 localhost:5173  ──proxy──>  后端 localhost:8000
/api/*                          /api/*
/health                         /health
```

**后端未启动时**：页面正常显示，但功能操作会提示"无法连接到服务器"。

启动后端：

```bash
cd job-ability-graph
pip install -r requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

> ⚠️ 必须从项目根目录 `job-ability-graph/` 启动，模块路径为 `backend.app.main:app`。

---

## 四、页面功能说明

### 4.1 数据概览（`/`）

- 查看系统健康状态、OCR / LLM 可用性
- 3D 星图可视化展示岗位-技能关系
- 快速导航到各功能页面

### 4.2 JD 管理（`/jd`）

三种上传方式：

| 方式                 | 说明                                             |
| -------------------- | ------------------------------------------------ |
| **文本输入**   | 粘贴 JD 原文，点击「创建 JD 文档」               |
| **单文件上传** | 拖拽/选择图片或 PDF，自动 OCR 识别后弹出校正界面 |
| **批量上传**   | 同时选择多个文件，带进度条批量 OCR               |

上传后可「生成画像」或「查看画像」。

### 4.3 简历管理（`/resume`）

功能与 JD 管理一致，支持文本输入、单文件 OCR、批量上传。文档类型为「简历」。

### 4.4 人岗匹配（`/match`）

1. 左侧粘贴候选人简历文本
2. 右侧粘贴岗位描述（JD）文本
3. 点击「一键匹配」
4. 系统自动完成：创建文档 → 生成画像 → 执行匹配 → 生成报告
5. 查看匹配得分、雷达图、技能差距分析
6. 支持导出为 TXT / JSON / CSV

### 4.5 匹配历史（`/history`）

- 查看所有历史匹配记录
- 点击「详情」查看完整匹配分析和 GapChart
- 勾选两条记录点击「对比」进行横向比较
- 支持单条导出和清空全部记录
- 数据保存在浏览器 localStorage，刷新不丢失

### 4.6 系统设置（`/settings`）

- 主题切换（深色/浅色）
- 主色调选择
- 侧边栏默认状态
- 设置自动保存到 localStorage

---

## 五、项目结构

```
frontend/
├── index.html
├── package.json
├── vite.config.js
└── src/
    ├── main.jsx                    # 入口（ErrorBoundary + 离线检测 + NProgress）
    ├── App.jsx                     # 路由配置
    ├── api/
    │   └── client.js               # Axios 实例（拦截器 + 重试 + 超时）
    ├── components/
    │   ├── Layout.jsx              # 应用布局（侧边栏 + 顶栏）
    │   ├── ErrorBoundary.jsx       # 全局错误边界
    │   ├── OfflineBanner.jsx       # 离线检测横幅
    │   ├── OCRCorrectionModal.jsx  # OCR 结果校正弹窗
    │   ├── GapChart.jsx            # 技能差距分析图
    │   ├── JobGalaxy.jsx           # 3D 星图（Three.js）
    │   └── SkillDag.jsx            # 技能 DAG 图（ECharts）
    ├── hooks/
    │   └── useRequest.js           # 统一请求状态管理 hook
    ├── pages/
    │   ├── Dashboard.jsx           # 数据概览
    │   ├── JDManage.jsx            # JD 管理
    │   ├── ResumeManage.jsx        # 简历管理
    │   ├── MatchResult.jsx         # 人岗匹配
    │   ├── MatchHistory.jsx        # 匹配历史
    │   └── Settings.jsx            # 系统设置
    ├── store/
    │   └── useStore.js             # Zustand 全局状态（设置 + 历史持久化）
    ├── styles/
    │   └── global.css              # 全局样式 + 响应式 + NProgress
    └── utils/
        ├── adapters.js             # 后端数据 → 前端格式适配器
        ├── pdfGenerator.js         # 报告导出（TXT/JSON/CSV）
        └── demoData.js             # 演示数据（5条JD + 3份简历 + 脚本）
```

---

## 六、技术栈

| 类别     | 技术                                |
| -------- | ----------------------------------- |
| 框架     | React 19                            |
| 构建     | Vite 8                              |
| UI 库    | Ant Design 6（暗色主题）            |
| 状态管理 | Zustand 5（含 localStorage 持久化） |
| 路由     | React Router DOM 7                  |
| HTTP     | Axios（拦截器 + 重试）              |
| 图表     | ECharts 6 + echarts-for-react       |
| 3D 渲染  | Three.js                            |
| 进度条   | NProgress                           |

---

## 七、演示数据

系统内置演示数据，位于 `src/utils/demoData.js`：

| 数据             | 数量 | 说明                                               |
| ---------------- | ---- | -------------------------------------------------- |
| `DEMO_JDS`     | 5 条 | Python开发、测试、数据分析、AI产品、前端           |
| `DEMO_RESUMES` | 3 份 | 张三（Python全栈）、李四（测试）、王五（数据分析） |
| `DEMO_SCRIPT`  | 6 步 | 比赛现场演示操作步骤                               |

---

## 八、常见问题

### Q: 页面白屏？

检查浏览器控制台（F12），确认是否有报错。系统已内置 ErrorBoundary，组件崩溃会显示错误页面而非白屏。

### Q: API 请求一直失败？

1. 确认后端已启动：`curl http://localhost:8000/health`
2. 确认端口一致：Vite 代理目标为 `http://127.0.0.1:8000`
3. 网络断开时页面顶部会显示红色离线横幅

### Q: 刷新后设置/历史丢失？

设置和匹配历史通过 Zustand persist 保存在 localStorage。如果清除了浏览器缓存则会丢失。

### Q: 构建产物太大？

Three.js + ECharts + Ant Design 体积较大，生产构建约 3MB（gzip 后约 935KB）。可通过 `vite build` 后在 `dist/` 目录部署。
