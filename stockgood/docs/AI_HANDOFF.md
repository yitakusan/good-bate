# Stockgood AI Handoff

新会话的第一份地图. 日期: 2026-10-14. 产品版本: **0.10.4**.

本文件只记决策和路径. 细节以 `docs/CODE_INDEX.md` 的单个 FEATURE 为准, 原因以 `docs/CHANGELOG_AI.md` 为准. 不要把这里的摘要当成比代码更新的事实.

核对过的界面 (2026-10-07): `frontend/src/App.tsx` 的 `NAV_SECTIONS`, `frontend/src/ApplyPage.tsx` 的申请步骤, `backend/app/services/retailer_cart.py` 的 `SHOP_CATALOG`. 与下面第 4, 5, 6 节一致.

---

## 1. 给下一个 AI 的用法

1. 先读本文件.
2. 再按任务打开 `docs/CODE_INDEX.md` 里**一个** FEATURE 章节, 然后只读该节列出的文件.
3. 需要「为什么」时, 在 `docs/CHANGELOG_AI.md` 搜同一个 `FEATURE: XXXXX`.
4. 不要为了熟悉项目去全库扫描 `App.tsx` / `main.py` / `api.ts`.

工作区根目录是 `stockgood/`. Git 仓库可能在上一级 `good-bate1.0.01`. 路径一律相对 `stockgood/`.

员工主界面是 `frontend/src/App.tsx` 里的分区, 没有独立出库页文件. 不要拆这个文件.

Effort 规则在 `AGENTS.md`. 单 FEATURE 常规改动用 Medium 或 High. 不要因为上下文不完整就升到 Extra High.

改完较大功能后, 按 `AGENTS.md` 做 Context Checkpoint: 有新决策才追加 `docs/CHANGELOG_AI.md`, 调用链变了才改 `docs/CODE_INDEX.md`.

---

## 2. 当前版本与运行

| 项 | 值 |
|---|---|
| 版本 | `0.10.4`, 落点: `VERSION`, `backend/app/main.py` 的 `APP_VERSION`, `frontend/package.json` |
| 界面 | http://localhost:5174 |
| API | http://localhost:8002 , 文档 http://localhost:8002/docs |
| 生产库 | `backend/data/stockgood.sqlite` (`STOCKGOOD_DB_MODE=production`, `start.bat` 默认) |
| 影子库 | `backend/data/stockgood.shadow.sqlite` (`start-shadow.bat` 或 `STOCKGOOD_DB_MODE=shadow`) |
| 测试临时库 | 环境变量 `STOCKGOOD_DATABASE_PATH` 指向临时 sqlite. unittest 禁止写生产库和共享影子库 |

开发页用 **5174**. 不要用 `8002/apply` 看热更新界面.

一键启动: `start.bat` (中文名 `启动.bat` 只是薄封装) 调用 `scripts/start-bg.ps1`, 后台起前后端, 日志在 `logs\`. 影子库: `start-shadow.bat`. 停止: `stop.bat`. 托盘: `start-tray.bat` (默认生产库). 隧道: `start-tunnel.bat`, 发给顾客的链接必须带 `/apply`.

客户示例账号 (README): `customer@stockgood.local` / `Customer12`.

unittest:

```text
cd backend
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

改 Pydantic 模型后, 在 `stockgood/` 用 `backend/.venv` 跑 `python scripts/gen-api-types.py`.

---

## 3. 业务逻辑地图

单团队库存. 核心是订单 + 明细行. 不保存客户档案和地址. 不做自动下单, 不做真实支付, 不做多租户.

货品状态 (`items.status`): `ordered` 已下单, `inbound_shipped` 已发往仓库, `in_stock` 在库, `outbound_shipped` 已发往用户, `delivered` 已签收, `cancelled` 取消. 订单状态由明细最慢状态汇总. 旧值 `in_transit` 启动时迁成 `inbound_shipped`.

### 主链

1. 顾客 `/apply` 登录后提交申请. 新建为「待付定金」(商品金额 30%, `STOCKGOOD_DEPOSIT_RATE`). 确认付款后才是「已提交」.
2. 员工「申请单」确认已下单或拒绝. 未付定金不能确认已下单. 确认时可选写成库存订单.
3. 库存订单 (也可由抓取导入或模板加购付款后生成). 一单一汇率, 手填, 不实时查汇.
4. 进库: 选一笔订单, `POST /api/orders/{id}/inbound`, 确认到仓后在库. 通用 `POST /api/shipments` 不是进库 UI 的路径.
5. 库存合箱: 不改货品状态, 与出库分箱分开.
6. 出库批次: 一批多箱, 可合多单, 不支持部分出库. 每箱独立运单号和运费 JPY. 创建时锁定货款应收 CNY. 未签收前可编辑并重算货款.
7. 确认整批签收.

