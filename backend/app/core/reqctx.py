"""请求上下文：trace_id / 客户端 IP / User-Agent。

合规原则 2.2 要求审计记录"终端 / IP"。`audit.record()` 全仓有 280+ 个调用点，
不可能逐个改签名去传 IP —— 这里用 ContextVar 在中间件里兜底。

FastAPI 的同步端点跑在 anyio 线程池里，contextvars 会随请求上下文复制过去，
所以中间件里 set 的值在路由/服务层都能读到。
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    """一次请求的取证上下文。"""

    trace_id: str = ""
    ip: str = ""
    user_agent: str = ""


_EMPTY = RequestContext()
_ctx: ContextVar[RequestContext] = ContextVar("bizsys_request_context", default=_EMPTY)


def set_context(ctx: RequestContext) -> Token:
    return _ctx.set(ctx)


def reset_context(token: Token) -> None:
    _ctx.reset(token)


def current() -> RequestContext:
    return _ctx.get()
