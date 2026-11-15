# AI Development Changelog

本文件用于记录 AI Coding Agent 在项目开发中的重要上下文。

目的：

当 Cursor / Codex 对话上下文丢失、压缩或开启新会话时，
新的 Agent 应首先读取本文件以恢复历史开发背景。

产品版本号变更见根目录 `CHANGELOG.md`。本文件记录**为什么这么改**、跨模块影响、用户硬性要求、踩坑，不记流水账。

搜索某功能历史时直接搜：`FEATURE: XXXXX`

---

## Current Development State

最后更新：2026-11-01

当前产品版本：**0.13.0**

新会话先读 `docs/AI_HANDOFF.md`，再按 FEATURE 打开 CODE_INDEX，不要全库扫描。

### 当前稳定功能

- FEATURE: ORDER — 库存订单 + 明细
- FEATURE: ORDER_IMPORT — 抓取导入（含 zozo 注文详情、&mall 注文履歴、vvstore 注文履歴详细、sofmap 商品页与お取引の詳細、cystore 購入履歴詳細、animate 注文履歴、eeo ご注文履歴詳細、lafary Shopify 注文详情、medicos EC-CUBE 購入履歴詳細、yostar SPA 商品 API / 已渲染ご注文履歴 / 注文 JSON、STORES `*.stores.jp` 商品 HTML / 購入詳細 HTML / 注文 JSON；订单后再抓同商品详情页可回填 JAN）。实现原理与各站解析：`docs/ORDER_IMPORT.md`
- FEATURE: RETAILER_CART — Tab「模板加购」；Shopify / FutureShop / HMV 链接，MakeShop 与 asobi store 表单，按店打开对方购物车（不付款）
- FEATURE: ORDER_REQUEST — 顾客申请（须登录、待付定金 30%）
- FEATURE: INBOUND — 按订单进库
- FEATURE: INVENTORY — 在库合箱（不改货品状态）
- FEATURE: OUTBOUND_BATCH — 批次出库、每箱独立运单/运费、未签收可编辑
- FEATURE: INV_EXPORT — 固定双 Sheet 模板导出 INV
- FEATURE: SF_EXPORT — 顺丰申报单列模板导出（样表格式；品牌=ip；草稿/批次）
- FEATURE: FEE_DETAIL — 固定双 Sheet 费用明细 Excel
- FEATURE: FINANCE — 下单汇率、批次运费/收款、月汇总
- FEATURE: APPLY_STATS — 申请日/月统计
- FEATURE: AUTH / USER_MANAGEMENT / CUSTOMER_PORTAL / ACTION_LOG / TUNNEL / SYSTEM

### 当前正在开发

- FEATURE: RETAILER_CART — Shopify 白名单 7 店已接；animate 等非 Shopify 仍未接。

### 最近修复

