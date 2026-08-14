import { useEffect } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import useStore from "./store/useStore";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import JDManage from "./pages/JDManage";
import ResumeManage from "./pages/ResumeManage";
import MatchResult from "./pages/MatchResult";
import MatchHistory from "./pages/MatchHistory";
import RecommendPage from "./pages/RecommendPage";
import KnowledgeGraph from "./pages/KnowledgeGraph";
import StarMap from "./pages/StarMap";
import Settings from "./pages/Settings";

// ── 路由守卫：未登录跳转到登录页 ──
function ProtectedRoute({ children }) {
  const { isAuthenticated } = useStore();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

// ── 角色守卫：根据角色限制页面访问 ──
function RoleRoute({ children, allowedRoles }) {
  const { user } = useStore();
  const role = user?.role || "job_seeker";

  if (allowedRoles && !allowedRoles.includes(role)) {
    return <Navigate to="/" replace />;
  }

  return children;
}

function ThemedApp() {
  const { settings, isAuthenticated } = useStore();
  const isDark = settings.theme === "dark";

  // 同步 data-theme 属性到 body
  useEffect(() => {
    document.body.setAttribute("data-theme", settings.theme || "dark");
  }, [settings.theme]);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: settings.primaryColor || "#4dd6ff",
          borderRadius: 10,
          colorBgContainer: isDark ? "#0d1117" : "#ffffff",
          colorBgElevated: isDark ? "#161b22" : "#ffffff",
          colorBgLayout: isDark ? "#010409" : "#f5f5f5",
          colorText: isDark ? "#e6edf3" : "#1f1f1f",
          colorTextSecondary: isDark ? "#8b949e" : "#666666",
          colorBorder: isDark ? "#30363d" : "#d9d9d9",
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
        },
        components: {
          Card: {
            colorBgContainer: isDark
              ? "rgba(13, 17, 23, 0.65)"
              : "#ffffff",
          },
          Menu: {
            colorItemBg: "transparent",
            colorSubItemBg: "transparent",
          },
        },
      }}
    >
      <Routes>
        {/* 登录页（不需要认证） */}
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
        />

        {/* 需要认证的页面 */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Dashboard />} />
          {/* HR 可完整管理 JD，求职者只读 */}
          <Route
            path="jd"
            element={
              <RoleRoute allowedRoles={["hr"]}>
                <JDManage />
              </RoleRoute>
            }
          />
          {/* 求职者可完整管理简历，HR 只读 */}
          <Route
            path="resume"
            element={
              <RoleRoute allowedRoles={["job_seeker"]}>
                <ResumeManage />
              </RoleRoute>
            }
          />
          <Route path="match" element={<MatchResult />} />
          <Route path="recommend" element={<RecommendPage />} />
          <Route path="history" element={<MatchHistory />} />
          <Route path="starmap" element={<StarMap />} />
          <Route path="graph" element={<KnowledgeGraph />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </ConfigProvider>
  );
}

export default function App() {
  return <ThemedApp />;
}
