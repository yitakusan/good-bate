# 隧道穿透复用说明（Cloudflare Tunnel）

给另一套本地库存 / 电商系统复用：在**日本（或海外）电脑**跑服务，让**国内朋友用浏览器**访问，对方**不用装 VPN**。

Animegood 已落地的脚本：`start-tunnel.bat`；配置见 `frontend/vite.config.ts`。

---

## 1. 在干什么

```
国内朋友浏览器
    → https://xxxx.trycloudflare.com
    → Cloudflare 边缘
    → 你本机 cloudflared
    → 本机前端端口（Animegood: 5173）
    → 前端把 /api 代理到本机后端（Animegood: 8001）
```

要点：

| 项 | 做法 |
|----|------|
| 穿透入口 | **只指到前端**（带 `/api` 反向代理的那个端口） |
| 后端 | 继续只听 `127.0.0.1`，不必对公网开放 |
| 抓取 / 写库 | 仍在你本机执行，不依赖国内网络 |

临时隧道（Quick Tunnel）**免费、免域名、免 Cloudflare 账号**；缺点是**每次重启 URL 会变**。

---

## 2. 本机服务要先满足的条件

另一套系统按同样原则改：

1. **前端**监听 `0.0.0.0`（或至少本机可访问），固定端口，例如 `5173`
2. **前端开发服务器**把 `/api` 代理到本机后端，例如 `http://127.0.0.1:8001`
3. 若用 **Vite**：必须允许临时隧道域名，否则会出现 `Blocked request. This host is not allowed`

Vite 示例：

```ts
server: {
  host: true,
  port: 5173,
  allowedHosts: [".trycloudflare.com", "localhost", ".local"],
  proxy: {
    "/api": {
      target: "http://127.0.0.1:8001",
      changeOrigin: true,
    },
  },
},
```

其它框架（Next / Nuxt / Webpack DevServer）同理：允许 Host、并保留 API 代理。

**不要**把隧道直接指到后端端口，除非前端是纯静态且 API 已同源或已单独配 CORS——开发态最省事仍是「只穿透前端」。

---

## 3. 安装 cloudflared（Windows）

任选其一：

```bat
winget install --id Cloudflare.cloudflared
```

或从官网下载：  
https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

装完后**新开**一个终端，确认：

```bat
where cloudflared
cloudflared --version
```

---

## 4. 启动步骤（可照搬）

1. 先启动本机前后端，确认本机浏览器能开前端（如 `http://localhost:5173`）
2. 再开隧道（把端口改成你的前端端口）：

```bat
cloudflared tunnel --url http://127.0.0.1:5173
```

3. 日志里找类似：

```text
https://xxxx.trycloudflare.com
Your quick Tunnel has been created
Registered tunnel connection
```

4. 把该 HTTPS 链接发给朋友
5. **保持** 后端、前端、隧道 **三个进程都开着**；关隧道窗口 = 链接失效

Animegood 封装：根目录双击 `start-tunnel.bat`（内部就是上面那条命令）。

---

## 5. 可复制的 bat 模板（换端口即可）

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo [ERROR] cloudflared not in PATH
    echo Install: winget install --id Cloudflare.cloudflared
    pause
    exit /b 1
)

REM 改成你的前端地址
cloudflared tunnel --url http://127.0.0.1:5173
pause
```

---

## 6. 安全（另一套库存系统强烈建议）

临时 URL 等于短暂公网入口，谁拿到链接谁都能进。

建议：

- 写接口（抓取、改库存、清空库）加 **管理口令**（请求头或登录）
- 分享前再开隧道；用完 `Ctrl+C` 关掉
- 不要指望临时隧道做正式生产；长期用 → 自有域名 + Named Tunnel，或 VPS

Animegood 对应环境变量：`ANIMEGOOD_ADMIN_TOKEN`（仅作命名参考，新系统用自己的变量名）。

---

## 7. 常见问题

| 现象 | 处理 |
|------|------|
| `cloudflared` 找不到 | 安装后重开终端；确认 PATH |
| `Blocked request. This host is not allowed` | 前端未允许 `*.trycloudflare.com`；改配置后**重启前端**再开隧道 |
| 页面开了但 API 全挂 | 检查前端是否把 `/api` 代理到本机后端；后端是否已启动 |
| 链接打不开 | 本机休眠/断网/关了隧道；或个别网络拦 Cloudflare，可改用 Tailscale |
| 日志提 `cert.pem` / `config.yml` | 临时隧道可忽略；看到 `Registered tunnel connection` 即通 |
| 重启后朋友进不去 | 正常：临时 URL 变了，把新链接再发一次 |

---

## 8. 备选：Tailscale / ZeroTier（熟人 VPN）

不适合「随便发个链接」时用：

1. 双方装同一 VPN，同一虚拟局域网
2. 前端听 `0.0.0.0`
3. 对方打开：`http://你的VPN_IP:5173`
4. Windows 防火墙放行入站 **TCP 前端端口**

国内访问一般不如 Cloudflare 顺；但更可控、URL 不飘。

---

## 9. 接到新库存系统的检查清单

- [ ] 前端端口固定，本机可打开
- [ ] `/api`（或你的 API 前缀）由前端代理到本机后端
- [ ] 开发服务器允许 `*.trycloudflare.com`（或等价 Host 校验关闭/放行）
- [ ] 已安装 `cloudflared`
- [ ] 隧道命令指向**前端** `http://127.0.0.1:<前端端口>`
- [ ] 敏感写操作有口令 / 鉴权
- [ ] 说明文档写清：要保持本机开机 + 三进程常开 + 临时 URL 会变

---

## 10. Animegood 对照（本仓库）

| 文件 / 配置 | 作用 |
|-------------|------|
| `start.bat` | 起后端 `8001` + 前端 `5173` |
| `start-tunnel.bat` | `cloudflared tunnel --url http://127.0.0.1:5173` |
| `frontend/vite.config.ts` | `host`、`allowedHosts`、`/api` → `8001` |
| `README.md`「日本电脑给国内朋友用」 | 面向最终用户的短步骤 |

其它系统不必依赖本仓库代码，按第 2～5、9 节改端口与鉴权即可。
