"""审批中心与流程定义路由 /api/v1/approval。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import service
from app.modules.approval.schemas import AddSignIn, CommentIn, DefinitionIn, PreviewIn, TransferIn, WithdrawIn
from app.modules.auth.models import User

router = APIRouter(prefix="/approval", tags=["approval"], route_class=EnvelopeRoute)


def _user_or_404(db: Session, user_id: int) -> User:
    u = db.scalar(select(User).where(User.id == user_id, User.deleted == 0))
    if not u or u.status != "enabled":
        raise BizException(R.GENERIC_NOT_FOUND, f"用户不存在或已停用：{user_id}")
    return u


# --- 待办 / 时间线（登录即可用，页签按本人过滤） ---


@router.get("/tasks")
def list_tasks(
    tab: str = Query("todo", pattern="^(todo|done|initiated)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_tasks(db, user, PageParams(page=page, size=size), tab)


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
    page: int = Query(1, ge=1),
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
