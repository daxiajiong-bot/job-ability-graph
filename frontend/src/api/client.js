import axios from "axios";
import NProgress from "nprogress";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 60000,
  headers: { "Content-Type": "application/json" },
});

// ── 全局请求拦截器 ──
api.interceptors.request.use(
  (config) => {
    NProgress.start();
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

    // 超时处理
    if (error.code === "ECONNABORTED" || error.message?.includes("timeout")) {
      error.message = "请求超时，服务器响应过慢，请稍后重试";
    }

    // 网络错误
    if (!error.response) {
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

// ── Profiles ───────────────────────────────────────────
export const createCandidateProfile = (documentId) =>
  requestWithRetry(() =>
    api.post("/candidate-profiles", { document_id: documentId })
  );

export const getCandidateProfile = (id) =>
  requestWithRetry(() => api.get(`/candidate-profiles/${id}`));

export const createJobProfile = (documentId) =>
  requestWithRetry(() =>
    api.post("/job-profiles", { document_id: documentId })
  );

export const getJobProfile = (id) =>
  requestWithRetry(() => api.get(`/job-profiles/${id}`));

// ── Matching ───────────────────────────────────────────
export const createMatch = (candidateProfileId, jobProfileId, options = {}) =>
  requestWithRetry(() =>
    api.post("/matches", {
      candidate_profile_id: candidateProfileId,
      job_profile_id: jobProfileId,
      options: {
        include_document_evidence: true,
        include_graph_evidence: true,
        ...options,
      },
    })
  );

export const getMatch = (id) =>
  requestWithRetry(() => api.get(`/matches/${id}`));

// ── Reports ────────────────────────────────────────────
export const createReport = (matchId, language = "zh-CN") =>
  requestWithRetry(() =>
    api.post("/reports", { match_id: matchId, language })
  );

// ── Knowledge Graph ────────────────────────────────────
export const createKnowledgeGraph = (data) =>
  requestWithRetry(() => api.post("/knowledge-graphs", data));

export const getKnowledgeGraph = (id) =>
  requestWithRetry(() => api.get(`/knowledge-graphs/${id}`));

// ── Data Governance ────────────────────────────────────
export const registerDocument = (formData) =>
  api.post("/data-governance/documents/register", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

export const processDocument = (docId, version = null) =>
  requestWithRetry(() =>
    api.post(`/data-governance/documents/${docId}/process`, { version })
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

// ── System ─────────────────────────────────────────────
// health 在根路径，不在 /api/v1 下
export const getHealth = () => axios.get("/health");
export const getCapabilities = () => api.get("/capabilities");

export default api;