双编号: 全站 `request_code` `SG-0001...` (员工台账) + 账户 `account_order_no` `SGuid-0001...` (用户端只显示账户流水).

### 旁路

- **抓取导入**: 粘贴 URL 或订单页 HTML/JSON, 预览后写入库存订单. 各站原理见 `docs/ORDER_IMPORT.md`. 与模板加购不是同一个按钮.
- **模板加购**: 只打开对方购物车或提交对方加购表单, **不代付, 不结算**. 付款后员工按店填对方订单号和总价, 再 `POST /api/orders`. 混店不能合成一个购物车或一张库存订单. 总价用运费差额 + 备注保存, 不新增库字段.
- **财务**: 商品与订单运费共用下单汇率折 CNY. 国际运费在出库批次, 各箱都有 JPY 时 `合计 JPY x 运费汇率`. 本月下单按 `ordered_at`, 本月出库按批次 `created_at`.
- **导出** (出库 Tab, 只读): INV 双 Sheet (`inv` + `PACKING LIST `, 表名末尾有空格), SF 申报 (A 列是发货箱号 `FIT{批次}-{箱号}`, 不是快递单号; 品牌取货品 `ip`), 费用明细双 Sheet.

写操作进 `action_logs`, 只能撤回最近一条且状态未被后续改动.

---

## 4. 当前界面分区

数量统计只在「库存」分区显示. 角色: `users` 仅 `admin`. `finance` 角色看不到抓取导入, 模板加购, 进库, 库存, 出库. 员工登录当前关掉时, 未登录也能进员工 API (见第 6 节).

### 员工端 `NAV_SECTIONS` (`frontend/src/App.tsx`)

| 分区 id | 标签 | 页面 (tab) | 主要文件 |
|---|---|---|---|
| `flow` | 库存 | 抓取导入 `scrape`, 模板加购 `retailer-cart`, 进库 `inbound`, 订单 `orders`, 库存 `inventory`, 出库 `outbound` | `App.tsx`; 服务 `orders.py` `items.py` `shipments.py` `stock_boxes.py` `outbound_batches.py`; 抓取 `scrapers/preview.py`, 加购 `retailer_cart.py` |
| `customer` | 顾客 | 申请单 `requests` | `App.tsx`; `order_requests.py` |
| `money` | 账目 | 财务 `finance`, 统计 `reports` | `finance.py`, `apply_stats.py` |
| `system` | 系统 | 操作日志 `logs`, 用户 `users` | `action_log.py`, `auth.py` |

出库按钮仍在出库页: 创建批次, 编辑批次, 确认整批签收, 导出 INV, 导出 SF, 费用明细 Excel. 草稿在浏览器 `localStorage` key `stockgood.outboundDraft.v1`.

### 顾客端

`/apply` (`ApplyPage.tsx`) 两个视图:

- **下单**: 同页三步 `pick` 选商品, `review` 确认清单, `submit` 提交. 提交后是待付定金, 确认付款后才正式提交.
- **进度**: 待付定金和已申请订单.

`/me` (`MePage.tsx`) 仍是进度页 (看自己的申请, 确认定金). 0.10.1 只对齐了页头, 没有改成三步下单.

路由分流: `frontend/src/main.tsx`.

---

## 5. 功能与文件路径

未接线 (不是必须立刻补的 bug): `GET /api/order-requests/{request_id}` 前端未用; `POST /api/shipments` 进库 UI 不用; `api.ts` 的 `createItem()` / `fetchOrderRequestByCode()` 页面未调. 前端未见 `*.test.ts`.

