import { useState, useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { Layout as AntLayout, Menu, Typography, theme, Badge, Tooltip } from "antd";
import {
  DashboardOutlined,
  FileTextOutlined,
  UserOutlined,
  SwapOutlined,
  NodeIndexOutlined,
  HistoryOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const { Sider, Content, Header } = AntLayout;

const MENU_ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: "数据概览" },
  { key: "/jd", icon: <FileTextOutlined />, label: "JD 管理" },
  { key: "/resume", icon: <UserOutlined />, label: "简历管理" },
  { key: "/match", icon: <SwapOutlined />, label: "人岗匹配" },
  { key: "/history", icon: <HistoryOutlined />, label: "匹配历史" },
  { key: "/graph", icon: <NodeIndexOutlined />, label: "知识图谱" },
  { key: "/settings", icon: <SettingOutlined />, label: "系统设置" },
];

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);

  // 获取当前页面标题
  const currentPageTitle = MENU_ITEMS.find((item) => item.key === location.pathname)?.label || "数据概览";

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        breakpoint="lg"
        onBreakpoint={(broken) => setCollapsed(broken)}
        width={220}
        style={{
          background: token.colorBgContainer,
          borderRight: `1px solid ${token.colorBorder}`,
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Logo 区域 */}
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: `1px solid ${token.colorBorder}`,
            position: "relative",
          }}
        >
          {/* 装饰渐变线 */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              height: 2,
              background: "linear-gradient(90deg, #4dd6ff, #7b61ff, #4dd6ff)",
              backgroundSize: "200% 100%",
              animation: "shimmer 3s ease-in-out infinite",
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <ThunderboltOutlined
              style={{
                fontSize: collapsed ? 20 : 18,
                color: "#4dd6ff",
                filter: "drop-shadow(0 0 4px rgba(77, 214, 255, 0.4))",
              }}
            />
            <Typography.Title
              level={4}
              style={{
                margin: 0,
                background: "linear-gradient(135deg, #4dd6ff, #7b61ff)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                whiteSpace: "nowrap",
                fontWeight: 700,
                letterSpacing: collapsed ? 0 : "0.05em",
                display: collapsed ? "none" : "block",
              }}
            >
              岗位能力图谱
            </Typography.Title>
          </div>
        </div>

        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
          style={{
            borderRight: 0,
            padding: "8px 0",
            background: "transparent",
          }}
        />

        {/* 底部版本信息 */}
        {!collapsed && (
          <div
            style={{
              position: "absolute",
              bottom: 56,
              left: 0,
              right: 0,
              textAlign: "center",
              padding: "0 16px",
            }}
          >
            <Typography.Text
              style={{
                fontSize: 11,
                color: "rgba(77, 214, 255, 0.25)",
                letterSpacing: "0.05em",
              }}
            >
              v3.0 · AI Powered
            </Typography.Text>
          </div>
        )}
      </Sider>

      <AntLayout>
        <Header
          style={{
            background: "rgba(13, 17, 23, 0.85)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            borderBottom: `1px solid ${token.colorBorder}`,
            padding: "0 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Typography.Text
              style={{
                color: "#8b949e",
                fontSize: 13,
                letterSpacing: "0.04em",
              }}
            >
              新一代信息技术岗位全景图谱 · 智能人岗匹配系统
            </Typography.Text>
            <Typography.Text
              style={{
                color: "#484f58",
                fontSize: 12,
              }}
            >
              |
            </Typography.Text>
            <Typography.Text
              style={{
                color: "#4dd6ff",
                fontSize: 13,
                fontWeight: 500,
              }}
            >
              {currentTime.toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </Typography.Text>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <Tooltip title="系统运行正常">
              <Badge status="success" />
            </Tooltip>
            <Typography.Text
              style={{ fontSize: 12, color: "#8b949e" }}
            >
              在线
            </Typography.Text>
          </div>
        </Header>

        <Content
          style={{
            margin: 16,
            overflow: "auto",
            minHeight: "calc(100vh - 64px - 32px)",
          }}
        >
          <div className="fade-in">
            <Outlet />
          </div>
        </Content>
      </AntLayout>
    </AntLayout>
  );
}
