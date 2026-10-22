# FEATURE: ORDER_IMPORT — 抓取商品链接实现原理与解析

本文记录 **当前代码实际行为** (约 v0.9.42), 不是规划。站点级 DOM 样例仍以 `backend/app/scrapers/templates/` 为准; 调用链地图见 `docs/CODE_INDEX.md` 的 `FEATURE: ORDER_IMPORT`。

抓取只做预览, **不写库存**。写入发生在员工点「导入为一笔订单」之后 (`POST /api/orders`)。测试写操作只用影子库。

---

## 1. 要解决什么

员工 (主界面 Tab「抓取」) 或顾客 (`/apply`) 把日本网店的 **商品 URL、整页 HTML、Elements 片段、Network JSON** 贴进同一输入框, 系统解析成统一货品清单, 勾选后导入成订单明细。

两类输入:

| 模式 | 何时用 | 后端入口 |
|------|--------|----------|
| URL 抓取 | 浏览器能被服务端 httpx / curl 打开的商品页、Shopify 店铺/系列 | `scrape_url` |
| 粘贴解析 | 反爬 (Akamai / Cloudflare / SPA 空壳 / 需登录的注文页) | `scrape_html_document` |

前端用 `looksLikeHtmlOrJsonPaste` 决定走哪条; 后端 `POST /api/scrape` 看有没有 `html` 字段。

---

## 2. 端到端流程

```text
输入框 (URL 列表 或 HTML/JSON)
        |
        +-- looksLikeHtmlOrJsonPaste? --是--> POST { html } --> scrape_html_document
        |                                              (站点识别, 先订单后商品)
        +-- 否: 按行拆 URL --> 间隔等待 --> POST { url } --> scrape_url
                                               (站点专用 fetch, 再 Shopify, 再通用 HTML)
        |
        v
ScrapeResult { products[], order_ref, shipping_fee, order_total, message }
        |
        v
appendScrapeProducts  (同商品去重 / 回填 JAN, 累加到清单)
        |
        v
勾选 + 改数量/单价/条码 + 共用注文番号/运费/汇率
        |
        v
POST /api/orders  (一笔订单 + 多行明细; 状态 ordered)
```

公开入口同样引擎: `POST /api/public/scrape` (有频率限制), 顾客勾选后走申请单, 不直接写库存。

---

## 3. 前端

| 文件 | 职责 |
|------|------|
| `frontend/src/App.tsx` | Tab「抓取」: `onScrape` / `appendScrapeProducts` / `onBatchCreate` |
| `frontend/src/ApplyPage.tsx` | `/apply` 同样识别粘贴并调用公开抓取 |
| `frontend/src/scrapePaste.ts` | 粘贴识别、URL 拆分、`scrapeProductMatchKey` |
| `frontend/src/scrapeDelay.ts` | 批量 URL 间隔: 一般 350ms; HMV / Bic Camera 1500ms; 失败再加 1000ms |
| `frontend/src/api.ts` | `scrapeUrl(url, html?)` → `POST /api/scrape`; `publicScrapeUrl` → 公开接口 |

### 3.1 何时当成「解析 HTML」而不是批量 URL

`looksLikeHtmlOrJsonPaste` 为真时, 按钮文案变成「解析 HTML」, 整段发给后端 `html`:

1. 以 `{` / `[` 开头, 且内容像 **&mall** `shop-order-skus` (含 `mallSkuId` / `itemName` 等)
2. 整页 HTML (`<!DOCTYPE html>` / `<html` / 同时有 `<head` `<body` `og:title`)
3. Elements 片段: `order-history-list` / `order-history-product` / `mallSkuId=` + 数量
4. 以 `<` 开头的较长 HTML 片段

**注意**: 后端能解析 Yostar / STORES 的 Network JSON, 但前端这段识别 **目前没有** 把任意 `{...}` 都当 JSON。若粘贴这两种 JSON 后按钮仍是「批量抓取」、提示「请粘贴网址」, 说明没走进粘贴路径。需要整页 HTML / Elements, 或先满足上面的 JSON 特征。

误把 `https://` 粘在 HTML 前面时, `normalizeHtmlPaste` 会剥掉, 避免 `Invalid IPv6 URL`。

### 3.2 批量 URL

`parseScrapeUrls`: 按换行 / 逗号 / 分号拆; 去序号前缀; 无 scheme 且含 `.` 则补 `https://`; 去重。HTML 粘贴不会被拆成 URL。

