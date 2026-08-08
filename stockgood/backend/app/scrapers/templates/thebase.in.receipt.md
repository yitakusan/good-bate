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
