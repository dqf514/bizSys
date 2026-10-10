# bizSys 本机部署说明（局域网直连 + 网关反代）

本次部署方式：Docker Compose 全栈，**不使用宿主机 nginx、不配置 SSL**（TLS 与域名由上层网关处理）。

## 端口（均已确认未被占用）

| 服务        | 宿主机端口 | 说明                                  |
| ----------- | ---------- | ------------------------------------- |
| 前端（入口）  | **18080**  | 局域网访问 / 网关反代目标              |
| 后端 API    | 18000      | 直连口（正常业务走 18080 的 `/api`）   |
| MySQL       | 13307      | 仅调试用                               |
| Redis       | 16379      | 仅调试用                               |

端口与绑定地址、密钥全部在 `deploy/.env`（不入库）中配置。

## 常用命令

```bash
cd /var/www/bizSys
docker compose -f deploy/docker-compose.yml up -d      # 启动
docker compose -f deploy/docker-compose.yml ps         # 状态
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml down       # 停止（数据卷保留）
```

首次启动会自动执行 `alembic upgrade head`（建表）与幂等种子数据。

## 网关反代（portal.hmvic.cn）

网关上把 `portal.hmvic.cn` 反代到 `http://<本机IP>:18080`，并透传原始 Host 与 `X-Forwarded-For` 即可。
容器内 nginx 使用 `server_name _`，对域名无要求；API 通过同源路径 `/api/` 转发到后端。

注意：反代需支持较长响应时间与较大请求体（项目内 nginx 已设 `proxy_read_timeout 300s`、`client_max_body_size 50m`，网关侧建议保持一致，否则大文件上传/Excel 导出会被截断）。

## 环境变量说明（deploy/.env）

- `WEB_PORT` / `API_PORT` / `MYSQL_PORT` / `REDIS_PORT`：宿主机端口
- `*_BIND`：绑定地址，`127.0.0.1` 表示不对局域网开放
- `MYSQL_ROOT_PASSWORD`、`JWT_SECRET`：随机强值，**更换后需重建 mysql 数据卷**（密码仅在初始化时生效）
- `CORS_ORIGINS`：跨域白名单（前端经容器内 nginx 同源访问时用不到，备用）

## 种子账号

| 用户名   | 密码           | 角色                    |
| -------- | -------------- | ----------------------- |
| admin    | Admin@123456   | 超级管理员              |
| manager1 | Test@123456    | 部门负责人（一级审批）  |
| leader1  | Test@123456    | 分管领导（二级审批）    |

> 上线后请立即修改默认密码。