### 3.3 清单合并与 JAN 回填

`appendScrapeProducts` 用 `scrapeProductMatchKey` 判断是否同一商品:

| 站点 | 匹配键 |
|------|--------|
| vvstore.jp | `vvstore:product:{id}` (`/products/detail/{id}`) |
| sofmap | `sofmap:product:{sku}` (`product_detail.aspx?sku=`) |
| cystore | `cystore:product:{pid}` (`pid` 或 `product_id`) |
| アニメイト | `animate:product:{id}` (`/pd/{id}`) |
| eeo.today | `eeo:product:{id}` (`/products/detail/{id}`) |
| lafary.shop | `lafary:product:{handle}` (`/products/{handle}`) |
| medicos | `medicos:product:{id}` (`/products/detail/{id}`) |
| yostar | `yostar:product:{id}` |
| STORES | `stores:item:{hex id}` (`/items/{id}`) |
| ZOZO | `zozo:goods:{gid}:did:{did}`; 无 `did` 时只有 goods id (**不同色必须带 `?did=`**, 否则会并成一行) |
| 其它 | `hostname + path` (去 www、去尾斜杠); 无 URL 则用品名小写 |

已在清单中的同一键: **不新增行**; 若旧行没有条码、新抓取有 JAN, 则回填 `barcode`。这是「先贴注文 HTML、再贴商品页补 JAN」的实现。

新品默认勾选; 数量优先用解析出的 `qty`; 单价写入可编辑框。

### 3.4 导入

`onBatchCreate` 调用 `createOrder` (`POST /api/orders`), 不是注释里写的 `createItemsBatch`。

- 共用注文番号: 输入框, 或解析得到的 `order_ref`; 都空则 `SCRAPE-YYYY-MM-DD`
- 运费 JPY: 解析结果或手填
- 下单汇率: 手填, 须 > 0
- 勾选行带上数量 / 单价 / 条码 / 预计发货

`POST /api/items/batch` (`create_items_batch`) 仍存在: 按 `order_ref` 分组建单; 抓取 Tab **当前未调用**。

---

## 4. API 与统一字段

| 方法 | 权限 | 行为 |
|------|------|------|
| `POST /api/scrape` | warehouse | `html` 非空 → `scrape_html_document`; 否则 `scrape_url` |
| `POST /api/public/scrape` | 公开, 15 次 / 60s | 同上引擎 |
| `POST /api/orders` | warehouse | 抓取 Tab 实际导入 |

请求 `ScrapeRequest`: `url` 与 `html` 至少一项。

响应 `ScrapeResult`:

```text
kind: "list"          # 永远是列表, 单件也包一层, 方便批量 UI
products: ScrapeProduct[]
message: str          # 给人看的解析摘要
order_ref: str        # 注文番号 (能解析到才有)
shipping_fee: float?  # 运费 JPY
order_total: float?   # 订单合计 (导入时不强制使用)
```

`ScrapeProduct`:

| 字段 | 含义 |
|------|------|
| `name` | 品名 (必要) |
| `shop` | 店名/域名; ZOZO 常为 `zozo.jp/{shop-slug}` |
| `unit_cost` | 进货单价 JPY (税込口径以各站为准) |
| `image_url` | 主图 |
| `source_url` | 商品页 URL (匹配键、补 JAN 都靠它) |
| `ip` | `IpNormalizer` 从品名/正文猜作品 IP |
| `barcode` | JAN/EAN (校验位通过才写入) |
| `qty` | 订单行数量; 商品页多为 1 |
| `release_date` | 原始发售/配送文案 (如 `2026-07-上旬`) |
| `expected_ship_at` | 映射后的 `YYYY-MM` |
| `expected_ship_period` | `early` / `mid` / `late` |

内部组装走 `preview._product_dict`: 缺 `ip` 时用 `IpNormalizer`; `release_date` 经 `map_release_to_expected_ship` 拆成预计发货年月与上中下旬。

---

## 5. URL 抓取: `scrape_url`

实现: `backend/app/scrapers/preview.py`。先 `_clean_url` (补 https、去掉 hash)。**按下面顺序短路**, 命中即返回。

### 5.1 站点专用 (httpx 往往过不了墙)

1. **STORES** `*.stores.jp` 且 URL 能抽出 `/items/{id}`  
   本机 `curl` 拉 SSR HTML (`scrape_stores_product`), 与 1999 同策略。httpx 常 403。失败提示改贴源代码。

