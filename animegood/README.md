# Animegood 动漫周边发现站

聚合日本电商与官方店的动漫周边新品，在本地网站里**发现商品、比价、收藏**，并通过购买链接导流回各店铺。

> 没用过也没关系：按下面「第一次启动」走一遍，约 5–10 分钟即可在浏览器里看到商品列表。

**端口说明：** 后端固定使用 **8001**（不是 8000）。Windows 上 C-Lodop 打印服务常占用 8000，打开 `http://localhost:8000/docs` 会看到 C-Lodop 页面而非本项目 API。

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost:5173 |
| 后端 API 文档 | http://localhost:8001/docs |
| 健康检查 | http://localhost:8001/health |

Vite 开发代理已将 `/api` 转发到 `http://127.0.0.1:8001`（见 `frontend/vite.config.ts`）。

---

## 你能用它做什么

| 功能 | 说明 |
|------|------|
| **发现** | 按 IP、店铺、**系列**（如圣诞企划）、发售月、关键词筛选；显示「共 N 件」、筛选摘要与一键清除；每页 40 条，底部「加载更多」 |
| **日文译名** | 按本地术语表 `name_glossary.json` 替换展示，无在线翻译 |
| **热度** | 全站「N 人收藏」计数；支持按「收藏最多」排序 |
| **收藏夹** | 个人收藏保存在浏览器本地；可 Base64 导入/导出备份；打开收藏页时用库内最新价格/库存刷新 |
| **购物车** | 本地购物车（数量、小计、合计），可导入/导出备份；数据在 `localStorage`（`animegood_cart_v1`） |
| **详情 & 比价** | 点商品卡片看详情；**同系列**其他商品；同一 IP 在不同店的价格对比 |
| **导流** | 「跳转到」链到原店，带 `utm_source=animegood` |
| **活动资讯** | 首页 hero 轮播；展示结束日（`ends_at`）；过期活动自动隐藏 |
| **汇率 / 人民币约价** | hero 显示支付宝汇率；商品卡片与详情在日元旁显示「约 ¥xx.xx」人民币估算 |
| **抓取** | 管理员可在空状态「拉取最新商品」或开发工具抓取；可配置定时自动抓取；公网须设管理口令 |

---

## 前置要求

| 软件 | 版本建议 | 用途 |
|------|----------|------|
| **Python** | 3.11+ | 后端 API、抓取 |
| **Node.js** | 18+ | 前端页面 |
| **Git** | 任意 | 克隆仓库（可选） |

Windows 用户推荐直接用根目录的 **`start.bat`** 一键启动（会检查依赖、安装 Playwright Chromium、打开浏览器）。

---

## 第一次启动（零基础教程）

### 步骤 1：拿到代码

```bash
git clone <你的仓库地址> animegood
cd animegood
```

或解压下载的 ZIP 后进入项目文件夹。

### 步骤 2：安装后端依赖（只需做一次）

```bash
cd backend
python -m venv .venv
```

**Windows（PowerShell / CMD）：**

```bash
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

**macOS / Linux：**

```bash
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> `playwright install chromium` 用于 STORES 类店铺（如 SHIBUYA TSUTAYA）。只跑 Shopify 源时可先跳过，但建议装上。

### 步骤 3：安装前端依赖（只需做一次）

```bash
cd ../frontend
npm install
```

### 步骤 4：启动服务

**方式 A — Windows 一键（推荐）**

双击项目根目录的 `start.bat`，或在根目录执行：

```bash
start.bat
```

会打开两个命令行窗口（后端 + 前端），并自动打开：

- 前端发现页：http://localhost:5173
- 后端 API 文档：http://localhost:8001/docs

**方式 B — 手动分别启动**

终端 1（后端）：

