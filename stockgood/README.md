# Stockgood — 简洁进货与出库库存

本地库存工具，覆盖从网上下单到用户签收的五段流程。核心是**订单 + 明细行**；进库按单订单一包，出库按批次多箱（可合多单，箱内按订单二级分类）。不保存客户档案、地址。

当前版本见根目录 [`VERSION`](VERSION)；变更说明见 [`CHANGELOG.md`](CHANGELOG.md)。

## 产品定位（可服务器化 · 模式 B）

**目标**：单团队长期运营；员工 + 客户账号；**不做**多租户 / 自动下单。当前约 **v0.9.4**。

客户侧产品死规定见 [`docs/client-product-rules.md`](docs/client-product-rules.md)（入口、定金、双编号、`/me` 职责、已拍板细节与明确推迟项）。个人主页相关新能力（改昵称/密码、凭证上传、员工二次确认、未登录不可看单等）**已写入规范第 8 节待办，暂不开发**。

### 已落地

| 项 | 说明 |
|---|---|
| 部署 | Docker Compose、Nginx、备份脚本；见 [`docs/deploy.md`](docs/deploy.md) |
| 账号 | Cookie 登录；角色 `admin` / `warehouse` / `finance` / `customer`；客户门户 `/me` |
| 申请 | 须登录；「待付定金」（商品金额 30%）→ 确认付款后才变为「已提交」 |
| 双编号 | 全站 `SG-0001…`（后台台账/统计）+ 账户 `SGuid-0001…`（用户端只显示账户流水） |
| 统计 | 后台「统计」Tab：日/月单量、热门链接、花费用户、商品 IP |

### 明确未做

- 自动下单 / 付款对接（对接前：客户凭证 + 员工二次确认，见规范；代码待个人主页迭代）
- 多租户 SaaS
- 真实支付网关
- 详见 [`docs/client-product-rules.md`](docs/client-product-rules.md) 第 7–8 节

### 本地测试（影子库）

| 地址 / 账号 | 用途 |
|---|---|
| API `http://localhost:8003` | 影子库后端 |
| 前端热更新 `http://localhost:5175` | 开发界面（**不要**用 `8003/apply` 看开发页） |
| `customer@stockgood.local` / `Customer12` | 客户示例账号 |

单元测试（不写生产库、不写共享影子库）：