- **0.13.0**：浏览器插件只把当前页 HTML 交给已有 `POST /api/scrape`，不新增地址字段。服务未开时提示运行 `启动.bat`。`extension/注册拉起.bat` 登记本机拉起组件后，插件可自己启动 8002。解析规则仍在各站 Python 解析里，地址继续不入库。
- **0.12.7**：Yostar OFFICIAL SHOP 已渲染的ご注文履歴可抓取导入。`.price-single` 是单价，`.price-total` 小计不是单价。摘要「送料」才是运费，手数料不算。同一页邮件正文不重复计行。不读配送信息、电话、邮箱、伝票番号。Ctrl+U 空壳和 Network JSON 路径不变。订单页无 JAN。
- **0.12.6**：ゲーマーズ注文履歴可抓取导入。结构和アニメイト订单卡相近，但图文件名不是 JAN。解析后异步打开商品页，取店舗予約用バーコード。N点旁边金额是行小计。不读お届け先和配送伝票番号。多个注文番号不合并。
- **0.12.5**：カドスト / ムービック購入履歴詳細没有商品图。解析后打开 `/shop/g/g{商品代码}/`，取 `img.js-img-source` 的 `/img/goods/L/`，没有则用含 `/img/goods/` 的 og:image。横幅不用。商品页失败时主图留空，单价、数量、运费不变。
- **0.12.4**：BASE「ご注文情報照会」（`dynamic_receipts`）可抓取导入。商品単価是税込单价。`itemList__additionalInfo` 写进品名，同一 `/items/{id}` 的两个规格不合并。送料与合計金額分开，不用商品小计当合计。不读购买者、地址、电话、邮箱、运单号。前端键 `base:{host}:item:{id}:{品名}`。
- **0.12.3**：ツインクル注文履歴与 store-gk / THEキャラ共用 MakeShop 解析。图床 `TwinCre` 识别为 `shop.twincre.com`。小计写着（税込）时单价不再乘 1.1。品名里的「2026年10月発送」写入预计发货年月。不读送付先。
- **0.12.2**：进库「待进库」增加全部勾选。
- **0.12.1**：Aniplex Online 注文詳細可抓取导入。単価（税込）为单价，行合计不是单价。商品代码不是 JAN。不读配送先姓名、地址、电话。一页两个注文番号不合并。
- **0.12.0**：THEキャラ注文履歴与 store-gk 共用 MakeShop 解析。图床 `thechara55` 识别为 `the-chara.com`。单价税抜×1.1。store-gk 与 THEキャラ仍是税抜×1.1，不要套到ツインクル上。
- **0.11.1**：新建仓库改为页头输入。原先 `window.prompt` 在内嵌窗口里会被拦住，点击没有可见结果。
- **0.11.0**：仓库彼此独立，页头切换。订单、进库运单、在库箱、出库批次、财务月汇总只看当前仓库。旧数据归「默认仓库」。顾客申请不拆开，确认生成库存订单时进入当前仓库。在库箱号按仓库各自编号。
- **0.10.14**：amnibus 注文卡片可抓取导入。数量旁价格为税込单价。无标价景品记 0。多笔卡片不合并。订单页无 JAN。
- **0.10.13**：カドスト購入履歴詳細与ムービック共用解析。运费取整单送料。13 位商品代码校验通过才填条形码。配送表不重复计行。
- **0.10.12**：ムービック購入履歴詳細可抓取导入。行合计÷数量为税込单价。手数料不算运费。列表页不解析。
- **0.10.11**：Yahoo!购物注文履歴詳細可抓取导入。单价税込，同链接不同规格不合并。订单页无 JAN。
- **0.10.10**：アニメイト注文履歴从商品图 `image={JAN}_...jpg` 填条形码，校验位不过则留空。
- **0.10.9**：进库排在订单之前。库存步骤：抓取导入、模板加购、进库、订单、库存、出库。
- **0.10.8**：进货并入库存步骤，位于订单之前。财务角色仍看不到抓取和加购。
- **0.10.7**：抓取页站点说明改为「各站支持方式」下拉列表，默认收起。
- **0.10.6**：Shopify 新版顾客订单的已渲染「注文アイテム」可抓取导入。Ctrl+U 空壳仍然不行。单价税込，同名规格不合并。
- **0.10.5**：store-gk 注文履歴 HTML 已接入抓取导入；多笔不自动合并订单号。
- **0.10.4**：KADOKAWA / JUMP CS 商品页走 FutureShop 解析（名称、税込价、大图、JAN）；模板加购预览同步。购物车仍是 `cart.aspx?goods=`。
- **0.10.3**：订单行单号左侧显示第一张商品预览图。
- **0.10.2**：窄屏订单行由四层收成两行。
- **0.10.1**：顾客 `/apply` 同页三步（选商品 → 确认清单 → 提交），进度另开一页视图。不改提交字段和定金规则。`/me` 仍是进度页，只对齐页头。
- **0.10.0**：主界面改为分区导航（库存 / 进货 / 顾客 / 账目 / 系统），不再把全部功能排在同一条 Tab 上。
- **0.9.54**：订单页折叠按钮改为「筛选 / 收起筛选」。
- **0.9.53**：订单页检索默认折叠，「登记订单」仍直接可见。
- **0.9.52**：模板加购接入 hmv.co.jp（`/basket/inbasket/?sku=`，每次加 1 件）。
- **0.9.51**：模板加购增加 FutureShop（JUMP CS、KADOKAWA）、MakeShop（miraithings、pricafe、store-gk）和 asobi store，仍按店分开。
- **0.9.50**：模板加购扩白名单并按店分类（Shopify permalink；Bushiroad 税抜×1.1，其余税込）。
- **0.9.49**：模板加购在付款后填订单号+总价，再 `POST /api/orders` 生成库存订单（总价=货款+运费差额，原文进 note）。
- **0.9.48**：模板加购 parse 并发补 Shopify 商品名/图/税込价；预览用复制按钮代替整段 URL。
- **0.9.47**：模板加购预览标题改为「商品」。
- **0.9.46**：员工登录暂时关闭（有员工账号也不再自动要求登录）；客户 /apply /me 不变。
- **0.9.45**：补 `python-multipart`；模板加购 File 上传曾让 `app.main` 启动即崩，一键启动打不开。
- **0.9.44**：模板加购第一站 bushiroad-store.com（Shopify permalink，不结算）。
- **0.9.43**：主页面拆出 Tab「模板加购」，与「抓取导入」分开；不结算。
- **0.9.42**：出库每箱可填国际运费 JPY；各箱都有金额时，批次运费 CNY = 各箱合计 × 运费汇率。
- **0.9.41**：出库每箱独立运单号，取消「同批次必须同一运单号」与前端改一箱同步全批。
- **0.9.40**：SF A 列「运单号*」改为发货箱号（`FIT{批次}-{箱号}` / `DRAFT-…`），非快递单号。
- **0.9.39**：FEATURE: SF_EXPORT — 出库导出顺丰申报 Excel（样表列格式）；品牌=货品 `ip`，产地日本、规格个，收件人固定腾越云仓；草稿/批次均可；不要求包装尺寸。
- **0.9.38 / 0.9.37**：商品种类新增光盘 / 挂毯 / 杯垫。
- **0.9.36**：STORES 商品页 curl 拉取绕过 Cloudflare 403。
- **0.9.35**：抓取导入 tip 中 JSX `{id}` 导致白屏。
- **0.9.34**：STORES 注文支持已渲染「購入詳細」HTML。
- **0.9.33**：ORDER_IMPORT 新增 STORES（`*.stores.jp`）。
- **0.9.32**：ORDER_IMPORT 新增 shop.yostar.co.jp。
- **0.9.31**：ORDER_IMPORT / ZOZO — 分色 `did` 去重修复。
- **0.9.30**：ORDER_IMPORT 新增 medicos-e-shop.net。
- **0.9.29**：ORDER_IMPORT 新增 lafary.shop。
- **0.9.28**：中文 bat UTF-8 无 BOM 启动问题；已恢复 ASCII `start.bat` 等。

### 待实现 / 旧行为（用户 2026-08-14 确认，不是 bug）

规范第 8 节（`docs/client-product-rules.md`）是**已经确定、但代码尚未落地的新行为**。现码仍走旧定金确认流程。标注为「待实现/旧行为」，**不得当成现有 bug 擅自修改**。包括：

- `/me` 改密、改昵称
- 定金凭证截图 + 支付单号
- 员工二次确认后才变为「已提交」
- 未登录不可查看公开申请列表

`POST /api/auth/change-password` 后端有、前端未接：同属第 8 节待实现，不是漏接 bug。

### 已知风险（已修复的迁移规则，不要补写事故细节）

- FEATURE: OUTBOUND_BATCH — 去掉 `shipments.tracking_no` UNIQUE 时，须在关外键前先 `conn.commit()`。SQLite 在未提交事务内会忽略 `PRAGMA foreign_keys=OFF`，随后 `DROP TABLE shipments` 会级联清空 `shipment_items`。
- **用户确认**：只遵守这条可确认规则；**不推断、不补写**已省略的箱数、单号等恢复细节。

### 下一步

1. 验收 SF 导出字段口径（品牌=ip 等）；通过后再定是否微调。
2. 个人主页 / 规范第 8 节 **等用户明示「开始实现」** 再做。
3. 明确要求前不执行 git commit。
4. 可交付改动写 `CHANGELOG.md` + 升版本。不要把文档规划说成已实现功能。
5. 新迁移加到 `backend/app/schema_migrations.py` 的 `MIGRATIONS` 列表，保持幂等；改 Pydantic 模型后跑 `python scripts/gen-api-types.py`。

---

# Session Handoff

如果当前 Agent 即将结束一个较大的开发阶段，请在这里留下简短交接信息。新 Agent 开始工作时**优先读取最近一条 Handoff**。

格式：

## Handoff - YYYY-MM-DD

### 当前任务

FEATURE: XXXXX

---

## Handoff - 2026-09-29 (员工登录暂时关闭)

### 当前任务

FEATURE: AUTH — 按用户要求暂时关掉员工登录（不是删掉）。

### 已完成

- `auth_required()`：未设 `STOCKGOOD_AUTH_REQUIRED=true` 时固定 False（原先「有员工账号就自动要求登录」已注释保留）
- `require_staff`：关闭鉴权时忽略客户 cookie，返回 local admin，避免 /me 登录挡住员工 API
- `App.tsx`：员工 `AuthPanel` 与管理口令栏用 `false &&` 短路；客户 `/apply` `/me` 未动
- 版本 0.9.46

### 未完成 / 注意