```bash
cd backend
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

终端 2（前端）：

```bash
cd frontend
npm run dev
```

浏览器访问 http://localhost:5173 。

### 步骤 5：导入第一批商品

刚装好时列表可能是空的，需要先抓取：

1. 打开 http://localhost:5173
2. 页面底部展开 **「开发工具」**
3. 设置「每源条数」如 `20`，点 **「抓取活动资讯」**（仅更新首页轮播公告），或点 **「立即抓取」**（商品 + 活动一起）
4. 等待抓取完成（默认最多 3 个站点同时抓取；Shopify 源较快，STORES / Playwright 源较慢）
5. 抓取结束后商品网格会自动刷新

列表页翻页：STORES 首页抓完后会继续点「もっと見る/次へ」或访问 `?page=N`（最多约 30 页）；BASE / おちゃのこ / カラーミー / FutureShop / EC-CUBE HTML 也会按 `?page=` 翻页。Shopify 本身已支持 `products.json` 多页。若「每源条数」设了上限（如 20），仍只会保留前 N 条。

也可用 API 文档 http://localhost:8001/docs 里的 **抓取 → POST /api/scrape/run**（全部）或 **POST /api/scrape/run/{source_id}**（单站）试跑。

### 步骤 6：像用户一样浏览

1. 顶部选 **「发现」** 标签
2. 用搜索框输入角色名或商品关键词（输入后约 300ms 防抖再请求）
3. 用下拉选 **IP / 店铺 / 发售月**，或点 IP 快捷标签
4. 勾选 **「仅可购买」**，排序选 **「收藏最多」** 看热门
5. **点击商品卡片** → 弹出详情与同 IP 多店比价表
6. 在卡片上点 **「收藏」** 或 **「加购」** 加入本地收藏夹 / 购物车
7. 在 **详情弹窗** 内点 **「跳转到」**（显示店名）跳转原店下单
8. 切到 **「收藏夹」** 或 **「购物车」** 标签查看
9. 列表底部点 **「加载更多」** 继续翻页（每页 40 条）

---

## 界面说明

```
┌─────────────────────────────────────────┐
│  Animegood                    [汇率]    │
│  [ 发现 ]  [ 收藏夹 ]  [ 购物车 ]        │
│  搜索 | IP | 店铺 | 月份 | 排序 | 可购买 │
│  IP 快捷标签…                            │
│  ┌────┐ ┌────┐ ┌────┐                    │
│  │商品│ │商品│ │商品│  ← 点卡片看详情    │
│  │收藏│ │收藏│ │收藏│    卡片仅收藏/加购 │
│  │加购│ │加购│ │加购│    跳转在详情内    │
│  └────┘ └────┘ └────┘                    │
│  ▸ 开发工具（抓取 / 清空 / 收录表）       │
└─────────────────────────────────────────┘
```

### 三个主标签

| 标签 | 作用 |
|------|------|
| **发现** | 主筛选区：搜索、IP、店铺、**系列**、发售月、排序、仅可购买；**筛选摘要 / 清除 / 共 N 件**；商品网格（日元 + 人民币约价）；底部「加载更多」；手机端双列卡片、吸顶标签与全屏详情 |
| **收藏夹** | 本地收藏商品；打开时用 `GET /api/products/by-ids` 刷新价格/库存/译名；底部可 **导出 Base64 备份** 或 **导入合并**（相同商品 ID 覆盖为导入快照，最多 200 条） |
| **购物车** | 显示 `购物车 (N)`（N 为件数合计）；每条可改数量（1–99）、移除、跳转原店；底部日元合计 + 按首页汇率估算人民币；可 **Base64 导入/导出**（相同 ID 累加数量，最多 200 种） |

### 首页活动与汇率

- **Hero 活动轮播**：展示活动标题、店铺、结束日（`ends_at`）；已过期活动不会返回。
- **汇率小部件**：hero 右上角显示支付宝日元汇率（如 `100 日元 ≈ 4.204 元（支付宝）`）。后端代理抓取 [5waihui.com](https://www.5waihui.com/alipay/)，**每小时更新一次**；「更新」时间为本系统最近抓取时刻（JST）。

### 收藏 vs 热度

| | 个人收藏 | 全站热度 |
|--|----------|----------|
| 存在哪 | 浏览器 `localStorage`（键名 `animegood:wishlist`） | 本地 SQLite `products.favorite_count` |
| 要不要登录 | 不需要 | 不需要 |
| 作用 | 「收藏夹」页只看自己的 | 卡片角标「N 人收藏」、排序「收藏最多」 |

### 开发工具（页面底部，默认折叠）

- **管理口令**：公网设置了 `ANIMEGOOD_ADMIN_TOKEN` 时必填（保存在本机浏览器）
- **选择店铺**：勾选要抓的已启用源（可全选 / 清空），不必每次全站抓
- **仅入库新数据**：默认开启。按商品链接查重，已有商品跳过不更新；关闭则为全量，会刷新价格/库存
- **立即抓取**：并发抓取勾选的商品源 + 活动源
- **抓取活动资讯**：只更新活动，不影响商品
- **每源条数**：限制单次抓取条数（开发调试建议 20）
- **清空抓取数据**：两步确认（先准备、等 3 秒再确认）；同样需要管理口令
- **网站收录表**：每行可对单站抓取（未启用源也可测试抓取）

列表为空时，发现页会显示「拉取最新商品」按钮（同样受口令保护），不必先翻到页面底部。定时任务默认也是**增量**模式。

---

## 常见问题

### 公网部署如何防止别人乱抓取 / 清空数据？

1. 在服务器环境变量中设置 **`ANIMEGOOD_ADMIN_TOKEN`**（强随机字符串）
2. 抓取与清空接口须带请求头 `X-Admin-Token`
3. 前端在开发者工具（或空状态）填写同一口令；口令只存在你自己的浏览器本地
4. 未设置该变量时，行为与本机开发相同（不鉴权）——**公网务必设置**

示例见根目录 [`.env.example`](.env.example)。

### 如何让商品自动更新，不用每次手动抓？

设置 **`ANIMEGOOD_SCRAPE_INTERVAL_HOURS`**（例如 `6` 表示约每 6 小时全量抓取一次）。为 `0` 或不设置则关闭。后端进程需保持运行（Docker / systemd）。

### 如何让异地朋友通过 VPN 打开我的前端？

适合少数熟人试用（Tailscale / ZeroTier 等）：

1. 你和朋友加入同一 VPN，本机用 `start.bat` 启动（前端已监听 `0.0.0.0:5173`）
2. 把你在 VPN 里的 IP 发给对方，对方打开：`http://你的VPN_IP:5173`
3. Windows 防火墙若拦截，放行入站 **TCP 5173**
4. 分享前建议设置 `ANIMEGOOD_ADMIN_TOKEN`，避免对方误触抓取/清空
5. 本机需保持开机；收藏在对方浏览器本地，不会同步到你这边

