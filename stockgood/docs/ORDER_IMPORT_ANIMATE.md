# FEATURE: ORDER_IMPORT — animate-onlineshop.jp（给 AI）

只描述 **当前代码**。改 animate 抓取前先读本文件，再改 `backend/app/scrapers/animate.py`。总引擎见 `docs/ORDER_IMPORT.md`。

站点：`https://www.animate-onlineshop.jp`（アニメイト通販）。

---

## 1. 已实现 / 未实现

已实现（v0.9.26 起）：

- 员工粘贴マイページ **「注文履歴」整页 HTML**（Ctrl+U 源代码）
- 解析多行商品、注文番号、配送料・手数料、注文合計金額
- 行金额按 **小计** 处理：`unit_cost = 小计円 / 点数`
- 跳过特典块
- 相同 `product_id` 合并数量
- 前端匹配键 `animate:product:{id}`，订单后再抓商品页可回填 JAN

未实现（不要当成 bug 去「补全」，除非用户明确要求）：

- `scrape_url` **没有** animate 专用分支
- `is_animate_url()` 已写，**没有任何调用方**
- **没有** 商品详情页 (`/pd/{id}/`) 专用 parser；贴商品 URL 会走通用 `parse_product_html` / Shopify 失败后的 HTML 兜底
- 订单页 **不提取 JAN**（`barcode` 恒为空字符串）
- 不解析配送伝票番号、注文日（fixture 里有，解析器不用）
- 多笔注文写在同一份 HTML 里时：行会全部扫出，但 `order_ref` / 运费 / 合计只取页面上 **第一处** 匹配

---

## 2. 调用链

```text
前端 Tab「抓取」
  looksLikeHtmlOrJsonPaste (DOCTYPE / <html) 为真
    POST /api/scrape  { html }
      scrape_html_document
        … cystore 注文分支之后 …
        is_animate_order_history_html?
          parse_animate_order_history_html
            parse_animate_order_history_lines
              _line_from_order_item  (跳过 privilege)
            merge_animate_products
            extract_animate_order_ref / shipping_fee / order_total
          缺 ip 则 _guess_ip(name)
          return ScrapeResult
    appendScrapeProducts
      scrapeProductMatchKey → animate:product:{pd数字}
    勾选导入 POST /api/orders
```

调度位置：`backend/app/scrapers/preview.py` 的 `scrape_html_document`，在 CyStore 之后、eeo 之前。插入新站时不要把 animate 识别挪到通用 HTML 之后，否则注文页会被 `og:title` 收成 1 件。

公开抓取 `POST /api/public/scrape` 走同一引擎。

---

## 3. 关键文件

| 路径 | 职责 |
|------|------|
| `backend/app/scrapers/animate.py` | 识别 + 解析 + 合并（本站唯一实现） |
| `backend/app/scrapers/preview.py` | `scrape_html_document` 接入与 `message` / IP 补全 |
| `backend/app/scrapers/templates/animate-onlineshop.jp.order-history.fixture.html` | 真实结构缩样；测试以它为准 |
| `backend/test_animate_order.py` | 检测、行、特典跳过、引擎接入 |
| `frontend/src/scrapePaste.ts` | `animate:product:{id}` |
| `frontend/src/App.tsx` | 抓取 Tab 提示文案（未要求不要改布局/文案） |

常量：`SHOP = "animate-onlineshop.jp"`，`BASE = "https://www.animate-onlineshop.jp"`。

---

## 4. 页面识别 `is_animate_order_history_html`

三组条件，**商品行 + (站点或页面)** 才为真：

1. **站点**（任一）：HTML 含 `animate-onlineshop.jp` / `techorus-cdn.com` / `tc-animate` / `アニメイト`
2. **页面**（任一）：`注文履歴` / `mypage/history` / `order_histories` / `class="order"` / `class='order'`
3. **商品行**：同时有 `order_item`，以及 (`注文番号` 或 `点`)，以及 (`円` 或 `order_item_price`)

