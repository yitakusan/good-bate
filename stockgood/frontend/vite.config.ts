import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  appType: "spa",
  server: {
    host: true,
    port: 5174,
    // Cloudflare Quick Tunnel hosts (*.trycloudflare.com); required or Vite blocks the request.
    allowedHosts: [".trycloudflare.com", "localhost", ".local"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
      },
      "/media": {
        target: "http://127.0.0.1:8002",
        changeOrigin: true,
      },
    },
  },
});
