# mitsui-shopping-park.com / &mall 注文履歴 模板

实现：`app/scrapers/andmall.py`  
样例：`mitsui-shopping-park.com.order-history.fixture.html`

## 页面

- URL：`https://mitsui-shopping-park.com/ec/account/orders`（&mall 注文履歴）
- 检测：`a.order-history-product` / `order-history-list`，或 Network JSON（`mallSkuId` + `itemName`）

## 重要：もっと見る 与「源代码」

「查看网页源代码 / Ctrl+U」只反映**首次 SSR**，点「もっと見る」后**不会变**。  
加载出来的行在浏览器 **实时 DOM** 或 **XHR JSON** 里，不在原始源码里。

正确复制方式（二选一）：

1. **Elements（推荐）**  
   F12 → Elements → 找到 `ul.order-history-list`（或含多条 `a.order-history-product` 的节点）→ 右键 → Copy → Copy outerHTML → 粘贴到抓取框。  
   先点够「もっと見る」直到显示 `29件 / 29件中`（或没有更多按钮）。

2. **Network JSON**  
   F12 → Network → 筛选 `shop-order-skus`（或含 `order`/`sku` 的 XHR）→ 点「もっと見る」会再出请求 → 对每个响应右键 Copy → Copy response，可多段粘贴到同一框（会合并）。

## 字段

| 字段 | 来源 |
|------|------|
| name | `.order-history-product-detail .name`（或 `img[alt]` / JSON `itemName`） |
| qty | `.quantity` 文本 `数量：N` / JSON `quantity` |
| shop | 固定 `mitsui-shopping-park.com`（店名标签在 `shop_label`） |
| image_url | `img[src*=product/color]` 或 JSON `imageUrl` |
| source_url | 稳定键 `https://mitsui-shopping-park.com/ec/product/{色番}` |
| mall_sku_id | 链接 query `mallSkuId` / JSON 同字段 |
| product_code | 图 URL `/product/color/{code}_…` 或 mallSkuId 前 13 位 |
| expected_ship_at | 品名中 `YYYY年M月`（如 `【2026年9月以降発送予定】` → `2026-09`） |

## 合并规则

相同 `mallSkuId`（其次色番 / source_url / 品名）的多行 **数量相加** 成一行。  
列表页无单价、无 JAN；运费不在本页。
