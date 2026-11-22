"""通行凭证二维码（F6）。

用纯 Python 的 `segno` 生成 SVG（无二进制依赖、无外部服务）：

- 载荷是**短链** `{门户地址}/portal/visits/{id}/pass?code={凭证码}`，方便微信转发；
- 前端**不用 `<img src>` 直连**（`<img>` 不会带 Authorization 头），而是走
  `portalHttp` 以 `responseType: 'blob'` 取回再 `URL.createObjectURL` 渲染。
"""

import segno

# 二维码边距（模块数），太小会影响识别率
BORDER = 2


def credential_payload(base_url: str, visit_id: int, code: str) -> str:
    """构造凭证二维码载荷（门户短链）。"""
    base = (base_url or "").rstrip("/")
    return f"{base}/portal/visits/{visit_id}/pass?code={code}"


def qr_svg(payload: str, scale: int = 6) -> str:
    """生成二维码 SVG 文本（黑底白字反相由 segno 处理，实际为白底黑码，便于扫描）。"""
    qr = segno.make(payload, error="m")
    return qr.svg_inline(scale=scale, border=BORDER)
