import { useState, useEffect } from "react";
import { Alert } from "antd";
import { DisconnectOutlined } from "@ant-design/icons";

export default function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const handleOffline = () => setIsOffline(true);
    const handleOnline = () => setIsOffline(false);

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <Alert
      message="网络连接已断开，请检查网络设置"
      type="error"
      banner
      closable
      icon={<DisconnectOutlined />}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        borderRadius: 0,
      }}
    />
  );
}