2. **Yostar** `shop.yostar.co.jp/products/detail/{id}`  
   不抓 HTML, 调 `POST /ecshop-api/api/v1/product/detail` (`product_id` 为 int)。价取 `sku[].price`。

3. **HobbySearch** `1999.co.jp`  
   `curl.exe` 拉 HTML; 解析販売価格 / JANコード / 発売日。不要用メーカー希望小売価格。Cloudflare challenge 则失败。

### 5.2 同一 httpx 会话内

请求头: 桌面 Chrome UA + `Accept-Language: ja,en;q=0.8,zh;q=0.7`。

4. **miraithings.com** 商品页 HTML: 主价 `p.item-price span` (MakeShop `data-id="makeshop-item-price:1"`)
5. **sofmap.com** `product_detail.aspx?sku=`: 特价 + `JANコード` / JSON-LD
6. **asobi store** `/products/detail/`: **只认** `#selling_price`, 避开关联推荐 `.selling_price`
7. **Shopify 整店**: 路径是 `/` 或 `/products` 时拉 `/products.json?limit=50&page=1..5`, 最多 250 件
8. **Shopify 单品**: 路径含 `/products/` → `{host}/products/{handle}.json` (含 `/collections/.../products/{handle}`)
9. **Shopify 系列**: `/collections/{handle}/products.json?limit=50`
10. **通用 HTML**: `_fetch_retailer_html` + `parse_product_html`  
    HMV / Bic Camera: 最多 3 次、间隔递增; 空壳 / 403 / 429 / 503 视为拦截。Bushiroad 税抜价 × 1.1, 并再抓 HTML 补お届け日。

11. 若 URL 是 **zozo.jp** 且前面都没解析出商品: 抛 Akamai 拦截说明, 引导粘贴源代码。

Shopify 变体价取 `variants[0].price`; JAN 来自变体 `barcode` / 校验通过的 `sku` / `body_html` 标注。缺图时会再补若干商品 JSON。

---

## 6. 粘贴解析: `scrape_html_document`

**顺序即优先级**: 先识别订单页/JSON, 避免注文 HTML 落到单品解析。缺 `ip` 时用品名补猜。

| 顺序 | 识别 | 解析 |
|------|------|------|
| 1 | STORES Captcha | 直接报错 |
| 2 | STORES 購入詳細 HTML (`.order_history_item`) | 行小计 ÷ 数量 |
| 3 | STORES マイページ SPA 空壳 | 报错, 引导 Elements / Network JSON |
| 4 | STORES 注文 JSON (`/web/customers/orders/{id}`) | 同上口径 |
| 5 | STORES 商品 SSR HTML | 单件 |
| 6 | Yostar `#app` SPA 空壳 | 报错 |
| 7 | Yostar 注文 JSON `/api/v1/order/detail` | 多行 |
| 8 | Yostar 商品 JSON `/api/v1/product/detail` | 单件或 sku |
| 9 | vvstore ご注文履歴詳細 | 单价 × 数量文本 |
| 10 | sofmap お取引の詳細 | 图 URL 常带 JAN |
| 11 | CyStore 購入履歴詳細 | 订单页通常无 JAN |
| 12 | アニメイト 注文履歴 | 行金额是小计; 跳过特典 |
| 13 | eeo ご注文履歴詳細 | 邮件正文商品コード可补 JAN |
| 14 | LAFARY Shopify 顾客注文 | 订单页通常无 JAN |
| 15 | MEDICOS 購入履歴詳細 | 邮件 BOXJAN 可补 JAN |
| 16 | &mall HTML 或 shop-order-skus JSON | 相同 SKU 合并; 不填运费 |
| 17 | ZOZO 注文内容の詳細 | 分色 `did` 分行 |
| 18 | ZOZO 注文履歴列表 | 报错, 要求打开详情 |
| 19 | miraithings 商品 HTML | 单件 |
| 20 | sofmap 商品 HTML (非注文) | 单件 |
| 21 | ZOZO gone 文案 | 报下架 |
| 22 | Yahoo!ショッピング 注文履歴詳細 | 单价税込; 同链接不同规格不合并; 无 JAN |
| 23 | **通用** `parse_product_html` | og / JSON-LD / h1 |

未命中且通用解析也没有品名 → 422。

---

## 7. 通用商品页 `parse_product_html`

