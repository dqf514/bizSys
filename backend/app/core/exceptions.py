"""业务异常与全院异常处理 → 统一错误响应体。"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from app.core import response as R

logger = logging.getLogger("bizsys")


class BizException(Exception):
    """业务异常：code 见 app.core.response 错误码注册表。"""

    def __init__(self, code: int, message: str | None = None, http_status: int = 200, data=None):
        self.code = code
        self.message = message or R.DEFAULT_MESSAGES.get(code, "错误")
        self.http_status = http_status
        self.data = data
        super().__init__(self.message)


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", uuid.uuid4().hex[:16])


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizException)
    async def _biz(request: Request, exc: BizException):
        return JSONResponse(
            status_code=exc.http_status,
            content=R.err(exc.code, exc.message, _trace_id(request), exc.data),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        detail = "; ".join(
            f"{'.'.join(str(x) for x in e.get('loc', []) if x != 'body')}: {e.get('msg')}" for e in exc.errors()[:5]
        )
        return JSONResponse(
            status_code=422,
            content=R.err(R.GENERIC_PARAM, detail or None, _trace_id(request)),
        )

    @app.exception_handler(Exception)
    async def _unknown(request: Request, exc: Exception):
        logger.exception("unhandled error trace=%s", _trace_id(request))
        return JSONResponse(
            status_code=500,
            content=R.err(R.GENERIC_SYSTEM, None, _trace_id(request)),
        )
