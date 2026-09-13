# vvstore.jp ご注文履歴詳細 HTML 模板

实现：`app/scrapers/vvstore.py`  
样例：`vvstore.jp.order-history.fixture.html`

## 页面

- URL：`https://vvstore.jp/mypage/history/{id}`（ご注文履歴詳細）
- 检测：`page_mypage_history` / `ご注文履歴詳細` / `ec-orderProduct__detailPrice` + `vvstore`

## 使用

浏览器打开订单详情 →「查看网页源代码」整页复制 → 粘贴到抓取框。  
本页为服务端渲染，一般无需 Elements。

## 字段

| 字段 | 来源 |
|------|------|
| name | `.ec-orderProduct__detailTitle a` |
| unit_cost / qty | `.ec-orderProduct__detailPrice` 文本 `￥2,500 × 3` |
| image_url | `.ec-imageGrid__img img[src]`（补全为绝对 URL） |
| source_url | `https://vvstore.jp/products/detail/{id}` |
| shop | 固定 `vvstore.jp` |
| order_ref | `ご注文番号` |
| shipping_fee | 合计区 `送料` |
| order_total | `.ec-totalBox__price` |
| barcode | **无**（详情页另抓） |

## 合并规则

相同 `products/detail/{id}`（其次 source_url / 品名）的多行 **数量相加**。