- 用户未要求恢复前，不要把自动登录检测加回去
- unittest / Docker 仍可用 `STOCKGOOD_AUTH_REQUIRED=true`

---

## Handoff - 2026-09-22 (出库每箱运单与运费)

### 当前任务

FEATURE: OUTBOUND_BATCH — 按第一批 1-5 / 第二批 1-3 写入快递单与运费

### 已完成

- `shipments.freight_jpy`；各箱都有金额时 `freight_cny = sum(freight_jpy) * freight_exchange_rate`
- 第一批出库批次 #1 箱 1-5 已写入 A-E 运单与运费
- 第二批出库批次 #2 已从库存箱 1-3 创建，箱 1-3 写入 F-H 运单与运费；库存箱已清空

### 未完成

- 无

---

## Handoff - 2026-09-14 (SF 申报导出)

### 当前任务

FEATURE: SF_EXPORT — 按业务样表导出顺丰申报 Excel

### 原因

用户提供样表 `女神异闻录杂货混(1).xlsx`，要求按该列格式做出库 SF 导出。

### 已完成

- 模板 `backend/data/templates/sf_export.xlsx`
- `sf_template.build_sf_workbook` + `export_sf_xlsx` / preview
- 出库 Tab「导出 SF」（草稿不要求包装尺寸）
- A 列发货箱号；**0.9.41** 起出库每箱独立快递单号（不再强制同批统一）
- unittest 通过；版本 **0.9.41**

### 口径（待用户确认）

- A 列「运单号*」= **发货箱号** `FIT{批次}-{箱号}`（草稿 `DRAFT-{箱号}`），与 INV packing 一致；非快递单号
- 品牌 = 货品 `ip`（空则空）
- 产地 = 日本；规格 = 个
- 收件人固定：张超 / 天津武清腾越云仓（省栏空，与样表一致）
- 同箱内同条码同单价合并数量；单价为日元文本 `0.00`

### 未完成 / 下一步

- 等用户验收字段口径；若品牌不应取 ip 或收件人要可配，再改

---

## Handoff - 2026-09-13 (STORES curl 商品 URL)

### 当前任务

FEATURE: ORDER_IMPORT — STORES 商品链接直抓

### 原因

`httpx` 对 `*.stores.jp` 常返回 Cloudflare 403；本机 `curl.exe` 可拿到 SSR HTML。

### 已完成

- `fetch_stores_html` / `scrape_stores_product`（curl，同 1999 策略）
- `scrape_url` 走 curl；6 条用户 URL 冒烟通过
- 版本 **0.9.36**

### 用法

直接批量粘贴 `/items/{id}` 链接；失败再贴商品页源代码。

---

### 当前任务

FEATURE: ORDER_IMPORT — STORES 已渲染「購入詳細」HTML

### 原因

用户粘贴 Elements 整页（含 `.order_history_item`），非空壳、非 JSON；0.9.33 仅有 JSON/商品 HTML，可能误走商品解析。

### 已完成

- `is_stores_order_detail_html` / `parse_stores_order_detail_html`；preview 优先于商品 HTML
- fixture `storesjp.order-detail.fixture.html` + 测试
- tip / 版本 **0.9.34**

### 用法

1. 商品：`/items/{id}` 源代码整页粘贴
2. 注文：購入詳細 Elements（含商品行）整页粘贴，或 Network `/web/customers/orders/{id}` JSON

---

## Handoff - 2026-09-13 (STORES / SHIBUYA TSUTAYA)

### 当前任务

FEATURE: ORDER_IMPORT — `*.stores.jp`（shibuyatsutaya）解析

### 原因

商品页 SSR 可用但服务器直连常 Cloudflare Captcha；注文页为 SPA（router-view），Ctrl+U 无行项目。注文 API：`GET /web/customers/orders/{id}`；行在 `deliveries[].items[]`，金额 `salesDetail.salesPayment` 为小计。

### 已完成

- `backend/app/scrapers/storesjp.py` + preview / tip / `stores:item:{id}`
- fixtures + `test_storesjp_order.py`
- 版本 **0.9.33**（其后 0.9.34 补 HTML 注文）

### 用法

1. 商品：浏览器打开 `/items/{id}` → 查看网页源代码整页粘贴（链接直连多半被拦）
2. 注文：Network → `/web/customers/orders/{id}` → Copy response；或已渲染購入詳細 HTML

---

## Handoff - 2026-09-13 (Yostar OFFICIAL SHOP)

### 当前任务

FEATURE: ORDER_IMPORT — shop.yostar.co.jp 解析

### 原因

站点为 SPA（`#app` 空壳 + `ecshop-api`）。用户给的「订单页源代码」只有静态壳，无法解析行项目。商品页需调 API；注文需登录后的 Network JSON。

### 已完成

- `backend/app/scrapers/yostar.py`：商品 `POST /ecshop-api/api/v1/product/detail`（`product_id` 须为 int）；价取 `sku[].price`；注文/商品 JSON 粘贴；SPA 空壳检测
- `preview.py` / `App.tsx` tip / `scrapePaste.ts` 匹配键 `yostar:product:{id}`
- fixture + `test_yostar_order.py`
- 版本 **0.9.32**

### 用法

1. 商品：直接贴 `https://shop.yostar.co.jp/products/detail/{id}`（可多行）
2. 注文：登录后 F12→Network→`/api/v1/order/detail`→Copy response 粘贴（Ctrl+U 无效）

### 验收

硬刷新前端后批量抓取用户给的三件商品 URL，应得到三行（单价约 ¥1980）。

---

## Handoff - 2026-09-13 (ZOZO 分色去重)

### 当前任务

FEATURE: ORDER_IMPORT — ZOZO 注文详情同商品不同色只显示一行

### 原因

后端已按 `did` 解析出多行；前端 `scrapeProductMatchKey` 只用 `host+path`，丢掉 `?did=`，`appendScrapeProducts` 把第二色当成重复跳过。

### 已完成

- `scrapePaste.ts`：ZOZO 匹配键改为 `zozo:goods:{gid}:did:{did}`
- 版本 **0.9.31**

### 验收

1. 硬刷新前端后重新粘贴本单 HTML
2. 应出现 2 行：その他7 ×5、その他8 ×3

---

## Handoff - 2026-09-13 (medicos 購入履歴詳細)

### 当前任务

FEATURE: ORDER_IMPORT — medicos-e-shop.net（MEDICOS ONLINE SHOP）EC-CUBE「購入履歴詳細」HTML 粘贴导入

### 已完成

- `medicos.py`：识别/解析 `ec-orderDelivery__item` / `ec-imageGrid`；注文号、送料、合计；邮件 `BOXJAN` 回填 barcode；无商品链接时用图片文件名作 product_id；按 pid/品名合并数量
- 前端抓取提示 + `scrapePaste` 的 `medicos:product:{id}`
- fixture + `test_medicos_order.py`；版本 **0.9.30**

