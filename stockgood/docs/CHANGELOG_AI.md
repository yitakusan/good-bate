# AI Development Changelog

本文件用于记录 AI Coding Agent 在项目开发中的重要上下文。

目的：

当 Cursor / Codex 对话上下文丢失、压缩或开启新会话时，
新的 Agent 应首先读取本文件以恢复历史开发背景。

产品版本号变更见根目录 `CHANGELOG.md`。本文件记录**为什么这么改**、跨模块影响、用户硬性要求、踩坑，不记流水账。

搜索某功能历史时直接搜：`FEATURE: XXXXX`

---

## Current Development State

最后更新：2026-08-14

当前产品版本：**0.9.14**

### 当前稳定功能

- FEATURE: ORDER — 库存订单 + 明细
- FEATURE: ORDER_IMPORT — 抓取导入
- FEATURE: ORDER_REQUEST — 顾客申请（须登录、待付定金 30%）
- FEATURE: INBOUND — 按订单进库
- FEATURE: INVENTORY — 在库合箱（不改货品状态）
- FEATURE: OUTBOUND_BATCH — 批次出库、共用运单、未签收可编辑
- FEATURE: INV_EXPORT — 固定双 Sheet 模板导出 INV
- FEATURE: FEE_DETAIL — 固定双 Sheet 费用明细 Excel
- FEATURE: FINANCE — 下单汇率、批次运费/收款、月汇总
- FEATURE: APPLY_STATS — 申请日/月统计
- FEATURE: AUTH / USER_MANAGEMENT / CUSTOMER_PORTAL / ACTION_LOG / TUNNEL / SYSTEM

### 当前正在开发

- 无进行中的业务功能开发。
- 2026-08-14 已完成（**仅文档/导航，不是产品功能**）：AI 代码导航 + 长期上下文机制。尚未 git commit；**未经用户明确要求不得 commit**。

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

1. 用户未指定下一业务任务；新会话先读 Handoff，不要自行开功能。
2. 个人主页 / 规范第 8 节 **等用户明示「开始实现」** 再做。
3. 导航注释与相关文档未提交；明确要求前不执行 git commit。
4. 可交付**业务**改动才写 `CHANGELOG.md` + 升版本。不要把文档规划说成已实现功能。

---

# Session Handoff

如果当前 Agent 即将结束一个较大的开发阶段，请在这里留下简短交接信息。新 Agent 开始工作时**优先读取最近一条 Handoff**。

格式：

## Handoff - YYYY-MM-DD

### 当前任务

FEATURE: XXXXX

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

## 2026-08-14

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
- 国际运费在出库批次上：`运费单价(JPY) × 计费重量 × 运费汇率`，与下单汇率独立。
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
