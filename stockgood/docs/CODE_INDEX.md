# Code Index

本文件是 Stockgood 的代码地图。

- `README.md`：项目是什么、如何运行
- `AGENTS.md`：Agent 怎么工作
- 本文件：FEATURE 对应哪些代码
- `docs/CHANGELOG_AI.md`：为什么这么改、当前状态、Session Handoff

新会话或较大改动前：先读 CODE_INDEX 定位，再搜 `CHANGELOG_AI.md` 里同一 `FEATURE: XXXXX` 的历史。

路径均相对仓库内 `stockgood/`。前端主界面是单文件多 Tab：`frontend/src/App.tsx`（没有独立 `*Page.tsx` 出库页）。

## 功能目录

- [FEATURE: AUTH](#feature-auth)
- [FEATURE: USER_MANAGEMENT](#feature-user_management)
- [FEATURE: CUSTOMER_PORTAL](#feature-customer_portal)
- [FEATURE: ORDER](#feature-order)
- [FEATURE: ORDER_IMPORT](#feature-order_import)
- [FEATURE: ORDER_REQUEST](#feature-order_request)
- [FEATURE: INBOUND](#feature-inbound)
- [FEATURE: INVENTORY](#feature-inventory)
- [FEATURE: OUTBOUND_BATCH](#feature-outbound_batch)
- [FEATURE: INV_EXPORT](#feature-inv_export)
- [FEATURE: FEE_DETAIL](#feature-fee_detail)
- [FEATURE: FINANCE](#feature-finance)
- [FEATURE: APPLY_STATS](#feature-apply_stats)
- [FEATURE: ACTION_LOG](#feature-action_log)
- [FEATURE: TUNNEL](#feature-tunnel)
- [FEATURE: SYSTEM](#feature-system)
- [SHARED MODULES](#shared-modules)

---

### 未确认 / 前端未接线

- `GET /api/order-requests/{request_id}`：员工列表多用列表接口；**前端未调用详情接口**
- `POST /api/shipments`：通用建单；**进库 UI 走** `POST /api/orders/{id}/inbound`
- `frontend/src/api.ts` 中 `createItem()`、`fetchOrderRequestByCode()`：**已封装，页面未调用**
- 前端单元测试：未见 `*.test.ts` / `*.spec.ts`

### 待实现 / 旧行为（不是 bug）

规范第 8 节已确定、代码未落地。现码仍走旧定金确认流程，不要擅自改成规范新行为：

- `/me` 改昵称 / 改密码（`POST /api/auth/change-password` 后端有、前端未接）
- 定金凭证截图 + 支付单号、员工二次确认
- 未登录不可查看公开申请列表

---

## FEATURE: AUTH

### 功能说明

Cookie 会话登录、登出、当前用户、客户自助注册。可选环境变量要求登录。

### 用户入口

- 员工主界面未登录时 `AuthPanel`（`allowRegister=false`）
- `/apply`、`/me` 上的登录/注册（`allowRegister` 因页而异）

### 前端页面

- `frontend/src/AuthPanel.tsx`
- `frontend/src/App.tsx`（页头登录态、logout）
- `frontend/src/ApplyPage.tsx`
- `frontend/src/MePage.tsx`

### 前端 API

- `frontend/src/api.ts`
  - `login()` → `POST /api/auth/login`
  - `logout()` → `POST /api/auth/logout`
  - `registerCustomer()` → `POST /api/auth/register`
  - `fetchMe()` → `GET /api/auth/me`
  - `getAdminToken()` / `setAdminToken()`（遗留 `X-Admin-Token`，与 Cookie 并存）

### 后端接口

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/register`
- `POST /api/auth/change-password`（后端有；**前端未调用**）

### 后端实现

- `backend/app/main.py`（账号路由）
- `backend/app/auth.py`（密码、session、角色依赖 `require_staff` 等）
- `backend/app/auth_context.py`
- `backend/app/admin_auth.py`（遗留管理员 token）

### 数据模型

- `backend/app/models.py`：`LoginIn`、`RegisterCustomerIn`、`ChangePasswordIn`、`UserOut`

### 数据库

- `users`
- `sessions`

### 测试

- 未确认独立 AUTH 单测；本地冒烟依赖影子库账号

### 调用链

`AuthPanel` → `login()` / `registerCustomer()` → `/api/auth/*` → `auth.py` → `users` / `sessions`

### 依赖关系

被几乎所有员工功能依赖。注册后进入 `ORDER_REQUEST` / `CUSTOMER_PORTAL`。

### 修改风险

改 Cookie / 角色依赖会影响全部需登录接口。改密接口若接线需同步 `CUSTOMER_PORTAL`。

---

## FEATURE: USER_MANAGEMENT

### 功能说明

管理员在主界面「用户」Tab 列出、创建员工/客户、启用/停用。

### 用户入口

`App.tsx` Tab `users`（仅 `authUser.role === "admin"`）

### 前端

- `frontend/src/App.tsx`（`tab === "users"`）
- `frontend/src/api.ts`：`fetchUsers`、`createUser`、`setUserActive`

### 后端接口

- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/{user_id}/active`

### 后端实现

- `backend/app/main.py`
- `backend/app/auth.py`：`list_users`、`create_user`、`set_user_active`

### 数据库

- `users`

### 依赖关系

依赖 `AUTH`。创建的 `customer` 用于申请下单。

---

## FEATURE: CUSTOMER_PORTAL

### 功能说明

登录客户查看自己的申请、确认定金。路由 `/me`。

### 用户入口

浏览器 `/me`；`frontend/src/main.tsx` 按路径挂载 `MePage`。

### 前端

- `frontend/src/MePage.tsx`
- `frontend/src/AuthPanel.tsx`
- `frontend/src/api.ts`：`fetchMe`、`fetchMyOrderRequests`、`confirmDeposit`

### 后端接口

- `GET /api/auth/me`
- `GET /api/me/order-requests`
- `POST /api/me/order-requests/{code}/confirm-deposit`

### 后端实现

- `backend/app/services/order_requests.py`

### 数据库

- `order_requests`（`user_id`）
- `users` / `sessions`

### 相关文档

- `docs/client-product-rules.md`（第 8 节已确定、代码未落地；现码为旧行为，不是 bug）

### 依赖关系

`AUTH`、`ORDER_REQUEST`

### 待实现 / 旧行为

改昵称 / 改密码 / 定金凭证上传 / 员工二次确认 / 未登录公开列表：规范第 8 节待实现，现码仍为旧定金流程。不要擅自改。

---

## FEATURE: ORDER

### 功能说明

库存订单列表、搜索、筛选、新建、编辑、追加明细、状态统计。订单状态由明细最慢状态汇总。

### 用户入口

主界面 Tab「订单」。

### 前端

- `frontend/src/App.tsx`（`tab === "orders"`；`onSearch`、`createOrder`、`updateOrder`、`updateItem`）
- `frontend/src/api.ts`：`fetchOrders`、`createOrder`、`updateOrder`、`fetchItems`、`updateItem`、`fetchStats`、`fetchShops`、`fetchProductKinds`

### 后端接口

- `GET /api/orders`
- `POST /api/orders`
- `GET /api/orders/{order_id}`
- `PATCH /api/orders/{order_id}`
- `POST /api/orders/{order_id}/lines`
- `GET /api/items`
- `POST /api/items`
- `GET /api/items/{item_id}`
- `PATCH /api/items/{item_id}`
- `GET /api/stats`
- `GET /api/shops`
- `GET /api/product-kinds`

### 后端实现

- `backend/app/services/orders.py`
- `backend/app/services/items.py`
- `backend/app/services/order_status.py`
- `backend/app/product_kind.py`

### 数据模型

- `OrderCreate` / `OrderUpdate` / `OrderOut` / `LineCreate` / `ItemCreate` / `ItemUpdate` / `ItemOut` / `StatsOut`

### 数据库

- `orders`
- `items`（含迁移列：`barcode`、`ip`、`product_kind`、`image_url`、`source_url`、`expected_ship_*` 等）

### 调用链

订单 Tab → `fetchOrders()` → `GET /api/orders` → `orders_svc.list_orders` → `orders` + `items`

### 依赖关系

被 `INBOUND`、`INVENTORY`、`OUTBOUND_BATCH`、`FINANCE`、`ORDER_IMPORT` 使用。

---

## FEATURE: ORDER_IMPORT

### 功能说明

粘贴商品 URL / HTML 抓取预览，勾选后批量写入货品/订单。

### 用户入口

主界面 Tab「抓取」。顾客申请页另有公开抓取（见 `ORDER_REQUEST`）。

### 前端

- `frontend/src/App.tsx`（`tab === "scrape"`）
- `frontend/src/scrapeDelay.ts`
- `frontend/src/api.ts`：`scrapeUrl`、`createItemsBatch`

### 后端接口

- `POST /api/scrape`
- `POST /api/items/batch`

### 后端实现

- `backend/app/scrapers/preview.py`（`scrape_url`、`scrape_html_document`）
- `backend/app/scrapers/*.py`（站点特化：zozo、hmv、hobbysearch 等）
- `backend/app/services/items.py`：`create_items_batch`

### 测试

- `backend/test_retailer_scrapers.py`
- `backend/test_zozo_order.py`

### 依赖关系

写入 `ORDER`（`orders`/`items`）。公开抓取 `POST /api/public/scrape` 同属抓取引擎，入口在 `ORDER_REQUEST`。

---

## FEATURE: ORDER_REQUEST

### 功能说明

顾客申请：登录后提交 → 待付定金（约 30%）→ 确认后 submitted → 员工确认下单或拒绝。可选生成库存订单。

### 用户入口

- 公开页 `/apply`（`ApplyPage.tsx`）
- 员工 Tab「申请单」
- 客户 `/me` 确认定金（`CUSTOMER_PORTAL`）

### 前端

- `frontend/src/ApplyPage.tsx`
- `frontend/src/App.tsx`（`tab === "requests"`）
- `frontend/src/api.ts`：`publicScrapeUrl`、`createOrderRequest`、`fetchPublicOrderRequests`、`fetchOrderRequestByCode`、`fetchOrderRequests`、`confirmOrderRequest`、`rejectOrderRequest`、`staffConfirmDeposit`、`confirmDeposit`

### 后端接口

- `POST /api/public/scrape`
- `POST /api/public/order-requests`
- `GET /api/public/order-requests`
- `GET /api/public/order-requests/{code}`
- `GET /api/order-requests`
- `GET /api/order-requests/{request_id}`
- `POST /api/order-requests/{request_id}/confirm-ordered`
- `POST /api/order-requests/{request_id}/reject`
- `POST /api/order-requests/{request_id}/confirm-deposit`

### 后端实现

- `backend/app/services/order_requests.py`
- 确认下单可调用 `orders_svc.create_order`

### 数据库

- `order_requests`（含 `account_order_no`、`deposit_*`、`user_id`、`stock_order_id` 等迁移列）

### 依赖关系

`AUTH`、`ORDER_IMPORT`（公开抓取）、确认后可创建 `ORDER`。统计见 `APPLY_STATS`。

---

## FEATURE: INBOUND

### 功能说明

按订单创建进库运单，确认到仓后货品变为在库。

### 用户入口

主界面 Tab「进库」。订单页也可跳到进库（`setTab("inbound")`）。

### 前端

- `frontend/src/App.tsx`（`tab === "inbound"`）
- `frontend/src/api.ts`：`fetchItems`、`fetchShipments`、`createOrderInbound`、`confirmShipment`

### 后端接口

- `POST /api/orders/{order_id}/inbound`
- `GET /api/shipments`
- `GET /api/shipments/{shipment_id}`
- `POST /api/shipments/{shipment_id}/confirm`
- `POST /api/shipments`（通用建单；**进库 UI 未使用**，走按订单进库）

### 后端实现

- `backend/app/services/shipments.py`
- `backend/app/tracking_links.py`

### 数据库

- `shipments`（`direction=inbound`）
- `shipment_items`
- `items.status`

### 依赖关系

前置 `ORDER`；确认后可供 `INVENTORY` / `OUTBOUND_BATCH`。

---

## FEATURE: INVENTORY

### 功能说明

在库货品查看；库存合箱（不改货品状态，与出库分箱独立）。主箱/子箱、并入、移出、解散。

### 用户入口

主界面 Tab「库存」。

### 前端

- `frontend/src/App.tsx`（`tab === "inventory"`）
- `frontend/src/api.ts`：`fetchStockBoxes`、`createStockBox`、`combineStockBox`、`addStockBoxOrders`、`updateStockBox`、`removeStockBoxOrders`、`deleteStockBox`、`mergeStockBoxChild`、`detachStockBoxChild`、`fetchItems`

### 后端接口

- `GET/POST /api/stock-boxes`
- `POST /api/stock-boxes/combine`
- `GET/PATCH /api/stock-boxes/{box_id}`
- `POST /api/stock-boxes/{box_id}/orders`
- `POST /api/stock-boxes/{box_id}/remove-orders`
- `DELETE /api/stock-boxes/{box_id}`
- `POST /api/stock-boxes/{parent_id}/merge-child`
- `POST /api/stock-boxes/{child_id}/detach-parent`

### 后端实现

- `backend/app/services/stock_boxes.py`

### 数据库

- `stock_boxes`
- `stock_box_orders`

### 测试

- `backend/_smoke_add_to_box.py`

### 依赖关系

读取在库 `ORDER`/`items`。出库选单会用库存合箱分组（`OUTBOUND_BATCH`）。

---

## FEATURE: OUTBOUND_BATCH

### 功能说明

出库批次：草稿分箱、同一批次共用运单号、包装尺寸、创建锁定货款应收、未签收前编辑、整批签收。

### 用户入口

主界面 Tab「出库」。

按钮（均在该 Tab）：

- 「创建出库批次」→ `createOutboundBatch`
- 「编辑批次」→ `updateOutboundBatch`
- 「确认整批签收」→ `confirmOutboundBatch`
- 「导出 INV」→ `INV_EXPORT`
- 「费用明细 Excel」→ `FEE_DETAIL`

### 前端

- `frontend/src/App.tsx`（`tab === "outbound"`；草稿 `localStorage` key `stockgood.outboundDraft.v1`）
- `frontend/src/api.ts`：`fetchOutboundBatches`、`createOutboundBatch`、`updateOutboundBatch`、`confirmOutboundBatch`、`updateOutboundBatchFinance`

### 后端接口

- `GET /api/outbound-batches`
- `POST /api/outbound-batches`
- `GET /api/outbound-batches/{batch_id}`
- `PUT /api/outbound-batches/{batch_id}`
- `POST /api/outbound-batches/{batch_id}/confirm`
- `PATCH /api/outbound-batches/{batch_id}/finance`（财务字段，见 `FINANCE`）

### 后端实现

- `backend/app/services/outbound_batches.py`：`create_batch`、`update_batch`、`confirm_batch`、`list_batches`、`get_batch`

### 数据模型

- `OutboundBatchCreate` / `Update` / `Out`、`OutboundBoxCreate` / `Update` / `Out`

### 数据库

- `outbound_batches`（含财务列、`invoice_ship_date` 迁移列）
- `shipments`（`direction=outbound`，`batch_id`，包装列 `net_weight` 等）
- `shipment_items`
- `items`（状态改为 `outbound_shipped` / `delivered`）

### 调用链

出库 Tab → `createOutboundBatch()` → `POST /api/outbound-batches` → `create_batch()` → `outbound_batches` + `shipments` + `shipment_items` + 更新 `items`

### 依赖关系

依赖在库 `ORDER`/`INVENTORY`。导出见 `INV_EXPORT`、`FEE_DETAIL`。运费/收款见 `FINANCE`。

### 修改风险

改运单唯一规则、分箱、数量会影响库存状态、货款锁定、INV/费用表。

---

## FEATURE: INV_EXPORT

### 功能说明

基于固定双 Sheet 模板导出 INV（`inv` + `PACKING LIST `）。草稿预览批次段为 `0`。

### 用户入口

出库 Tab：「导出 INV」（已有批次）、「导出 INV」（创建前预览）。

### 前端

- `frontend/src/App.tsx`：`onExportDraftInv`、`downloadOutboundInv`
- `frontend/src/api.ts`：`downloadOutboundInv`、`downloadOutboundInvPreview`

### 后端接口

- `GET /api/outbound-batches/{batch_id}/inv.xlsx`
- `POST /api/outbound-batches/preview-inv.xlsx`

### 后端实现

- `backend/app/services/outbound_batches.py`：`export_inv_xlsx`、`export_inv_preview_xlsx`
- `backend/app/services/inv_template.py`：`build_inv_workbook`
- 模板（只读）：`backend/data/templates/inv_fit_shipping.xlsx`

### 数据库

读 `outbound_batches`、`shipments` 包装字段、`items`（条码、种类、单价、数量）。不写库。

### 调用链

按钮「导出 INV」→ `downloadOutboundInv(id)` → `GET .../inv.xlsx` → `export_inv_xlsx` → `build_inv_workbook` → 模板填数 → xlsx bytes

### 依赖关系

`OUTBOUND_BATCH`。种类英文映射在 `inv_template.KIND_EN`。

---

## FEATURE: FEE_DETAIL

### 功能说明

发货费用明细 Excel：主表货品金额 + 子表「对应订单」（按箱号列出订单）。

### 用户入口

出库 Tab 按钮「费用明细 Excel」（权限：财务角色依赖 `require_finance`）。

### 前端

- `frontend/src/App.tsx`：`downloadOutboundFeeDetail`
- `frontend/src/api.ts`：`downloadOutboundFeeDetail`

### 后端接口

- `GET /api/outbound-batches/{batch_id}/fee-detail.xlsx`

### 后端实现

- `backend/app/services/outbound_batches.py`：`export_fee_detail_xlsx`
- 模板（只读）：`backend/data/templates/fee_detail.xlsx`（Sheet：`发货费用明细`、`对应订单`）

### 数据库

只读批次/箱/货品/订单汇率。不写库。

### 依赖关系

`OUTBOUND_BATCH`、`FINANCE`（底部运费汇总读批次财务字段）。

### 相关脚本

- `backend/_enrich_fee_detail.py`（历史手工 enrich，**不是**线上导出路径）

---

## FEATURE: FINANCE

### 功能说明

订单下单汇率折算 CNY；出库批次国际运费与已收款；财务 Tab 月汇总。

### 用户入口

- Tab「财务」
- 出库批次上的运费/收款表单

### 前端

- `frontend/src/App.tsx`（`tab === "finance"`；出库内 `updateOutboundBatchFinance`）
- `frontend/src/api.ts`：`fetchFinanceSummary`、`updateOutboundBatchFinance`

### 后端接口

- `GET /api/finance/summary`
- `PATCH /api/outbound-batches/{batch_id}/finance`

### 后端实现

- `backend/app/services/finance.py`
- `backend/app/services/outbound_batches.py`：`update_finance`

### 数据库

- `orders.exchange_rate`、`shipping_fee`
- `outbound_batches` 财务列

### 测试

- `backend/_smoke_finance.py`

### 依赖关系

`ORDER`、`OUTBOUND_BATCH`、`FEE_DETAIL`

---

## FEATURE: APPLY_STATS

### 功能说明

申请单日/月统计：单量、热门链接、花费用户、IP。

### 用户入口

主界面 Tab「统计」（`reports`）。

### 前端

- `frontend/src/App.tsx`（`tab === "reports"`）
- `frontend/src/api.ts`：`fetchApplyReport`

### 后端接口

- `GET /api/reports/apply`

### 后端实现

- `backend/app/services/apply_stats.py`

### 数据库

读 `order_requests`（按创建时间）。

### 依赖关系

`ORDER_REQUEST`

---

## FEATURE: ACTION_LOG

### 功能说明

写操作记日志；可撤回最近一步。

### 用户入口

主界面顶部撤回条；Tab「日志」。

### 前端

- `frontend/src/App.tsx`：`undoActionLog`、`fetchActionLogs`、`fetchLatestActionLog`
- `frontend/src/api.ts`：同名函数

### 后端接口

- `GET /api/action-logs`
- `GET /api/action-logs/latest`
- `POST /api/action-logs/{log_id}/undo`

### 后端实现

- `backend/app/services/action_log.py`  
  各写服务内 `action_log.record(...)`

### 数据库

- `action_logs`

### 依赖关系

被订单/进库/出库/合箱等写路径调用。

---

## FEATURE: TUNNEL

### 功能说明

本机 Cloudflare 快速隧道，把前端 `5174` 暴露为临时 HTTPS。

### 用户入口

员工主界面页头隧道按钮（管理员启停）。

### 前端

- `frontend/src/App.tsx`
- `frontend/src/api.ts`：`fetchTunnelStatus`、`startTunnel`、`stopTunnel`

### 后端接口

- `GET /api/tunnel`
- `POST /api/tunnel/start`
- `POST /api/tunnel/stop`

### 后端实现

- `backend/app/tunnel_status.py`
- `scripts/run-tunnel.ps1`、`start-tunnel.bat`

### 文档

- `docs/tunnel.md`

### 数据库

无。

---

## FEATURE: SYSTEM

### 功能说明

健康检查、前端元信息（库模式、版本、当前用户）、商品种类列表。

### 前端

- `fetchMeta()`（`App.tsx` / `ApplyPage` 启动）
- `fetchProductKinds()`（订单/抓取种类下拉）

### 后端接口

- `GET /api/health`
- `GET /api/meta`
- `GET /api/product-kinds`

### 后端实现

- `backend/app/main.py`
- `backend/app/settings.py`
- `backend/app/product_kind.py`
- `backend/data/product_kinds.json`

### 测试

- `backend/_smoke_product_kind.py`

---

## SHARED MODULES

| 模块 | 用途 | 使用 FEATURE |
|---|---|---|
| `backend/app/database.py` | SQLite 连接、`init_db`、列迁移 | 全部写路径 |
| `backend/app/models.py` | Pydantic 请求/响应 | 全部 API |
| `frontend/src/api.ts` | 浏览器 `fetch` 封装 | 全部前端 |
| `backend/app/settings.py` | 环境变量、库模式、CORS | SYSTEM / AUTH |
| `backend/app/services/order_status.py` | 订单状态由明细汇总 | ORDER / INBOUND / OUTBOUND |
| `backend/app/tracking_links.py` | 承运商查询 URL | INBOUND / OUTBOUND |
| `backend/app/rate_limit.py` | 公开接口限流 | ORDER_REQUEST |
| `backend/app/notifications.py` | 申请通知（若启用） | ORDER_REQUEST |
| `frontend/src/main.tsx` | `/` `App`、`/apply`、`/me` 分流 | AUTH / ORDER_REQUEST / CUSTOMER_PORTAL |

---

## 数据库索引

| 表 | FEATURE | 定义 | 用途 |
|---|---|---|---|
| `orders` | ORDER, FINANCE | `database.py` `init_db` | 库存订单头 |
| `items` | ORDER, INBOUND, OUTBOUND, INV_EXPORT | 同上 | 明细行 |
| `outbound_batches` | OUTBOUND_BATCH, FINANCE, INV_EXPORT, FEE_DETAIL | 同上 + `_ensure_column` | 出库批次与财务 |
| `shipments` | INBOUND, OUTBOUND_BATCH | 同上；包装列迁移 | 进/出库箱 |
| `shipment_items` | INBOUND, OUTBOUND_BATCH | 同上 | 箱内货品 |
| `stock_boxes` | INVENTORY | 同上 | 在库合箱 |
| `stock_box_orders` | INVENTORY | 同上 | 合箱-订单 |
| `users` | AUTH, USER_MANAGEMENT | 同上 | 账号 |
| `sessions` | AUTH | 同上 | Cookie 会话 |
| `order_requests` | ORDER_REQUEST, APPLY_STATS, CUSTOMER_PORTAL | 同上 + 定金列迁移 | 顾客申请 |
| `action_logs` | ACTION_LOG | 同上 | 可撤销日志 |

`outbound_batches.invoice_ship_date`、`shipments.net_weight` 等在 `CREATE TABLE` 原文中可能没有，由 `_ensure_column` 补齐。

---

## 测试与脚本（非 FEATURE）

| 路径 | 说明 |
|---|---|
| `backend/test_retailer_scrapers.py` | ORDER_IMPORT |
| `backend/test_zozo_order.py` | ORDER_IMPORT |
| `backend/_smoke_finance.py` | FINANCE 影子库冒烟 |
| `backend/_smoke_product_kind.py` | SYSTEM / 种类 |
| `backend/_smoke_add_to_box.py` | INVENTORY |
| `start.bat` / `start-shadow.bat` / `stop.bat` | 启停 |
| `scripts/start-bg.ps1` | 后台起前后端 |
| `scripts/backup-db.ps1` | SQLite 备份 |
| `scripts/tray_app.py` | 托盘 |
| 前端单元测试 | **未确认**（未见 `*.test.ts`） |
