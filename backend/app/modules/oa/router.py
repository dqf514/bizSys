"""OA 路由 /api/v1/oa：用户侧（目录/发起/我的/相关/统计）+ 管理侧（设计/统计/干预）。"""

from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import get_current_user, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.admin.models import DictItem
from app.modules.approval import service as approval_svc
from app.modules.approval.models import ApprovalDefinition
from app.modules.auth.models import User
from app.modules.oa import schemas as S
from app.modules.oa import service as svc
from app.modules.oa.models import OaInstance
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/oa", tags=["oa"], route_class=EnvelopeRoute)

OA_STATUS_CN = {
    "running": "处理中",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已撤回",
    "terminated": "已终止",
}

OA_MY_EXPORT_COLS = [
    {"key": "displayNo", "label": "申请编号", "width": 20},
    {"key": "formName", "label": "表单", "width": 18},
    {"key": "category", "label": "分类", "width": 12},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "pendingNames", "label": "当前待办人", "width": 16},
    {"key": "applicantName", "label": "申请人", "width": 12},
    {"key": "createTime", "label": "申请时间", "width": 19},
    {"key": "finishedAt", "label": "完成时间", "width": 19},
]


def _user_or_404(db: Session, user_id: int) -> User:
    u = db.scalar(select(User).where(User.id == user_id, User.deleted == 0))
    if not u or u.status != "enabled":
        raise BizException(R.GENERIC_NOT_FOUND, f"用户不存在或已停用：{user_id}")
    return u


# ---------------- 用户侧 ----------------


@router.get("/catalog")
def catalog(current: User = Depends(require_perm("oa:apply")), db: Session = Depends(get_db)):
    return svc.catalog(db)


@router.post("/instances", status_code=201)
def apply(body: S.ApplyIn, current: User = Depends(require_perm("oa:apply")), db: Session = Depends(get_db)):
    inst = svc.apply(db, body.form_id, current, body.data)
    record(
        db,
        user_id=current.id,
        module="oa",
        action="oa_apply",
        biz_type="oa",
        biz_id=inst.id,
        detail={"displayNo": inst.display_no, "formKey": inst.form_key},
    )
    db.commit()
    return svc.instance_item(db, inst)


@router.get("/instances/my")
def my_instances(
    status: str = Query(""),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("oa:my")),
    db: Session = Depends(get_db),
):
    return svc.my_instances(db, current, PageParams(page=page, size=size), status=status)


@router.get("/instances/my/export")
def export_my_instances(
    status: str = Query(""),
    current: User = Depends(require_perm("oa:my")),
    db: Session = Depends(get_db),
):
    """我的申请导出（沿用列表查看权限，复用 my_instances 过滤）。"""
    data = svc.my_instances(db, current, SimpleNamespace(page=1, size=100_000), status=status)
    cat_map = dict(
        db.execute(
            select(DictItem.value, DictItem.label).where(
                DictItem.dict_type_code == "oa_category", DictItem.deleted == 0
            )
        ).all()
    )
    rows = []
    for item in data["items"]:
        item = dict(item)
        item["status"] = OA_STATUS_CN.get(item["status"], item["status"])
        item["category"] = cat_map.get(item["category"], item["category"])
        item["pendingNames"] = item["pendingNames"] or "-"
        rows.append(item)
    payload = export_xlsx_styled(rows, OA_MY_EXPORT_COLS, "oa_my_instances")
    record(db, user_id=current.id, module="oa", action="oa_my_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('oa_my_instances')}"},
    )