仅「アニメイト 商品一覧」不够（测试覆盖）。商品详情页通常 **不会** 走这条（缺 `order_item` + 注文履歴特征），会落到后面的通用 HTML。

---

## 5. DOM 与字段

用户操作：マイページ → 注文履歴（可先检索到单笔）→ 查看网页源代码 → 整页粘贴。不要只复制可见文本。

结构（与 fixture 一致）：

```text
.order_histories > .order
  p.order_id          「注文番号　52898468」
  .order_inner
    .order_item                 商品行
      a[href*="/pd/{id}/"]      品名 + product_id
      img[src|data-src]         主图（常 techorus-cdn）
      p.order_item_price        「140点」与「84,700円」分两个节点
    .order_item.order_item_privilege   特典，必须跳过
  .order_bill table
    商品小計 / 配送料・手数料 / 注文合計金額
```

商品链接形态：`/pn/{slug}/pd/{id}/`（相对路径）。id 用正则 `/pd/(\d+)/?`。绝对 URL：`https://www.animate-onlineshop.jp` + href。无 href 但有 id 时拼 `{BASE}/pd/{id}/`。

### 5.1 行字段 `_line_from_order_item`

| 输出 | 来源 |
|------|------|
| `name` | `.order_item_info a[href*='/pd/']` 文本；否则 `h3` |
| `product_id` | href 里 `/pd/(\d+)` |
| `source_url` | 绝对化 href |
| `qty` | `.order_item_price` 中含「点」的节点；默认 1 |
| `unit_cost` | 含「円」的 `.order_item_price` **当作小计**，再 ÷ qty，`round(..., 2)` |
| `image_url` | `img src` 或 `data-src`；`//` 补 `https:` |
| `shop` | 恒 `animate-onlineshop.jp` |
| `barcode` | 恒 `""` |
| `ip` / 发售 | 恒空；preview 再用品名猜 IP。行内「発売日：」**不解析** |

没有品名 → 整行丢弃。

金额兜底：若没有任何 `.order_item_price` 含「円」，对整个 item 做 `_parse_yen`（可能误吃其它金额，改选择器时要小心）。

### 5.2 订单头

| 字段 | 函数 | 规则 |
|------|------|------|
| `order_ref` | `extract_animate_order_ref` | 先 `.order_id` 里 `注文番号\s*([0-9]{6,})`，否则节点内连续数字 >= 6 位，再全文同一正则 |
| `shipping_fee` | `extract_animate_shipping_fee` | `.order_bill` 表：标签含 `配送料・手数料` / `配送料` / `送料`；否则全文正则。**0 円是合法值** |
| `order_total` | `extract_animate_order_total` | 标签 `注文合計金額` / `ご請求金額`；全文只搜 `注文合計金額`。不要用「商品小計」当合计 |

`_bill_amount`：扫 `.order_bill tr, .order-bill tr, table tr`，第一格当标签、第二格当金额。

---

## 6. 必须遵守的业务规则

### 6.1 单价 = 小计 ÷ 点数

注文行上的「84,700円」是 **行小计**，不是一件的单价。

fixture 例：140点 × 605円 = 84,700 → `unit_cost == 605.0`。

禁止把「円」节点直接当 `unit_cost`。测试会锁 605 / 275。

### 6.2 跳过特典

`_line_from_order_item` 在读价之前就要 return None：

- class 含 `privilege` 或 `tokuten`
- 或内部有 `.order_item_privilege_title` / `.order_item_privilege_name`

fixture 有 `BOX特典` / 「この受注に付与される特典」；测试断言这些字符串不得出现在商品名里。特典不是进货 SKU。

### 6.3 合并

`merge_animate_products` 键优先级：`product_id` → `source_url` → `name`。

同键：数量相加；已有单价不覆盖；缺图才补图。顺序保持首次出现。

`raw_line_count` 是合并前行数；`products` 是合并后。preview 的 message 会写「解析 N 行，合并为 M 种」。

