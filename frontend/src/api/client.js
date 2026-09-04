import axios from "axios";
import NProgress from "nprogress";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

const LEARNING_ADVICE_TIMEOUT_MS = 360000;

// ── 获取认证信息（从 localStorage） ──
function getStoredState() {
  try {
    return JSON.parse(localStorage.getItem("job-galaxy-store"))?.state || {};
  } catch {
    return {};
  }
}

function getToken() {
  return getStoredState().token || null;
}

function getUserId() {
  return getStoredState().userId || null;
}

// ── 全局请求拦截器 ──
api.interceptors.request.use(
  (config) => {
    NProgress.start();
    // 优先使用 JWT token
    const token = getToken();
    if (token) {
      config.headers["Authorization"] = `Bearer ${token}`;
    }
    // 兼容：也附加 X-User-ID
    const userId = getUserId();
    if (userId) {
      config.headers["X-User-ID"] = userId;
    }
    // 网络离线时直接拒绝
    if (!navigator.onLine) {
      NProgress.done();
      return Promise.reject(new Error("网络连接已断开，请检查网络设置"));
    }
    return config;
  },
  (error) => {
    NProgress.done();
    return Promise.reject(error);
  }
);

// ── 全局响应拦截器 ──
api.interceptors.response.use(
  (response) => {
    NProgress.done();
    return response;
  },
  (error) => {
    NProgress.done();

    // 401 未授权 → 清除登录状态，跳转到登录页
    if (error.response?.status === 401) {
      try {
        const stored = JSON.parse(localStorage.getItem("job-galaxy-store"));
        if (stored?.state?.isAuthenticated) {
          stored.state.token = null;
          stored.state.user = null;
          stored.state.isAuthenticated = false;
          localStorage.setItem("job-galaxy-store", JSON.stringify(stored));
          window.location.href = "/login";
        }
      } catch {}
    }

    // 超时处理
    const isTimeout = error.code === "ECONNABORTED" || error.message?.includes("timeout");
    if (isTimeout) {
      error.message = "请求超时，服务器响应过慢，请稍后重试";
    }

    // 网络错误
    if (!error.response && !isTimeout) {
      if (!navigator.onLine) {
        error.message = "网络连接已断开，请检查网络设置";
      } else {
        error.message = "无法连接到服务器，请确认后端服务已启动";
      }
    }

    // 统一从后端错误格式中提取 message
    if (error.response?.data?.error?.message) {
      error.message = error.response.data.error.message;
    }

    return Promise.reject(error);
  }
);

// ── 带自动重试的请求封装 ──
async function requestWithRetry(requestFn, retries = 2, delay = 1000) {
  for (let i = 0; i <= retries; i++) {
    try {
      return await requestFn();
    } catch (e) {
      if (i === retries || !navigator.onLine) throw e;
      await new Promise((r) => setTimeout(r, delay * (i + 1)));
    }
  }
}

// ── Documents ──────────────────────────────────────────
export const createDocument = (data) =>
  requestWithRetry(() => api.post("/documents", data));

export const createDocumentOCR = (formData) =>
  api.post("/documents/ocr", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000, // OCR 需要更长超时
  });

export const getDocument = (id) =>
  requestWithRetry(() => api.get(`/documents/${id}`));

export const listDocuments = (offset = 0, limit = 50) =>
  requestWithRetry(() => api.get("/documents", { params: { offset, limit } }));

export const deleteDocument = (id) =>
  requestWithRetry(() => api.delete(`/documents/${id}`));

// ── Profiles (async task-based) ────────────────────────
export const createCandidateProfile = (documentId) =>
  requestWithRetry(() =>
    api.post("/candidate-profiles", { document_id: documentId })
  );

export const getCandidateProfileTask = (taskId) => {
  if (!taskId) return Promise.reject(new Error("候选人画像任务 ID 缺失"));
  return requestWithRetry(() => api.get(`/candidate-profiles/tasks/${taskId}`));
};

export const getCandidateProfile = (id) =>
  requestWithRetry(() => api.get(`/candidate-profiles/${id}`));

export const getCandidateProfilesByDocuments = (documentIds) =>
  requestWithRetry(() =>
    api.post("/candidate-profiles/by-documents", { document_ids: documentIds })
  );

export const createJobProfile = (documentId) =>
  requestWithRetry(() =>
    api.post("/job-profiles", { document_id: documentId })
  );

export const getJobProfileTask = (taskId) => {
  if (!taskId) return Promise.reject(new Error("岗位画像任务 ID 缺失"));
  return requestWithRetry(() => api.get(`/job-profiles/tasks/${taskId}`));
};

export const getJobProfile = (id) =>
  requestWithRetry(() => api.get(`/job-profiles/${id}`));

export const getJobProfilesByDocuments = (documentIds) =>
  requestWithRetry(() =>
    api.post("/job-profiles/by-documents", { document_ids: documentIds })
  );

// ── Matching ───────────────────────────────────────────
export const createMatch = (candidateProfileId, jobProfileId, options = {}) =>
  api.post("/matches", {
      candidate_profile_id: candidateProfileId,
      job_profile_id: jobProfileId,
      options: {
        include_document_evidence: true,
        include_graph_evidence: true,
        ...options,
      },
    }, { timeout: 90000 });

export const getMatch = (id) =>
  requestWithRetry(() => api.get(`/matches/${id}`));

// ── Reports ────────────────────────────────────────────
export const createReport = (matchId, language = "zh-CN") =>
  requestWithRetry(() =>
    api.post("/reports", { match_id: matchId, language })
  );