### 验收

1. 重启后端后粘贴真实「購入履歴詳細」整页源代码
2. 导入请用影子库（`STOCKGOOD_DB_MODE=shadow`）

### 相关文件

- `backend/app/scrapers/medicos.py`
- `backend/app/scrapers/templates/medicos-e-shop.mypage-history.fixture.html`
- `backend/test_medicos_order.py`

---

## Handoff - 2026-09-13 (lafary Shopify 注文)

### 当前任务

FEATURE: ORDER_IMPORT — lafary.shop（LAFARY ONLINE）Shopify「注文 #…」HTML 粘贴导入

### 已完成

- `lafary.py`：识别/解析 `table.order-summary` / `line-item` / `sale-price`；注文号、送料、合计；按品名合并数量；订单页通常无 JAN
- 前端抓取提示 + `scrapePaste` 的 `lafary:product:{handle}`
- fixture + `test_lafary_order.py`；版本 **0.9.29**

### 验收

1. 重启后端后粘贴真实注文页源代码
2. 导入请用影子库（`STOCKGOOD_DB_MODE=shadow`）

### 相关文件

- `backend/app/scrapers/lafary.py`
- `backend/app/scrapers/templates/lafary.shop.customers-order.fixture.html`
- `backend/test_lafary_order.py`

### 已完成

- ...

### 未完成

- ...

### 下一步建议

- ...

### 关键文件

- `...`

### 需要特别注意

- ...

### 不要做

- ...

---

## Handoff - 2026-09-13 (eeo ご注文履歴詳細)

### 当前任务

FEATURE: ORDER_IMPORT — eeo.today（eeo Store）「ご注文履歴詳細」HTML 粘贴导入

### 已完成

- `eeo.py`：识别/解析 `.ec-orderDelivery__item`、ご注文番号、送料、合计；单价取自 `￥N × qty`；邮件正文「商品コード」按品名回填 barcode；按 pid 合并数量
- 接入 `preview.scrape_html_document`（animate 订单分支之后）
- 前端抓取提示 + `scrapePaste` 的 `eeo:product:{id}`
- fixture + `test_eeo_order.py`；版本 **0.9.27**

### 未完成

- 用户用真实整页源代码在抓取 Tab 验收（建议影子库导入）

### 下一步建议

1. **重启后端**（否则仍跑旧代码）
2. eeo Store「ご注文履歴詳細」→查看网页源代码→整页粘贴
3. 核对注文番号 / 运费 / 合计 / 各 SKU 数量与单价 / JAN（若邮件区有商品コード）

### 关键文件

- `backend/app/scrapers/eeo.py`
- `backend/app/scrapers/templates/eeo.today.order-history-detail.fixture.html`
- `backend/test_eeo_order.py`
- `backend/app/scrapers/preview.py`
- `frontend/src/App.tsx` / `frontend/src/scrapePaste.ts`

---

## Handoff - 2026-09-13 (animate 注文履歴)

### 当前任务

FEATURE: ORDER_IMPORT — animate-onlineshop.jp（アニメイト通販）「注文履歴」HTML 粘贴导入

### 已完成

- `animate.py`：识别/解析 `.order_item`、注文番号、配送料・手数料、注文合計金額；行内金额按小计÷点数得单价；跳过 `.order_item_privilege`；按 pid 合并数量
- 接入 `preview.scrape_html_document`（cystore 订单分支之后）
- 前端抓取提示 + `scrapePaste` 的 `animate:product:{pd}`
- fixture + `test_animate_order.py`；版本 **0.9.26**

### 未完成

- 用户用真实整页源代码在抓取 Tab 验收（建议影子库导入）

### 下一步建议

1. **重启后端**（否则仍跑旧代码）
2. アニメイト「注文履歴」→查看网页源代码→整页粘贴
3. 核对注文番号 / 运费 / 合计 / 各 SKU 数量与单价（单价=小计÷点数）

### 关键文件

- `backend/app/scrapers/animate.py`
- `backend/app/scrapers/templates/animate-onlineshop.jp.order-history.fixture.html`
- `backend/test_animate_order.py`
- `backend/app/scrapers/preview.py`
- `frontend/src/App.tsx` / `frontend/src/scrapePaste.ts`

---

## Handoff - 2026-09-13 (字符半角约束)

### 当前任务

协作规则：所有代码侧字符统一英文半角格式

### 已完成

- `.cursor/rules/important-constraints.mdc` 增加「字符格式：统一用英文半角」
- `AGENTS.md` Safety Rules 同步
- 版本 **0.9.25**

### 要点

- 代码/配置/路径/正则/键名：半角 `()[]{}:;,."'`
- 中日文正文可保留；标点优先半角
- 抓取匹配外部页面原文时保留站点全角

---

## Handoff - 2026-09-13 (cystore 購入履歴詳細)

### 当前任务

FEATURE: ORDER_IMPORT — cystore.com（CyStore）「購入履歴詳細」HTML 粘贴导入

### 已完成

- `cystore.py`：识别/解析订单行、ご注文番号、配送料金、総合計；图路径取 product_id；兼容 `clas="cartitem__name"`；按 pid 合并数量
- 接入 `preview.scrape_html_document`（sofmap 订单分支之后）
- 前端抓取提示 + `scrapePaste` 的 `cystore:product:{pid}`
- fixture + `test_cystore_order.py`；版本 **0.9.24**

### 未完成

- 用户用真实整页源代码在抓取 Tab 验收

### 下一步建议

1. **重启后端**（否则仍跑旧代码）
2. CyStore「購入履歴詳細」→查看网页源代码→整页粘贴
3. 核对注文番号 / 运费 / 合计 / 各 SKU 数量

### 关键文件

- `backend/app/scrapers/cystore.py`
- `backend/app/scrapers/preview.py`
- `backend/test_cystore_order.py`
- `frontend/src/App.tsx`
- `frontend/src/scrapePaste.ts`

### 不要做

- 不要期望订单页带出 JAN（通常没有）
- 不要把订单页误走单商品 PDP 解析

---

## Handoff - 2026-09-13 (sofmap 订单详情)

### 当前任务

FEATURE: ORDER_IMPORT — sofmap「お取引の詳細」HTML 粘贴导入

### 已完成

- `sofmap.py`：订单行/注文番号/送料/合计；图 URL JAN；按 SKU 合并
- 接入 `scrape_html_document`；前端 `scrapeProductMatchKey` 按 sku 匹配
- `test_sofmap_order.py`；版本 **0.9.23**

### 未完成

- 用户用真实整页源代码在抓取 Tab 验收

### 下一步建议

