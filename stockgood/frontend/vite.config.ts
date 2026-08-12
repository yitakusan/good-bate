import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxy =
  process.env.STOCKGOOD_API_PROXY || "http://127.0.0.1:8002";

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
        target: apiProxy,
        changeOrigin: true,
      },
      "/media": {
        target: apiProxy,
        changeOrigin: true,
      },
    },
  },
});
