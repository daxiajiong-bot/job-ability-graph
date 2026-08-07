import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import useStore from "./store/useStore";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import JDManage from "./pages/JDManage";
import ResumeManage from "./pages/ResumeManage";
import MatchResult from "./pages/MatchResult";
import MatchHistory from "./pages/MatchHistory";
import StarMap from "./pages/StarMap";
import Settings from "./pages/Settings";

function ThemedApp() {
  const { settings } = useStore();
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
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="jd" element={<JDManage />} />
          <Route path="resume" element={<ResumeManage />} />
          <Route path="match" element={<MatchResult />} />
          <Route path="history" element={<MatchHistory />} />
          <Route path="starmap" element={<StarMap />} />
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