- 粘贴「お取引の詳細」源码，确认 5 行、数量 70、JAN、运费 0、注文番号自动填入

### 关键文件

- `backend/app/scrapers/sofmap.py`
- `backend/app/scrapers/preview.py`
- `backend/test_sofmap_order.py`
- `frontend/src/scrapePaste.ts`
- `frontend/src/App.tsx`

### 不要做

- 不要把订单页误走单商品 PDP 解析

---

## Handoff - 2026-09-13 (sofmap 商品页)

### 当前任务

FEATURE: ORDER_IMPORT — sofmap.com 商品详情页抓取

### 已完成

- `backend/app/scrapers/sofmap.py`：解析品名/特价/JANコード/商品图/发售日；shop 归一 sofmap.com
- 接入 `scrape_url` / `scrape_html_document`；忽略站点 OGP
- fixture + `test_sofmap_product.py`；版本 **0.9.22**

### 未完成

- 用户用真实商品 URL 在抓取 Tab 验收

### 下一步建议

- 粘贴 `https://a.sofmap.com/product_detail.aspx?sku=102018397` 确认 JAN/图/价格

### 关键文件

- `backend/app/scrapers/sofmap.py`
- `backend/app/scrapers/preview.py`
- `backend/test_sofmap_product.py`
- `frontend/src/App.tsx`（提示文案）

### 不要做

- 不要在未要求时做 sofmap 订单页解析

---

## Handoff - 2026-09-13 (JAN 回填)

### 当前任务

FEATURE: ORDER_IMPORT — 订单后再抓商品页自动回填 JAN

### 已完成

- `scrapeProductMatchKey`：vvstore `/products/detail/{id}` 按商品 ID 匹配订单行与 PDP
- `appendScrapeProducts`：同 key 且原行无条码时回填 JAN（不覆盖已有）
- 抓取完成提示含「回填 JAN N 条」；版本 **0.9.21**

### 未完成

- 用户用真实流程验收：先粘贴注文詳細 → 再批量粘贴商品详情 URL

### 下一步建议

- 验收：清单 JAN 列应自动填入；已有 JAN 不被覆盖

### 关键文件

- `frontend/src/scrapePaste.ts`（`scrapeProductMatchKey`）
- `frontend/src/App.tsx`（`appendScrapeProducts`）

### 不要做

- 不要在订单 HTML 解析里硬造 JAN
- 不要自动替用户请求全部商品页（当前是用户再粘贴/再抓）

---

## Handoff - 2026-09-13

### 当前任务

FEATURE: ORDER_IMPORT — vvstore.jp ご注文履歴詳細 HTML 粘贴导入

### 已完成

- `backend/app/scrapers/vvstore.py`：解析品名/单价/数量/图/注文番号/运费；同商品 URL 合并数量
- 接入 `scrape_html_document`；抓取 Tab 提示
- `test_vvstore_order.py` 通过；版本 **0.9.20**
- 本页无 JAN（已告知用户）

### 未完成

- 用户用真实「ご注文履歴詳細」整页源代码验收
- ~~（可选）商品详情页补 JAN~~ → 见上方 0.9.21 Handoff

### 下一步建议

- 用户粘贴整页源代码验收；确认注文番号/运费是否自动填入抓取表单

### 关键文件

- `backend/app/scrapers/vvstore.py`
- `backend/app/scrapers/preview.py`
- `backend/test_vvstore_order.py`
- `frontend/src/App.tsx`

### 需要特别注意

- vvstore 详情页是 SSR，一般用「查看网页源代码」即可
- 生产库禁止写测试订单

### 不要做

- （已由用户请求落地）vvstore 商品详情补 JAN 见 0.9.21

---

## Handoff - 2026-09-12

### 当前任务

FEATURE: ORDER_IMPORT — &mall 注文履歴粘贴导入（HTML / Elements / Network JSON）

### 已完成

- `andmall.py`：HTML + Elements 片段 + `shop-order-skus` JSON（可多页粘贴合并）
- 说明：Ctrl+U「查看网页源代码」点もっと見る后**不会变**（仅 SSR）
- 样例 HTML 10 行 → 4 种；JSON 多页合并测试通过
- 版本 **0.9.19**（HTML 片段误当 URL → Invalid IPv6 已修；粘贴后按钮应为「解析 HTML」）

### 未完成

- 用户用 Elements / Network 粘贴完整 29 件验收
- 列表页无单价/JAN

### 下一步建议

- 用户按 Elements 或 Network 方式粘贴后验收

### 关键文件

- `backend/app/scrapers/andmall.py`
- `backend/app/scrapers/preview.py`
- `backend/app/scrapers/templates/mitsui-shopping-park.com.order-history.md`
- `backend/test_andmall_order.py`

### 需要特别注意

- 不要教用户再靠「查看网页源代码」拿もっと見る后的内容
- 生产库禁止写测试订单

### 不要做

- 未验收前不要扩大到其它三井页面

---

## Handoff - 2026-08-14

### 当前任务

把测试从「有」补到能挡住导出写错格、双鉴权漏权、进库确认撤回、改批次货款重算。

### 已完成

- INV：双 Sheet 名（`PACKING LIST ` 尾随空格）、PACKING **F5** 写 INV 号且 **F6 不被占用**、预览 `FIT0`、模板文件哈希不变
- 费用明细：`发货费用明细` + `对应订单`、表头与订单号/件数、模板不被写回
- Cookie 与 `X-Admin-Token`：无凭证 401、错 token 401、仅 token 当管理员；已登录顾客/仓库**不会**被 token 提权
- 进库确认撤回 → `inbound_shipped`；编辑批次改数量后货款 225→175 CNY
- 版本 **0.9.16**

### 未完成

- 未经用户明确要求不得 git commit
- 未抽 App.tsx hooks / 未拆 main.py routers
- 规范第 8 节仍待实现

### 下一步建议

- 架构还债下一刀：从 `App.tsx` 抽 hooks（不改布局）
- 业务功能等用户下一条指令

### 关键文件

- `backend/tests/test_exports.py`
- `backend/tests/test_auth_roles.py`
- `backend/tests/test_order_flow.py`
- `backend/tests/factories.py` / `harness.py`

### 需要特别注意

- 测试仍禁止写生产库或共享影子库
- 不要拆 App/api.ts/main.py；不要把第 8 节当 bug
- 不要写回 INV / 费用明细模板文件

### 不要做

- 不要为了测试改导出格位或鉴权行为
- 不要在用户明确要求前 commit

---

## Handoff - 2026-08-14

### 当前任务

基础设施：可记录迁移、关键路径测试、OpenAPI 生成 TS 类型（不拆 App/main、不改业务规则）。

### 已完成

