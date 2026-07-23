import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import OfflineBanner from "./components/OfflineBanner";
import "./styles/global.css";
import "nprogress/nprogress.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <OfflineBanner />
      <ConfigProvider
        locale={zhCN}
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: "#4dd6ff",
            borderRadius: 10,
            colorBgContainer: "#0d1117",
            colorBgElevated: "#161b22",
            colorBgLayout: "#010409",
            colorText: "#e6edf3",
            colorTextSecondary: "#8b949e",
            colorBorder: "#30363d",
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
          },
          components: {
            Card: {
              colorBgContainer: "rgba(13, 17, 23, 0.65)",
            },
            Menu: {
              colorItemBg: "transparent",
              colorSubItemBg: "transparent",
            },
          },
        }}
      >
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ConfigProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
