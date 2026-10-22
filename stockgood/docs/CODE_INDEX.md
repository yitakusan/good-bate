# Code Index

本文件是 Stockgood 的代码地图。

- `README.md`：项目是什么、如何运行
- `AGENTS.md`：Agent 怎么工作
- 本文件：FEATURE 对应哪些代码
- `docs/CHANGELOG_AI.md`：为什么这么改、当前状态、Session Handoff
- `docs/ORDER_IMPORT.md`：抓取商品链接实现原理与各站解析

新会话或较大改动前：先读 CODE_INDEX 定位，再搜 `CHANGELOG_AI.md` 里同一 `FEATURE: XXXXX` 的历史。

路径均相对仓库内 `stockgood/`。前端主界面是单文件多 Tab：`frontend/src/App.tsx`（没有独立 `*Page.tsx` 出库页）。

## 功能目录

- [FEATURE: AUTH](#feature-auth)
- [FEATURE: USER_MANAGEMENT](#feature-user_management)
- [FEATURE: CUSTOMER_PORTAL](#feature-customer_portal)
- [FEATURE: ORDER](#feature-order)
- [FEATURE: ORDER_IMPORT](#feature-order_import)
- [FEATURE: RETAILER_CART](#feature-retailer_cart)
- [FEATURE: ORDER_REQUEST](#feature-order_request)
- [FEATURE: INBOUND](#feature-inbound)
- [FEATURE: INVENTORY](#feature-inventory)
- [FEATURE: OUTBOUND_BATCH](#feature-outbound_batch)
- [FEATURE: INV_EXPORT](#feature-inv_export)
- [FEATURE: SF_EXPORT](#feature-sf_export)
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

**临时**：员工主界面登录已关掉（`auth.py` `auth_required()` 在非强制 `STOCKGOOD_AUTH_REQUIRED=true` 时返回 false；`App.tsx` 员工 `AuthPanel` 已短路）。客户门户登录仍在。

### 用户入口

- 员工主界面未登录时 `AuthPanel`（`allowRegister=false`；**当前已用 `false &&` 短路，不弹出**）
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

- `backend/tests/test_auth_roles.py`（顾客 403 员工接口；仓库不能费用明细/改财务；财务可打费用明细接口；Cookie 与 `X-Admin-Token` 双路径）

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

### 测试

- `backend/tests/test_order_flow.py`（下单 → 进库 → 在库 → 合箱不改状态 → 出库锁定货款 → 撤回；进库确认撤回；编辑批次后货款重算）

### 调用链

订单 Tab → `fetchOrders()` → `GET /api/orders` → `orders_svc.list_orders` → `orders` + `items`

### 依赖关系

被 `INBOUND`、`INVENTORY`、`OUTBOUND_BATCH`、`FINANCE`、`ORDER_IMPORT`、`RETAILER_CART`（模板加购「生成库存订单」→ `createOrder`）使用。

---

## FEATURE: ORDER_IMPORT

原理与各站解析见 [`docs/ORDER_IMPORT.md`](ORDER_IMPORT.md)。

### 功能说明

粘贴商品 URL / HTML 抓取预览，勾选后批量写入货品/订单。

### 用户入口

主界面 Tab「抓取导入」。顾客申请页另有公开抓取（见 `ORDER_REQUEST`）。加购在独立 Tab「模板加购」（`RETAILER_CART`）。

### 前端

- `frontend/src/App.tsx`（`tab === "scrape"`；`appendScrapeProducts` 同商品可回填 JAN）
- `frontend/src/scrapePaste.ts`（HTML/JSON 粘贴识别、`scrapeProductMatchKey`；ZOZO 分色须带 `?did=`，键为 `zozo:goods:{gid}:did:{did}`）
- `frontend/src/scrapeDelay.ts`
- `frontend/src/api.ts`：`scrapeUrl`、`createOrder`（抓取 Tab 导入）；`createItemsBatch` 仍可用但当前 Tab 未调用

### 后端接口

- `POST /api/scrape`
- `POST /api/orders`（抓取导入）
- `POST /api/items/batch`（按 order_ref 批量建单，抓取 UI 未接线）

### 后端实现

- `backend/app/scrapers/preview.py`（`scrape_url`、`scrape_html_document`；商品页通用 `extract_jan_from_html`）
- `backend/app/scrapers/*.py`（站点特化：zozo、andmall/&mall、vvstore、sofmap、cystore、animate、eeo、lafary、medicos、hmv、hobbysearch、futureshop 等）
  - &mall：整页 SSR HTML、Elements 列表 outerHTML、Network `shop-order-skus` JSON；相同 SKU 合并数量。Ctrl+U 不含もっと見る结果。
  - vvstore：ご注文履歴詳細整页 HTML；含单价/数量/运费/注文番号，无 JAN；相同商品 URL 合并数量。订单后再抓 `/products/detail/{id}` 商品页，前端按商品 ID 回填 JAN。
  - sofmap：`product_detail.aspx?sku=` 商品页；JANコード / JSON-LD。另支持「お取引の詳細」订单 HTML（数量/运费/注文番号；图 URL 常含 JAN）；前端按 sku 匹配。
  - cystore：購入履歴詳細整页 HTML；含单价/数量/运费/注文番号；订单页通常无 JAN；商品 ID 取自图片路径；相同 pid 合并数量。
  - animate：注文履歴整页 HTML；行内金额为小计（单价=小计÷点数）；含运费/注文番号；跳过特典；商品 ID 取自 `/pd/{id}/`；相同 pid 合并数量；JAN 取自商品图 `image=` 文件名且须通过校验位。详见 [`docs/ORDER_IMPORT_ANIMATE.md`](ORDER_IMPORT_ANIMATE.md)。
  - eeo：ご注文履歴詳細整页 HTML；含单价/数量/运费/注文番号；邮件正文商品コード可回填 JAN；商品 ID 取自 `/products/detail/{id}`；相同 pid 合并数量。
  - lafary：Shopify 顾客「注文 #…」整页 HTML；含单价/数量/运费/注文番号；订单页通常无 JAN；按品名合并数量。
  - shopify_account：新版顾客账户已渲染「注文アイテム」（`role=row`、`￥n/ユニット`、配送/合計）。单价税込。同名不同规格不合并。Ctrl+U 空壳不解析。片段可不带店铺域名。
  - yahoo_shopping：Yahoo!ショッピング「注文履歴詳細」整页 HTML。`.elPrice` 为税込单价，`×N` 为数量。同链接不同规格不合并。订单页无 JAN。前端键 `yahoo:{store}:{item}:{品名}`。
  - medicos：EC-CUBE「購入履歴詳細」整页 HTML；含单价/数量/运费/注文番号；邮件 BOXJAN 可回填 JAN；商品 ID 取自图片文件名或 `/products/detail/{id}`；相同 pid/品名合并数量。
  - yostar：SPA + ecshop-api；商品 URL 调 `product/detail`；Ctrl+U 空壳不可用；注文/商品可粘贴 Network JSON；价取 `sku[].price`；匹配键 `yostar:product:{id}`。
  - storesjp：STORES `*.stores.jp`；商品页 URL 优先本机 curl（httpx 常 403）；亦可粘贴 SSR HTML；注文可贴已渲染「購入詳細」HTML（`.order_history_item`）或 Network `/web/customers/orders/{id}` JSON；行小计÷数量；匹配键 `stores:item:{id}`。
- `backend/app/services/items.py`：`create_items_batch`

### 测试

- `backend/test_retailer_scrapers.py`
- `backend/test_zozo_order.py`
- `backend/test_andmall_order.py`
- `backend/test_vvstore_order.py`
- `backend/test_sofmap_product.py`
- `backend/test_sofmap_order.py`
- `backend/test_cystore_order.py`
- `backend/test_animate_order.py`
- `backend/test_eeo_order.py`
- `backend/test_lafary_order.py`
- `backend/test_medicos_order.py`
- `backend/test_yostar_order.py`
- `backend/test_storesjp_order.py`
- `backend/test_yahoo_shopping_order.py`

### 依赖关系

写入 `ORDER`（`orders`/`items`）。公开抓取 `POST /api/public/scrape` 同属抓取引擎，入口在 `ORDER_REQUEST`。

---

## FEATURE: RETAILER_CART

### 功能说明

主页面独立 Tab「模板加购」：上传 CSV/xlsx（列：链接、数量），按店筛白名单并合并同商品数量。白名单分五类，购物车不能混店：Shopify permalink（`bushiroad-store.com` 税抜×1.1，其余税込：`lafary.shop`、`animeshi.jp`、`cocollabo.net`、`qinocop.com`、`mono-mo.com`、`cho-kaguyahime-officialstore.bookstores.jp`）；FutureShop GET `/shop/cart/cart.aspx?goods=&qty=`（`jumpcs.shueisha.co.jp`、`store.kadokawa.co.jp`）；HMV GET `/basket/inbasket/?sku=`（`hmv.co.jp`，商品页 `item_..._编号`，每次打开加 1 件）；MakeShop POST `/api/basket/add.html`（`miraithings.com`、`pricafe.shop`、`store-gk.com`）；asobi store POST `/cart`（`shop.asobistore.jp`）。`POST /api/retailer-cart/parse` 对 Shopify 行并发拉 `products/{handle}.json`；对 FutureShop（`store.kadokawa.co.jp`、`jumpcs.shueisha.co.jp`）拉商品页 HTML 补名称、大图、税込价。`POST /api/retailer-cart/add` 按 kind 返回链接或表单，前端在员工浏览器打开。付款后仍按店填订单号+总价，走 `POST /api/orders`。

### 用户入口

主界面 Tab「模板加购」（与「抓取导入」并列，财务角色不可见）。

### 前端

- `frontend/src/App.tsx`（`tab === "retailer-cart"`）
- `frontend/src/api.ts`：`parseRetailerCartTemplate`、`addRetailerCart`、`downloadRetailerCartTemplate`、`createOrder`

### 后端接口

- `GET /api/retailer-cart/template.csv`
- `POST /api/retailer-cart/parse`
- `POST /api/retailer-cart/add`

### 后端实现

- `backend/app/services/retailer_cart.py`

### 测试

- `backend/test_retailer_cart.py`
- `backend/tests/test_retailer_cart_order.py`（IsolatedDbTestCase 临时 sqlite）

### 依赖关系

加购本身不写 `orders`/`items`。生成库存订单复用 FEATURE: ORDER 的 `createOrder` / `POST /api/orders`（一店一单）。Shopify 购物车 permalink 按 host 拆分。不要与 `ORDER_IMPORT` / `ORDER_REQUEST` 混用按钮。

---

## FEATURE: ORDER_REQUEST

### 功能说明

顾客申请：登录后提交 → 待付定金（约 30%）→ 确认后 submitted → 员工确认下单或拒绝。可选生成库存订单。

### 用户入口

- 公开页 `/apply`（`ApplyPage.tsx`）：同页步骤「选商品 → 确认清单 → 提交」，「进度」查看待付定金和已申请订单
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

### 测试

- `backend/tests/test_order_flow.py`（`create_inbound_for_order` → `confirm_shipment`；确认后可撤回回 `inbound_shipped`）

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
- `backend/tests/test_order_flow.py`（已在其他箱则 `add_orders` 拒绝）

### 依赖关系

读取在库 `ORDER`/`items`。出库选单会用库存合箱分组（`OUTBOUND_BATCH`）。

---

## FEATURE: OUTBOUND_BATCH

### 功能说明

出库批次：草稿分箱、每箱独立运单号与运费 JPY、包装尺寸、创建锁定货款应收、未签收前编辑、整批签收。

### 用户入口

主界面 Tab「出库」。

按钮（均在该 Tab）：

- 「创建出库批次」→ `createOutboundBatch`
- 「编辑批次」→ `updateOutboundBatch`
- 「确认整批签收」→ `confirmOutboundBatch`
- 「导出 INV」→ `INV_EXPORT`
- 「导出 SF」→ `SF_EXPORT`
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
- `shipments`（`direction=outbound`，`batch_id`，`tracking_no`，`freight_jpy`，包装列 `net_weight` 等）
- `shipment_items`
- `items`（状态改为 `outbound_shipped` / `delivered`）

### 测试

- `backend/tests/test_order_flow.py`（创建批次锁定 `goods_receivable_cny`，撤回批次；编辑批次改数量后重算货款）

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

### 测试

- `backend/tests/test_exports.py`（双 Sheet 名、PACKING F5 而非 F6、预览 `FIT0`、模板文件不被写回）

---

## FEATURE: SF_EXPORT

### 功能说明

按业务样表单 Sheet 导出顺丰申报 Excel。列：运单号*、商品条形码、商品中文名称*、品牌*、産地*、规格*、数量*、单价*、收件人信息*。**表头「运单号*」在本系统填发货箱号**（`FIT{batch}-{box}`，与 INV packing 同口径），不是快递单号；每箱首行写箱号，同箱后续行空。整表首行写收件人。同箱内同条码同单价合并数量。品牌取货品 `ip`；产地固定「日本」、规格固定「个」。不要求包装尺寸与快递单号。

### 用户入口

出库 Tab：「导出 SF」（已有批次）、「导出 SF」（创建前预览）。

### 前端

- `frontend/src/App.tsx`：`onExportDraftSf`、`downloadOutboundSf`
- `frontend/src/api.ts`：`downloadOutboundSf`、`downloadOutboundSfPreview`

### 后端接口

- `GET /api/outbound-batches/{batch_id}/sf.xlsx`
- `POST /api/outbound-batches/preview-sf.xlsx`

### 后端实现

- `backend/app/services/outbound_batches.py`：`export_sf_xlsx`、`export_sf_preview_xlsx`
- `backend/app/services/sf_template.py`：`build_sf_workbook`
- 模板（只读）：`backend/data/templates/sf_export.xlsx`

### 数据库

读 `outbound_batches`、`shipments.tracking_no`、`items`（条码、名称、ip、单价、数量）。不写库。

### 调用链

按钮「导出 SF」→ `downloadOutboundSf(id)` → `GET .../sf.xlsx` → `export_sf_xlsx` → `build_sf_workbook` → 模板填数 → xlsx bytes

### 依赖关系

`OUTBOUND_BATCH`。收件人常量与 INV 中文地址一致。

### 测试

- `backend/tests/test_exports.py`（表头、首行收件人、次行无运单号、预览 `FIT0`、模板不被写回）

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

### 测试

- `backend/tests/test_auth_roles.py`（仓库 403，财务可访问接口；遗留 token 可进、已登录仓库带 token 仍 403）
- `backend/tests/test_exports.py`（双 Sheet、表头、订单号/件数、模板不被写回）

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
- `shipments.freight_jpy`（每箱国际运费 JPY；各箱都有则批次 CNY=合计×运费汇率）

### 测试

- `backend/_smoke_finance.py`
- `backend/tests/test_order_flow.py`（出库锁定货款 225 CNY；改数量后重算 175 CNY）

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

### 测试

- `backend/tests/test_order_flow.py`（撤回最近 `create_outbound_batch`；撤回进库 `confirm_shipment`）

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
- `scripts/run-tunnel.ps1`、`启动隧道.bat`

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
- `backend/app/schema_migrations.py`（幂等列迁移记录）
- `backend/app/product_kind.py`
- `backend/data/product_kinds.json`

### 测试

- `backend/_smoke_product_kind.py`
- `backend/tests/test_migrations.py`（`schema_migrations`、tracking UNIQUE 拆除）

---

## SHARED MODULES

| 模块 | 用途 | 使用 FEATURE |
|---|---|---|
| `backend/app/database.py` | SQLite 连接、`init_db` 建表 | 全部写路径 |
| `backend/app/schema_migrations.py` | 具名幂等迁移 + `schema_migrations` 表 | 全部写路径（启动） |
| `backend/app/models.py` | Pydantic 请求/响应 | 全部 API |
| `frontend/src/api-types.generated.ts` | OpenAPI 生成的 TS 类型 | `api.ts` |
| `frontend/src/api.ts` | 浏览器 `fetch` 封装（类型引用生成文件） | 全部前端 |
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
| `schema_migrations` | SYSTEM | `init_db` + `schema_migrations.py` | 已应用的幂等迁移名 |

`outbound_batches.invoice_ship_date`、`shipments.net_weight` 等在 `CREATE TABLE` 原文中可能没有，由迁移 `0001_ensure_legacy_columns` 补齐。

---

## 测试与脚本（非 FEATURE）

| 路径 | 说明 |
|---|---|
| `backend/tests/` | 关键路径 unittest（临时 sqlite：`STOCKGOOD_DATABASE_PATH`） |
| `backend/tests/test_exports.py` | INV / 费用明细模板契约 |
| `backend/test_retailer_scrapers.py` | ORDER_IMPORT |
| `backend/test_zozo_order.py` | ORDER_IMPORT |
| `backend/test_andmall_order.py` | ORDER_IMPORT |
| `backend/test_vvstore_order.py` | ORDER_IMPORT |
| `backend/test_sofmap_product.py` | ORDER_IMPORT |
| `backend/test_sofmap_order.py` | ORDER_IMPORT |
| `backend/test_cystore_order.py` | ORDER_IMPORT |
| `backend/test_animate_order.py` | ORDER_IMPORT |
| `backend/test_retailer_cart.py` | RETAILER_CART |
| `backend/test_eeo_order.py` | ORDER_IMPORT |
| `backend/test_lafary_order.py` | ORDER_IMPORT |
| `backend/test_shopify_account_order.py` | ORDER_IMPORT |
| `backend/test_yahoo_shopping_order.py` | ORDER_IMPORT |
| `backend/test_medicos_order.py` | ORDER_IMPORT |
| `backend/_smoke_finance.py` | FINANCE 影子库冒烟 |
| `backend/_smoke_product_kind.py` | SYSTEM / 种类 |
| `backend/_smoke_add_to_box.py` | INVENTORY |
| `scripts/gen-api-types.py` | OpenAPI → `frontend/src/api-types.generated.ts` |
| `启动.bat` / `启动影子库.bat` / `停止.bat` | 启停 |
| `scripts/start-bg.ps1` | 后台起前后端 |
| `scripts/backup-db.ps1` | SQLite 备份 |
| `scripts/tray_app.py` | 托盘 |
| 前端单元测试 | **未确认**（未见 `*.test.ts`） |
