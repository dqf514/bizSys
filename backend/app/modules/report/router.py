"""报告路由 /api/v1/report：上传 → 签批 → 签章 → 下载/导出。"""

from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import reqctx
from app.core import response as R
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import registry
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.hr import authorization as hr_auth
from app.modules.report import schemas as S
from app.modules.report import service as svc
from app.modules.report.models import Report, ReportFile
from app.modules.task.models import Task, TaskItem
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/report", tags=["report"], route_class=EnvelopeRoute)

STATUS_CN = {
    "uploaded": "已上传待审",
    "approving": "审批中",
    "approved": "批准通过",
    "rejected": "已驳回",
    "sealing": "用章审批中",
    "seal_approved": "用章已批准",
    "sealed": "签章完成",
}

ALLOWED_EXT = {"pdf", "doc", "docx"}

EXPORT_COLS = [
    {"key": "reportNo", "label": "报告编号", "width": 20},
    {"key": "taskNo", "label": "任务编号", "width": 20},
    {"key": "contractNo", "label": "关联合同", "width": 20},
    {"key": "itemName", "label": "实验条目", "width": 24},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "fileName", "label": "文件名", "width": 28},
    {"key": "status", "label": "状态", "width": 12},
    {"key": "createBy", "label": "上传人", "width": 12},
    {"key": "createTime", "label": "上传时间", "width": 19},
    {"key": "sealTime", "label": "签章时间", "width": 19},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _load_report(db: Session, rid: int, lock: bool = False) -> Report:
    r = db.get(Report, rid, with_for_update=lock)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return r


def _brief_map(db: Session, rows: list[Report]) -> tuple[dict[int, TaskItem], dict[int, Task], dict[int, str]]:
    if not rows:
        return {}, {}, {}
    items = {i.id: i for i in db.scalars(select(TaskItem).where(TaskItem.id.in_({r.task_item_id for r in rows})))}
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_({r.task_id for r in rows})))}
    uids = {r.create_by for r in rows if r.create_by} | {r.seal_by for r in rows if r.seal_by}
    users = dict(db.execute(select(User.id, User.name).where(User.id.in_(uids))).all()) if uids else {}
    return items, tasks, users


def _out(r: Report, items: dict, tasks: dict, users: dict[int, str]) -> dict:
    item = items.get(r.task_item_id)
    task = tasks.get(r.task_id)
    return {
        "id": r.id,
        "reportNo": r.report_no,
        "taskId": r.task_id,
        "taskNo": task.task_no if task else "",
        "taskItemId": r.task_item_id,
        "itemName": item.name if item else "",
        "contractId": task.contract_id if task else None,
        "contractNo": task.contract_no if task else "",
        "customerId": task.customer_id if task else None,
        "customerName": task.customer_name if task else "",
        "fileName": r.file_name,
        "status": r.status,
        "statusText": STATUS_CN.get(r.status, r.status),
        "pdfReady": bool(r.pdf_file_id),
        "sealBy": users.get(r.seal_by, "") if r.seal_by else "",
        "sealTime": _t(r.seal_time),
        "remark": r.remark or "",
        "conclusion": r.conclusion or "",
        "approvalInstanceId": r.approval_instance_id,
        "sealFlowInstanceId": r.seal_flow_instance_id,
        "createBy": users.get(r.create_by, "") if r.create_by else "",
        "createTime": _t(r.create_time),
    }


def _filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Report)
    extra = []
    # 报告无 contract_id/customer_id 列，经任务关联过滤（?x= 与 filters[x]= 两种写法均可）
    for key in ("contract_id", "customer_id"):
        raw = request.query_params.get(key) or request.query_params.get(f"filters[{key}]")
        if raw:
            extra.append(
                Report.task_id.in_(select(Task.id).where(Task.deleted == 0, getattr(Task, key) == raw))
            )
    q = (request.query_params.get("q") or "").strip()
    if q:  # 报告号/文件名 + 任务号/条目名/客户名（子查询）
        like = f"%{q}%"
        tsub = select(Task.id).where(
            Task.deleted == 0,
            or_(Task.task_no.like(like), Task.task_name.like(like), Task.customer_name.like(like)),
        )
        isub = select(TaskItem.id).where(TaskItem.deleted == 0, TaskItem.name.like(like))
        extra.append(
            or_(
                Report.report_no.like(like),
                Report.file_name.like(like),
                Report.task_id.in_(tsub),
                Report.task_item_id.in_(isub),
            )
        )
    return apply_list_filters(
        stmt,
        Report,
        request.query_params,
        db,
        page,
        filter_cols={"task_id"},
        range_cols={"create_time"},
        sort_cols={"update_time", "create_time", "id", "report_no", "file_name", "status", "seal_time"},
        extra_where=extra,
    )


