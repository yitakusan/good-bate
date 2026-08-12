# Stockgood 服务器部署（模式 B）

单机 VPS + Docker Compose：应用（FastAPI + 静态前端）+ Nginx + 日备。

## 快速开始

1. 复制环境文件并改密钥：

```bash
cp .env.production.example .env.production
# 编辑 SESSION_SECRET、BOOTSTRAP_ADMIN_*、CORS_ORIGINS、域名相关
```

2. 构建并启动：

```bash
docker compose up -d --build
```

3. 浏览器打开 `http://服务器IP/`，用 bootstrap 管理员登录。  
   客户申请页：`/apply`；客户门户：`/me`。

4. HTTPS：把 `fullchain.pem` / `privkey.pem` 放到 `deploy/certs/`，按 [`deploy/nginx.conf`](../deploy/nginx.conf) 注释启用 443，并设 `STOCKGOOD_COOKIE_SECURE=true`。

## 备份与恢复

- 容器 `backup` 每天调用 [`scripts/backup-db.sh`](../scripts/backup-db.sh)，文件在数据卷 `backend/data/backups/`。
- 手动：`docker compose exec backup /app/scripts/backup-db.sh manual`
- 恢复：停应用后，用备份覆盖 `stockgood.sqlite`（并删除对应 `-wal`/`-shm`），再启动。**请先在影子库演练。**

## 健康检查

`GET /api/health` 返回 `status`、磁盘用量、`last_backup`、`user_count`。

## 账号角色

| 角色 | 能力 |
|---|---|
| admin | 全部 + 用户管理 |
| warehouse | 订单/进库/库存/出库/申请处理 |
| finance | 财务写 + 员工只读 |
| customer | 自助注册、我的申请、可绑定提交 |

本地开发无用户且未设 `STOCKGOOD_AUTH_REQUIRED=true` 时，员工 API 仍可无登录访问（与旧行为兼容）。生产务必 `AUTH_REQUIRED=true` 并 bootstrap 管理员。

## 阶段 4（按需，未默认启用）

详见 [`ops-later.md`](ops-later.md)：Postgres、客户地址簿、监控建议；多租户 / 自动下单明确不做。

## 监控建议

- 对 `/api/health` 做外探（Uptime Kuma / 云监控）。
- 告警：`free_bytes` 过低、容器重启、备份目录长时间无新文件。
