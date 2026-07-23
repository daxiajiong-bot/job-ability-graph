import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import JDManage from "./pages/JDManage";
import ResumeManage from "./pages/ResumeManage";
import MatchResult from "./pages/MatchResult";
import MatchHistory from "./pages/MatchHistory";
import KnowledgeGraph from "./pages/KnowledgeGraph";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="jd" element={<JDManage />} />
        <Route path="resume" element={<ResumeManage />} />
        <Route path="match" element={<MatchResult />} />
        <Route path="history" element={<MatchHistory />} />
        <Route path="graph" element={<KnowledgeGraph />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
