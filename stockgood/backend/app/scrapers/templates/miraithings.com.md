# miraithings.com（MakeShop / mirai things Online Store）商品页模板

实现：`app/scrapers/miraithings.py`

## 商品页 URL

`https://miraithings.com/view/item/{itemId}?category_page_id=...`  
例：`https://miraithings.com/view/item/000000000810?category_page_id=sasakoi_sanrio`

## 字段映射（PDP）

| 字段 | 来源 |
|------|------|
| name | `p.item-name`（`section.content-wrap.item-name-box` 内）；fallback `og:title` |
| unit_cost | **`p.item-price > span:nth-child(1)`**（Chrome：`body > div.wrap > div > section.content-wrap.item-name-box > p.item-price > span:nth-child(1)`）；稳定属性 `span[data-id="makeshop-item-price:1"]` |
| image | MakeShop CDN `makeshop-multi-images.../shopimages/...`（本站常无 `og:image`） |
| shop | `miraithings.com` |

## 价格 DOM 示例

```html
<p class="item-price">
  ￥
  <span data-id="makeshop-item-price:1">1,980</span>
  <span class="item-price-tax">（税込）</span>
</p>
```

第一个 span 只有数字（无「円」），解析时按纯数字/带逗号金额处理。

## 注意

- 通用 og/全文价格回退容易失败或取错；miraithings 走专用解析。
- 关联推荐若存在，仍以 `item-name-box` 内主价为准。
