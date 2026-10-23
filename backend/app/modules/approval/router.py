"""审批中心与流程定义路由 /api/v1/approval。"""

from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import service
from app.modules.approval.schemas import AddSignIn, CommentIn, DefinitionIn, PreviewIn, TransferIn, WithdrawIn
from app.modules.auth.models import User
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/approval", tags=["approval"], route_class=EnvelopeRoute)

_BIZ_TYPE_CN = {
    "contract": "合同",
    "task": "任务",
    "report": "报告",
    "invoice": "开票申请",
    "settlement": "结算",
    "oa": "OA申请",
}

_DONE_ACTION_CN = {"agree": "已同意", "reject": "已驳回", "transfer": "已转办", "add_sign": "已加签"}

_INSTANCE_STATUS_CN = {"running": "审批中", "approved": "已通过", "rejected": "已驳回", "withdrawn": "已撤回"}

TASK_EXPORT_COLS = [
    {"key": "title", "label": "标题", "width": 36},
    {"key": "bizType", "label": "业务类型", "width": 12},
    {"key": "nodeName", "label": "节点", "width": 16},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "initiatorName", "label": "发起人", "width": 12},
    {"key": "assigneeName", "label": "处理人", "width": 12},
    {"key": "comment", "label": "意见", "width": 24},
    {"key": "createTime", "label": "发起时间", "width": 19},
    {"key": "actedAt", "label": "处理时间", "width": 19},
]


def _user_or_404(db: Session, user_id: int) -> User:
    u = db.scalar(select(User).where(User.id == user_id, User.deleted == 0))
    if not u or u.status != "enabled":
        raise BizException(R.GENERIC_NOT_FOUND, f"用户不存在或已停用：{user_id}")
    return u


# --- 待办 / 时间线（登录即可用，页签按本人过滤） ---


