import { create } from "zustand";
import { persist } from "zustand/middleware";

const useStore = create(
  persist(
    (set, get) => ({
      // ── Documents ──
      documents: [],
      currentDocument: null,
      addDocument: (doc) => set((s) => ({ documents: [doc, ...s.documents] })),
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

      // ── Matches ──
      matches: [],
      currentMatch: null,
      addMatch: (m) => set((s) => ({ matches: [m, ...s.matches] })),
      setCurrentMatch: (m) => set({ currentMatch: m }),

      // ── Knowledge Graph ──
      knowledgeGraph: null,
      setKnowledgeGraph: (g) => set({ knowledgeGraph: g }),

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
    }),
    {
      name: "job-galaxy-store",
      partialize: (state) => ({
        settings: state.settings,
        matchHistory: state.matchHistory,
      }),
    }
  )
);

export default useStore;