// ── Learning Advice ────────────────────────────────────
export const getLearningAdvice = (matchId) =>
  api.post(
    "/learning-advice",
    { match_id: matchId },
    { timeout: LEARNING_ADVICE_TIMEOUT_MS }
  );

// ── Auto Match (智能推荐) ─────────────────────────────
export const autoMatch = (documentId, topN = 5, filters = {}, maxPerCompany = 2) =>
  api.post("/auto-match", {
    document_id: documentId,
    top_n: topN,
    filters,
    max_per_company: maxPerCompany,
  }, { timeout: 180000 });

// ── Intelligence Contracts ─────────────────────────────
export const retrieveDocumentEvidence = (query, documentIds, filters = {}) =>
  requestWithRetry(() =>
    api.post("/document-retrievals", {
      query,
      document_ids: documentIds,
      filters,
    })
  );

// ── Knowledge Graph (Neo4j-backed) ─────────────────────
export const createKnowledgeGraph = (payload) =>
  requestWithRetry(() => api.post("/knowledge-graphs", payload));

export const getKnowledgeGraph = (id) =>
  requestWithRetry(() => api.get(`/knowledge-graphs/${id}`));

export const graphRetrieval = (graphId, query, seedEntityIds = [], relationTypes = []) =>
  requestWithRetry(() =>
    api.post(
      `/graph-retrievals`,
      {
        query,
        seed_entity_ids: seedEntityIds,
        relation_types: relationTypes,
      },
      { params: { graph_id: graphId }, timeout: 60000 }
    )
  );

export const discoverPositions = (documentIds, options = {}) =>
  requestWithRetry(() =>
    api.post("/position-discoveries", {
      document_ids: documentIds,
      options,
    })
  );

export const comparePositions = (baselineJobProfileId, currentJobProfileId, supportingDocumentIds = []) =>
  requestWithRetry(() =>
    api.post("/position-deltas", {
      baseline_job_profile_id: baselineJobProfileId,
      current_job_profile_id: currentJobProfileId,
      supporting_document_ids: supportingDocumentIds,
    })
  );

// ── Data Governance ────────────────────────────────────
export const registerDocument = (formData) =>
  api.post("/data-governance/documents/register", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const registerDocumentPath = (data) =>
  requestWithRetry(() =>
    api.post("/data-governance/documents/register-path", data)
  );

export const processDocument = (docId, version = null) =>
  requestWithRetry(() =>
    api.post(`/data-governance/documents/${docId}/process`, { version })
  );

export const getGovernedDocument = (docId, version = null) =>
  requestWithRetry(() =>
    api.get(`/data-governance/documents/${docId}`, { params: { version } })
  );

export const getDocumentLineage = (docId) =>
  requestWithRetry(() =>
    api.get(`/data-governance/documents/${docId}/lineage`)
  );

export const searchRAG = (query, docIds = [], topK = 5) =>
  requestWithRetry(() =>
    api.post("/data-governance/rag/search", {
      query,
      doc_ids: docIds,
      top_k: topK,
    })
  );

export const answerRAG = (query, docIds = [], topK = 5) =>
  requestWithRetry(() =>
    api.post("/data-governance/rag/answer", {
      query,
      doc_ids: docIds,
      top_k: topK,
    })
  );

// ── JobTrend Discovery (岗位发现) ──────────────────────
export const getEmergingRoles = () =>
  requestWithRetry(() => api.get("/trend/emerging-roles"));

export const generateRoleDefinition = (roleId) =>
  api.post(`/trend/emerging-roles/${encodeURIComponent(roleId)}/generate-definition`, {}, { timeout: 180000 });

export const saveRoleDefinition = (roleId, definition, status) =>
  requestWithRetry(() =>
    api.put(`/trend/emerging-roles/${encodeURIComponent(roleId)}/definition`, {
      ...definition,
      status,
    })
  );

export const reviewRoleDefinition = (roleId, decision, notes = "") =>
  requestWithRetry(() =>
    api.post(`/trend/emerging-roles/${encodeURIComponent(roleId)}/review`, {
      decision,
      notes,
      reviewer: "expert",
    })
  );

export const getSkillUpdates = () =>
  requestWithRetry(() => api.get("/trend/skill-updates"));

// 审核「既有岗位技能更新」：decision=approved/rejected；skillNames 为空数组表示对该更新的全部变化项生效
export const reviewSkillUpdate = (updateId, decision, skillNames = [], notes = "") =>
  requestWithRetry(() =>
    api.post(`/trend/skill-updates/${encodeURIComponent(updateId)}/review`, {
      decision,
      skill_names: skillNames,
      notes,
    })
  );

export const getTrendFeatures = () =>
  requestWithRetry(() => api.get("/trend/features"));

export const getReviewQueue = () =>
  requestWithRetry(() => api.get("/trend/review-queue"));

export const getTrendSummary = () =>
  requestWithRetry(() => api.get("/trend/summary"));

// ── Users ─────────────────────────────────────────────
export const initUser = () => api.post("/users/init");

// ── Auth ──────────────────────────────────────────────
export const authAPI = {
  register: (data) => api.post("/auth/register", data),
  login: (data) => api.post("/auth/login", data),
  getMe: () => api.get("/auth/me"),
};

export const listUserDocuments = (userId, documentType = null, offset = 0, limit = 50) => {
  const params = { offset, limit };
  if (documentType) params.document_type = documentType;
  return api.get(`/users/${userId}/documents`, { params });
};

// ── System ─────────────────────────────────────────────
// health 在根路径，不在 /api/v1 下
export const getHealth = () => axios.get("/health");
export const getCapabilities = () => api.get("/capabilities");

export default api;