后端仍只监听 `127.0.0.1:8001`，远程请求走 Vite 的 `/api` 代理即可。长期公开给多人请改用公网 VPS + 域名。

### 日本电脑给国内朋友用：Cloudflare Tunnel（推荐先试）

朋友**不用装 VPN**，用浏览器打开一个临时 HTTPS 链接即可。

更完整的复用说明（架构、Vite 配置、bat 模板、给其它库存系统照搬）见 **[docs/tunnel.md](docs/tunnel.md)**。

1. 本机先用 `start.bat` 启动，确认 http://localhost:5173 能打开  
2. 安装 [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)（或 `winget install --id Cloudflare.cloudflared`）  
3. 双击根目录 **`start-tunnel.bat`**（或执行 `cloudflared tunnel --url http://127.0.0.1:5173`）  
4. 窗口里会出现类似 `https://xxxx.trycloudflare.com` 的地址，把这个发给朋友  
5. **保持** Backend / Frontend / Tunnel 三个窗口都开着；关隧道窗口链接就失效  
6. 临时链接**每次重启都会变**；分享前建议设置 `ANIMEGOOD_ADMIN_TOKEN`

若浏览器出现 `Blocked request. This host is not allowed`：说明前端未用最新配置。请**关掉 Frontend 窗口再开**（或重跑 `start.bat`），再开一次 `start-tunnel.bat`。`vite.config.ts` 已允许 `*.trycloudflare.com`。

