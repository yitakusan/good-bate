import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // 监听所有网卡，便于局域网 / Tailscale / ZeroTier 异地访问
    host: true,
    port: 5173,
    // Cloudflare 临时隧道域名每次会变，允许 *.trycloudflare.com
    allowedHosts: [".trycloudflare.com", "localhost", ".local"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
});
