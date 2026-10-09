"""EnvelopeRoute：把路由返回的普通 JSON 自动包成 {code,message,data,traceId}。

- 异常处理路径（BizException/校验错误/未知异常）已由 exception handler 直接产出信封，不经过此处。
- 已带 code+message 的响应（如 /health）不重复包裹。
- 非 JSONResponse（xlsx 流、204 等）原样放行。
"""

import json

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.responses import Response

from app.core import response as R


class EnvelopeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def custom(request: Request) -> Response:
            response = await original(request)
            if isinstance(response, JSONResponse):
                try:
                    body = json.loads(response.body)
                except Exception:
                    return response
                if isinstance(body, dict) and "code" in body and "message" in body:
                    return response
                wrapped = R.ok(body, getattr(request.state, "trace_id", ""))
                headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
                return JSONResponse(
                    wrapped,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )
            return response

        return custom
