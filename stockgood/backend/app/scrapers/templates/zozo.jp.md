# zozo.jp

- 商品 URL：`https://zozo.jp/shop/{shop}/goods/{goodsId}/?did={colorId}`
- 自动化请求常被 Akamai `403 Access Denied`；本机浏览器可打开时，粘贴整页 HTML 解析。
- 图片 CDN：`https://c.imgz.jp/{goodsId后3位}/{goodsId}/{goodsId}_{色序号}_d_500.jpg`
- 抓取失败会区分：**拦截**（CDN 图仍在 → 多半未下架）vs **下架/不存在**（404 / 「見つかりません」 / CDN 无图）。

## 注文内容の詳細（订单详情导入）

- URL：`https://zozo.jp/_member/orderhistory/detail.html?oid={注文番号}`
- 实现：`app/scrapers/zozo.py` → `parse_zozo_order_detail_html`
- 样例夹具：`templates/zozo.jp.order-detail.snippet.html`
- 粘贴整页源代码到抓取框；**不要**粘贴注文履歴列表页（会提示改开详情）。

| 字段 | 来源 |
|------|------|
| 注文番号 | `input[name=oid]` / 表头「注文番号」 |
| 送料 / 支払い金額 | `.bottomTbl` |
| 商品行 | `tr.thumbBox.detail`：`.itemName` / `.colorName` / `.priceNum` + 数量 |
| source_url | `shop/{slug}/goods/{gid}/?did={did}`（从 image.html 链接取 slug） |
| 行名 | `{品名}（{色 / サイズ}）` |