说明：流量从你日本电脑经 Cloudflare 出去，国内多数情况可打开；若个别网络打不开，再试 Tailscale。抓取仍在你本机执行。日志里 `cert.pem` / `config.yml` 对临时隧道可忽略，只要看到 `Your quick Tunnel has been created` 和 `Registered tunnel connection` 即表示隧道已通。

### 打开 /docs 看到的是 C-Lodop，不是本项目？

本机 **8000** 常被 C-Lodop（打印控件）占用。Animegood 后端在 **8001**：

- 正确：http://localhost:8001/docs
- 错误：http://localhost:8000/docs（那是 C-Lodop）

`start.bat`、`uvicorn --port 8001`、`vite.config.ts` 代理与 Docker 均已按 8001 配置。

### 页面空白 / 一直加载？

- 确认后端窗口没有报错，访问 http://localhost:8001/health 应返回 `{"status":"正常"}`
- 若刚改过后端代码，**重启 uvicorn** 再试

### 抓取全部失败（HTTP 500）？

- 看后端窗口具体报错；常见原因是后端未重启、虚拟环境未激活
- 在 http://localhost:8001/docs 单独试 `POST /api/scrape/run/mono-mo?limit=5`

### SHIBUYA TSUTAYA 抓取失败

- 在本机后端虚拟环境中执行：`playwright install chromium`
- 详情页有 Cloudflare，当前只抓列表页；失败不影响其他源
- 若错误为 **`NotImplementedError`**：多见 Windows 上 `uvicorn --reload` 与 Playwright 冲突；请**重启后端**（`start.bat` 会热重载代码）。仍失败时关掉后端窗口再开一次

### mono-mo / Anique 很慢？

- 开发模式建议设 `limit`（如 20），小批量测试
- 全量抓取会慢一些，属正常

### 并发抓取与资源占用

- 后端默认**同时抓取 3 个站点**（商品源与活动源各自并发；`POST /api/scrape/run` 会商品 + 活动并行）
- 可通过环境变量调整（须在启动 uvicorn **之前**设置，范围 1–8）：

```bash
# Windows PowerShell
$env:ANIMEGOOD_SCRAPE_CONCURRENCY = "2"

# macOS / Linux
export ANIMEGOOD_SCRAPE_CONCURRENCY=2
```

- **Playwright 源**（如 SHIBUYA TSUTAYA）每个实例较重，并发过高可能占满内存或 CPU；机器较弱时建议设为 `1` 或 `2`

### 收藏夹没了？

- 收藏在**本浏览器本地**，清站点数据、换浏览器或换电脑会丢失；全站热度计数仍在服务器数据库里
- 可在收藏夹页 **复制备份**，换设备后 **导入合并**（与购物车备份用法相同）

### 搜索卡顿或只看到一部分商品？

- 搜索约 **300ms 防抖**后再请求，避免中文输入法每个字都打接口
- 发现列表每页 **40** 条，底部点 **加载更多**；筛选变更会回到第 1 页

### 「系列」从哪来？筛选为空怎么办？

- 入库时从商品名自动解析（如 `○○シリーズ`、`『』` / `「」` 书名号、`【】` 企划名、圣诞/万圣节等活动前缀）
- 解析不到的商品 `series` 为空，不会出现在系列下拉框
- 旧数据在后端首次启动时会自动回填；之后新抓取会写入系列字段
- 详情页可点「系列：xxx」一键筛到同系列，或看「同系列其他商品」列表

### 购物车 / 收藏夹备份怎么用？

1. 在对应标签底部点 **复制备份**，得到 Base64 字符串
2. 在另一台设备打开同一站点，粘贴到 **导入** 文本框，点 **导入合并**
3. 格式为 `{ "v": 1, "items": [...] }` 的 JSON 再 Base64 编码；收藏最多 200 条，购物车最多 200 种

### 改完代码不生效？