@router.get("/tasks")
def list_tasks(
    tab: str = Query("todo", pattern="^(todo|done|initiated)$"),
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_tasks(db, user, PageParams(page=page, size=size), tab)


@router.get("/tasks/export")
def export_tasks(
    tab: str = Query("todo", pattern="^(todo|done|initiated)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """审批中心导出（与 /tasks 同为登录可用，复用 list_tasks 过滤）。"""
    data = service.list_tasks(db, user, SimpleNamespace(page=1, size=100_000), tab)
    rows = []
    for item in data["items"]:
        item = dict(item)
        item["bizType"] = _BIZ_TYPE_CN.get(item["bizType"], item["bizType"])
        if tab == "todo":
            item["status"] = item.get("statusText") or "待审批"
        elif tab == "done":
            item["status"] = _DONE_ACTION_CN.get(item.get("action", ""), item.get("action", ""))
        else:
            item["status"] = _INSTANCE_STATUS_CN.get(item["status"], item["status"])
        rows.append(item)
    payload = export_xlsx_styled(rows, TASK_EXPORT_COLS, f"approval_{tab}")
    record(db, user_id=user.id, module="approval", action="tasks_export", detail={"tab": tab, "count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename(f'approval_{tab}')}"},
    )


@router.get("/instances/{instance_id}")
def instance_detail(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.instance_snapshot(db, instance_id)
    if not data:
        raise BizException(R.GENERIC_NOT_FOUND)
    service.mark_instance_seen(db, instance_id, user)  # 发起人查看 → 未读角标清零
    db.commit()
    data["timeline"] = service.instance_timeline(db, instance_id)["records"]
    return data


@router.get("/instances/{instance_id}/timeline")
def timeline_by_instance(
    instance_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.instance_timeline(db, instance_id)


@router.get("/instances/{biz_type}/{biz_id}/timeline")
def instance_timeline(
    biz_type: str,
    biz_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.timeline(db, biz_type, biz_id)


@router.post("/tasks/{task_id}/approve")
def approve(
    task_id: int,
    body: CommentIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = body.comment if body else ""
    inst = service.approve(db, task_id, user, comment)
    record(db, user_id=user.id, module="approval", action="approve", biz_type=inst.biz_type, biz_id=inst.biz_id,
           detail={"taskId": task_id, "comment": comment})
    db.commit()
    return {"instanceId": inst.id, "status": inst.status}


@router.post("/tasks/{task_id}/reject")
def reject(
    task_id: int,
    body: CommentIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inst = service.reject(db, task_id, user, body.comment)
    record(db, user_id=user.id, module="approval", action="reject", biz_type=inst.biz_type, biz_id=inst.biz_id,
           detail={"taskId": task_id, "comment": body.comment})
    db.commit()
    return {"instanceId": inst.id, "status": inst.status}


@router.post("/tasks/{task_id}/transfer")
def transfer(
    task_id: int,
    body: TransferIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    to_user = _user_or_404(db, body.to_user_id)
    inst = service.transfer(db, task_id, user, to_user, body.comment)
    record(db, user_id=user.id, module="approval", action="transfer", biz_type=inst.biz_type, biz_id=inst.biz_id,
           detail={"taskId": task_id, "to": to_user.username})
    db.commit()
    return {"instanceId": inst.id, "status": inst.status}


@router.post("/tasks/{task_id}/add-sign")
def add_sign(
    task_id: int,
    body: AddSignIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    approver = _user_or_404(db, body.approver_id)
    inst = service.add_sign(db, task_id, user, approver, body.comment)
    record(db, user_id=user.id, module="approval", action="add_sign", biz_type=inst.biz_type, biz_id=inst.biz_id,
           detail={"taskId": task_id, "approver": approver.username})
    db.commit()
    return {"instanceId": inst.id, "status": inst.status}


@router.post("/instances/{instance_id}/withdraw")
def withdraw(
    instance_id: int,
    body: WithdrawIn | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inst = service.withdraw(db, instance_id, user, body.comment if body else "")
    record(db, user_id=user.id, module="approval", action="withdraw", biz_type=inst.biz_type, biz_id=inst.biz_id,
           detail={"instanceId": instance_id})
    db.commit()
    return {"instanceId": inst.id, "status": inst.status}


# --- 抄送我的 / 分支预览 ---


@router.get("/cc")
def list_cc(
    unread: int = Query(0, ge=0, le=1),
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_cc(db, user, PageParams(page=page, size=size), unread_only=bool(unread))


@router.post("/cc/{cc_id}/read")
def mark_cc_read(
    cc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service.mark_cc_read(db, cc_id, user)
    db.commit()
    return {"id": cc_id}


@router.post("/preview")
def preview_route(
    body: PreviewIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.preview(db, body.definition_code, body.variables, draft_nodes=body.nodes)


# --- 流程定义管理（admin:flow:*） ---


@router.get("/definitions", dependencies=[Depends(require_perm("admin:flow:list"))])
def list_definitions(db: Session = Depends(get_db)):
    return service.list_definitions(db)


@router.post("/definitions", dependencies=[Depends(require_perm("admin:flow:edit"))])
def create_definition(
    body: DefinitionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.create_definition(db, body)
    record(db, user_id=user.id, module="approval", action="create_definition", detail={"code": body.code})
    db.commit()
    return data


@router.put("/definitions/{def_id}", dependencies=[Depends(require_perm("admin:flow:edit"))])
def update_definition(
    def_id: int,
    body: DefinitionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = service.update_definition(db, def_id, body)
    record(db, user_id=user.id, module="approval", action="update_definition", biz_id=def_id,
           detail={"code": body.code})
    db.commit()
    return data


@router.delete("/definitions/{def_id}", dependencies=[Depends(require_perm("admin:flow:edit"))])
def delete_definition(
    def_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    disabled = service.delete_definition(db, def_id)
    record(db, user_id=user.id, module="approval",
           action="disable_definition" if disabled else "delete_definition", biz_id=def_id)
    db.commit()
    return {"disabled": disabled}