用于 Jump CS、多数 Shopify 店的 HTML 粘贴、HMV/Bic、以及没有专用解析器的站点。

1. 品名: JSON-LD `name` → `h1` → `<title>` → `og:title` (会去掉站点后缀噪音)
2. 主图: 页面画廊优先 (避免 JSON-LD 小图 / 全站 og:image logo)
3. 价格: JSON-LD `offers.price` → `_parse_price_from_page`  
   优先 `#selling_price`, 再若干常见价节点; 全文 `¥` / `円` 时跳过「以上で送料無料」一类门槛
4. ZOZO: shop 用 slug; 无图时用 `c.imgz.jp/{后三位}/{gid}/{gid}_{色}_d_500.jpg`
5. JAN: `extract_jan_from_html`
6. 发售: `_RELEASE_RE` (発売日 / お届け時期 / 上中下旬)

### 7.1 JAN (`backend/app/scrapers/jan.py`)

只接受 **JAN-8 / JAN-13 (含 EAN 校验位)**。12 位 UPC 补前导 0。优先 45/49 开头的日本 JAN-13。

提取顺序 (商品页):

1. JSON-LD `gtin13` / `gtin` / `ean` / `jan` 等
2. meta `product:upc` / `og:upc` / `gtin`
3. `dt/dd`、`th/td` 标注「JANコード」
4. 正文 `JANコード：…`

**不扫**无标注的 13 位数字 (避免统计 ID、BASE 页面噪音)。Shopify 变体 `sku` 只有校验通过才当 JAN。

### 7.2 IP 与发售映射

- `IpNormalizer`: 别名文件 (默认含 女神异闻录 / 明日方舟 / 初音未来 等) 在品名与正文里做包含匹配
- `2026-07-上旬` → `expected_ship_at=2026-07`, `period=early`; 纯 `YYYY-MM-DD` 只留年月

---

## 8. 各站点解析要点

「粘贴」= 走 `scrape_html_document`; 「URL」= 走 `scrape_url`。单价均为 JPY。

### 8.1 Shopify 通用 (含 bushiroad-store、多数独立店)

- URL: `/products/{handle}.json`、系列 `products.json`、店根最多 250
- 价: 第一变体; **bushiroad-store.com 按税抜 × 1.1**
- JAN: 变体 barcode
- 发售: `body_html`; Bushiroad 再抓 HTML 补お届け日
- 新版顾客订单 (`shopify_account.py`): 查看源代码是空的 `#app`，不能解析。检查元素复制已渲染的「注文アイテム」+「注文合計」。单价取 `￥n/ユニット`（税込）。规格写进品名，不按品名合并。注文番号取 `注文 (4227)`。片段里没有店铺域名时店铺留空。

### 8.2 ZOZO (`zozo.py`)

| 页 | 用法 |
|----|------|
| 商品页 URL | 常被 Akamai 403, 引导粘贴 Ctrl+U |
| 商品 HTML | 落入通用解析; 可用 CDN 补图 |
| **注文内容の詳細 HTML** | 首选导入路径 |
| 注文履歴列表 | 拒绝, 必须进详情 |

注文行: `.thumbDetail` / `.itemName` / `.colorName` / `.priceNum` / 数量。`source_url` = `/shop/{slug}/goods/{gid}/?did={did}`。品名附颜色。**后端不分色合并; 前端键必须含 did。** 运费/实付从详情表头解析。注文页通常无 JAN。

### 8.3 &mall / 三井ショッピングパーク (`andmall.py`)

| 输入 | 说明 |
|------|------|
| Ctrl+U 整页 | 仅 SSR 首屏 (常 10 件); 「もっと見る」不会进源代码 |
| Elements `ul.order-history-list` outerHTML | 点完もっと見る后再复制 |
| Network `shop-order-skus` JSON | 可多页 |

合并键: `mallSkuId` → 色番 → URL → 品名。可解析发送年月。 **不解析运费/注文番号** (`order_ref` 空)。若计数器 `shown < total` 且行数不足, 提示改用 Elements/JSON。

### 8.4 vvstore.jp (`vvstore.py`)

ご注文履歴詳細: `.ec-imageGrid` + `.ec-orderProduct__detailPrice` (`￥2,500 × 3`)。合并: `product_id` / URL / 品名。无 JAN。事后抓 `/products/detail/{id}` 可按键回填 JAN。有注文番号与送料。

### 8.5 sofmap.com (`sofmap.py`)

