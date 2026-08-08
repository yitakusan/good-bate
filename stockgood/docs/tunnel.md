# 隧道穿透（Cloudflare Tunnel）

在日本 / 海外电脑跑 Stockgood，国内朋友用浏览器访问，无需 VPN。

实现对照 Animegood 的复用说明（`animegood/docs/tunnel.md`），端口改为本仓库配置。

## 架构

```
国内朋友浏览器
    → https://xxxx.trycloudflare.com
    → Cloudflare 边缘
    → 本机 cloudflared
    → 本机前端 :5174
    → 前端把 /api、/media 代理到本机后端 :8002
```

只穿透前端；后端仍听 `127.0.0.1`。

## 一键启动

根目录双击 **`start-tunnel.bat`**：

1. 检查 `cloudflared` 是否在 PATH
2. 若 `http://127.0.0.1:5174` 未就绪，则调用 `scripts/start-bg.ps1` 起前后端
3. 执行：`cloudflared tunnel --url http://127.0.0.1:5174`
4. 把日志中的 `https://xxxx.trycloudflare.com/apply` **发给顾客**（申请页）
5. 管理端仍用本机 `http://localhost:5174`，或隧道根路径（勿把根路径当顾客链接）

前置：已安装依赖（见 README），以及 [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)。

## Vite

`frontend/vite.config.ts` 已配置：

- `appType: "spa"`（保证 `/apply` 直链回退到 `index.html`）
- `host: true`
- `allowedHosts: [".trycloudflare.com", "localhost", ".local"]`
- `/api`、`/media` → `http://127.0.0.1:8002`

改配置后需重启前端。

## 安全

临时 URL 谁拿到谁都能进。分享前再开、用完 `Ctrl+C` 关隧道；本地用 `stop.bat` 停服务。

**顾客链接请用：** `https://xxxx.trycloudflare.com/apply`  
（页头「复制申请页」即复制此地址；勿发根路径，否则会进库存管理界面。）

可选：`STOCKGOOD_ADMIN_TOKEN` 保护管理端写接口；公开 scrape / 提交有 IP 限流。

## 常见问题

| 现象 | 处理 |
|---|---|
| `cloudflared` 找不到 | 安装后重开终端 |
| `Blocked request. This host is not allowed` | 确认 `allowedHosts` 后重启前端 |
| `/apply` 404 | 确认 `appType: "spa"` 后重启前端 |
| 页面开了但 API 挂 | 后端是否在 8002；代理是否指向本机 |
| 重启后朋友进不去 | 临时 URL 已变，重发新的 `.../apply` |