### 6.4 JAN

注文页没有 JANコード 栏。条码只从该行商品图文件名读取：`image={8或13位}_....jpg`（含 `_{序号}_{时间戳}.jpg`）。`canonicalize_jan` 校验位通过才写入 `barcode`；校验失败或文件名不是这个位置的数字，留空。不扫描页面里其它 13 位（追踪号、时间戳、商品 id）。

商品页仍无 animate 专用 JAN 逻辑。图文件名没有条码时，再贴/抓 `.../pd/{同一数字}/`，前端键 `animate:product:{id}` 相同则只回填、不新增行。商品页依赖通用 `extract_jan_from_html`（必须带 JANコード 类标注 + 校验位）。

---

## 7. 前端

`scrapeProductMatchKey`（`frontend/src/scrapePaste.ts`）：

- host 含 `animate-onlineshop`
- path 匹配 `/pd/(\d+)`
- 返回 `animate:product:{id}`

`/pn/{slug}/pd/{id}/` 与 `/pd/{id}/` 会落到同一键。query 被丢掉，animate 不分色 did。

粘贴识别：整页 HTML 走 `looksLikeHtmlOrJsonPaste`，**不**靠站点名。订单 HTML 不是 JSON。

---

## 8. 引擎返回形状

`scrape_html_document` 在识别成功且 `products` 非空时：

```text
kind: "list"
products: [...]          # 已合并；已补 ip
order_ref / shipping_fee / order_total
message: 含「アニメイト」「注文番号」。图文件名校验通过时写「已从商品图文件名填入 JAN」，否则写「订单页无 JAN」。
```

识别成功但 0 件商品 → `ValueError`（HTTP 422），提示确认是注文履歴整页源代码。

---

## 9. 测试（改解析必跑）

```text
cd backend
.venv\Scripts\python.exe -m unittest test_animate_order.py -v
```

锁住的期望（fixture）：

| 项 | 值 |
|----|-----|
| 合并后件数 | 3（特典不算） |
| order_ref | `52898468` |
| shipping_fee | `0.0` |
| order_total | `128700.0` |
| pid 3459202 | qty 140, unit_cost 605, source 含 `/pd/3459202/` |
| pid 3459221 / 3459222 | qty 80, unit_cost 275 |
| qty 合计 | 300 |

unittest 必须用临时库规则：本文件只测解析，不写 sqlite。

---

## 10. 改代码时不要做的事

1. 不要把行内「円」当成单价。
2. 不要导入特典行。
3. 不要把注文页里无标注的 13 位数字当 JAN。只认商品图 `image=` 文件名开头、且校验位通过的号码。追踪号、时间戳、商品 id 都不是条码。
4. 不要把 animate 从 `scrape_html_document` 订单链里拿掉，改走通用 HTML。
5. 用户没要求时不要改抓取 Tab 提示文案/布局。
6. 不要把 `is_animate_url` 随便接到 `scrape_url` 却不写商品页 parser（会让人以为 PDP 已支持）。
7. 选择器优先匹配站点原文（含全角「注文番号　」）；代码里的正则/键名用半角。

---

## 11. 加功能时怎么动

| 需求 | 动哪里 |
|------|--------|
| 注文 DOM 变了 | `animate.py` + 更新 fixture + `test_animate_order.py` |
| 商品 URL 专用抓取 | 新 `parse_animate_product_html`，并在 `scrape_url` / paste 链接线；同时用上 `is_animate_url` |
| 注文页 JAN | 只在有可靠标注时提取；仍走 `jan.canonicalize_jan` |
| 匹配键变了 | 同步 `scrapePaste.ts` 与注文 `source_url` 形态，否则补 JAN 会失效 |
| 只改提示 | 等用户明确说改文案 |

历史决策：`docs/CHANGELOG_AI.md` 搜 `FEATURE: ORDER_IMPORT — animate`（0.9.26）。