| FEATURE | 入口 | 前端 | API | 后端 |
|---|---|---|---|---|
| AUTH | 员工登录已短路; `/apply` `/me` 仍登录 | `AuthPanel.tsx`, `App.tsx`, `ApplyPage.tsx`, `MePage.tsx` | `/api/auth/login` `logout` `me` `register`. `change-password` 仅后端 | `auth.py`, `auth_context.py`, `admin_auth.py`. 表 `users` `sessions` |
| USER_MANAGEMENT | 系统 / 用户, 仅 admin | `App.tsx` `tab === "users"` | `/api/users` | `auth.py` `list_users` / `create_user` / `set_user_active` |
| CUSTOMER_PORTAL | `/me` | `MePage.tsx` | `/api/me/order-requests`, `.../confirm-deposit` | `order_requests.py` |
| ORDER | 库存步骤 / 订单 | `App.tsx` `orders` | `/api/orders`, `/api/items`, `/api/stats` | `orders.py`, `items.py`, `order_status.py` |
| ORDER_IMPORT | 库存步骤 / 抓取导入 | `App.tsx` `scrape`, `scrapePaste.ts` | `POST /api/scrape`, 导入走 `POST /api/orders` | `scrapers/preview.py` 与 `scrapers/*.py`. 见 `docs/ORDER_IMPORT.md` |
| RETAILER_CART | 库存步骤 / 模板加购 | `App.tsx` `retailer-cart` | `/api/retailer-cart/template.csv` `parse` `add`; 建单 `POST /api/orders` | `services/retailer_cart.py`. 加购本身不写订单 |
| ORDER_REQUEST | `/apply`; 顾客 / 申请单 | `ApplyPage.tsx`, `App.tsx` `requests` | `/api/public/scrape`, `/api/public/order-requests`, `/api/order-requests` | `order_requests.py`. 表 `order_requests` |
| INBOUND | 库存 / 进库 | `App.tsx` `inbound` | `POST /api/orders/{id}/inbound`, `POST /api/shipments/{id}/confirm` | `shipments.py`, `tracking_links.py` |
| INVENTORY | 库存 / 库存 | `App.tsx` `inventory` | `/api/stock-boxes` | `stock_boxes.py` |
| OUTBOUND_BATCH | 库存 / 出库 | `App.tsx` `outbound` | `/api/outbound-batches` | `outbound_batches.py` |
| INV_EXPORT | 出库「导出 INV」 | `downloadOutboundInv` | `GET .../inv.xlsx`, `POST .../preview-inv.xlsx` | `inv_template.py`, 模板 `backend/data/templates/inv_fit_shipping.xlsx` |
| SF_EXPORT | 出库「导出 SF」 | `downloadOutboundSf` | `GET .../sf.xlsx`, `POST .../preview-sf.xlsx` | `sf_template.py`, 模板 `sf_export.xlsx` |
| FEE_DETAIL | 出库「费用明细 Excel」 | `downloadOutboundFeeDetail` | `GET .../fee-detail.xlsx` | `outbound_batches.py`, 模板 `fee_detail.xlsx`. 财务可下, 仓库 403 |
| FINANCE | 账目 / 财务; 出库上的运费收款 | `App.tsx` `finance` | `GET /api/finance/summary`, `PATCH .../finance` | `finance.py` |
| APPLY_STATS | 账目 / 统计 | `App.tsx` `reports` | `GET /api/reports/apply` | `apply_stats.py` |
| ACTION_LOG | 顶栏撤回; 系统 / 操作日志 | `App.tsx` `logs` | `/api/action-logs` | `action_log.py` |
| TUNNEL | 页头隧道 | `App.tsx` | `/api/tunnel` | `tunnel_status.py`, `docs/tunnel.md` |
| SYSTEM | 启动 `fetchMeta` | `App.tsx`, `ApplyPage.tsx` | `/api/health` `/api/meta` `/api/product-kinds` | `main.py`, `settings.py`, `schema_migrations.py`, `product_kind.py` |

共享: `database.py`, `models.py`, `frontend/src/api.ts`, `frontend/src/api-types.generated.ts`.

---

## 6. 最近功能变动与工作进度 (约 0.9.46 到 0.10.3)

`docs/CHANGELOG_AI.md` 的 Current Development State 写着最后更新 2026-10-06, 版本已是 0.10.3. 其中「正在开发: Shopify 白名单 7 店已接; animate 等非 Shopify 仍未接」**已过时**. 以 `SHOP_CATALOG` 为准: FutureShop, MakeShop, asobi store, HMV 都已接入.

### 已完成 (代码与 CHANGELOG 已落地)

- **0.9.46 员工登录临时关闭.** `auth.py` `auth_required()` 在未设 `STOCKGOOD_AUTH_REQUIRED=true` 时固定返回 false (旧的「有员工账号就要求登录」保留为注释). `App.tsx` 员工 `AuthPanel` 和管理口令栏是 `false &&` 短路. 客户 `/apply` `/me` 仍要登录. 恢复前不要把自动登录加回去. unittest / Docker 仍可设 `STOCKGOOD_AUTH_REQUIRED=true`.
- **0.9.43-0.9.52 模板加购**, 不代付. 白名单按店拆开. 种类与 host (`SHOP_CATALOG`):
  - Shopify permalink, Bushiroad `bushiroad-store.com` 税抜 x 1.1; 税込: `lafary.shop`, `animeshi.jp`, `cocollabo.net`, `qinocop.com`, `mono-mo.com`, `cho-kaguyahime-officialstore.bookstores.jp`
  - FutureShop: `jumpcs.shueisha.co.jp`, `store.kadokawa.co.jp`
  - MakeShop 表单: `miraithings.com`, `pricafe.shop`, `store-gk.com`
  - asobi store 表单: `shop.asobistore.jp`
  - HMV: `hmv.co.jp`, 商品页末尾编号, `GET /basket/inbasket/?sku=`. **每次打开加 1 件**; 数量大于 1 就重复打开同一链接
