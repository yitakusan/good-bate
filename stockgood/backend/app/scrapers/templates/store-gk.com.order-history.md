# store-gk.com（MakeShop）注文履歴 HTML 模板

样例文件：浏览器另存 `https://www.store-gk.com/ssl/ssl_confirm/confirm.html`  
实现：`app/scrapers/storegk.py`

## 编码

另存页多为 **EUC-JP**（也可能 CP932）。解析时按 `euc_jp → cp932 → utf-8` 尝试。

## 订单块

| 字段 | 选择器 | 样例 |
|------|--------|------|
| 注文番号 | `div.orderBlock dl.orderNum dd` | `P186589095997101361` |
| 状态 | `p.orderStatus` | `発送完了 - 処理日 : 2026/07/17 (17:28)` |
| 注文日時 | `dl.orderDaytime dd` | `2026年05月22日 21:18:05` |

## 明细表 `table.orderList`

表头：商品 / オプション / **単価** / **数量** / 税率 / **小計**

行结构：

```html
<tr>
  <td>
    <dl class="orderItem">
      <dt><a href="javascript:open_brand_detail('shopdetail/000000004984/')"><img ...></a></dt>
      <dd><a href="javascript:open_brand_detail('shopdetail/000000004984/')">商品名</a></dd>
    </dl>
  </td>
  <td></td>
  <td>1,500</td>   <!-- 税抜単価 -->
  <td>3</td>
  <td>10%</td>
  <td>4,500円</td> <!-- 税抜小計 -->
</tr>
```

合计行：

- `tr.orderCharge` 消費税 / 送料
- `tr.orderTotal` 合計金額

## 入库字段映射

- `order_ref` ← 注文番号  
- `shop` ← `store-gk.com`  
- `shipping_fee` ← 送料（税込表示，样例 660）  
- `unit_cost` ← 税抜単価 × 1.1（本系统合计口径含税）  
- `source_url` ← `https://www.store-gk.com/shopdetail/{id}/`（历史页商品可能已下架）  
- `expected_ship_at` ← 品名中「7月中旬頃以降発送」+ 注文年份  

## 注意

- 公开商品页常已 404，必须以注文履歴 HTML 为准。  
- 本地另存的 `*_files/*.jpg` 仅本机路径，不写入库存图床。  