| 页 | 价格 / JAN |
|----|------------|
| `product_detail.aspx?sku=` URL 或 HTML | 特价节点 / JSON-LD; 规格表 `JANコード` |
| お取引の詳細 HTML | 行单价; 图 URL 路径里常能抽出合法 JAN |

合并按 sku。前端匹配 `sofmap:product:{sku}`。

### 8.6 cystore.com (`cystore.py`)

購入履歴詳細 `.cartitem`。商品 id 常从图片路径来。订单页通常无 JAN。合并 pid。有送料与注文番号。

### 8.7 animate-onlineshop.jp (`animate.py`)

给 AI 的完整说明：[`docs/ORDER_IMPORT_ANIMATE.md`](ORDER_IMPORT_ANIMATE.md)。

マイページ注文履歴 `.order_item`。链接 `/pd/{id}/`。行内「円」多为 **小计**, `unit_cost = 小计 ÷ 点数`。class 含 privilege/tokuten 或特典标题的块 **跳过**。JAN 只取商品图 `image={JAN}_...jpg`，且须通过校验位。

### 8.8 eeo.today (`eeo.py`)

ご注文履歴詳細 (EC-CUBE 风格 `.ec-orderDelivery__item`)。pid `/products/detail/{id}`。同页若粘到邮件正文「商品コード」, 按品名回填 JAN。

### 8.9 lafary.shop (`lafary.py`)

Shopify 顾客「注文 #…」: `table.order-summary` / `line-item` / `sale-price`。合并优先品名 (订单行 handle 可能不全)。订单页通常无 JAN。前端用 `/products/{handle}` 匹配补 JAN。

### 8.10 medicos-e-shop.net (`medicos.py`)

EC-CUBE 購入履歴詳細。pid 来自 `/products/detail/{id}` 或图片文件名。邮件 `BOXJAN` 可回填。合并 pid/品名。

### 8.11 shop.yostar.co.jp (`yostar.py`)

SPA + `ecshop-api`。Ctrl+U 只有 `#app` 空壳, **不能**当商品/注文解析。

| 输入 | 行为 |
|------|------|
| 商品 URL `/products/detail/{id}` | POST product/detail; 价 `sku[].price` |
| Network 商品 JSON | 同上 |
| Network 注文 JSON (`list[]`) | 品名 + `sku_name`; 合并 `product_id` |

注文 JSON 通常无 JAN。

### 8.12 STORES `*.stores.jp` (`storesjp.py`)

| 输入 | 行为 |
|------|------|
| `/items/{id}` URL | curl SSR; `h1.item_name` / `product:price:amount` / `p.item_price` |
| 商品页源代码 | 同字段 |
| 購入詳細已渲染 HTML | `.order_history_item`; `order_sales_payment_num` 为小计, 单价 = 小计 ÷ 数量 |
| Network `/web/customers/orders/{id}` JSON | `deliveries[].items` 或 `items`; 同样小计 ÷ 数量 |
| Captcha / マイページ空壳 | 明确报错 |

合并 `product_id` (`/items/{hex}`)。注文通常无 JAN。

### 8.13 miraithings.com (`miraithings.py`)

商品 URL 或粘贴 HTML。价必须用 **`p.item-price` 第一个 span**, 不要当普通 `¥…円` (该 span 常常只有数字)。图走 MakeShop CDN。JAN 走通用提取。

### 8.14 asobi store (`asobistore.py`)

**已接线**: 仅商品 URL (`#selling_price`)。  
**未接线**: `parse_asobi_order_history_html` (購入履歴文本块、品名旁 JAN) 存在, **没有**进入 `scrape_html_document` 调度。

### 8.15 1999.co.jp HobbySearch (`hobbysearch.py`)

仅 URL + curl。販売価格、`dl.c-spec` 的 JANコード / シリーズタイトル / 発売日。

### 8.16 Yahoo!ショッピング (`yahoo_shopping.py`)

注文履歴詳細整页源代码（须已登录后的 HTML）。`.elPrice` 是税込单价，`.elNum` 的 `×N` 是数量，不把「商品合計」当单价。规格取选项里冒号后的文字，写进品名；同一商品链接的不同规格不合并。订单页无 JAN，图文件名是店铺商品代码。

### 8.17 HMV / Bic Camera (`hmv.py` / `biccamera.py`)

