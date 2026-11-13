# 周边履约工作台

Stockgood 的独立私有 Sites 应用。应用以订单明细为采购和库存记录单位。支持商品 SKU 档案，以及关联采购记录的淘宝全球购履约订单。看板根据各环节状态更新，三单与清关信息由用户登记。

## 数据来源

既有字段取自同级 `stockgood/backend/app/models.py` 中的 `OrderOut` / `LineOut`，以及 `stockgood/backend/app/database.py` 的 `orders`、`items`、`shipments` 和 `shipment_items`。应用可导入 Stockgood 的订单 JSON（订单数组或 `{"orders":[...]}`，含 `lines`）。导入会保留订单头、明细及补充字段，Stockgood 订单头与明细状态分开保存。未明确的仓储、申报和可售件数显示「需确认」。

如来源是 SQLite，在仓库根目录运行下列命令，把实际文件路径替换为你选择的备份和新输出文件。可通过 `--warehouse` 指定一个仓库 ID。脚本以 SQLite 只读模式读取，输出文件已经存在时会停止。

```powershell
python sites/scripts/export-stockgood.py "<Stockgood SQLite 备份路径>" "<新的 JSON 输出路径>"
```

在工作台选择「导入」，预览后确认。按记录 ID 去重。文件超过页面的行数或体积限制时，可按仓库或将订单数组拆分后导入。运营台账保存在 Sites D1，通过站点登录账户 ID 隔离。示例数据按当前日期生成。

## 统计与异常口径

- 采购金额为采购明细数量乘以 JPY 单价之和。订单运费和下单汇率保留在原订单字段中。
- 到货与可售数量按确认录入统计。冻结、缺货、售罄或已出库的明细排除在可售汇总外。
- 高周转门槛为下单日加六个自然月。年月和旬别表示时间区间，跨过门槛的区间可在「需确认」中查看。
- 延期从预计区间末日之后起算，已发货或已取消的采购明细停止计算。延期 30 天或无预计日期且下单满六个月的待发采购明细会进入「长期未发货」。
- 缺货、物流或清关异常、申报退回、合规受限和延期 30 天以上排在高优先。异常由当前状态与手动标记实时计算。

## 同步扩展

- 交换格式为 `stockgood-fulfillment/v1`，根对象的 `entries` 保存记录数组。每条记录使用 `id`、`kind`、`fields` 和 `manual`。字段和校验在 `lib/fulfillment.ts`，CSV 及 Stockgood 映射在 `lib/exchange.ts`。
- 使用稳定 ID 可让本地多 Agent、DSH、QQ 和外部数据库生成可重复导入的文件。现有记录由人工编辑，已有 ID 的导入行会跳过。将来接入自动更新时，可在独立的服务入口加入来源授权、字段映射和版本检查。
- 「导出 → PROJECT-STATUS.md」生成统计、流程和异常摘要，可由本地流程选择写入 `docs/PROJECT-STATUS.md`。目前可手动交换文件。
- GitHub 分支保存站点源码。Sites 的源仓库负责发布，D1 保存实际业务记录。

## 本地运行

需要 Node.js 22.13 或以上。运行 `npm ci` 安装依赖，`npm run build` 构建，`npm run dev` 启动。在本地预览首次使用前应用迁移：

```powershell
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0000_grey_lady_mastermind.sql
```

本地预览提供测试登录及独立 D1。使用 `node node_modules/typescript/bin/tsc --noEmit` 检查类型。