@router.get("/related")
def related(
    tab: str = Query("todo", pattern="^(todo|done|cc)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("oa:related")),
    db: Session = Depends(get_db),
):
    """与我相关：待办/已办/抄送——复用 approval 查询，过滤 biz_type='oa'。"""
    pp = PageParams(page=page, size=size)
    if tab == "cc":
        return approval_svc.list_cc(db, current, pp, biz_type="oa")
    return approval_svc.list_tasks(db, current, pp, tab, biz_type="oa")


@router.get("/stats")
def stats(current: User = Depends(require_perm("oa:stats:view")), db: Session = Depends(get_db)):
    return svc.stats(db)


@router.get("/instances/{inst_id}")
def instance_detail(inst_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    inst = db.get(OaInstance, inst_id)
    if not inst or inst.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return svc.instance_detail(db, inst, current)


@router.post("/instances/{inst_id}/withdraw")
def withdraw(inst_id: int, current: User = Depends(require_perm("oa:apply")), db: Session = Depends(get_db)):
    inst = db.get(OaInstance, inst_id)
    if not inst or inst.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if inst.applicant_id != current.id:
        raise BizException(R.AUTH_FORBIDDEN, "仅申请人可撤回", http_status=403)
    if not inst.flow_instance_id or inst.status != "running":
        raise BizException(R.OA_INVALID_STATE, "仅处理中的申请可撤回")
    flow = approval_svc.withdraw(db, inst.flow_instance_id, current)  # 事件回写 oa_instance.status
    record(db, user_id=current.id, module="oa", action="oa_withdraw", biz_type="oa", biz_id=inst.id)
    db.commit()
    return {"instanceId": flow.id, "status": flow.status}


# ---------------- 管理侧：流程设计 ----------------


@router.get("/admin/forms")
def admin_list_forms(current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)):
    return svc.list_forms(db)


@router.post("/admin/forms", status_code=201)
def admin_create_form(
    body: S.FormIn, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    data = svc.create_form(db, body, current)
    record(db, user_id=current.id, module="oa", action="oa_form_create", biz_type="oa_form", biz_id=data["id"])
    db.commit()
    return data


@router.put("/admin/forms/{form_id}")
def admin_update_form(
    form_id: int,
    body: S.FormIn,
    current: User = Depends(require_perm("oa:admin:design")),
    db: Session = Depends(get_db),
):
    data = svc.update_form(db, form_id, body, current)
    record(db, user_id=current.id, module="oa", action="oa_form_update", biz_type="oa_form", biz_id=form_id)
    db.commit()
    return data


@router.post("/admin/forms/{form_id}/new-version", status_code=201)
def admin_new_version(
    form_id: int, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    data = svc.new_version(db, form_id, current)
    record(db, user_id=current.id, module="oa", action="oa_form_new_version", biz_type="oa_form", biz_id=form_id)
    db.commit()
    return data


@router.post("/admin/forms/{form_id}/publish")
def admin_publish_form(
    form_id: int, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    data = svc.publish_form(db, form_id, current)
    record(db, user_id=current.id, module="oa", action="oa_form_publish", biz_type="oa_form", biz_id=form_id)
    db.commit()
    return data


@router.post("/admin/forms/{form_id}/disable")
def admin_disable_form(
    form_id: int, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    data = svc.disable_form(db, form_id, current)
    record(db, user_id=current.id, module="oa", action="oa_form_disable", biz_type="oa_form", biz_id=form_id)
    db.commit()
    return data


@router.delete("/admin/forms/{form_id}")
def admin_delete_form(
    form_id: int, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    svc.delete_form(db, form_id)
    record(db, user_id=current.id, module="oa", action="oa_form_delete", biz_type="oa_form", biz_id=form_id)
    db.commit()
    return None


@router.post("/admin/forms/{form_id}/bind-latest-flow")
def admin_bind_latest_flow(
    form_id: int, current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)
):
    data = svc.bind_latest_flow(db, form_id, current)
    record(db, user_id=current.id, module="oa", action="oa_form_bind_latest_flow", biz_type="oa_form", biz_id=form_id,
           detail={"flowDefinitionId": data["flowDefinitionId"]})
    db.commit()
    return data


@router.get("/admin/flow-defs")
def admin_flow_defs(current: User = Depends(require_perm("oa:admin:design")), db: Session = Depends(get_db)):
    """可绑定的流程定义下拉（enabled 且同 code 仅最新版本；发布校验要求 biz_type=oa）。"""
    rows = db.scalars(
        select(ApprovalDefinition)
        .where(ApprovalDefinition.enabled == 1, ApprovalDefinition.deleted == 0)
        .order_by(ApprovalDefinition.id)
    ).all()
    latest: dict[str, int] = {}
    for d in rows:
        latest[d.code] = max(latest.get(d.code, 0), d.flow_version)
    return [
        {"id": d.id, "code": d.code, "name": d.name, "bizType": d.biz_type, "version": d.flow_version}
        for d in rows
        if d.flow_version == latest[d.code]
    ]


# ---------------- 管理侧：统计 / 异常干预 ----------------


@router.get("/admin/stats")
def admin_stats(current: User = Depends(require_perm("oa:admin:stats")), db: Session = Depends(get_db)):
    return svc.stats(db, with_backlog=True)


@router.get("/admin/instances")
def admin_instances(
    status: str = Query(""),
    keyword: str = Query(""),
    stuck_days: int = Query(0, ge=0, alias="stuckDays"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("oa:admin:handle")),
    db: Session = Depends(get_db),
):
    return svc.admin_instances(
        db, PageParams(page=page, size=size), status=status, keyword=keyword, stuck_days=stuck_days
    )


@router.post("/admin/instances/{inst_id}/terminate")
def admin_terminate(
    inst_id: int,
    body: S.TerminateIn | None = None,
    current: User = Depends(require_perm("oa:admin:handle")),
    db: Session = Depends(get_db),
):
    data = svc.terminate(db, inst_id, current, body.comment if body else "")
    record(db, user_id=current.id, module="oa", action="oa_terminate", biz_type="oa", biz_id=inst_id,
           detail=body.comment if body else "")
    db.commit()
    return data


@router.post("/admin/instances/{inst_id}/reassign")
def admin_reassign(
    inst_id: int,
    body: S.ReassignIn,
    current: User = Depends(require_perm("oa:admin:handle")),
    db: Session = Depends(get_db),
):
    to_user = _user_or_404(db, body.to_user_id)
    data = svc.reassign(db, inst_id, body.task_id, to_user, current, body.comment)
    record(db, user_id=current.id, module="oa", action="oa_reassign", biz_type="oa", biz_id=inst_id,
           detail={"taskId": body.task_id, "to": to_user.username})
    db.commit()
    return data


@router.post("/admin/instances/{inst_id}/restart")
def admin_restart(
    inst_id: int,
    body: S.RestartIn,
    current: User = Depends(require_perm("oa:admin:handle")),
    db: Session = Depends(get_db),
):
    data = svc.restart(db, inst_id, body.seq, current, body.comment)
    record(db, user_id=current.id, module="oa", action="oa_restart", biz_type="oa", biz_id=inst_id,
           detail={"seq": body.seq})
    db.commit()
    return data
