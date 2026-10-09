"""集成适配器状态与占位调用 /api/v1/integration。"""

from fastapi import APIRouter, Depends

from app.core import response as R
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.integration.adapters import ADAPTERS

router = APIRouter(prefix="/integration", tags=["integration"], route_class=EnvelopeRoute)


@router.get("/status")
def adapter_status(
    user: User = Depends(get_current_user),
):
    return [a.status() for a in ADAPTERS.values()]


@router.post("/{key}/ping")
def adapter_ping(
    key: str,
    user: User = Depends(require_perm("admin:flow:list")),
):
    """探测适配器连通性；未启用 → 90001。"""
    adapter = ADAPTERS.get(key)
    if not adapter:
        raise BizException(R.GENERIC_NOT_FOUND, f"未知适配器：{key}")
    adapter._guard()
    return {"key": key, "pong": True}
