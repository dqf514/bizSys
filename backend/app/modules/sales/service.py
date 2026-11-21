"""销售系统业务：报价模板 CRUD/版本发布 + 报价单状态机/审批事件回写 + AI 生成三级回退 + 发送留痕 + 转合同。

- 金额口径：行 amount=qty×unit_price、单 total_amount=Σamount，全部服务端重算（不信任前端/AI 提交值）；
- AI 生成只出草稿数据回填前端，不落库；来源/回退原因由前端随保存透传 ai_meta 落行；
- 发送：email 走 settings.notify.send_email（SMTP 未配置时非生产自动调试通道留痕），
  print/download 仅留痕标记；auto_send=1 时审批完成事件里自动发邮件（异常不阻断审批事务）。
"""

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.common.filters import apply_list_filters
from app.common.pagination import PageParams, page_result
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.crm.models import Customer
from app.modules.sales import schemas as S
from app.modules.sales.models import SalesQuotation, SalesQuotationItem, SalesQuoteSendLog, SalesQuoteTemplate
from app.services import ai as ai_svc
from app.services import masking as masking_svc
from app.services import prompts
from app.services.numbering import next_no

logger = logging.getLogger("bizsys.sales")

EDITABLE = ("draft", "rejected")
FEEDBACKABLE = ("approved", "sent")
QUOTE_STATUSES = ("draft", "approving", "approved", "rejected", "sent", "accepted", "declined", "voided")


def _layout_of(tpl: SalesQuoteTemplate) -> dict:
    try:
        data = json.loads(tpl.layout_json or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


# ---------------- 模板 ----------------


def _tpl_out(t: SalesQuoteTemplate) -> dict:
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "status": t.status,
        "tplVersion": t.tpl_version,
        "layout": _layout_of(t),
        "sort": t.sort,
        "publishedAt": t.published_at.strftime("%Y-%m-%d %H:%M:%S") if t.published_at else "",
        "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else "",
        "updateTime": t.update_time.strftime("%Y-%m-%d %H:%M:%S") if t.update_time else "",
    }


def list_templates(db: Session) -> list[dict]:
    rows = db.scalars(
        select(SalesQuoteTemplate)
        .where(SalesQuoteTemplate.deleted == 0)
        .order_by(SalesQuoteTemplate.sort, SalesQuoteTemplate.key, SalesQuoteTemplate.tpl_version.desc())
    ).all()
    return [_tpl_out(t) for t in rows]


def template_options(db: Session) -> list[dict]:
    """报价编辑页选择器：仅 published。"""
    rows = db.scalars(
        select(SalesQuoteTemplate)
        .where(SalesQuoteTemplate.status == "published", SalesQuoteTemplate.deleted == 0)
        .order_by(SalesQuoteTemplate.sort, SalesQuoteTemplate.id)
    ).all()
    return [
        {"id": t.id, "key": t.key, "name": t.name, "tplVersion": t.tpl_version, "layout": _layout_of(t)}
        for t in rows
    ]


