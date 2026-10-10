"""FastAPI 应用入口。"""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core import response as R
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时可做探活/预热；迁移与种子走 alembic / scripts
    yield


app = FastAPI(
    title="bizSys API",
    version="0.1.0",
    docs_url="/docs" if settings.is_dev else None,
    openapi_url="/openapi.json" if settings.is_dev else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:16]
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


# 统一响应信封（必须在注册路由前设置，对后续 add/include 的路由生效）
from app.core.route import EnvelopeRoute  # noqa: E402

app.router.route_class = EnvelopeRoute


@app.get("/api/v1/health")
def health():
    data = {"status": "up", "version": app.version, "db": "unknown", "redis": "unknown"}
    try:
        from sqlalchemy import text

        from app.core.db import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        data["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        data["db"] = f"error: {exc.__class__.__name__}"
    try:
        from app.core.redis import get_redis

        get_redis().ping()
        data["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        data["redis"] = f"error: {exc.__class__.__name__}"
    data["status"] = "up" if data["db"] == "ok" else "degraded"
    return R.ok(data)


register_exception_handlers(app)

# --- 路由注册（按模块递增挂载） ---
from app.modules.admin.router import router as admin_router  # noqa: E402
from app.modules.approval.router import router as approval_router  # noqa: E402
from app.modules.auth.router import router as auth_router  # noqa: E402
from app.modules.auth.wecom import router as wecom_router  # noqa: E402
from app.modules.contract.router import router as contract_router  # noqa: E402
from app.modules.crm.router import router as crm_router  # noqa: E402
from app.modules.finance.router import router as finance_router  # noqa: E402
from app.modules.integration.router import router as integration_router  # noqa: E402
from app.modules.report.router import router as report_router  # noqa: E402
from app.modules.settings.router import public_router  # noqa: E402
from app.modules.settings.router import router as settings_router  # noqa: E402
from app.modules.task.router import router as task_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1")
app.include_router(wecom_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")
app.include_router(approval_router, prefix="/api/v1")
app.include_router(crm_router, prefix="/api/v1")
app.include_router(contract_router, prefix="/api/v1")
app.include_router(task_router, prefix="/api/v1")
app.include_router(finance_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(integration_router, prefix="/api/v1")


def include(module_router, prefix: str = "/api/v1") -> None:
    app.include_router(module_router, prefix=prefix)