@router.get("/reports")
def list_reports(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("report:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = list(db.scalars(stmt).all())
    items, tasks, users = _brief_map(db, rows)
    return {"items": [_out(r, items, tasks, users) for r in rows], "total": total, "page": page, "size": size}


@router.get("/reports/counts")
def report_counts(
    user: User = Depends(require_perm("report:list")),
    db: Session = Depends(get_db),
):
    """状态页签计数（全部/uploaded/approving/approved/rejected/sealing/seal_approved/sealed）。"""
    rows = db.execute(select(Report.status, func.count()).where(Report.deleted == 0).group_by(Report.status)).all()
    data = {s: 0 for s in ("uploaded", "approving", "approved", "rejected", "sealing", "seal_approved", "sealed")}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/reports/item-options")
def item_options(
    q: str = Query("", max_length=64),
    task_id: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    """可上传报告的条目：need_report=1 且有 report_no，尚无未删除报告；task_id 可限定到单个任务。"""
    stmt = (
        select(TaskItem, Task)
        .join(Task, Task.id == TaskItem.task_id)
        .where(
            TaskItem.deleted == 0,
            Task.deleted == 0,
            TaskItem.need_report == 1,
            TaskItem.report_no != "",
            ~select(Report.id).where(Report.task_item_id == TaskItem.id, Report.deleted == 0).exists(),
        )
    )
    if task_id:
        stmt = stmt.where(TaskItem.task_id == task_id)
    if q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(TaskItem.report_no.like(like), TaskItem.name.like(like), Task.task_no.like(like)))
    rows = db.execute(stmt.order_by(TaskItem.update_time.desc()).limit(limit)).all()
    return [
        {"value": i.id, "label": i.report_no, "sub": f"{t.task_no}/{i.name}".strip("/")} for i, t in rows
    ]


@router.post("/reports", status_code=201)
def create_report(
    item_id: int = Form(...),
    file: UploadFile = ...,
    current: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    item = db.get(TaskItem, item_id, with_for_update=True)  # 锁条目行：并发上传只放行一个
    if not item or item.deleted or not item.need_report or not item.report_no:
        raise BizException(R.GENERIC_PARAM, "条目不存在或未启用报告")
    if db.scalar(select(Report.id).where(Report.task_item_id == item.id, Report.deleted == 0)):
        raise BizException(R.REPORT_EXISTS, "该条目已存在报告")
    task = db.get(Task, item.task_id)
    if not task or task.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "任务不存在")
    # B9-C3：编制人须持有 report_role=preparer 授权（方法维度 = 条目依据标准）
    hr_auth.assert_authorized(
        db,
        current,
        auth_type=hr_auth.AUTH_TYPE_REPORT_ROLE,
        role_code=hr_auth.ROLE_PREPARER,
        method=item.std or None,
        domain=item.dept or None,
        label="编制检测报告",
    )
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT or ext not in settings.upload_ext_set:
        raise BizException(R.GENERIC_PARAM, f"不支持的文件类型：{ext or '无扩展名'}（允许 pdf/doc/docx）")
    data = file.file.read()
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > settings.upload_max_mb * 1024 * 1024:
        raise BizException(R.GENERIC_PARAM, f"文件超过大小上限 {settings.upload_max_mb}MB")
    f = svc.save_file(data, filename, file.content_type or "")
    f.create_by = current.id
    db.add(f)
    db.flush()
    r = Report(
        report_no=item.report_no,
        task_id=task.id,
        task_item_id=item.id,
        file_id=f.id,
        file_name=filename or "file",
        status="uploaded",
        create_by=current.id,
        preparer_id=current.id,
        preparer_name=current.name or current.username,
    )
    db.add(r)
    db.flush()
    svc.sync_item_status(db, item.id, "uploaded")
    audit(db, user_id=current.id, module="report", action="report_create", biz_type="report", biz_id=r.id,
          detail={"reportNo": r.report_no, "file": filename})
    db.commit()
    return {"id": r.id, "reportNo": r.report_no, "fileName": r.file_name, "status": r.status}


@router.post("/reports/{rid}/submit")
def submit_report(
    rid: int,
    body: S.SubmitIn | None = None,
    current: User = Depends(require_perm("report:submit")),
    db: Session = Depends(get_db),
):
    r = _load_report(db, rid, lock=True)
    if r.status not in ("uploaded", "rejected"):
        raise BizException(R.REPORT_INVALID_STATE, f"状态「{r.status}」不允许提交审批")
    inst = approval_svc.start(
        db,
        biz_type="report",
        biz_id=r.id,
        definition_code="report_sign",
        title=f"{r.report_no} 报告签批",
        initiator=current,
        form_snapshot=svc.form_snapshot(r),
        variables={"report_no": r.report_no},
    )
    r.status = "approving"
    r.approval_instance_id = inst.id
    r.version += 1
    r.update_time = datetime.now()
    svc.sync_item_status(db, r.task_item_id, "approving")
    audit(db, user_id=current.id, module="report", action="report_submit", biz_type="report", biz_id=rid,
          detail={"instanceId": inst.id, "comment": body.comment if body else ""})
    db.commit()
    return {"id": r.id, "status": r.status}


@router.post("/reports/{rid}/seal")
def seal_report(
    rid: int,
    body: S.SealIn | None = None,
    current: User = Depends(require_perm("report:seal")),
    db: Session = Depends(get_db),
):
    r = _load_report(db, rid, lock=True)
    # B9-C3：用章人须持有 report_role=approver 或 signer 授权
    item = db.get(TaskItem, r.task_item_id)
    hr_auth.assert_authorized(
        db,
        current,
        auth_type=hr_auth.AUTH_TYPE_REPORT_ROLE,
        role_codes=(hr_auth.ROLE_APPROVER, hr_auth.ROLE_SIGNER),
        method=(item.std or None) if item else None,
        domain=(item.dept or None) if item else None,
        label="报告用章",
    )
    # B9-C3：职责分离 —— 三级审核（节点数 ≥ 2）时编制/复核/批准不得同人且各持授权
    svc.assert_report_sod(db, r)
    # F5：用章申请与实际签章分离 —— 流程启用时必须先通过用章审批（seal_approved）
    seal_ready = "seal_approved" if registry.flow_enabled(db, "report_seal") else "approved"
    if r.status != seal_ready:
        raise BizException(
            R.REPORT_INVALID_STATE,
            f"状态「{r.status}」不允许签章（需{STATUS_CN.get(seal_ready, seal_ready)}）",
        )
    r.status = "sealed"
    r.seal_by = current.id
    # 截断到秒：seal_time 列是 DATETIME(0)，签名载荷按秒口径计算
    r.seal_time = datetime.now().replace(microsecond=0)
    r.version += 1
    r.update_time = datetime.now()
    stamped = svc.apply_seal_watermark(db, r, current.name or current.username)
    if stamped:
        r.remark = svc._append_remark(r.remark, "已叠加签章水印(占位)")
    if body and body.comment:
        r.remark = svc._append_remark(r.remark, body.comment)
    # B9：签章密码学绑定 —— 内容哈希必须在叠章之后算（盖章会产出新 PDF）
    svc.sign_seal(db, r, current.name or current.username)
    svc.sync_item_status(db, r.task_item_id, "sealed")
    audit(db, user_id=current.id, module="report", action="report_seal", biz_type="report", biz_id=rid,
          detail={
              "reportNo": r.report_no,
              "watermark": stamped,
              "alg": r.seal_alg,
              "contentHash": r.seal_content_hash,
              "sealedIp": reqctx.current().ip,
          })
    db.commit()
    return {
        "id": r.id,
        "status": r.status,
        "sealTime": _t(r.seal_time),
        "sealAlg": r.seal_alg,
        "sealContentHash": r.seal_content_hash,
    }


@router.get("/reports/{rid}/seal/verify")
def verify_seal(
    rid: int,
    user: User = Depends(require_perm("report:list")),
    db: Session = Depends(get_db),
):
    """签章验签（B9 合规 2.4）：签名有效性 + 签章后内容是否被改。"""
    r = _load_report(db, rid)
    result = svc.verify_seal(db, r)
    if not result["signatureValid"]:
        audit(
            db, user_id=user.id, module="report", action="report_seal_verify",
            biz_type="report", biz_id=rid,
            detail={"reportNo": r.report_no, "reason": result["reason"]},
        )
        db.commit()
    return {"id": r.id, "reportNo": r.report_no, **result}


@router.post("/reports/{rid}/seal-apply")
def seal_apply(
    rid: int,
    body: S.SealIn | None = None,
    current: User = Depends(require_perm("report:seal:apply")),
    db: Session = Depends(get_db),
):
    """用章申请（F5）：提交用章审批，审批通过后由有权人执行签章。"""
    r = _load_report(db, rid)
    if r.status != "approved":
        raise BizException(R.REPORT_INVALID_STATE, f"状态「{r.status}」不允许申请用章（需批准通过）")
    instance, _row = registry.submit_flow(
        db,
        "report_seal",
        rid,
        title=f"报告用章申请 {r.report_no}",
        initiator=current,
        variables={"reportNo": r.report_no, "taskId": r.task_id},
        form_snapshot={
            "reportNo": r.report_no,
            "fileName": r.file_name,
            "conclusion": (r.conclusion or "")[:500],
            "remark": r.remark or "",
        },
    )
    if body and body.comment:
        r.remark = svc._append_remark(r.remark, body.comment)
    audit(db, user_id=current.id, module="report", action="report_seal_apply", biz_type="report_seal",
          biz_id=rid, detail={"reportNo": r.report_no, "instanceId": instance.id if instance else 0})
    db.commit()
    return {"id": r.id, "status": r.status, "sealFlowInstanceId": r.seal_flow_instance_id}


@router.get("/reports/export")
def export_reports(
    request: Request,
    current: User = Depends(require_perm("report:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = list(db.scalars(stmt).all())
    items, tasks, users = _brief_map(db, rows)
    payload_rows = []
    for r in rows:
        item = _out(r, items, tasks, users)
        item["status"] = STATUS_CN.get(r.status, r.status)
        payload_rows.append(item)
    payload = export_xlsx_styled(payload_rows, EXPORT_COLS, "reports")
    audit(db, user_id=current.id, module="report", action="report_export", detail={"count": len(rows)},
          trace_id=getattr(request.state, "trace_id", ""))
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('reports')}"},
    )


@router.get("/reports/{rid}")
def get_report(
    rid: int,
    user: User = Depends(require_perm("report:list")),
    db: Session = Depends(get_db),
):
    r = _load_report(db, rid)
    items, tasks, users = _brief_map(db, [r])
    data = _out(r, items, tasks, users)
    data["timeline"] = approval_svc.timeline(db, "report", rid)["records"]
    return data


@router.get("/reports/{rid}/download")
def download_report(
    rid: int,
    pdf: int = Query(0),
    user: User = Depends(require_perm("report:list")),
    db: Session = Depends(get_db),
):
    r = _load_report(db, rid)
    fid = r.pdf_file_id if pdf and r.pdf_file_id else r.file_id
    f = db.get(ReportFile, fid)
    if not f or f.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "文件不存在")
    dest = svc.file_path(f)
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "文件已丢失")
    return Response(
        dest.read_bytes(),
        media_type=f.content_type or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.file_name)}"},
    )