- 后端：`uvicorn --reload` 多数会自动重载；抓取器大改建议手动重启
- 前端：Vite 一般热更新；不行就刷新页面

### 汇率显示「暂不可用」？

- 后端需能访问外网 `www.5waihui.com`；可在 http://localhost:8001/docs 试 `GET /api/exchange-rate`
- 该站表格由 JavaScript 填充，后端会在静态 HTML 为空时改读 `data/rmb.js`；若对方改版可能导致解析失败

---

## Docker 启动（可选）

```bash
docker compose up --build
```

- 前端：http://localhost:5173（容器内 Nginx 会把 `/api` 转到后端 `8001`）
- 健康检查：http://localhost:8001/health
- 抓取：`POST http://localhost:8001/api/scrape/run`

### 公网 VPS + 域名（简要）

1. 买一台 Ubuntu VPS，装 Docker：`sudo apt install -y docker.io docker-compose-plugin`
2. 域名 A 记录指到 VPS 公网 IP
3. 把本仓库放到服务器，执行 `docker compose up --build -d`
4. 安装宿主机 Nginx，用仓库里的 `deploy/nginx-vps.conf`（把 `YOUR_DOMAIN` 改成你的域名），反代到 `127.0.0.1:5173`
5. 申请 HTTPS：`sudo certbot --nginx -d 你的域名`
6. 云厂商安全组只开放 **22 / 80 / 443**（不必对公网开 8001、5173）

公网务必设置环境变量（可写在 `docker-compose.yml` 的 `environment` 或 `.env`）：

```bash
ANIMEGOOD_ADMIN_TOKEN=换成足够长的随机串
ANIMEGOOD_SCRAPE_INTERVAL_HOURS=6
```

上线后可用管理口令在页面点一次「拉取最新商品」，之后靠定时任务保持更新。定期备份 `backend/data/animegood.sqlite`。

---

## API 速查

