# shop.asobistore.jp 抓取模板

实现：`app/scrapers/asobistore.py`

## 根因（反查）

商品详情页上存在两类价格：

| 位置 | 选择器 | 含义 |
|------|--------|------|
| **主商品销售价** | `#selling_price` / `#selling_price_wrap` | 正确单价（例：1,500円税込） |
| 关联推荐 | `.area_rel_product_product .selling_price` / `p.price` | 推荐商品价（例：2,500 / 700…） |

旧逻辑用全文/`p.price` 取**第一个**价格，会命中关联区，把立牌抓成 2500、徽章抓成 700。  
订单履历里的成交价与 `#selling_price` 一致（价格未改时）。

## 商品页 URL

`https://shop.asobistore.jp/products/detail/{sku}`  
例：`.../237784-00-00-00`

## 字段映射（PDP）

| 字段 | 来源 |
|------|------|
| name | `og:title` 或详情区标题 |
| unit_cost | `#selling_price`（税込） |
| image | `og:image` |
| shop | `shop.asobistore.jp` |

## 購入履歴 HTML（另存）

`mypage` → 購入履歴詳細。文本块示例：

```
注文番号
注文日
A10232026052902545
2026/05/29
商品名
品番
数量
価格
…商品名…
237784-00-00-00
6
1,500円
…
商品金額合計(税込) 37,000円
送料(税込) 660円
お支払金額(税込) 37,660円
```

历史价以履历为准；商品页可能已调价。