```text
cd backend
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

改 Pydantic 模型后重新生成前端类型：`python scripts/gen-api-types.py`（在 `stockgood/` 下，用 `backend/.venv`）。

## 能力

| 能力 | 说明 |
|---|---|
| 订单 + 明细 | 一笔注文番号下多行 SKU；状态以订单为准（由明细最慢状态汇总） |
| 五段状态 | 已下单 → 已发往仓库 → 在库 → 已发往用户 → 已签收；也可取消 |
| 下单汇率 / 财务 | 一单一汇率（手填，不实时查）；商品与订单运费同汇率折算 CNY；出库批次锁定货款应收；国际运费独立汇率；按批次登记已收/未收；财务页可看本月下单与本月出库汇总 |
| 发货费用明细 | 出库批次可导出 Excel（主表含箱号、**订单号**、品名、合计 JPY / CNY；子表 **对应订单** 按箱列出订单号） |
| 抓取批量导入 | 粘贴链接单批抓取后勾选并填数量导入；同注文番号归入同一订单 |
| 顾客申请下单 | 公开页 `/apply`（订单申请）：抓取导入同款批量清单 → 勾选提交；列表看进度；后台「申请单」确认后可选写入库存（可填下单汇率） |
| 进库 | 单订单维度：选一笔订单的明细行，登记一个进库包裹；确认到仓后在库 |
| 出库 | 一批次多箱；每箱独立箱号与运单；一箱可合多订单明细，界面按订单二级分组；不支持部分出库 |
| 官方物流跳转 | Yamato、佐川单号可打开官方查询页面；其他承运商仅保存单号 |
| 操作撤回 | 登记/批量导入、进出库、确认、取消等写入操作日志；可撤回最近一步 |
| 预计发货 | 按「年月 + 可选上中下旬」管理；可一键查看本月（与财务「本月下单/出库」口径不同） |

## 项目导航

给人和 AI 的快速入口。

| 文件 | 职责 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | AI 如何工作、修改规则、新会话如何恢复上下文 |
| [`README.md`](README.md) | 项目是什么、如何运行 |
| [`docs/CODE_INDEX.md`](docs/CODE_INDEX.md) | FEATURE 对应哪些代码、接口、数据库、页面 |
| [`docs/CHANGELOG_AI.md`](docs/CHANGELOG_AI.md) | 为什么这么改、当前开发状态、Session Handoff |

产品版本记录仍是 [`CHANGELOG.md`](CHANGELOG.md)，与 `CHANGELOG_AI.md` 职责不同。

本项目用 `FEATURE: XXXXX` 标记业务功能。修改某功能时：先查 FEATURE → 读 CODE_INDEX → 搜 CHANGELOG_AI 历史 → 只打开相关文件。

### 项目结构

```text
frontend/          React + Vite 界面（端口 5174）
backend/           FastAPI + SQLite（端口 8002）
backend/app/       路由、模型、服务、抓取
backend/data/      数据库、模板、备份（勿提交密钥）
docs/              部署、产品规范、代码索引、AI 开发上下文
scripts/           启停、备份、隧道、托盘
deploy/            Docker / systemd
```

| 目录 / 文件 | 用途 |
|---|---|
| `frontend/src/App.tsx` | 员工主界面（多 Tab，无独立出库页文件） |
| `frontend/src/ApplyPage.tsx` | 顾客申请 `/apply` |
| `frontend/src/MePage.tsx` | 客户门户 `/me` |
| `frontend/src/api.ts` | 前端全部 HTTP 封装 |
| `backend/app/main.py` | FastAPI 全部 endpoint |
| `backend/app/services/` | 业务逻辑 |
| `backend/app/database.py` | SQLite 连接与建表 |
| `backend/app/models.py` | Pydantic 请求/响应 |

### 功能总览

| FEATURE | 功能 | 前端入口 | 后端入口 | 主要接口 | 数据库 |
|---|---|---|---|---|---|
| AUTH | 登录/注册/会话 | `AuthPanel.tsx` | `auth.py` | `/api/auth/*` | `users`, `sessions` |
| USER_MANAGEMENT | 用户管理 | `App.tsx` Tab 用户 | `main.py` + `auth.py` | `/api/users*` | `users` |
| CUSTOMER_PORTAL | 客户门户 | `/me` `MePage.tsx` | `order_requests.py` | `/api/me/order-requests*` | `order_requests` |
| ORDER | 库存订单 | `App.tsx` Tab 订单 | `orders.py` / `items.py` | `/api/orders*`, `/api/items*` | `orders`, `items` |
| ORDER_IMPORT | 抓取导入 | `App.tsx` Tab 抓取 | `scrapers/preview.py` | `POST /api/scrape` | `orders`, `items` |
| ORDER_REQUEST | 顾客申请 | `/apply`；Tab 申请单 | `order_requests.py` | `/api/public/order-requests*` | `order_requests` |
| INBOUND | 进库 | `App.tsx` Tab 进库 | `shipments.py` | `POST /api/orders/{id}/inbound` | `shipments` |
| INVENTORY | 库存合箱 | `App.tsx` Tab 库存 | `stock_boxes.py` | `/api/stock-boxes*` | `stock_boxes` |
| OUTBOUND_BATCH | 批次出库 | `App.tsx` Tab 出库 | `outbound_batches.py` | `/api/outbound-batches*` | `outbound_batches` |
| INV_EXPORT | 导出 INV | 出库「导出 INV」 | `inv_template.py` | `.../inv.xlsx` | 只读批次/箱 |
| FEE_DETAIL | 费用明细 Excel | 出库「费用明细 Excel」 | `outbound_batches.py` | `.../fee-detail.xlsx` | 只读批次 |
| FINANCE | 财务汇总 | Tab 财务；出库运费 | `finance.py` | `/api/finance/summary` | 订单汇率、批次财务列 |
| APPLY_STATS | 申请统计 | Tab 统计 | `apply_stats.py` | `GET /api/reports/apply` | `order_requests` |
| ACTION_LOG | 操作撤回 | 顶部撤回条；Tab 日志 | `action_log.py` | `/api/action-logs*` | `action_logs` |
| TUNNEL | Cloudflare 隧道 | 页头隧道按钮 | `tunnel_status.py` | `/api/tunnel*` | 无 |
| SYSTEM | 健康/元信息/种类 | 启动时 `fetchMeta` | `main.py` | `/api/health`, `/api/meta` | 无 |

完整表与调用链：[`docs/CODE_INDEX.md`](docs/CODE_INDEX.md)。

### 前端页面索引

| 页面/功能 | FEATURE | 文件 | API |
|---|---|---|---|
| 员工主界面 | 多个 Tab | `frontend/src/App.tsx` | 见各 FEATURE |
| 登录框 | AUTH | `frontend/src/AuthPanel.tsx` | `login`, `registerCustomer` |
| 订单申请 `/apply` | ORDER_REQUEST | `frontend/src/ApplyPage.tsx` | `publicScrapeUrl`, `createOrderRequest` |
| 客户门户 `/me` | CUSTOMER_PORTAL | `frontend/src/MePage.tsx` | `fetchMyOrderRequests`, `confirmDeposit` |
| 路由分流 | SHARED | `frontend/src/main.tsx` | — |

### 前端 API 索引

封装集中在 `frontend/src/api.ts`。按 FEATURE 搜索函数名即可。常用：

| API函数 | FEATURE | 后端接口 |
|---|---|---|
| `login` / `logout` / `fetchMe` | AUTH | `/api/auth/*` |
| `fetchOrders` / `createOrder` | ORDER | `/api/orders` |
| `scrapeUrl` / `createItemsBatch` | ORDER_IMPORT | `/api/scrape`, `/api/items/batch` |
| `createOutboundBatch` | OUTBOUND_BATCH | `POST /api/outbound-batches` |
| `downloadOutboundInv` | INV_EXPORT | `GET .../inv.xlsx` |
| `downloadOutboundFeeDetail` | FEE_DETAIL | `GET .../fee-detail.xlsx` |

### 后端接口索引

完整 OpenAPI：http://localhost:8002/docs 。实现文件均为 `backend/app/main.py`，业务在 `backend/app/services/`。

### 数据库索引

表定义：`backend/app/database.py` `init_db()`。部分列由 `_ensure_column` 迁移补齐（如 `invoice_ship_date`、包装尺寸）。详见 CODE_INDEX「数据库索引」。

### AI 快速使用方式

需要修改某个功能时，优先：

1. 查找 FEATURE
2. 阅读 `docs/CODE_INDEX.md`
3. 在 `docs/CHANGELOG_AI.md` 搜索同一 FEATURE 的历史
4. 阅读对应前端/后端文件
5. 检查相关接口和数据库
6. 修改前确认影响范围

新会话示例：

```text
这是新会话，请读取 AGENTS、CODE_INDEX 和 CHANGELOG_AI，然后继续上次未完成工作。
```

```text
先看最近一次 Session Handoff，然后继续开发。
```

```text
先恢复项目上下文，再处理 FEATURE: INV_EXPORT。
```

```text
读取 FEATURE: INV_EXPORT 的全部相关代码。
```

```text
修改 FEATURE: OUTBOUND_BATCH。
先根据 docs/CODE_INDEX.md 确定影响范围，
只读取和修改相关文件。
```

```text
找到「出库 → 导出 INV」按钮从前端到数据库的完整调用链。
```

```text
完成后做一次 Context Checkpoint。
把这次重要设计决策记录进 CHANGELOG_AI。
```

## 启动

### 安装依赖

**后端**

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**前端**

```bat
cd frontend
npm install
```

### 运行

在项目根目录运行：

```bat
start.bat
```

后台静默启动（无常驻 CMD 窗口），日志在 `logs\`，并会打开浏览器。

#### 系统托盘（推荐日常 / 开机自启）

```bat
start-tray.bat
```

- 右下角托盘常驻（青绿色图标）
- 菜单：打开界面 / 打开 API 文档 / 停止并退出
- **不**自动打开浏览器；默认生产库
- 退出托盘会停止 8002 / 5174 并做库备份
- 日志：`logs\tray.log`（另有 backend/frontend 日志）

开机自启（当前 Windows 用户，登录后启动托盘）：

```bat
install-autostart.bat
```

取消自启：

```bat
uninstall-autostart.bat
```

| 启动 | 数据库 |
|---|---|
| `start.bat` | 实际库存 `stockgood.sqlite` |
| `start-tray.bat` | 实际库存（托盘；可用环境变量 `STOCKGOOD_DB_MODE=shadow`） |
| `start-shadow.bat` | 测试影子库 `stockgood.shadow.sqlite`（采购导入等，不参与实库存） |

一键关闭：

```bat
stop.bat
```

（托盘运行时也可用托盘「停止并退出」，或 `stop.bat` 后再关托盘。）

| 地址 | 用途 |
|---|---|
| http://localhost:5174 | 界面 |
| http://localhost:8002/docs | API 文档 |

数据保存在 `backend/data/stockgood.sqlite`。已有数据库会在启动时把旧的 `in_transit` 状态迁移为 `inbound_shipped`。

**自动备份**：`start.bat` / `stop.bat` 会各做一次 SQLite 快照，目录为 `backend/data/backups/`（文件名含时间与 `start`/`stop`；每种库最多保留约 30 份）。

### 给国内朋友用（Cloudflare 临时隧道）

日本 / 海外电脑跑本机服务，国内用浏览器打开，对方无需 VPN。

1. 安装一次 [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)（或 `winget install --id Cloudflare.cloudflared`）
2. 双击根目录 **`start-tunnel.bat`**  
   - 若本机尚未启动，会自动后台拉起前后端，再开隧道  
   - 日志里找到 `https://xxxx.trycloudflare.com`，把该链接发给朋友  
3. **保持隧道窗口开着**；关掉 = 链接失效。本地服务用 `stop.bat` 关闭  
4. 临时 URL **每次重启都会变**；链接等于短暂公网入口，用完即关
5. **发给顾客的链接必须带 `/apply`**：`<隧道域名>/apply`（页头点「复制申请页」即可）。不要发根路径，否则会打开库存管理。

若出现 `Blocked request. This host is not allowed`：请重启前端（`stop.bat` 后再 `start.bat` / `start-tunnel.bat`）。`vite.config.ts` 已允许 `*.trycloudflare.com`。

可选：在 `backend/.env` 设置 `STOCKGOOD_ADMIN_TOKEN=...`（兼容旧口令），或配置用户登录（见下）。公开 scrape / 提交申请有 IP 限流。

### 账号与服务器部署

- **本地默认**：无员工账号、未强制 `STOCKGOOD_AUTH_REQUIRED` 时，员工 API 仍可无登录使用。
- **登录**：员工在管理页登录（角色 `admin` / `warehouse` / `finance`）；客户 `/me` 注册/登录；申请 `/apply` **须登录**，提交后为「待付定金」，确认付款后才「已提交」。
- **服务器**：见 [`docs/deploy.md`](docs/deploy.md)（Docker Compose + Nginx + 日备）。首启用 `STOCKGOOD_BOOTSTRAP_ADMIN_EMAIL` / `PASSWORD` 创建管理员。

## 使用流程

1. 到 **订单** 登记，或 **抓取导入** 勾选清单后导入。填写 **下单汇率**（手填）与日元单价/运费后，列表会显示折算 CNY。
2. 到 **进库** 选择「已下单」货品，选择 Yamato、佐川急便或其他承运商，填写单号并登记。
   货品会变成「已发往仓库」。
3. 在同一页的待确认包裹中点「确认到仓」，整包货品变成「在库」。
4. 到 **出库** 选择在库货品分箱、填运单；可选填国际运费（运费汇率 / 单价 JPY / 计费重量）。创建批次时锁定货款应收 CNY。
5. 在出库批次上登记已收款、保存国际运费，或点「费用明细 Excel」导出给客户的发货费用明细。
6. 在出库页点「确认签收」，整包货品变成「已签收」。
7. 到 **财务** 查看指定月份的「本月下单金额」与「本月出库应收/已收/未收」。

误操作时：顶部会出现「最近操作」条，点「撤回」可撤销最近一步；也可在 **操作日志** Tab 查看历史。仅允许撤回最近一条未撤回记录，且货品状态未被后续操作改动。

一个追踪号可关联多件货品，但全局保持唯一。每件货可各自关联一个进库包裹和一个出库包裹。

### 财务口径（简要）

| 项目 | 规则 |
|---|---|
| 下单汇率 | 一单一汇率；商品与订单运费共用 |
| 国际运费 | 出库批次独立汇率：`运费单价(JPY) × 计费重量 × 运费汇率` |
| 应收锁定 | 出库**创建**时锁定货款应收；收款挂在出库批次 |
| 本月下单 | 按订单 `ordered_at` 所属月 |
| 本月出库 | 按出库批次 `created_at` 所属月 |

## 物流与抓取说明

- Yamato 跳转到其官方查询 URL；佐川急便也跳转到官方查询 URL。界面的「查物流」在新标签页打开。
- 应用不会抓取 Yamato 或佐川的物流轨迹页面，也不会用 iframe 嵌入这些页面。
- Shopify 店铺根页或 `/products` 通过 `products.json` 最多抓取 5 页（约 250 件）；系列页通过 collection `products.json` 抓取；单品页同样返回单元素列表。
- 其他站点使用页面元数据（`og:title`、`og:image`）和简单价格解析，导入前请核对。后端依赖已包含 `httpx`、`beautifulsoup4`；费用明细导出另需 `openpyxl`（见 `requirements.txt`）。

## API 速查

前缀为 `/api`。完整列表见 http://localhost:8002/docs 。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/stats` | 五段状态与待确认进/出库包裹统计 |
| GET/POST | `/api/orders` | 订单列表 / 新建（含 `exchange_rate`、运费等） |
| PATCH | `/api/orders/{id}` | 更新订单（含下单汇率） |
| GET | `/api/items` | 货品列表；参数 `status`、`shop`、`q`、`expected_ship_month`（YYYY-MM） |
| POST | `/api/items` | 手动新建货品 |
| POST | `/api/items/batch` | 批量导入 `{ "items": [...] }` |
| POST | `/api/scrape` | `{ "url": "..." }`，始终返回 `{ products: [...] }` |
| PATCH | `/api/items/{id}` | 更新明细（含取消等） |
| GET | `/api/shipments` | 包裹列表；参数 `status`、`tracking_no`、`direction` |
| POST | `/api/shipments` | `{ tracking_no, direction, carrier, item_ids }` |
| GET | `/api/shipments/{id}` | 包含官方 `tracking_url`（可用时） |
| POST | `/api/shipments/{id}/confirm` | 按包裹方向确认到仓或签收 |
| GET/POST | `/api/outbound-batches` | 出库批次列表 / 新建（创建时锁定货款应收） |
| PUT | `/api/outbound-batches/{id}` | 未签收前编辑批次（箱/商品/数量） |
| PATCH | `/api/outbound-batches/{id}/finance` | 更新国际运费或已收款 |
| GET | `/api/outbound-batches/{id}/inv.xlsx` | 导出 INV 发货单 |
| POST | `/api/outbound-batches/preview-inv.xlsx` | 创建前按草稿预览导出 INV |
| GET | `/api/outbound-batches/{id}/fee-detail.xlsx` | 导出发货费用明细 Excel |
| GET | `/api/finance/summary` | 财务月汇总；参数 `month`（YYYY-MM） |
| GET | `/api/action-logs` | 操作日志；参数 `limit` |
| GET | `/api/action-logs/latest` | 最近一条可撤回日志（或 null） |
| POST | `/api/action-logs/{id}/undo` | 撤回该条（须为最新未撤回） |

`direction` 为 `inbound` 或 `outbound`；`carrier` 为 `yamato`、`sagawa` 或 `other`。

可撤回类型：`create_item`、`create_items_batch`、`create_shipment`、`confirm_shipment`、`cancel_item` 等（见操作日志）。

## 刻意不做

- 客户档案、收货地址
- 实时汇率查询 / 自动扣款 / 完整会计账
- 爬取承运商 HTML 物流轨迹
- iframe 内嵌承运商页面
- 自动根据承运商物流状态推进货品状态
- 与 animegood 共用数据库或进程
