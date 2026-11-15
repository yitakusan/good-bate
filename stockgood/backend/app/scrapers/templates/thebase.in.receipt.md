# thebase.in dynamic_receipts 收据页

样例：`https://c.thebase.in/dynamic_receipts/{shop-slug}/{receiptId}`  
另存例：`28F0EB8F6D842EA0.html`

## 关键字段（英文 UI）

| 字段 | 文本标记 |
|------|----------|
| Order ID | `Order ID` 下一行收据号（例 `28F0EB8F6D842EA0`） |
| Order date | `Order date` |
| Item total | `Item total` / `¥200,850` |
| Shipping fee | `Shipping fee` / `¥1,200` |
| Total | `Total` / `¥202,050` |
| Tracking | `クロネコヤマト（ID：…）` |

## 明细行模式

```
Item Name
…
Shipped
{商品名}
Expected shipping date：Beginning of July 2026
¥550
225qty
宅急便
```

单价为税込日元；数量后缀 `qty`。

## 日文界面（与上面同一套 DOM）

`data-scope-controller="dynamicreceipts"`。解析器：`backend/app/scrapers/thebase.py`。

| 字段 | 位置 |
|------|------|
| 注文ID | `#x_uniqueKey`，或 `table.orderInfoTable` 的「注文ID」 |
| 店铺 | 商品链接域名（如 `shop.chara-pic.com`）。没有链接时才用 `#x_shop_id` |
| 品名 | `span.itemList__titleClamp` |
| 规格 | `p.itemList__additionalInfo`，拼进品名，同一 `/items/{id}` 不合并 |
| 单价 | `table.itemList` 商品単価列，税込，不乘 1.1 |
| 数量 | `N点` |
| 送料 | `ul.chargeBreakdown` 的「送料」 |
| 合计 | 「合計金額」，不是商品小計 |

不读取购买者、地址、电话、邮箱，也不读取配送状况里的运单号。