# ---------------- AI 报告摘要 ----------------


@router.post("/reports/{rid}/ai-summary")
def ai_summary(
    rid: int,
    current: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    """AI 生成摘要/结论草稿（不落库；人工编辑后经 PUT remark 采用）。"""
    r = _load_report(db, rid)
    data = svc.ai_summary(db, r, current)
    audit(db, user_id=current.id, module="report", action="report_ai_summary", biz_type="report", biz_id=rid)
    db.commit()
    return data


@router.put("/reports/{rid}/remark")
def put_remark(
    rid: int,
    body: S.RemarkIn,
    current: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    """采用摘要/编辑备注：仅 uploaded/rejected 可改。"""
    r = _load_report(db, rid)
    svc.update_remark(db, r, body.remark, current)
    audit(db, user_id=current.id, module="report", action="report_remark_update", biz_type="report", biz_id=rid)
    db.commit()
    return {"id": r.id, "remark": r.remark or ""}


# ---------------- AI 全文辅助（结论草稿/校对/完整性检查） ----------------


@router.post("/reports/{rid}/ai-assist")
def ai_assist(
    rid: int,
    body: S.AssistIn,
    current: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    """AI 全文辅助：结论草稿 / 校对清单 / 完整性清单。只展示不落库（结论经 PUT conclusion 采用）。"""
    r = _load_report(db, rid)
    data = svc.ai_assist(db, r, current, body.kind)
    audit(db, user_id=current.id, module="report", action="report_ai_assist", biz_type="report", biz_id=rid,
          detail={"kind": body.kind})
    db.commit()
    return data


@router.put("/reports/{rid}/conclusion")
def put_conclusion(
    rid: int,
    body: S.ConclusionIn,
    current: User = Depends(require_perm("report:create")),
    db: Session = Depends(get_db),
):
    """采用结论段（人工编辑后落库）：仅 uploaded/rejected 可改。"""
    r = _load_report(db, rid)
    svc.update_conclusion(db, r, body.conclusion, current)
    audit(db, user_id=current.id, module="report", action="report_conclusion_update", biz_type="report", biz_id=rid)
    db.commit()
    return {"id": r.id, "conclusion": r.conclusion or ""}