无独立字段映射, 走通用 HTML。检测空壳 / 等候页后重试。批量抓取前端拉长间隔。仍失败则提示 1–2 分钟后再试。

---

## 9. 代码里有、调度未接入

下列模块/模板 **不会**被「抓取」Tab 自动调用, 不要当成已上线能力:

| 模块 | 说明 |
|------|------|
| `storegk.py` + `templates/store-gk.com.order-history.md` | MakeShop 注文履歴已接入 `scrape_html_document`。粘贴 `confirm.html` 整页源代码；多笔注文全部列出，不自动合成一笔订单号 |
| `templates/thebase.in.receipt.md` | BASE 收据页字段说明, 无对应 parser 接线 |
| `asobistore.parse_asobi_order_history_html` | 履历解析已写, 调度未调用 |

---

## 10. 导入后如何进库存

抓取成功只改前端清单。导入:

1. `POST /api/orders` 建 `orders` + `items` 行, `status=ordered`
2. 同一 `order_ref` 归一单; 运费、汇率写在订单上
3. 之后进库 / 合箱 / 出库走其它 FEATURE, 与抓取引擎无关

`create_items_batch` 按 `order_ref` 分组插入; 空 ref 则每件单独一单。抓取 UI 未走此接口。

---

## 11. 已知限制与踩坑

1. **服务端不是浏览器**: 无登录态、少 cookie、不跑 JS。需登录的注文必须用户粘贴。
2. **Cloudflare / Akamai**: STORES 与 1999 用本机 curl 碰运气; ZOZO 商品 URL 基本放弃, 改粘贴。
3. **SPA**: Yostar、STORES マイページ Ctrl+U 是空壳。
4. **&mall もっと見る**: 必须 Elements 或 Network JSON, 不要用「查看网页源代码」。
5. **ZOZO 分色**: 丢掉 `?did=` 会把不同色合成一行。
6. **单价口径不统一**: 有的站是标价, 有的是小计÷数量 (animate / STORES)。Bushiroad JSON 要加税。
7. **JAN 经常缺**: 多数注文页没有; 设计是再抓商品页回填。通用提取故意不做「页面上任意 13 位数字」。
8. **前端 JSON 识别偏窄**: 完整支持 &mall JSON; Yostar/STORES JSON 依赖后端, 前端可能仍当 URL 处理。
9. **Shopify 整店上限 250**; 系列接口一页 50。
10. **IP 是猜的**, 导入前应看一眼。

---

## 12. 文件与测试

```text
backend/app/scrapers/preview.py     # 引擎: scrape_url / scrape_html_document / parse_product_html
backend/app/scrapers/jan.py         # JAN 校验与提取
backend/app/scrapers/{站点}.py      # 各站 is_* / parse_*
backend/app/scrapers/templates/     # 站点 DOM 样例 (不是调度文档)
backend/app/release_date.py
backend/app/ip_normalizer.py
backend/app/models.py               # ScrapeRequest / ScrapeProduct / ScrapeResult
backend/app/main.py                 # /api/scrape, /api/public/scrape, /api/orders
backend/app/services/items.py       # create_items_batch (备用)
frontend/src/App.tsx                 # 抓取 Tab
frontend/src/scrapePaste.ts
frontend/src/scrapeDelay.ts
```

测试 (均应使用临时 sqlite, 不要写共享影子库 / 生产库):

| 文件 | 覆盖 |
|------|------|
| `backend/test_retailer_scrapers.py` | 通用 / 零售 |
| `backend/test_zozo_order.py` | ZOZO 注文 |
| `backend/test_andmall_order.py` | &mall |
| `backend/test_vvstore_order.py` | vvstore |
| `backend/test_sofmap_product.py` / `test_sofmap_order.py` | sofmap |
| `backend/test_cystore_order.py` | CyStore |
| `backend/test_animate_order.py` | アニメイト |
| `backend/test_eeo_order.py` | eeo |
| `backend/test_lafary_order.py` | LAFARY |
| `backend/test_medicos_order.py` | MEDICOS |
| `backend/test_yostar_order.py` | Yostar |
| `backend/test_storesjp_order.py` | STORES |

加新站时: 新建 `scrapers/{shop}.py` → 在 `scrape_html_document` 和/或 `scrape_url` **按优先级插入** → 前端提示 + 必要时扩 `scrapeProductMatchKey` / `looksLikeHtmlOrJsonPaste` → fixture 与 unittest → 更新本文与 CODE_INDEX。