- `schema_migrations` + `backend/app/schema_migrations.py`（现有幂等步骤登记后可跳过）
- `STOCKGOOD_DATABASE_PATH` 覆盖库路径；unittest 只用临时 sqlite
- `backend/tests/`：状态流 / 合箱 / 出库锁定+撤回 / 角色 / 迁移（含 UNIQUE 拆除保 `shipment_items`）
- `scripts/gen-api-types.py` → `frontend/src/api-types.generated.ts`；`api.ts` 类型改为引用
- 版本 **0.9.15**

### 未完成

- 未经用户明确要求不得 git commit
- 未拆 `App.tsx` / `main.py`（有意）
- 规范第 8 节仍待实现

### 下一步建议

- 新迁移只追加 `MIGRATIONS`，保持幂等；改 Pydantic 后跑 `python scripts/gen-api-types.py`
- 跑测试：`backend/.venv/Scripts/python.exe -m unittest discover -s tests -v`（在 `backend/` 下）
- 业务功能等用户下一条指令

### 关键文件

- `backend/app/schema_migrations.py`
- `backend/app/database.py` / `backend/app/settings.py`
- `backend/tests/`
- `scripts/gen-api-types.py`
- `frontend/src/api-types.generated.ts` / `frontend/src/api.ts`

### 需要特别注意

- 测试**禁止**写 `stockgood.sqlite` 或共享 `stockgood.shadow.sqlite`
- 去掉 tracking UNIQUE 时仍须先 `conn.commit()` 再 `PRAGMA foreign_keys=OFF`
- 不要拆 App/api.ts/main.py；不要把第 8 节当 bug

### 不要做

- 不要引入 Alembic / openapi-typescript 除非用户要求
- 不要把 fetch 封装整文件改成生成代码
- 不要在用户明确要求前 commit

---

## Handoff - 2026-08-14

### 当前任务

建立 AI 代码导航 + 长期上下文/交接机制（非业务功能）。

### 已完成

- FEATURE 索引：`docs/CODE_INDEX.md`、主要代码 `FEATURE:` 注释
- `AGENTS.md` 工作规则 + 上下文恢复 / Checkpoint / Incomplete Context
- 本文 `docs/CHANGELOG_AI.md`（Current State + 历史决策）
- README「项目导航」指向上述文档

### 未完成

- 上述文档与注释尚未 commit（**未经用户明确要求不得 commit**）
- 无未完成的业务代码

### 下一步建议

- 新会话：读 AGENTS → README → CODE_INDEX → 本文 → 最近 Handoff，再改代码
- 若继续业务：默认从用户下一条指令开始，不要主动改 INV/出库/申请流
- 规范第 8 节保持「待实现/旧行为」，不要当 bug 改

### 关键文件

- `AGENTS.md`
- `docs/CODE_INDEX.md`
- `docs/CHANGELOG_AI.md`
- `docs/client-product-rules.md`（客户侧拍板规则；第 8 节暂不开发）
- `frontend/src/App.tsx`（单页多 Tab，无独立出库页文件）
- `backend/app/services/outbound_batches.py`
- `backend/app/services/inv_template.py`
- `backend/app/database.py`

### 需要特别注意

- 工作区根是 `stockgood/`；Git 仓库可能在上一级 `good-bate1.0.01/`
- 测试写操作只用影子库；改实际库存须用户确认
- 未明示则不改 UI 布局/文案/控件位置
- INV / 费用明细模板**只读填充，禁止写回模板文件**
- PACKING LIST 的 Sheet 名带**尾随空格**：`"PACKING LIST "`
- 同出库批次必须同一运单号；不同批次/进库不可复用

### 不要做

- 不要把 INV 改回「从零建 xlsx」
- 不要把运单号改回全局 UNIQUE
- 不要在事务内对 `shipments` 做 DROP/重建（须先 commit 再关 FK）
- 不要补写 UNIQUE 迁移事故已省略的箱数、单号等恢复细节
- 不要把规范第 8 节（改密/凭证/二次确认/未登录列表）当 bug 改；那是待实现，现码是旧行为
- 不要删除「看起来多余」的兼容字段（如遗留 `X-Admin-Token`、空运单 `__none__` 前缀）
- 不要拆 `App.tsx` / `api.ts` / `main.py`
- 不要把文档/导航规划描述成已实现的产品功能；当前未提交内容是文档与导航注释，无业务逻辑 / API / 数据库变更
- 不要在用户明确要求前执行 git commit

---

## 2026-09-12

### FEATURE: ORDER_IMPORT — &mall もっと見る / Elements / JSON（0.9.18）

#### 修改内容

- 澄清：Ctrl+U 只反映 SSR，点もっと見る后源码不变
- 支持 Elements outerHTML 片段、Network JSON（可多段粘贴合并）
- 不全页计数时改提示用 Elements / Network，不再说「再复制源代码」

#### 原因

用户点了もっと見る但「查看网页源代码」仍是 10/29。

---

### FEATURE: ORDER_IMPORT — &mall 注文履歴

#### 修改内容

- 新增 `andmall.py`：识别 mitsui-shopping-park 注文履歴 DOM，解析品名/数量/图/mallSkuId
- 相同 mallSkuId（其次色番）合并数量；从品名提取 `YYYY-MM` 发货月
- `scrape_html_document` 优先走该解析；前端抓取说明补一行

#### 涉及文件

- `backend/app/scrapers/andmall.py`
- `backend/app/scrapers/preview.py`
- `backend/app/scrapers/templates/mitsui-shopping-park.com.order-history.md`
- `backend/test_andmall_order.py`
- `frontend/src/App.tsx`（提示文案）

#### 原因

用户订单履历里同款多行下单，导入时需要自动合并数量，避免手工累加。

#### 用户确认

- 用户要求「做一个吧，重复商品自动合并」；单元测试已用其样例 HTML 验证，待页面粘贴验收。

#### 影响范围

- 仅 HTML 粘贴抓取路径；不影响 URL 抓取其它站点

#### 风险

- 「もっと見る」未点时只解析当前页已渲染行
- 无单价/JAN

---

## 2026-08-14

### FEATURE: INV_EXPORT / FEE_DETAIL / AUTH / ACTION_LOG / OUTBOUND_BATCH

#### 修改内容

- 补 unittest：导出模板契约、Cookie 与遗留 token 双路径、进库确认撤回、编辑批次重算货款
- 不改导出填充逻辑、不改鉴权规则

#### 涉及文件

- `backend/tests/test_exports.py`
- `backend/tests/test_auth_roles.py`
- `backend/tests/test_order_flow.py`
- `backend/tests/factories.py`
- `backend/tests/harness.py`（`STOCKGOOD_ADMIN_TOKEN` 按用例隔离）

#### 原因

