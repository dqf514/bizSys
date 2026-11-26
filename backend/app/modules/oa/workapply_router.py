"""B8 作业申请路由（/api/v1/oa/work-applies）：叉车 / 吊装 / 高处 / 动火 作业许可申请。

复用 OA 域既有能力，不另起炉灶：

- **单据**：``oa_instance``（``category='work_apply'``），状态语义与 OA 一致
  （running / approved / rejected / withdrawn / terminated）。
- **发起**：``oa/service.py::apply`` —— 校验 → 发 OA 号 → 存单据 → 走审批引擎（``biz_type='oa'``）。
- **时间线**：``approval/service.py::instance_timeline``（approval_record 只追加流水）。
- **可见范围**：作业申请是「全厂可见的作业许可」，持有 ``oa:workapply:list`` 即可查看全量；
  撤销仅申请人本人。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.core.schemas import CamelModel
from app.modules.approval import service as approval_svc
from app.modules.approval.graph import parse_json
from app.modules.auth.models import User
from app.modules.oa import service as svc
from app.modules.oa.models import OaForm, OaInstance

router = APIRouter(prefix="/oa", tags=["oa"], route_class=EnvelopeRoute)

#: OA 模板分类（作业申请）
WORK_APPLY_CATEGORY = "work_apply"

#: 单据状态 → 中文（前端另有 i18n 兜底；此处供导出/接口直接消费）
STATUS_CN = {
    "running": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "withdrawn": "已撤回",
    "terminated": "已终止",
}

#: 列表摘要抽取字段（作业地点 / 作业时间 / 作业内容 / 风险等级 / 作业部门）
SUMMARY_FIELDS = ("work_location", "work_dept", "work_content", "risk_level")


class WorkApplyIn(CamelModel):
    """发起作业申请入参：``{"formKey": "work_apply_forklift", "data": {...}}``。"""

    form_key: str
    data: dict = {}


def _fmt(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if v else ""


def _summary(form_data: dict | None) -> dict[str, Any]:
    """从 form_data 抽取列表摘要（缺字段不返回，避免前端渲染空列）。"""
    d = form_data or {}
    out: dict[str, Any] = {}
    for k in SUMMARY_FIELDS:
        v = d.get(k)
        if v not in (None, "", []):
            out[k] = v
    window = d.get("work_time")
    if isinstance(window, (list, tuple)) and len(window) == 2:
        out["work_time"] = f"{window[0]} ~ {window[1]}"
    return out


def _item(db: Session, inst: OaInstance) -> dict:
    return {
        "id": inst.id,
        "displayNo": inst.display_no,
        "formKey": inst.form_key,
        "formName": inst.form_name,
        "applicantId": inst.applicant_id,
        "applicantName": inst.applicant_name,
        "status": inst.status,
        "statusText": STATUS_CN.get(inst.status, inst.status),
        "flowInstanceId": inst.flow_instance_id or 0,
        "createTime": _fmt(inst.create_time),
        "finishedAt": _fmt(inst.finished_at),
        "data": _summary(parse_json(inst.form_data, {})),
    }


def _work_apply_or_404(db: Session, inst_id: int) -> OaInstance:
    inst = db.get(OaInstance, inst_id)
    if not inst or inst.deleted or inst.category != WORK_APPLY_CATEGORY:
        raise BizException(R.OA_WORK_APPLY_NOT_FOUND)
    return inst


# ---------------- 列表 / 计数 ----------------


@router.get("/work-applies")
def list_work_applies(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("oa:workapply:list")),
    db: Session = Depends(get_db),
):
    """作业申请列表（协议同通用列表检索：q / status / filters[k] / range[k] / sort）。"""
    pp = PageParams(page=page, size=size)
    stmt = select(OaInstance).where(OaInstance.category == WORK_APPLY_CATEGORY)
    stmt, total = apply_list_filters(
        stmt,
        OaInstance,
        request.query_params,
        db,
        pp,
        search_cols=["display_no", "form_name", "applicant_name"],
        filter_cols={"status", "form_key"},
        range_cols={"create_time"},
        sort_cols={"id", "display_no", "create_time"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {
        "items": [_item(db, r) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/work-applies/counts")
def work_apply_counts(
    current: User = Depends(require_perm("oa:workapply:list")),
    db: Session = Depends(get_db),
):
    """作业申请状态页签计数（all 最左，与 OA 单据状态口径一致）。"""
    rows = db.execute(
        select(OaInstance.status, func.count())
        .where(OaInstance.deleted == 0, OaInstance.category == WORK_APPLY_CATEGORY)
        .group_by(OaInstance.status)
    ).all()
    data: dict[str, int] = {
        "running": 0,
        "approved": 0,
        "rejected": 0,
        "withdrawn": 0,
        "terminated": 0,
    }
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


# ---------------- 目录 / 详情 ----------------


@router.get("/work-apply-catalog")
def work_apply_catalog(
    current: User = Depends(require_perm("oa:workapply:list")),
    db: Session = Depends(get_db),
):
    """作业申请模板目录（4 类：叉车 / 吊装 / 高处 / 动火）。"""
    rows = db.scalars(
        select(OaForm)
        .where(
            OaForm.category == WORK_APPLY_CATEGORY,
            OaForm.status == "published",
            OaForm.deleted == 0,
        )
        .order_by(OaForm.sort, OaForm.id)
    ).all()
    return [
        {
            "id": f.id,
            "key": f.key,
            "name": f.name,
            "description": f.description,
            "icon": f.icon,
            "fields": svc.normalized_fields(f),
        }
        for f in rows
    ]


@router.get("/work-applies/{inst_id}")
def work_apply_detail(
    inst_id: int,
    current: User = Depends(require_perm("oa:workapply:list")),
    db: Session = Depends(get_db),
):
    """作业申请详情：单据 + 表单结构 + 表单数据 + 审批时间线。"""
    inst = _work_apply_or_404(db, inst_id)
    data = _item(db, inst)
    data["schema"] = {"fields": svc.normalized_fields(inst)}
    data["formData"] = parse_json(inst.form_data, {})
    data["timeline"] = (
        approval_svc.instance_timeline(db, inst.flow_instance_id)["records"] if inst.flow_instance_id else []
    )
    return data


# ---------------- 发起 / 撤销 ----------------


@router.post("/work-applies", status_code=201)
def create_work_apply(
    body: WorkApplyIn,
    current: User = Depends(require_perm("oa:workapply:create")),
    db: Session = Depends(get_db),
):
    """发起作业申请：校验模板 → 复用 OA 发起能力（落库 + 走审批引擎）。"""
    form = db.scalar(
        select(OaForm).where(
            OaForm.key == body.form_key,
            OaForm.category == WORK_APPLY_CATEGORY,
            OaForm.deleted == 0,
        ).limit(1)
    )
    if not form:
        raise BizException(R.OA_WORK_APPLY_NOT_FOUND)
    if form.status != "published":
        raise BizException(R.OA_FORM_NOT_PUBLISHED, f"作业申请模板「{form.name}」未发布或已停用")
    inst = svc.apply(db, form.id, current, body.data)
    record(
        db,
        user_id=current.id,
        module="oa",
        action="work_apply_create",
        biz_type="oa",
        biz_id=inst.id,
        detail={"displayNo": inst.display_no, "formKey": inst.form_key},
    )
    db.commit()
    return {
        "id": inst.id,
        "displayNo": inst.display_no,
        "formKey": inst.form_key,
        "formName": inst.form_name,
        "status": inst.status,
        "flowInstanceId": inst.flow_instance_id or 0,
    }


@router.post("/work-applies/{inst_id}/cancel")
def cancel_work_apply(
    inst_id: int,
    current: User = Depends(require_perm("oa:workapply:create")),
    db: Session = Depends(get_db),
):
    """撤销作业申请：仅申请人本人、仅处理中可撤销（撤回审批实例）。"""
    inst = _work_apply_or_404(db, inst_id)
    if inst.applicant_id != current.id:
        raise BizException(R.AUTH_FORBIDDEN, "仅申请人可撤销作业申请", http_status=403)
    if inst.status != "running":
        raise BizException(R.OA_WORK_APPLY_INVALID_STATE, "仅审批中的作业申请可撤销")
    if not inst.flow_instance_id:
        raise BizException(R.OA_WORK_APPLY_INVALID_STATE, "该作业申请未走审批流程，无法撤销")
    flow = approval_svc.withdraw(db, inst.flow_instance_id, current)  # 事件回写 oa_instance.status
    record(
        db,
        user_id=current.id,
        module="oa",
        action="work_apply_cancel",
        biz_type="oa",
        biz_id=inst.id,
        detail={"displayNo": inst.display_no},
    )
    db.commit()
    return {"id": inst.id, "displayNo": inst.display_no, "status": flow.status}