def get_template(db: Session, tid: int) -> dict:
    t = db.get(SalesQuoteTemplate, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _tpl_out(t)


def create_template(db: Session, body: S.TemplateIn, user: User) -> dict:
    if db.scalar(
        select(SalesQuoteTemplate).where(
            SalesQuoteTemplate.key == body.key, SalesQuoteTemplate.tpl_version == 1, SalesQuoteTemplate.deleted == 0
        )
    ):
        raise BizException(R.SALES_TEMPLATE_CONFLICT)
    t = SalesQuoteTemplate(
        key=body.key,
        name=body.name.strip(),
        sort=body.sort,
        status="draft",
        layout_json=json.dumps(body.layout.model_dump(by_alias=True), ensure_ascii=False),
        create_by=user.id,
    )
    db.add(t)
    db.flush()
    return _tpl_out(t)


def _editable_template(db: Session, tid: int) -> SalesQuoteTemplate:
    t = db.get(SalesQuoteTemplate, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if t.status == "published":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "已发布模板不可编辑，请新建版本")
    return t


def update_template(db: Session, tid: int, body: S.TemplateIn, user: User) -> dict:
    t = _editable_template(db, tid)
    t.name = body.name.strip()
    t.sort = body.sort
    t.layout_json = json.dumps(body.layout.model_dump(by_alias=True), ensure_ascii=False)
    t.update_by = user.id
    db.flush()
    return _tpl_out(t)


def new_version_template(db: Session, tid: int, user: User) -> dict:
    """从现有版本复制出 tpl_version+1 草稿（改版入口）。"""
    src = db.get(SalesQuoteTemplate, tid)
    if not src or src.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    latest = db.scalar(
        select(func.max(SalesQuoteTemplate.tpl_version)).where(
            SalesQuoteTemplate.key == src.key, SalesQuoteTemplate.deleted == 0
        )
    ) or src.tpl_version
    t = SalesQuoteTemplate(
        key=src.key,
        name=src.name,
        tpl_version=latest + 1,
        sort=src.sort,
        status="draft",
        layout_json=src.layout_json,
        create_by=user.id,
    )
    db.add(t)
    db.flush()
    return _tpl_out(t)


def publish_template(db: Session, tid: int, user: User) -> dict:
    t = _editable_template(db, tid)
    # 同 key 旧版本自动停用，保证目录里同 key 只有一个 published
    for old in db.scalars(
        select(SalesQuoteTemplate).where(
            SalesQuoteTemplate.key == t.key,
            SalesQuoteTemplate.status == "published",
            SalesQuoteTemplate.id != t.id,
            SalesQuoteTemplate.deleted == 0,
        )
    ):
        old.status = "disabled"
        old.update_time = datetime.now()
    t.status = "published"
    t.published_at = datetime.now()
    t.update_by = user.id
    db.flush()
    return _tpl_out(t)


def disable_template(db: Session, tid: int, user: User) -> dict:
    t = db.get(SalesQuoteTemplate, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if t.status != "published":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅已发布模板可停用")
    t.status = "disabled"
    t.update_by = user.id
    db.flush()
    return _tpl_out(t)


def delete_template(db: Session, tid: int) -> None:
    t = db.get(SalesQuoteTemplate, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if t.status != "draft":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅草稿模板可删除")
    used = db.scalar(
        select(SalesQuotation.id).where(SalesQuotation.template_id == t.id, SalesQuotation.deleted == 0)
    )
    if used:
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "已有报价单引用该模板，不能删除")
    t.deleted = t.id  # deleted 入唯一键：写 id 保证同 key+version 软删行互不冲突
    t.update_time = datetime.now()


# ---------------- 报价单 ----------------


def _item_out(it: SalesQuotationItem) -> dict:
    return {
        "id": it.id,
        "seq": it.seq,
        "name": it.name,
        "spec": it.spec,
        "unit": it.unit,
        "qty": float(it.qty),
        "unitPrice": float(it.unit_price),
        "amount": float(it.amount),
        "remark": it.remark,
    }


def _out(q: SalesQuotation, with_items: bool = False) -> dict:
    data = {
        "id": q.id,
        "quoteNo": q.quote_no or "",
        "title": q.title,
        "customerId": q.customer_id,
        "customerName": q.customer_name,
        "contactName": q.contact_name,
        "contactPhone": q.contact_phone,
        "contactEmail": q.contact_email,
        "templateId": q.template_id,
        "tplVersion": q.tpl_version,
        "requirement": q.requirement or "",
        "introHtml": q.intro_html or "",
        "termsHtml": q.terms_html or "",
        "totalAmount": float(q.total_amount or 0),
        "taxRate": float(q.tax_rate or 0),
        "currency": q.currency,
        "validUntil": q.valid_until.strftime("%Y-%m-%d") if q.valid_until else "",
        "status": q.status,
        "aiMeta": q.ai_meta or "",
        "autoSend": bool(q.auto_send),
        "sentAt": q.sent_at.strftime("%Y-%m-%d %H:%M:%S") if q.sent_at else "",
        "sentChannel": q.sent_channel,
        "sentTo": q.sent_to,
        "feedbackNote": q.feedback_note,
        "flowInstanceId": q.flow_instance_id,
        "contractId": q.contract_id,
        "createTime": q.create_time.strftime("%Y-%m-%d %H:%M:%S") if q.create_time else "",
        "updateTime": q.update_time.strftime("%Y-%m-%d %H:%M:%S") if q.update_time else "",
    }
    if with_items:
        data["items"] = [_item_out(it) for it in q.items]
        data["layout"] = _snapshot_layout(q)
    return data


def _snapshot_layout(q: SalesQuotation) -> dict:
    try:
        data = json.loads(q.layout_snapshot or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _load(db: Session, qid: int) -> SalesQuotation:
    q = db.get(SalesQuotation, qid)
    if not q or q.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return q


def _check_editable(q: SalesQuotation) -> None:
    if q.status == "approving":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "审批中报价单禁止编辑，请先撤回")
    if q.status not in EDITABLE:
        raise BizException(R.SALES_QUOTE_INVALID_STATE, f"状态「{q.status}」不允许编辑")


def _customer(db: Session, customer_id: int) -> Customer:
    c = db.get(Customer, customer_id)
    if not c or c.deleted:
        raise BizException(R.GENERIC_PARAM, "往来单位不存在")
    return c


def _apply_items(q: SalesQuotation, items: list[S.QuotationItemIn]) -> None:
    """替换明细并重算金额（服务端口径）。"""
    q.items.clear()
    db_items = []
    for idx, it in enumerate(items, start=1):
        amount = (it.qty * it.unit_price).quantize(Decimal("0.01"))
        db_items.append(
            SalesQuotationItem(
                seq=idx,
                name=it.name.strip(),
                spec=it.spec.strip(),
                unit=it.unit.strip(),
                qty=it.qty,
                unit_price=it.unit_price,
                amount=amount,
                remark=it.remark.strip(),
            )
        )
    q.items.extend(db_items)
    q.total_amount = sum((it.amount for it in db_items), Decimal("0"))


def _apply(db: Session, q: SalesQuotation, body: S.QuotationIn, is_create: bool) -> None:
    customer = _customer(db, body.customer_id)
    q.customer_id = customer.id
    q.customer_name = customer.name
    q.title = body.title.strip()
    q.contact_name = body.contact_name.strip()
    q.contact_phone = body.contact_phone.strip()
    q.contact_email = body.contact_email.strip()
    q.requirement = body.requirement.strip()
    q.intro_html = body.intro_html
    q.terms_html = body.terms_html
    q.tax_rate = body.tax_rate
    q.auto_send = 1 if body.auto_send else 0
    q.ai_meta = body.ai_meta.strip()
    if body.template_id:
        tpl = db.get(SalesQuoteTemplate, body.template_id)
        if not tpl or tpl.deleted:
            raise BizException(R.GENERIC_PARAM, "报价模板不存在")
        q.template_id = tpl.id
        q.tpl_version = tpl.tpl_version
        q.layout_snapshot = tpl.layout_json or "{}"
        layout = _layout_of(tpl)
        if is_create and body.valid_until is None and layout.get("validDays"):
            q.valid_until = date.today() + timedelta(days=int(layout["validDays"]))
    else:
        q.template_id = None
        q.tpl_version = 1
        q.layout_snapshot = ""
    if body.valid_until is not None:
        q.valid_until = body.valid_until
    _apply_items(q, body.items)


def create_quotation(db: Session, current: User, body: S.QuotationIn) -> SalesQuotation:
    q = SalesQuotation(status="draft")
    _apply(db, q, body, is_create=True)
    q.create_by = current.id
    db.add(q)
    db.flush()
    return q


def update_quotation(db: Session, current: User, qid: int, body: S.QuotationIn) -> SalesQuotation:
    q = _load(db, qid)
    _check_editable(q)
    _apply(db, q, body, is_create=False)
    q.update_by = current.id
    db.flush()
    return q


def delete_quotation(db: Session, current: User, qid: int) -> None:
    q = _load(db, qid)
    if q.status != "draft":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅草稿报价单可删除")
    q.deleted = 1
    q.update_by = current.id
    q.update_time = datetime.now()
    db.flush()


def snapshot(q: SalesQuotation) -> dict:
    return {
        "quoteNo": q.quote_no or "",
        "title": q.title,
        "customerId": q.customer_id,
        "customerName": q.customer_name,
        "contactName": q.contact_name,
        "totalAmount": float(q.total_amount or 0),
        "taxRate": float(q.tax_rate or 0),
        "validUntil": q.valid_until.strftime("%Y-%m-%d") if q.valid_until else "",
        "status": q.status,
    }


def submit_quotation(db: Session, current: User, qid: int) -> SalesQuotation:
    """提交审批（调用方已加行锁）：校验 → 发号 → 启动 quote_approve 两级组织审批。"""
    from app.modules.approval import service as approval_svc  # noqa: PLC0415 避免模块加载循环

    q = _load(db, qid)
    if q.status not in EDITABLE:
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅草稿/已驳回报价单可提交审批")
    if not q.items:
        raise BizException(R.GENERIC_PARAM, "报价明细至少一行，不能提交审批")
    if not q.total_amount or q.total_amount <= 0:
        raise BizException(R.GENERIC_PARAM, "报价合计必须大于 0，不能提交审批")
    if not q.valid_until or q.valid_until < date.today():
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "报价有效期未填或已过期，不能提交审批")
    if q.template_id:
        tpl = db.get(SalesQuoteTemplate, q.template_id)
        if not tpl or tpl.deleted or tpl.status != "published":
            raise BizException(R.SALES_TEMPLATE_NOT_PUBLISHED)
    if not q.quote_no:
        # 提交即发放正式编号；驳回/撤回后重提沿用
        q.quote_no = next_no(db, "quotation")
        db.flush()
    inst = approval_svc.start(
        db,
        biz_type="sales_quotation",
        biz_id=q.id,
        definition_code="quote_approve",
        title=f"{q.quote_no} {q.title}",
        initiator=current,
        form_snapshot=json.loads(json.dumps(snapshot(q), ensure_ascii=False, default=str)),
        variables={"amount": float(q.total_amount), "customer_name": q.customer_name},
    )
    q.status = "approving"
    q.flow_instance_id = inst.id
    q.update_by = current.id
    db.flush()
    return q


# ---------------- 审批事件回写（导入即订阅，见 main.py） ----------------


def _handle_completed(event: ApprovalCompleted) -> None:
    if event.biz_type != "sales_quotation":
        return
    db: Session = event.db
    q = db.get(SalesQuotation, event.biz_id)
    if not q or q.deleted or q.status != "approving":
        return
    q.status = "approved"
    q.flow_instance_id = event.instance_id
    q.update_time = datetime.now()
    if q.auto_send and q.contact_email:
        _auto_send(db, q)


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "sales_quotation":
        return
    db: Session = event.db
    q = db.get(SalesQuotation, event.biz_id)
    if not q or q.deleted or q.status != "approving":
        return
    q.status = "rejected"
    q.flow_instance_id = event.instance_id
    q.update_time = datetime.now()


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    """撤回后回写 draft（可编辑/可再提交），避免报价单卡在 approving。"""
    if event.biz_type != "sales_quotation":
        return
    db: Session = event.db
    q = db.get(SalesQuotation, event.biz_id)
    if not q or q.deleted or q.status != "approving":
        return
    q.status = "draft"
    q.flow_instance_id = event.instance_id
    q.update_time = datetime.now()


def register_flow_handlers() -> None:
    """F5：审批处理器注册入口，由 ``app.modules.approval.wiring.install()`` 显式装配。

    不再在模块 import 时自动订阅 —— 漏一个 import 就会让单据永久卡在 approving。
    """
    subscribe(ApprovalCompleted, _handle_completed)
    subscribe(ApprovalRejected, _handle_rejected)
    subscribe(ApprovalWithdrawn, _handle_withdrawn)



# ---------------- 发送与留痕 ----------------


def _log_send(
    db: Session,
    q: SalesQuotation,
    channel: str,
    recipient: str,
    result: str,
    detail: str = "",
    sender: User | None = None,
) -> None:
    db.add(
        SalesQuoteSendLog(
            quotation_id=q.id,
            channel=channel,
            recipient=recipient,
            result=result,
            detail=detail[:500],
            sender_id=sender.id if sender else None,
            sender_name=(sender.name or sender.username) if sender else "auto",
        )
    )


def _mark_sent(q: SalesQuotation, channel: str, recipient: str) -> None:
    q.status = "sent"
    q.sent_at = datetime.now()
    q.sent_channel = channel
    q.sent_to = recipient
    q.update_time = datetime.now()


def _mail_payload(q: SalesQuotation) -> tuple[str, str]:
    subject = f"报价单 {q.quote_no or ''} {q.title}".strip()
    lines = [
        f"报价编号：{q.quote_no or '-'}",
        f"报价标题：{q.title}",
        f"报价金额：{q.total_amount} {q.currency}",
        f"有效期至：{q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '-'}",
        "明细与条款请见随附打印件/PDF。",
    ]
    return subject, "\n".join(lines)


def send_quotation(db: Session, current: User, qid: int, body: S.SendIn) -> dict:
    """手动发送：email 走 SMTP 配置（未配置非生产走调试通道）；print/download 仅留痕标记。"""
    from app.modules.settings import notify  # noqa: PLC0415 避免模块加载循环

    q = _load(db, qid)
    if q.status not in ("approved", "sent"):
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅审批通过的报价单可发送")
    if body.channel == "email":
        recipient = (body.recipient or q.contact_email).strip()
        if not recipient:
            raise BizException(R.GENERIC_PARAM, "邮件通道需要收件人邮箱（可在报价单上填联系人邮箱）")
        subject, text = _mail_payload(q)
        mode = notify.send_email(db, recipient, subject, text)  # real/debug；真实通道失败抛错
        _log_send(db, q, "email", recipient, mode, "", current)
        _mark_sent(q, "email", recipient)
    else:
        recipient = body.recipient.strip() or q.contact_name
        _log_send(db, q, body.channel, recipient, "marked", "", current)
        _mark_sent(q, body.channel, recipient)
    q.update_by = current.id
    db.flush()
    return _out(q)


def _auto_send(db: Session, q: SalesQuotation) -> None:
    """auto_send：审批完成事件内自动发邮件。异常只留痕，不阻断审批事务。"""
    from app.modules.settings import notify  # noqa: PLC0415

    try:
        subject, text = _mail_payload(q)
        mode = notify.send_email(db, q.contact_email, subject, text)
        _log_send(db, q, "email", q.contact_email, mode, "auto_send")
        _mark_sent(q, "email", q.contact_email)
    except Exception as exc:  # noqa: BLE001 自动发送失败不能回滚审批通过
        logger.exception("报价单 auto_send 失败 quotation=%s", q.id)
        _log_send(db, q, "email", q.contact_email, "failed", f"auto_send: {type(exc).__name__}")


def send_logs(db: Session, qid: int) -> list[dict]:
    rows = db.scalars(
        select(SalesQuoteSendLog)
        .where(SalesQuoteSendLog.quotation_id == qid, SalesQuoteSendLog.deleted == 0)
        .order_by(SalesQuoteSendLog.id.desc())
    ).all()
    return [
        {
            "id": r.id,
            "channel": r.channel,
            "recipient": r.recipient,
            "result": r.result,
            "detail": r.detail,
            "senderName": r.sender_name,
            "sentAt": r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
        }
        for r in rows
    ]


# ---------------- 客户反馈 / 转合同 ----------------


def feedback_quotation(db: Session, current: User, qid: int, body: S.FeedbackIn) -> SalesQuotation:
    q = _load(db, qid)
    if q.status not in FEEDBACKABLE:
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅审批通过/已发送的报价单可登记客户反馈")
    q.status = "accepted" if body.action == "accept" else "declined"
    q.feedback_note = body.note.strip()
    q.update_by = current.id
    q.update_time = datetime.now()
    db.flush()
    return q


def to_contract(db: Session, current: User, qid: int) -> dict:
    """accepted 报价单一键转合同（草稿）；幂等：已转过直接返回原合同 id。"""
    q = _load(db, qid)
    if q.contract_id:
        return {"contractId": q.contract_id, "duplicated": True}
    if q.status != "accepted":
        raise BizException(R.SALES_QUOTE_INVALID_STATE, "仅客户已接受的报价单可转合同")
    c = Contract(
        name=q.title,
        customer_id=q.customer_id,
        customer_name=q.customer_name,
        contract_type="sales",
        amount=q.total_amount,
        contact_person=q.contact_name or None,
        contact_phone=q.contact_phone or None,
        remark=f"由报价单 {q.quote_no or q.id} 转入",
        status="draft",
    )
    c.create_by = current.id
    db.add(c)
    db.flush()
    q.contract_id = c.id
    q.update_by = current.id
    q.update_time = datetime.now()
    db.flush()
    return {"contractId": c.id, "duplicated": False}


# ---------------- 列表 / counts ----------------


def list_quotations(db: Session, pp: PageParams, query_params) -> dict:
    stmt, total = apply_list_filters(
        select(SalesQuotation),
        SalesQuotation,
        query_params,
        db,
        pp,
        search_cols=["quote_no", "title", "customer_name", "contact_name"],
        filter_cols={"customer_id"},
        range_cols={"valid_until"},
        sort_cols={
            "quote_no", "title", "customer_name", "total_amount", "valid_until",
            "status", "create_time", "update_time", "id",
        },
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return page_result([_out(r) for r in rows], total, pp.page, pp.size)


def counts(db: Session) -> dict:
    rows = db.execute(
        select(SalesQuotation.status, func.count()).where(SalesQuotation.deleted == 0).group_by(SalesQuotation.status)
    ).all()
    data = {s: 0 for s in QUOTE_STATUSES}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


# ---------------- AI 生成（三级回退） ----------------


def _history_quotations(db: Session, customer_id: int, limit: int = 3) -> list[SalesQuotation]:
    if not customer_id:
        return []
    return list(
        db.scalars(
            select(SalesQuotation)
            .where(SalesQuotation.customer_id == customer_id, SalesQuotation.deleted == 0)
            .order_by(SalesQuotation.id.desc())
            .limit(limit)
        ).all()
    )


def _ai_meta(source: str, fallback_reason: str = "", model: str = "") -> str:
    meta: dict = {"source": source, "promptVersion": prompts.feature_version("quote")}
    if fallback_reason:
        meta["fallbackReason"] = fallback_reason
    if model:
        meta["model"] = model
    return json.dumps(meta, ensure_ascii=False)


def _template_fallback(layout: dict, reason: str) -> dict:
    return {
        "source": "template",
        "fallbackReason": reason,
        "title": "",
        "introHtml": str(layout.get("introHtml") or ""),
        "termsHtml": str(layout.get("termsHtml") or ""),
        "items": [],
        "aiMeta": _ai_meta("template", reason),
    }


def _history_fallback(latest: SalesQuotation, layout: dict) -> dict:
    no = latest.quote_no or f"#{latest.id}"
    items = []
    for it in latest.items:
        remark = f"{it.remark}（复制自 {no}）" if it.remark else f"复制自 {no}"
        items.append(
            {
                "name": it.name,
                "spec": it.spec,
                "unit": it.unit,
                "qty": float(it.qty),
                "unitPrice": float(it.unit_price),
                "amount": float(it.amount),
                "remark": remark[:255],
            }
        )
    return {
        "source": "history",
        "fallbackReason": "ai_failed",
        "title": "",
        "introHtml": str(layout.get("introHtml") or latest.intro_html or ""),
        "termsHtml": str(layout.get("termsHtml") or latest.terms_html or ""),
        "items": items,
        "aiMeta": _ai_meta("history", "ai_failed"),
    }


def _history_summary(history: list[SalesQuotation]) -> str:
    """该客户最近报价摘要（few-shot 上下文）。"""
    blocks = []
    for q in history:
        lines = [f"报价 {q.quote_no or q.id}（{q.title}，合计 {q.total_amount}）："]
        for it in q.items[:10]:
            lines.append(f"- {it.name} {it.spec} {it.qty}{it.unit} × {it.unit_price}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_prompt(requirement: str, customer_name: str, layout: dict, history: list[SalesQuotation]) -> list[dict]:
    parts = [f"客户：{customer_name or '未知'}", f"客户需求：{requirement}"]
    terms = str(layout.get("termsHtml") or "").strip()
    if terms:
        parts.append(f"公司标准条款（可作为 termsHtml 基础改写）：{terms}")
    if history:
        parts.append(f"该客户最近历史报价（参考口径与价格水平）：\n{_history_summary(history)}")
    return [
        {"role": "system", "content": prompts.get("quote")["system"]},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


class _AiStructureError(Exception):
    """AI 输出 JSON 结构不符（触发历史回退）。"""


def _parse_ai_json(raw: str) -> dict:
    text = raw.strip()
    if not text.startswith("{"):
        # 容错：截取首个 { 到末个 }（模型偶发包裹说明文字/代码围栏）
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise _AiStructureError("no json object")
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise _AiStructureError("invalid json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise _AiStructureError("missing items")
    items = []
    for it in data["items"][:50]:
        if not isinstance(it, dict) or not str(it.get("name") or "").strip():
            raise _AiStructureError("item missing name")
        try:
            qty = Decimal(str(it.get("qty", 0)))
            unit_price = Decimal(str(it.get("unitPrice", 0)))
        except ArithmeticError as exc:
            raise _AiStructureError("bad number") from exc
        if qty <= 0 or unit_price < 0:
            raise _AiStructureError("bad number range")
        # 金额服务端重算：不信任模型算术
        items.append(
            {
                "name": str(it["name"]).strip()[:255],
                "spec": str(it.get("spec") or "")[:255],
                "unit": str(it.get("unit") or "")[:16],
                "qty": float(qty),
                "unitPrice": float(unit_price),
                "amount": float((qty * unit_price).quantize(Decimal("0.01"))),
                "remark": str(it.get("remark") or "")[:255],
            }
        )
    if not items:
        raise _AiStructureError("empty items")
    return {
        "title": str(data.get("title") or "")[:255],
        "introHtml": str(data.get("introHtml") or "")[:8000],
        "termsHtml": str(data.get("termsHtml") or "")[:8000],
        "items": items,
    }


def ai_generate(db: Session, current: User, body: S.AiGenerateIn) -> dict:
    """需求文本 → 报价草稿（回填前端不落库）。回退：未配置/功能停用→模板默认；调用失败→该客户最近报价复制。

    统一走 AI 网关（feature=quote）：配额超限直接抛 65003 回前端；其余回退均落用量日志。
    """
    q = _load(db, body.quotation_id) if body.quotation_id else None
    if q is not None:
        _check_editable(q)
    customer_id = body.customer_id or (q.customer_id if q else 0)
    template_id = body.template_id or (q.template_id if q else 0)
    customer_name = ""
    if customer_id:
        customer = db.get(Customer, customer_id)
        if customer and not customer.deleted:
            customer_name = customer.name
    tpl = db.get(SalesQuoteTemplate, template_id) if template_id else None
    layout = _layout_of(tpl) if tpl and not tpl.deleted else {}

    if not ai_svc.ai_ready(db):
        ai_svc.log_usage(db, feature="quote", status=ai_svc.USAGE_FALLBACK, error="ai_not_configured",
                         user=current, biz_type="sales_quotation", biz_id=q.id if q else None,
                         prompt_version=prompts.feature_version("quote"),
                         masking=masking_svc.effective_level(db, "quote"))
        return _template_fallback(layout, "ai_not_configured")

    history = _history_quotations(db, customer_id, limit=3)
    messages = _build_prompt(body.requirement.strip(), customer_name, layout, history)
    try:
        raw = ai_svc.gateway_chat(
            db, feature="quote", messages=messages, user=current,
            biz_type="sales_quotation", biz_id=q.id if q else None,
            prompt_version=prompts.feature_version("quote"),
        )
        data = _parse_ai_json(raw)
    except ai_svc.AiQuotaExceeded:
        raise  # 配额超限：明确错误码回前端，不静默回退
    except ai_svc.AiFeatureDisabled:
        return _template_fallback(layout, "feature_disabled")
    except (ai_svc.AiUnavailable, _AiStructureError) as exc:
        logger.warning("AI 报价生成失败，走回退：%s", exc)
        if history and history[0].items:
            return _history_fallback(history[0], layout)
        return _template_fallback(layout, "ai_failed")
    cfg = ai_svc.ai_config(db)
    return {
        "source": "ai",
        "fallbackReason": "",
        "title": data["title"],
        "introHtml": data["introHtml"],
        "termsHtml": data["termsHtml"],
        "items": data["items"],
        "aiMeta": _ai_meta("ai", model=cfg["model"]),
    }
