# bizSys — HMVIC 业务系统

模块化单体业务系统（客户 CRM / 合同管理 / 审批中心 / 任务管理），桌面级 Web 外壳（页签工作区 + 双主题 + 中英双语）。

- 需求基线：[`开发需求文档-MVP.md`](./开发需求文档-MVP.md)
- 技术设计：[`技术设计文档.md`](./技术设计文档.md)
- API 契约（前后端共用）：[`docs/api-contract.md`](./docs/api-contract.md)
- 关键决策：[`docs/adr/`](./docs/adr/) — Python+FastAPI（ADR-0001）、自研审批引擎（ADR-0002）、单包前端（ADR-0003）

## 技术栈

| 层   | 选型                                                                                              |
| --- | ----------------------------------------------------------------------------------------------- |
| 后端  | Python 3.13 · FastAPI · SQLAlchemy 2（同步）· Alembic · MySQL 8 · Redis 7 · PyJWT/bcrypt · openpyxl |
| 审批流 | 自研轻量可配置引擎（定义/节点/实例/待办/记录 5 表；顺序多级 + 或签/加签/转办/撤回）                                                |
| 前端  | Vue 3 · TypeScript · Vite · Pinia · Element Plus · vue-i18n（单包，见 ADR-0003）                      |
| 部署  | Docker Compose（mysql/redis/backend/frontend-nginx）· GitHub Actions CI                           |

## 快速开始（开发模式）

```bash
# 1. 基础设施（MySQL:3307 / Redis:6379）
docker compose -f deploy/docker-compose.dev.yml up -d

# 2. 后端
cd backend
uv sync
cp .env.example .env            # 按需修改（DB_URL 默认 127.0.0.1:3307）
uv run alembic upgrade head     # 建表
uv run python -m app.seeds.init_data   # 幂等种子（菜单/字典/编号/流程/账号）
uv run uvicorn app.main:app --port 8000

# 3. 前端（另开终端）
pnpm install
pnpm dev                        # http://localhost:5173，/api 已代理到 8000
```

### 种子账号

| 用户名      | 密码           | 角色            |
| -------- | ------------ | ------------- |
| admin    | Admin@123456 | 超级管理员         |
| manager1 | Test@123456  | 部门负责人（合同一级审批） |
| leader1  | Test@123456  | 分管领导（合同二级审批）  |

## 测试与质量

```bash
cd backend
uv run ruff check app tests     # lint
uv run pytest -q                # 14 例：auth/numbering/approval/engine/contract/task（独立测试库 bizsys_test）

pnpm lint && pnpm typecheck && pnpm i18n:check && pnpm build   # 前端
```

## 全栈一键（Docker）

```bash
docker compose -f deploy/docker-compose.yml up -d --build
# 前端 http://localhost:8080 · API http://localhost:8000 · MySQL 3307 · Redis 6379
# 首次启动自动执行 alembic 迁移 + 种子
```

## 主链路（验收脚本路径）

登录 → 新建客户（CC 编号）→ 新建合同（HT 编号）→ 提交审批（manager1 → leader1 两级同意）→ 合同已通过 →
按合同建任务（RW 编号 / BG 报告号 / 样品号 任务号-01）→ 状态机流转（submit/start/start/finish/close）→ 列表检索 → Excel 导出。

## 安全与数据边界

- 数据不出内网：`.env` 与密钥不入库；上传文件仅落本地 `backend/uploads/`（已 gitignore）
- JWT access 15min + refresh 7d（jti 存 Redis 可吊销）；登录失败 5 次/15 分钟锁定
- 权限码三点式 `module:resource:action`，超管角色绕过；全量操作写 `sys_audit_log`
- 生产部署前必须更换 `JWT_SECRET` 与 MySQL root 密码

## 目录

```
backend/    FastAPI 应用（app/core 横切 · app/modules 业务模块 · alembic 迁移 · tests）
frontend/   Vue3 单包（src/modules/* 按业务分模块 · src/styles 设计令牌）
deploy/     docker-compose（dev 基础设施 / 全栈）+ Dockerfile + nginx
docs/       API 契约 · ADR
```
