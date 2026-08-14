import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // 忽略编辑器原子写入留下的临时文件，避免 Windows 上 chokidar EBUSY 崩溃
    watch: {
      ignored: ["**/.tmpdir/**", "**/*.tmp", "**/*~"],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
      },
    },
  },
});
