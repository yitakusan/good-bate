# sofmap.com（アキバ☆ソフマップ）模板

实现：`app/scrapers/sofmap.py`

## 商品页 URL

`https://a.sofmap.com/product_detail.aspx?sku={sku}`  
例：`https://a.sofmap.com/product_detail.aspx?sku=102018397`

移动端：`product_detail_sp.aspx?sku=...`

页面编码多为 **Shift_JIS**。

### 字段映射（PDP）

| 字段 | 来源 |
|------|------|
| name | JSON-LD `Product.name`；fallback 表「商品名」/ title |
| unit_cost | JSON-LD `offers.price`；fallback 表「ソフマップ特価」/ `.price` |
| barcode | 表「JANコード」 |
| image_url | JSON-LD `image`（`image.sofmap.com/...`）；**不用**站点 OGP |
| release / expected_ship | 表「発売日」「メーカー発売日」 |
| shop | 归一为 `sofmap.com` |

## 订单详情「お取引の詳細」

会员页「お買い物履歴」→ 打开详情 →「查看网页源代码」整页粘贴。

### 字段映射（订单）

| 字段 | 来源 |
|------|------|
| name | `a.product_name` |
| source_url / sku | `product_detail.aspx?sku=` 或 `.product_box[rel]` |
| unit_cost | `販売価格` |
| qty | `数量` |
| image_url | `.product_img img` |
| barcode | 图片文件名中的 8/13 位 JAN（校验通过才采纳） |
| order_ref | `ご注文番号` |
| shipping_fee | `送料合計` |
| order_total | `ご注文合計` / `お支払い総額` |

相同 SKU 自动合并数量。前端按 `sku` 匹配商品页以便回填/去重。