JSON/OpenAPI 测不到 Excel 格位；只测 Cookie 测不到旧口令门。改数量后若不重算会锁错应收。

#### 用户确认

- 用户要求做架构还债第 4 步（挡得住导出和双鉴权，含撤回与改批次重算）

---

### FEATURE: SYSTEM

#### 修改内容

- 列迁移从 `init_db` 内联改为具名幂等步骤，写入 `schema_migrations`
- unittest 经 `STOCKGOOD_DATABASE_PATH` 使用临时库，避免污染影子库
- OpenAPI → `api-types.generated.ts`，停止在 `api.ts` 手抄 Pydantic 模型

#### 涉及文件

- `backend/app/schema_migrations.py`
- `backend/app/database.py`
- `backend/app/settings.py`
- `backend/tests/`
- `scripts/gen-api-types.py`
- `frontend/src/api.ts` / `frontend/src/api-types.generated.ts`

#### 原因

架构评审优先项：迁移可追踪、关键路径可回归、前后端类型单一来源。不拆大文件、不改业务规则。

#### 影响范围

启动路径仍 `init_db()`；旧库第一次启动会跑完全部步骤并打戳。API 行为不变。

#### 用户确认

- 用户：「现在就改吧」（针对迁移记录 / 关键测试 / 生成 TS 类型）

---

### FEATURE: INV_EXPORT

#### 修改内容

- 不再从零生成 INV 表格，改为填充固定模板 `backend/data/templates/inv_fit_shipping.xlsx`
- 双 Sheet：`inv` 与 `PACKING LIST `（名称**带尾随空格**，必须原样使用）
- INV 号：`{YYYYMM}/{DD}FIT{batch_id}-{total_qty}`；草稿预览 `batch_id` 固定为 `0`
- 文件名：`INV_YYYYMMDD_FIT{batch}_{qty}.xlsx`
- 出库箱增加净毛重、长宽高；批次增加 `invoice_ship_date`
- 导出前校验包装字段；缺则 400
- PACKING LIST 的 INVOICE NUMBER 写入模板原格 **F5**（0.9.10 曾误写 F6，0.9.11 已修）

#### 涉及文件

- `backend/app/services/inv_template.py`
- `backend/app/services/outbound_batches.py`（`export_inv_xlsx` / `export_inv_preview_xlsx`）
- `backend/app/database.py`（包装列、`invoice_ship_date` 用 `_ensure_column`）
- `frontend/src/App.tsx`（出库 Tab「导出 INV」）
- `frontend/src/api.ts`（`downloadOutboundInv` / `downloadOutboundInvPreview`）

#### 修改原因

用户提供现成 FIT 发货单模板，要求保留格式与双表结构，只填数。从零建表会毁掉边框/列宽/公式布局。

#### 调用链影响

出库 Tab「导出 INV」
↓
`downloadOutboundInv` / `downloadOutboundInvPreview`
↓
`GET .../inv.xlsx` 或 `POST .../preview-inv.xlsx`
↓
`export_inv_xlsx` → `build_inv_workbook`
↓
只读打开模板 → 填单元格 → 返回 bytes（**不写回模板文件**）

#### 兼容性 / 注意事项

- **禁止**对 `inv_fit_shipping.xlsx` 做 save/write-back
- Sheet 名 `PACKING LIST ` 的空格是模板原名，改掉会找不到表
- INV 表上 G.Total 一类格子是 **INV 号码**，不是金额合计；UNIT PRICE 是单价不是行金额
- 种类英文映射在 `inv_template.KIND_EN`；未知种类回落到 `Toys`
- 收货人英文块写死在 `CONSIGNEE_EN`，不要随手改成中文或删掉换行

#### 用户明确要求

- INV 必须保持两个 worksheet
- 模板只读使用
- 草稿预览批次段为 `0`
- 导出错误提示要能显示 FastAPI `detail`（包装字段缺失时）

#### 未完成

- 无代码待办。现有批次若缺包装字段会 400，属预期，不是 bug。

#### 验证

- 影子库导出验收：双表一致、格式未毁、原模板未改（0.9.10）
- PACKING LIST F5 人工核对（0.9.11）

---

### FEATURE: FEE_DETAIL

#### 修改内容

- 发货费用明细改为固定双 Sheet 模板：`发货费用明细` + `对应订单`
- 子表按箱号列出该箱订单号与件数（箱号/运单可合并单元格）
- 线上路径是 `export_fee_detail_xlsx`；`backend/_enrich_fee_detail.py` 只是历史手工脚本，**不是**导出实现

#### 涉及文件

- `backend/app/services/outbound_batches.py`（`export_fee_detail_xlsx`）
- `backend/data/templates/fee_detail.xlsx`
- `frontend/src/App.tsx`（按钮「费用明细 Excel」）
- `frontend/src/api.ts`（`downloadOutboundFeeDetail`）

#### 修改原因

客户对账需要「每箱对应哪些订单」，单表不够。

#### 调用链影响

出库「费用明细 Excel」（需财务角色 `require_finance`）
↓
`GET /api/outbound-batches/{id}/fee-detail.xlsx`
↓
读批次/箱/货品/订单汇率 → 填模板 → xlsx bytes

#### 兼容性 / 注意事项

- 模板只读，不要写回
- 底部运费/合计 CNY 依赖批次财务字段和订单汇率；没有汇率时 CNY 为空是预期
- 不要把 `_enrich_fee_detail.py` 接到 API 上

#### 用户明确要求

- 子表必须按箱列出订单
- 主表保留货品金额口径（与 INV 数量×单价应对得上）

#### 未完成

- 无

#### 验证

- 0.9.14 按模板导出；金额口径曾与 INV 对过（合计 JPY 一致）

---

### FEATURE: OUTBOUND_BATCH

#### 修改内容

- 同一出库批次各箱**必须同一运单号**；不同批次以及进库单号不可复用（0.9.12–0.9.13）
- 去掉 `shipments.tracking_no` 的 UNIQUE 索引（SQLite 需重建表）
- 未签收前可编辑批次（改箱/数量/移回在库并重算货款应收）
- 出库草稿存在 `localStorage` key `stockgood.outboundDraft.v1`，创建成功后清空

#### 涉及文件

- `backend/app/database.py`（`_drop_shipments_tracking_unique`）
- `backend/app/services/outbound_batches.py`（`_require_shared_batch_tracking`、`create_batch`、`update_batch`）
- `backend/app/services/shipments.py`（空运单用 `__none__` + uuid 占位，因 SQLite UNIQUE 不能存多个空串——UNIQUE 去掉后该前缀仍在用，**不要随意删除**）
- `frontend/src/App.tsx`（出库 Tab；同步各箱运单）

#### 修改原因

一批货多箱走同一快递单号是真实业务；旧 UNIQUE 会卡死整批发同一个号。

