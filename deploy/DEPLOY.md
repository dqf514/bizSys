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

### 网关侧必须用「追加语义」设置 X-Forwarded-For

网关要把**它看到的对端地址追加**到 `X-Forwarded-For`，否则应用侧无法还原真实客户端 IP
（审计日志会把网关 IP 当成访问者 IP）。nginx 网关的标准写法：

```nginx
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # 追加，不要用 $http_x_forwarded_for 原样透传
proxy_set_header X-Real-IP $remote_addr;
```

原样透传客户端自带的 `X-Forwarded-For`（`$http_x_forwarded_for`）会让链首可被伪造。

## 真实客户端 IP（审计日志的「终端 IP」）

后端在容器 nginx 之后，`request.client.host` 拿到的是 **TCP 对端**（nginx / 网关容器的内网 IP），
不是访问者的公网 IP。应用侧用 `app/core/client_ip.py::client_ip()` 从 `X-Forwarded-For` 还原：

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `TRUSTED_PROXY_HOPS` | `2` | 受控代理跳数，从 `X-Forwarded-For` 右侧往左数。**本部署 = 上层网关 + 容器 nginx = 2 跳**；若去掉网关直连 18080，链只有 1 条，自动取最左一条，结论不变 |
| `TRUST_PROXY_HEADERS` | `true` | 总开关。关掉则一律用 TCP 对端（不采信任何代理头） |
| `TRUSTED_PROXY_CIDRS` | 空 | 可选，显式受信任代理的 IP/CIDR（逗号分隔）。填了则改按网段判定（优先于跳数），适合"不同访问路径跳数不同"的场景，例 `172.16.0.5/32` |

> 这三个变量由 `deploy/docker-compose.yml` 透传给后端容器，改动后 `docker compose up -d backend` 生效。

## 环境变量说明（deploy/.env）

- `WEB_PORT` / `API_PORT` / `MYSQL_PORT` / `REDIS_PORT`：宿主机端口
- `*_BIND`：绑定地址，`127.0.0.1` 表示不对局域网开放
- `MYSQL_ROOT_PASSWORD`、`JWT_SECRET`：随机强值，**更换后需重建 mysql 数据卷**（密码仅在初始化时生效）
- `CORS_ORIGINS`：跨域白名单（前端经容器内 nginx 同源访问时用不到，备用）
- `TRUSTED_PROXY_HOPS` / `TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_CIDRS`：真实客户端 IP 的代理链判定（见上节）

## 种子账号

| 用户名   | 密码           | 角色                    |
| -------- | -------------- | ----------------------- |
| admin    | Admin@123456   | 超级管理员              |
| manager1 | Test@123456    | 部门负责人（一级审批）  |
| leader1  | Test@123456    | 分管领导（二级审批）    |

> 上线后请立即修改默认密码。
