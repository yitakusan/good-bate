# 后续演进备忘（阶段 4，按需）

## Postgres

当前生产默认 **SQLite 单 worker**（见 Docker `uvicorn --workers 1`）。若出现明显写锁/多写并发需求：

1. 引入连接层抽象（替换 `sqlite3` 直连）。
2. 用 Alembic/迁移脚本搬 schema。
3. Compose 增加 `postgres` 服务与备份策略（`pg_dump`）。

## 客户地址簿

出库对客强依赖收件信息时再开：`addresses` 表（user_id、姓名、电话、邮编、地址），出库批次可选关联。暂不实现以免打乱现有出库 UI。

## 监控

- 探针：`GET /api/health`（含 `disk.free_bytes`、`last_backup`）。
- 建议外挂 Uptime 检查与磁盘告警；备份容器日志失败时人工复查 `backend/data/backups/`。

## 明确不做

- 网站自动下单/付款
- 多租户 SaaS / `tenant_id` 全面铺开