所有业务接口前缀为 **`/api`**。完整说明见 http://localhost:8001/docs（中文标签）。

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/health` | 健康检查（也可用 `/api/health`） |
| GET | `/api/products` | 商品列表（含 `total` 总数） |
| GET | `/api/products/by-ids` | 按 ID 批量取商品（收藏夹刷新） |
| GET | `/api/filters` | 下拉筛选项（IP、店铺、系列、月份） |
| GET | `/api/events` | 活动资讯列表（首页轮播） |
| GET | `/api/exchange-rate` | 支付宝日元汇率（服务端缓存 1 小时） |
| GET | `/api/admin/status` | 是否需要管理口令、定时抓取间隔 |
| POST | `/api/products/{id}/favorite?delta=1\|-1` | 更新全站收藏热度 |
| GET | `/api/sources` | 数据源配置 |
| GET | `/api/source-registry` | 网站收录总览 |
| GET | `/api/runs` | 最近抓取记录 |
| POST | `/api/scrape/run` | 抓取商品（可选 `source_ids`、`incremental`、`include_events`） |
| POST | `/api/scrape/run/{source_id}` | 抓取单个源（可选 `incremental`） |
| POST | `/api/scrape/events/run` | 仅抓取活动资讯源（可选 `incremental`） |
| POST | `/api/admin/clear-scraped-data/prepare` | 清空数据（第一步，等 3 秒） |
| POST | `/api/admin/clear-scraped-data/confirm` | 清空数据（第二步，需 token） |

**商品列表常用查询参数：**

```text
GET /api/products?q=クリスマス&series=クリスマス&shop=mono-mo&available_only=true&sort=popular&limit=40&offset=0
```

| 参数 | 说明 |
|------|------|
| `q` | 关键词（商品名 / IP / 店铺 / 系列） |
| `ip` / `shop` / `series` / `release_month`（`YYYY-MM`） | 精确筛选 |
| `available_only=true` | 仅可购买 |
| `sort` | `newest` \| `popular` \| `price_asc` \| `price_desc` |
| `limit` / `offset` | 分页（前端发现页每页 40） |

**命令行小批量抓取：**

```bash
cd backend
.venv\Scripts\activate
python scripts/run_scrape.py
```

---

## 数据源配置

### 商品源：`backend/config/sources.json`

`enabled: true` 的源会参与「立即抓取」。

**当前默认启用的商品源：**

| ID | 平台 | 店铺 |
|----|------|------|
| `mono-mo` | Shopify | mono-mo |
| `animeshi` | Shopify | animeshi |
| `cocollabo` | Shopify | cocollabo |
| `qinocop` | Shopify | qinocop |
| `shop-anique` | Shopify | Anique Shop |
| `shop-yostar` | Yostar API | Yostar（明日方舟分类） |
| `shop-yostar-c108` | Yostar API | C108 通贩 |
| `csmcanvas` | BASE | CSM Canvas |
| `shibuyatsutaya` | STORES | SHIBUYA TSUTAYA（需 Playwright） |
| `miraithings` | おちゃのこ | mirai things |
| `pricafe` | おちゃのこ | プリカフェ |
| `i-rightsshop` | カラーミー | i-rightsshop |
| `vvstore` | EC-CUBE HTML | vvstore |
| `hakuichi` | EC-CUBE HTML | 白一 HAKUICHI |
| `shop-asobistore` | EC-CUBE HTML | ASOBI STORE |
| `medicos-e-shop` | EC-CUBE HTML | MEDICOS |
| `store-kadokawa` | FutureShop | カドカワストア |
| `hakusensha-shop` | EC-CUBE HTML | 白泉社 SHOP |

**仍关闭（待确认）：**

| ID | 原因 |
|----|------|
| `internetangel` | BASE 店铺页无商品链接，疑似停更 |

新增源流程：实现对应 `scrapers/` 模板 → 写入 `sources.json` → `enabled: false` 下单源实测 → 通过后改为 `true`。

### 活动源：`backend/config/event_sources.json`

与商品源分开；HTTP 抓取，不依赖 X API。当前默认：

| ID | 平台 | 说明 |
|----|------|------|
| `anique-news` | html-news | Anique Shop `/blogs/news`；卡片列表 + 正文「開催期間」，过期自动隐藏 |
| `animeshi-news` | html-news | animeshi `/blogs/news`；同上 |

**可选字段（按源配置）：**

| 字段 | 作用 |
|------|------|
| `include_keywords` | 非空时，标题/摘要须命中至少一个关键词才入库 |
| `exclude_keywords` | 命中任一项则丢弃；默认已排除「発送遅延」「配送遅延」「お届け遅延」「メンテナンス」等客服公告 |
| `title_min_length` | 标题最短长度，默认 `8` |

发货延迟、致歉、维护类公告（正文含「発送遅延」等）**不会入库**。重新「抓取活动资讯」时，还会把库里已匹配噪音词的旧条目隐藏。

在开发工具区点 **「抓取活动资讯」**，或调用 `POST /api/scrape/events/run`。

---

## 商品名翻译

含「缶バッジ / アクリルスタンド」等日文术语的商品名，会按 `backend/data/name_glossary.json` 做本地替换：有匹配则中文为主标题、原文以小字显示。

1. **展示时**：读取商品列表时即时对照术语表，无网络请求
2. **抓取时**：入库也会写入 `display_name_zh` 缓存（同样只走术语表）
3. 自行编辑 `name_glossary.json` 补充词条后，**刷新页面**即可生效

---

## IP 归一化

`backend/data/ip_aliases.json` 把商品标题里的别名归到标准 IP，便于筛选和比价。改完后重新抓取或等下次入库时生效。

---

## 维护说明

- **改功能时请同步更新本 README**，让没用过的人仍能按教程上手
- 后端 OpenAPI 描述（`main.py`）与前端行为不一致时，以实际代码为准，并修正文档
- 项目内 Cursor 规则 `.cursor/rules/readme-updates.mdc` 要求代理在交付改动时默认更新本文档相关章节

## 相关文档

- OpenAPI 交互文档：http://localhost:8001/docs
- 模块化约定：`.cursor/rules/modular-architecture.mdc`