#### 调用链影响

出库 Tab 创建/编辑
↓
`POST|PUT /api/outbound-batches`
↓
校验同批次运单一致 + 跨批次/进库不冲突
↓
写 `outbound_batches` + `shipments` + `shipment_items`，更新 `items.status`

#### 兼容性 / 注意事项

- **踩坑（必须记住）**：在未提交事务里执行 `PRAGMA foreign_keys=OFF` 会被 SQLite 忽略；随后 `DROP TABLE shipments` 会在 FK 仍 ON 时级联清空 `shipment_items`。
- **可确认规则（用户 2026-08-14 确认）**：关外键、重建 `shipments` 之前必须先 `conn.commit()`。见 `database.py` `_drop_shipments_tracking_unique`。
- **不要**推断或补写已省略的恢复细节（箱数、单号等）。
- 不要把运单号改回全局 UNIQUE。
- 创建批次时锁定货款应收；改数量会重算。签收后不要当草稿改。

#### 用户明确要求

- 同批次共用一个运单号
- 不同批次 / 进库不能用同一个号
- 未明示不改出库页布局

#### 未完成

- 无代码待办

#### 验证

- 迁移代码已改为先 commit 再关 FK。事故恢复的箱数/单号等细节**不记录、不补写**。

---

### 文档：AI 代码导航（非业务 FEATURE）

#### 修改内容

- 新增 `AGENTS.md`、`docs/CODE_INDEX.md`；README 增加「项目导航」
- 在主要入口加 `FEATURE:` / `SHARED MODULE` 注释，**未改业务逻辑**

#### 修改原因

让新会话用 FEATURE 定位代码，避免每次全仓扫描。

#### 用户明确要求

- 不删代码、不重构拆文件、不改 API/库
- 主界面保持 `App.tsx` Tab，不要虚构 `OutboundBatchPage.tsx`

#### 未完成

- 未 commit

---

## 2026-08-12

### FEATURE: ORDER_REQUEST / CUSTOMER_PORTAL / APPLY_STATS

#### 修改内容

- 申请须登录；状态 `pending_payment` → 确认定金后 `submitted` → 员工 `ordered` / `rejected`
- 定金默认商品金额 30%（`STOCKGOOD_DEPOSIT_RATE`）
- 双编号：全站 `request_code`（`SG-0001…`，后台/统计）+ 账户 `account_order_no`（`SG{用户ID}-0001…`，用户端只显示这个）
- 旧按账户编号的历史值保留不改写
- 员工不可对未付定金申请「确认已下单」
- 统计 Tab：日/月单量、热门链接、花费用户、商品 IP

#### 涉及文件

- `backend/app/services/order_requests.py`
- `backend/app/services/apply_stats.py`
- `frontend/src/ApplyPage.tsx`、`MePage.tsx`、`App.tsx`
- `docs/client-product-rules.md`

#### 修改原因

模式 B：员工 + 客户账号；先收定金再下单；台账要全站流水、客户只要自己的账户流水。

#### 兼容性 / 注意事项

- **待实现 / 旧行为**（规范第 8 节已确定，代码未落地；**不是 bug**）：
  - `/me` 改昵称 / 改密码
  - 定金须支付单号 + 截图，员工二次确认后才「已提交」
  - 申请页去掉未登录公开列表
  - 固定文案「财务系统对接前可手动确认」
- 现码仍允许客户/员工直接 `confirmDeposit` 把状态打到 submitted（无截图、无二次确认）。这是**旧行为**，不是漏改。
- `POST /api/auth/change-password` 已存在但前端未调用（待实现，不是漏接）。

#### 用户明确要求

- 客户：`/apply` 下单，`/me` 看自己的单；退出只在 `/apply` 用户名菜单，`/me` 不做退出按钮
- 不做多租户、不做网站自动下单付款
- 用户端只显示账户流水

#### 未完成

- 个人主页迭代（规范第 8 节整表）

---

### FEATURE: AUTH / USER_MANAGEMENT

#### 修改内容

- Cookie 会话；角色 `admin` / `warehouse` / `finance` / `customer`
- 兼容遗留 `STOCKGOOD_ADMIN_TOKEN` / `X-Admin-Token`（`getAdminToken`）
- 本地未强制 `STOCKGOOD_AUTH_REQUIRED` 时员工 API 仍可无登录使用

#### 兼容性 / 注意事项

- 不要删 `X-Admin-Token`：旧口令路径仍可能用
- 生产推荐 bootstrap 管理员 + `STOCKGOOD_AUTH_REQUIRED=true`

---

## 2026-08-08 及更早（压缩记录）

只保留后续 Agent 容易误判的决策：

### FEATURE: INVENTORY

- 合箱**不改变**货品状态，也不等于出库装箱。
- 子箱可挂主箱一层；筛选时子箱缩进在主箱下，不要改回平级列表。
- 未选目标箱则新建；已选则合入。不要「优化」成另一种交互，除非用户要求改 UI。

### FEATURE: FINANCE

- 下单汇率一单一条，商品与订单运费同汇率折 CNY。
- 国际运费优先按出库箱 `freight_jpy`：各箱都有金额时，`freight_cny = 各箱合计 × 运费汇率`。否则仍为 `运费单价(JPY) × 计费重量 × 运费汇率`。与下单汇率独立。
- 货款应收在**创建出库批次时锁定**。
- 财务「本月下单」按 `orders.ordered_at`；「本月出库」按批次 `created_at`。与订单页「本月预计发货」不是同一口径。

### FEATURE: ORDER / SYSTEM（商品种类）

- 种类按品名关键字识别，可手动改；别名在 `backend/data/product_kinds.json`。
- `ぬいぐるみ` / `ぬい` / `マスコット` / plush = **玩偶**，不要再标成挂件。

### 工程约束（用户长期要求）

- 未明确要求时**不改 UI 位置/布局/按钮文案**。
- 可交付改动写 `CHANGELOG.md` 并升版本（`VERSION`、`main.py`、`frontend/package.json`）。
- 测试数据只写影子库 `STOCKGOOD_DB_MODE=shadow`。
- 会改实际库存：先影子库验收，用户确认后再动生产库。
- 不做：客户档案/地址、实时汇率、爬承运商轨迹、iframe 物流页、与 animegood 共用库。

---

## 维护说明

以后 Agent：

- 改业务规则 / API / 库读写 / 导入导出 / 兼容逻辑 / 用户硬性要求 → **必须**在对应日期下追加 `### FEATURE: XXXXX`
- 纯注释、格式化、无逻辑重构 → **不要**写入
- 大阶段结束 → 更新 Current Development State，必要时追加一条 Handoff
- 原则：记录决策，不记录流水账；记录原因，不复制整段代码；记录风险，不堆日志
