import { create } from "zustand";
import { persist } from "zustand/middleware";

// Generate a unique user ID for this browser
function generateUserId() {
  return "u_" + crypto.randomUUID().replace(/-/g, "").slice(0, 16);
}

const useStore = create(
  persist(
    (set, get) => ({
      // ── User identity ──
      userId: null,
      initUserId: () => {
        const existing = get().userId;
        if (existing) return existing;
        const id = generateUserId();
        set({ userId: id });
        return id;
      },

      // ── Documents ──
      documents: [],
      currentDocument: null,
      addDocument: (doc) => set((s) => ({ documents: [doc, ...s.documents] })),
      setDocuments: (docs) => set({ documents: docs }),
      setCurrentDocument: (doc) => set({ currentDocument: doc }),

      // ── Profiles ──
      candidateProfiles: [],
      jobProfiles: [],
      currentCandidateProfile: null,
      currentJobProfile: null,
      addCandidateProfile: (p) =>
        set((s) => ({ candidateProfiles: [p, ...s.candidateProfiles] })),
      addJobProfile: (p) =>
        set((s) => ({ jobProfiles: [p, ...s.jobProfiles] })),
      setCurrentCandidateProfile: (p) => set({ currentCandidateProfile: p }),
      setCurrentJobProfile: (p) => set({ currentJobProfile: p }),

      // ── 画像缓存（按 docId 索引，持久化到 localStorage）──
      candidateProfileCache: {},
      jobProfileCache: {},
      setCachedCandidateProfile: (docId, profile) =>
        set((s) => ({
          candidateProfileCache: { ...s.candidateProfileCache, [docId]: profile },
        })),
      setCachedJobProfile: (docId, profile) =>
        set((s) => ({
          jobProfileCache: { ...s.jobProfileCache, [docId]: profile },
        })),
      setCachedCandidateProfiles: (profilesMap) =>
        set((s) => ({
          candidateProfileCache: { ...s.candidateProfileCache, ...profilesMap },
        })),
      setCachedJobProfiles: (profilesMap) =>
        set((s) => ({
          jobProfileCache: { ...s.jobProfileCache, ...profilesMap },
        })),
      removeCachedCandidateProfile: (docId) =>
        set((s) => {
          const next = { ...s.candidateProfileCache };
          delete next[docId];
          return { candidateProfileCache: next };
        }),
      removeCachedJobProfile: (docId) =>
        set((s) => {
          const next = { ...s.jobProfileCache };
          delete next[docId];
          return { jobProfileCache: next };
        }),

      // ── Matches ──
      matches: [],
      currentMatch: null,
      addMatch: (m) => set((s) => ({ matches: [m, ...s.matches] })),
      setCurrentMatch: (m) => set({ currentMatch: m }),

      // ── 匹配页面缓存（保留上次匹配的输入和结果）──
      lastMatchInputs: null, // { resumeText, jdText }
      lastMatchResult: null, // match result object
      setLastMatch: (inputs, result) =>
        set({ lastMatchInputs: inputs, lastMatchResult: result }),
      clearLastMatch: () => set({ lastMatchInputs: null, lastMatchResult: null }),

      // ── UI State ──
      loading: false,
      setLoading: (v) => set({ loading: v }),
      error: null,
      setError: (e) => set({ error: e }),
      clearError: () => set({ error: null }),

      // ── 用户偏好设置（持久化）──
      settings: {
        theme: "dark",
        primaryColor: "#4dd6ff",
        sidebarCollapsed: false,
        radarColors: ["#4dd6ff", "#52c41a", "#faad14", "#ff4d4f"],
      },
      updateSettings: (partial) =>
        set((s) => ({
          settings: { ...s.settings, ...partial },
        })),

      // ── 用户自定义 JD（用于岗位星图，持久化）──
      customJDs: [],
      addCustomJD: (jd) =>
        set((s) => {
          // 去重：根据岗位名称判断
          const exists = s.customJDs.some(
            (existing) => existing.job_title === jd.job_title
          );
          if (exists) return s;
          return { customJDs: [...s.customJDs, jd] };
        }),
      removeCustomJD: (jobId) =>
        set((s) => ({
          customJDs: s.customJDs.filter((jd) => jd.job_id !== jobId),
        })),

      // ── 匹配历史记录（持久化）──
      matchHistory: [],
      addMatchHistory: (record) =>
        set((s) => ({
          matchHistory: [
            { ...record, timestamp: Date.now() },
            ...s.matchHistory,
          ].slice(0, 100), // 最多保存 100 条
        })),
      removeMatchHistory: (timestamp) =>
        set((s) => ({
          matchHistory: s.matchHistory.filter((r) => r.timestamp !== timestamp),
        })),
      clearMatchHistory: () => set({ matchHistory: [] }),
      saveLearningAdvice: (timestamp, advice) =>
        set((s) => ({
          matchHistory: s.matchHistory.map((r) =>
            r.timestamp === timestamp ? { ...r, learningAdvice: advice } : r
          ),
        })),
    }),
    {
      name: "job-galaxy-store",
      partialize: (state) => ({
        settings: state.settings,
        matchHistory: state.matchHistory,
        userId: state.userId,
        candidateProfileCache: state.candidateProfileCache,
        jobProfileCache: state.jobProfileCache,
        lastMatchInputs: state.lastMatchInputs,
        lastMatchResult: state.lastMatchResult,
        customJDs: state.customJDs,
      }),
    }
  )
);

export default useStore;