- **0.9.49** 付款后填对方订单号 + 总价 JPY, 再生成库存订单.
- **0.9.53-0.9.54** 订单页筛选默认收起; 按钮文案「筛选 / 收起筛选」; 「登记订单」仍在外面.
- **0.10.0** 员工导航改成上面五区, 一次一个分区.
- **0.10.1** `/apply` 三步 + 「进度」. `/me` 仍是进度页.
- **0.10.2** 窄屏订单行收成两行: 单号和状态一行, 件数金额和操作一行.
- **0.10.3** 订单行在单号左侧显示该订单第一张商品预览图.

更早且仍有效: 出库每箱独立运单 (0.9.41) 和每箱运费 JPY (0.9.42); SF 导出 (0.9.39, A 列是箱号 0.9.40); 抓取站点见 `docs/ORDER_IMPORT.md` (含 animate / ZOZO / sofmap 的**导入解析**, 不是加购).

### 浏览器验收

CHANGELOG_AI **没有**写 0.10.0-0.10.3 或模板加购各站「已在浏览器点过」. 本交接只对过源码和文档, **没有**打开 5174. 这些界面是否在浏览器验过: **未确认**.

### 明确不要做

- `docs/client-product-rules.md` **第 8 节已拍板但未落地**, 现码仍是旧定金流程. **不要当成 bug 改.** 包括: `/me` 改密改昵称, 定金凭证截图 + 支付单号, 员工二次确认后才变「已提交」, 未登录不可看公开申请列表. `POST /api/auth/change-password` 后端有, 前端未接, 同属这一节.
- 用户没说恢复之前, 不要恢复员工自动登录.
- 不要把模板加购和抓取导入合成一个按钮或代付.
- 改 `shipments` 重建表时, 关外键前必须先 `commit`. 不要补写已省略的事故恢复细节.
- 不要主动 `git commit`, 不要为纯文档交接升 `VERSION`.

### 模板加购已知限制

- animate (`animate-onlineshop.jp`), ZOZO, Sofmap **不在** `SHOP_CATALOG`. 现有 Shopify permalink 不能套这三站. 它们只在抓取导入里有解析. 要不要接成加购: `CHANGELOG_AI` 下一步**没写**, 标为 **未确认**.
- HMV 每次打开加 1 件: 已实现 (`build_hmv_urls` 按数量重复 URL).
- Lawson / Loppi / HMV 限定不能和普通 HMV 放进同一个购物车: **员工页提示文案已写** (`App.tsx` 模板加购说明). 后端没有单独的 Lawson host, 也没有另做拆车逻辑. 是否只靠人工分开: 以这段文案为准, 代码强制拆车为 **未确认** (当前未见强制).

---

## 7. 设定目标 / 未完成

来自 `CHANGELOG_AI`「下一步」, 不是新编的产品目标:

1. SF 导出字段口径等用户验收 (品牌 = 货品 `ip`, 收件人固定腾越云仓, A 列 = 发货箱号). 通过后再决定是否微调.
2. 个人主页 / 规范第 8 节: **等用户明示「开始实现」**.
3. 明确要求前不执行 git commit.
4. 可交付的功能改动要写根目录 `CHANGELOG.md` 并升版本 (`VERSION`, `main.py`, `package.json`). 不要把文档规划说成已实现功能.
5. 新迁移写入 `backend/app/schema_migrations.py` 的 `MIGRATIONS`, 保持幂等.

最近一条 Session Handoff 是 **2026-09-29 员工登录暂时关闭** (FEATURE: AUTH). 其后的 0.9.47-0.10.3 记在 Current Development State 和根目录 `CHANGELOG.md`, 没有新的 Handoff 条目.

未在「下一步」里、本文件也不当作目标的事: 把 animate / ZOZO / Sofmap 接进模板加购. **未确认.**

---

## 8. 硬性约束

- 代码, 配置, 路径, 标识符, 正则, JSON 键, 日志模板用英文半角. 匹配外部网站原文 (例如订单页标签) 必须与页面字符一致.
- 用户没要求改布局 / 文案 / 控件位置时, 只改逻辑和数据. 不要顺手改按钮文案或重排 Tab.
- 测试数据只写影子库, 或 unittest 用 `STOCKGOOD_DATABASE_PATH` 临时文件. **禁止**往 `stockgood.sqlite` 写测试订单, 申请, 货品.
- 会改变实际库存的操作: 先在影子库做完同等路径, 用户说「验收通过 / 确认 / 可以改实库」之后, 才能写生产库.
- 不主动 git commit. 不 `git reset --hard`. 不删文件, 不清库, 不做破坏性迁移, 除非用户明确要求.
- 不拆 `App.tsx`. 不升级主框架, 不大规模重构.
- 改路径时全库搜旧引用并同步, 改完再搜一遍.
- 可交付行为变更要更新 `CHANGELOG.md` 和三处版本号. 只改文档 / 本交接文件时不升版本.
