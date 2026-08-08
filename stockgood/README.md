# Stockgood — 简洁进货与出库库存

本地库存工具，覆盖从网上下单到用户签收的五段流程。核心是**订单 + 明细行**；进库按单订单一包，出库按批次多箱（可合多单，箱内按订单二级分类）。不保存客户档案、地址。

## 能力

| 能力 | 说明 |
|---|---|
| 订单 + 明细 | 一笔注文番号下多行 SKU；状态以订单为准（由明细最慢状态汇总） |
| 五段状态 | 已下单 → 已发往仓库 → 在库 → 已发往用户 → 已签收；也可取消 |
| 下单汇率 / 财务 | 一单一汇率（手填，不实时查）；商品与订单运费同汇率折算 CNY；出库批次锁定货款应收；国际运费独立汇率；按批次登记已收/未收；财务页可看本月下单与本月出库汇总 |
| 发货费用明细 | 出库批次可导出 Excel（含箱号、**订单号**、品名、合计 JPY、下单汇率、合计 CNY 及运费汇总区） |
| 抓取批量导入 | 粘贴链接单批抓取后勾选并填数量导入；同注文番号归入同一订单 |
| 顾客申请下单 | 公开页 `/apply`（订单申请）：抓取导入同款批量清单 → 勾选提交；列表看进度；后台「申请单」确认后可选写入库存（可填下单汇率） |
| 进库 | 单订单维度：选一笔订单的明细行，登记一个进库包裹；确认到仓后在库 |
| 出库 | 一批次多箱；每箱独立箱号与运单；一箱可合多订单明细，界面按订单二级分组；不支持部分出库 |
| 官方物流跳转 | Yamato、佐川单号可打开官方查询页面；其他承运商仅保存单号 |
| 操作撤回 | 登记/批量导入、进出库、确认、取消等写入操作日志；可撤回最近一步 |
| 预计发货 | 按「年月 + 可选上中下旬」管理；可一键查看本月（与财务「本月下单/出库」口径不同） |

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

后台静默启动（无常驻 CMD 窗口），日志在 `logs\`。

| 启动 | 数据库 |
|---|---|
| `start.bat` | 实际库存 `stockgood.sqlite` |
| `start-shadow.bat` | 测试影子库 `stockgood.shadow.sqlite`（采购导入等，不参与实库存） |

一键关闭：

```bat
stop.bat
```

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

可选：在 `backend/.env` 设置 `STOCKGOOD_ADMIN_TOKEN=...`，则管理端写操作需在页面保存同一口令（请求头 `X-Admin-Token`）。公开 scrape / 提交申请有 IP 限流。

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
| PATCH | `/api/outbound-batches/{id}/finance` | 更新国际运费或已收款 |
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
