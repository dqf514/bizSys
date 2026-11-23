"""报告服务：审批事件订阅、PDF 转换（LibreOffice 探测降级）、签章占位、条目状态同步。

PDF 转换策略（技术设计「CA 未定前占位」）：
- 原件即 PDF → 直接复用为 pdf_file；
- 探测到 soffice（LibreOffice）→ subprocess 无头转换，超时 120s；
- 未安装/转换失败 → pdf_file_id=原件并在 remark 标注，流程不阻断。
"""

import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.core import response as R
from app.core import signature
from app.core.config import settings
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.report.models import Report, ReportFile
from app.modules.task.models import TaskItem
from app.services import prompts

logger = logging.getLogger("bizsys.report")

CONVERT_TIMEOUT = 120  # soffice 转换超时（秒）


def snapshot(r: Report) -> dict:
    return {
        "reportNo": r.report_no,
        "taskId": r.task_id,
        "taskItemId": r.task_item_id,
        "fileName": r.file_name,
        "status": r.status,
    }


def form_snapshot(r: Report) -> dict:
    return json.loads(json.dumps(snapshot(r), ensure_ascii=False, default=str))


def sync_item_status(db: Session, task_item_id: int, status: str) -> None:
    """同步 task_item.report_status（pending/uploaded/approving/approved/rejected/sealed）。"""
    item = db.get(TaskItem, task_item_id)
    if not item or item.deleted:
        return
    item.report_status = status
    item.update_time = datetime.now()


def save_file(data: bytes, file_name: str, content_type: str, subdir: str = "report") -> ReportFile:
    rel = Path(subdir) / uuid.uuid4().hex
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return ReportFile(file_name=file_name, size=len(data), content_type=content_type, path=str(rel))


def file_path(f: ReportFile) -> Path:
    return Path(settings.upload_dir) / f.path


def _is_pdf(f: ReportFile) -> bool:
    return f.file_name.lower().endswith(".pdf") or f.content_type == "application/pdf"


def convert_to_pdf(db: Session, r: Report, operator_id: int | None = None) -> None:
    """审批通过后自动转 PDF；任何失败都降级为「PDF=原件 + remark 标注」，不阻断流程。"""
    src = db.get(ReportFile, r.file_id)
    if not src or src.deleted:
        return
    if _is_pdf(src):
        r.pdf_file_id = r.file_id
        return
    soffice = shutil.which("soffice")
    if not soffice:
        r.pdf_file_id = r.file_id
        r.remark = _append_remark(r.remark, "未安装转换器(LibreOffice)，PDF 下载返回原件")
        return
    src_path = file_path(src)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(  # noqa: S603
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src_path)],
                timeout=CONVERT_TIMEOUT,
                capture_output=True,
                check=False,
            )
            produced = Path(tmp) / (src_path.stem + ".pdf")
            if not produced.exists() or produced.stat().st_size == 0:
                raise RuntimeError("soffice 未产出 PDF")
            pdf_name = src_path.stem + ".pdf"
            f = save_file(produced.read_bytes(), pdf_name, "application/pdf")
            f.create_by = operator_id
            db.add(f)
            db.flush()
            r.pdf_file_id = f.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("report %s pdf convert failed: %s", r.id, exc)
        r.pdf_file_id = r.file_id
        r.remark = _append_remark(r.remark, f"PDF 转换失败（{exc.__class__.__name__}），PDF 下载返回原件")


def _append_remark(remark: str | None, note: str) -> str:
    base = (remark or "").strip()
    return f"{base}；{note}" if base else note


def apply_seal_watermark(db: Session, r: Report, operator_name: str) -> bool:
    """签章占位适配器：pypdf 可用时在 PDF 末页叠加文字水印；不可用则仅状态+留痕（CA 未定前占位）。"""
    try:
        from pypdf import PdfReader, PdfWriter  # noqa: PLC0415
        from pypdf.annotations import FreeText  # noqa: PLC0415
    except ImportError:
        return False
    fid = r.pdf_file_id or r.file_id
    f = db.get(ReportFile, fid)
    if not f or f.deleted or not _is_pdf(f):
        return False
    path = file_path(f)
    if not path.exists():
        return False
    try:
        reader = PdfReader(str(path))
        writer = PdfWriter()
        writer.append(reader)
        stamp = FreeText(
            text=f"已签章 {operator_name} {datetime.now():%Y-%m-%d}",
            rect=(400, 30, 580, 60),
            font="Helv",
            font_size="14pt",
            font_color="ff0000",
            border_color="ff0000",
        )
        writer.add_annotation(page_number=len(writer.pages) - 1, annotation=stamp)
        sealed_rel = Path("report") / f"{uuid.uuid4().hex}"
        sealed_dest = Path(settings.upload_dir) / sealed_rel
        sealed_dest.parent.mkdir(parents=True, exist_ok=True)
        with sealed_dest.open("wb") as fp:
            writer.write(fp)
        nf = ReportFile(
            file_name=f.file_name,
            size=sealed_dest.stat().st_size,
            content_type="application/pdf",
            path=str(sealed_rel),
            create_by=r.seal_by,
        )
        db.add(nf)
        db.flush()
        r.pdf_file_id = nf.id
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("report %s seal watermark failed: %s", r.id, exc)
        return False


# ---------------- B9 签章密码学绑定 + 签章后锁定 ----------------


def compute_content_hash(db: Session, r: Report) -> str:
    """签章内容哈希 = sha256(最终PDF字节 | 单号 | 条目id | sha256(结论))。

    **铁律**：必须在 `apply_seal_watermark()` 之后计算 —— 盖章会产出新的 PDF 文件，
    先算必然与最终交付物对不上。文件缺失时 PDF 段留空（验签端点仍可验签名本身）。
    """
    file_hash = ""
    fid = r.pdf_file_id or r.file_id
    if fid:
        f = db.get(ReportFile, fid)
        if f and not f.deleted:
            path = file_path(f)
            if path.exists():
                file_hash = signature.sha256_file(str(path))
    parts = [
        file_hash,
        r.report_no or "",
        str(r.task_item_id or 0),
        signature.sha256_hex(r.conclusion or ""),
    ]
    return signature.sha256_hex("|".join(parts))


def seal_sign_payload(r: Report) -> dict:
    """按签章时同样的口径重建签名载荷（验签用）。

    时间戳统一截断到秒：`seal_time` 列是 DATETIME(0)，MySQL 对带小数的
    时间值会**四舍五入**而不是截断，签名里若用未截断值会与落库值不一致。
    """
    return {
        "biz_type": "report",
        "report_no": r.report_no or "",
        "task_item_id": r.task_item_id or 0,
        "content_hash": r.seal_content_hash or "",
        "sealed_by_id": r.seal_by or 0,
        "sealed_by_name": r.seal_by_name or "",
        "sealed_at": r.seal_time.replace(microsecond=0).isoformat(timespec="seconds") if r.seal_time else "",
    }


def sign_seal(db: Session, r: Report, sealed_by_name: str) -> None:
    """签章后落签名（内容哈希 + HMAC 签名），落在同一事务内。"""
    r.seal_by_name = sealed_by_name or ""
    r.seal_content_hash = compute_content_hash(db, r)
    r.seal_signature = signature.sign(seal_sign_payload(r), signature.REPORT_SEAL_FIELDS)
    r.seal_alg = signature.ALG


def verify_seal(db: Session, r: Report) -> dict:
    """签章验签结论。

    - `signatureValid`：签名与当前单据字段一致（签名没被伪造）；
    - `contentMatch`：当前内容哈希与签章时一致（内容签完没被改）；
    - `contentUnavailable`：最终 PDF 已丢失，只能验签名、无法验内容。
    """
    if not r.seal_signature:
        return {
            "signatureValid": False,
            "contentMatch": False,
            "contentUnavailable": False,
            "alg": r.seal_alg or "",
            "sealedBy": r.seal_by_name or "",
            "sealedAt": r.seal_time.isoformat(timespec="seconds") if r.seal_time else "",
            "contentHash": r.seal_content_hash or "",
            "reason": "该报告未签章或为存量行（无密码学绑定）",
        }
    signature_valid = signature.verify(seal_sign_payload(r), signature.REPORT_SEAL_FIELDS, r.seal_signature)
    current_hash = compute_content_hash(db, r)
    content_match = current_hash == (r.seal_content_hash or "")
    fid = r.pdf_file_id or r.file_id
    unavailable = True
    if fid:
        f = db.get(ReportFile, fid)
        if f and not f.deleted and file_path(f).exists():
            unavailable = False
    reason = ""
    if not signature_valid:
        reason = "签章签名与当前单据字段不一致（签名被伪造或单据关键字段被改）"
    elif not content_match:
        reason = "签章后内容发生变化（结论或交付文件被修改）"
    return {
        "signatureValid": signature_valid,
        "contentMatch": content_match,
        "contentUnavailable": unavailable,
        "alg": r.seal_alg or signature.ALG,
        "sealedBy": r.seal_by_name or "",
        "sealedAt": r.seal_time.isoformat(timespec="seconds") if r.seal_time else "",
        "contentHash": r.seal_content_hash or "",
        "reason": reason,
    }


def assert_report_editable(db: Session, r: Report) -> None:
    """签章后锁定（B9 合规 2.4「签名后记录锁定」）。

    已签章的报告不得原地修改 —— 只能作废后重做，避免"签完再改"导致签章失效。
    """
    if r.status == "sealed":
        raise BizException(R.REPORT_SEALED_LOCKED, f"报告 {r.report_no} 已签章锁定，不能原地修改")


# ---------------------------------------------------------------------------
# B9-C3 三级审核与职责分离（SoD）
# ---------------------------------------------------------------------------


def resolve_report_roles(db: Session, r: Report) -> dict:
    """解析报告的编制 / 复核 / 批准三人 + 当前签批流程的审批节点数。

    **动态探测**（不改流程定义）：管理员在「流程设置」给 `report_sign` 发新版本
    加节点 → `flow_version` 递增 → 新实例取新版本 → 节点数从 1 变 2/3，
    本函数自动识别为三级审核，代码零改动即变硬拦截。

    - `node_count` = 签批实例所用流程定义中 `approval` 类型节点数；
    - 复核人 = 时间线里第 1 个通过人，批准人 = 第 2 个通过人；
    - 编制人 = 报告上传人（`preparer_id` / `create_by`）。
    """
    preparer_id = r.preparer_id or r.create_by
    reviewer_id = r.reviewer_id
    approver_id = r.approver_id
    node_count = 0

    inst = None
    if r.approval_instance_id:
        from app.modules.approval.models import ApprovalInstance

        inst = db.get(ApprovalInstance, r.approval_instance_id)
    if inst is not None and inst.definition_id:
        from app.modules.approval.models import ApprovalNode

        node_count = len(
            db.scalars(
                select(ApprovalNode).where(
                    ApprovalNode.definition_id == inst.definition_id,
                    ApprovalNode.node_type == "approval",
                    ApprovalNode.deleted == 0,
                )
            ).all()
        )
        if node_count >= 2:
            from app.modules.approval.models import ApprovalRecord

            records = db.scalars(
                select(ApprovalRecord)
                .where(ApprovalRecord.instance_id == inst.id, ApprovalRecord.action == "agree")
                .order_by(ApprovalRecord.seq, ApprovalRecord.id)
            ).all()
            approvers: list[int] = []
            for rec in records:
                if rec.operator_id and rec.operator_id not in approvers:
                    approvers.append(rec.operator_id)
            if not reviewer_id and len(approvers) >= 1:
                reviewer_id = approvers[0]
            if not approver_id and len(approvers) >= 2:
                approver_id = approvers[1]

    names: dict[int, str] = {}
    ids = [i for i in (preparer_id, reviewer_id, approver_id) if i]
    if ids:
        from app.modules.auth.models import User as _User

        for u in db.scalars(select(_User).where(_User.id.in_(ids))).all():
            names[u.id] = u.name or u.username

    return {
        "nodeCount": node_count,
        "level": "triple" if node_count >= 2 else "single",
        "preparerId": preparer_id or 0,
        "preparerName": names.get(preparer_id or 0, "") or (r.preparer_name or ""),
        "reviewerId": reviewer_id or 0,
        "reviewerName": names.get(reviewer_id or 0, "") or (r.reviewer_name or ""),
        "approverId": approver_id or 0,
        "approverName": names.get(approver_id or 0, "") or (r.approver_name or ""),
    }


def assert_report_sod(db: Session, r: Report) -> dict:
    """职责分离校验（合规 2.3 / HR 3.4）。

    - 三级审核（审批节点数 ≥ 2）→ **硬拦截**：编制 / 复核 / 批准不得同一人，
      且三人各自须持对应角色的有效授权；
    - 单级审核（节点数 = 1）→ **降级告警**：写审计，不阻断（流程尚未升级到三级）。
    """
    from app.modules.hr import authorization as auth

    roles = resolve_report_roles(db, r)
    node_count = roles["nodeCount"]
    if node_count < 2:
        audit(
            db,
            user_id=None,
            module="report",
            action="report_sod_warning",
            biz_type="report",
            biz_id=r.id,
            reason="签批流程仍为单级，未启用编制/复核/批准三方职责分离",
            detail={
                "reportNo": r.report_no,
                "nodeCount": node_count,
                "preparerId": roles["preparerId"],
                "approverId": roles["approverId"],
            },
        )
        return roles

    auth.assert_sod(
        db,
        preparer_id=roles["preparerId"] or None,
        reviewer_id=roles["reviewerId"] or None,
        approver_id=roles["approverId"] or None,
    )
    # 三方各自须持对应角色授权（缺一即不合规）
    for role, uid in (
        (auth.ROLE_PREPARER, roles["preparerId"]),
        (auth.ROLE_REVIEWER, roles["reviewerId"]),
        (auth.ROLE_APPROVER, roles["approverId"]),
    ):
        if not uid:
            continue
        auth.assert_authorized(
            db,
            _UserRef(uid),
            auth_type=auth.AUTH_TYPE_REPORT_ROLE,
            role_code=role,
            label=f"报告 {r.report_no} 的{_ROLE_CN.get(role, role)}",
        )
    return roles


class _UserRef:
    """轻量用户引用（只有 id / name 即可满足授权校验接口）。"""

    __slots__ = ("id", "name", "username", "role_codes")

    def __init__(self, uid: int, name: str = "", role_codes: tuple[str, ...] = ()):
        self.id = uid
        self.name = name
        self.username = ""
        self.role_codes = role_codes


_ROLE_CN = {"preparer": "编制", "reviewer": "复核", "approver": "批准", "signer": "签字"}



def _handle_completed(event: ApprovalCompleted) -> None:
    """签批通过 → approved + 自动转 PDF（同事务，失败降级不阻断）。"""
    if event.biz_type != "report":
        return
    db: Session = event.db
    r = db.get(Report, event.biz_id)
    if not r or r.deleted or r.status != "approving":
        return
    r.status = "approved"
    r.approval_instance_id = event.instance_id
    r.update_time = datetime.now()
    convert_to_pdf(db, r, operator_id=event.operator_id)
    sync_item_status(db, r.task_item_id, "approved")
    db.flush()


def _rollback_uploaded(db: Session, biz_id: int, instance_id: int, status: str) -> None:
    r = db.get(Report, biz_id)
    if not r or r.deleted or r.status != "approving":
        return
    r.status = status
    r.approval_instance_id = instance_id
    r.update_time = datetime.now()
    sync_item_status(db, r.task_item_id, status)


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "report":
        return
    _rollback_uploaded(event.db, event.biz_id, event.instance_id, "rejected")


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    if event.biz_type != "report":
        return
    _rollback_uploaded(event.db, event.biz_id, event.instance_id, "uploaded")


def register_flow_handlers() -> None:
    """F5：审批处理器注册入口，由 ``app.modules.approval.wiring.install()`` 显式装配。

    不再在模块 import 时自动订阅 —— 漏一个 import 就会让单据永久卡在 approving。
    """
    subscribe(ApprovalCompleted, _handle_completed)
    subscribe(ApprovalRejected, _handle_rejected)
    subscribe(ApprovalWithdrawn, _handle_withdrawn)



# ---------------- AI 报告摘要（草稿 → 人工编辑 → 采用才写 remark） ----------------


def ai_summary(db: Session, r: Report, user: User) -> dict:
    """基于报告文件文本（可提取时）+ 任务信息生成摘要草稿；不落库。"""
    from app.modules.task.models import Task, TaskItem
    from app.services import ai as ai_svc

    if not ai_svc.feature_enabled(db, "report_summary"):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或报告摘要功能已停用")

    item = db.get(TaskItem, r.task_item_id)
    task = db.get(Task, r.task_id)
    context = [
        f"报告编号：{r.report_no}",
        f"任务：{task.task_name if task else ''}（{task.task_no or '' if task else ''}）",
        f"客户：{task.customer_name if task else ''}",
        f"条目：{item.name if item else ''}（依据标准：{item.std if item else ''}）",
        f"工作内容：{(task.content or '')[:500] if task else ''}",
    ]
    text_note = ""
    f = db.get(ReportFile, r.file_id)
    if f:
        try:
            path = file_path(f)
            if path.exists():
                extracted = ai_svc.extract_text(f.file_name, path.read_bytes())
                text_note = f"\n\n报告文件文本（节选）：\n{extracted}"
        except BizException:
            text_note = "\n\n（报告文件文本不可提取，请基于任务信息概括）"
    messages = [
        {"role": "system", "content": prompts.get("report_summary")["system"]},
        {"role": "user", "content": "\n".join(context) + text_note},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="report_summary", messages=messages, user=user,
            biz_type="report", biz_id=r.id, prompt_version=prompts.feature_version("report_summary"),
            json_mode=False, max_tokens=1200,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    return {"summary": raw.strip()[:4000], "source": "ai"}


def update_remark(db: Session, r: Report, remark: str, user: User) -> Report:
    """采用 AI 摘要/人工编辑结论：仅 uploaded/rejected 可改（审批中/已签章锁定）。"""
    assert_report_editable(db, r)
    if r.status not in ("uploaded", "rejected"):
        raise BizException(R.REPORT_INVALID_STATE, "当前报告状态不允许修改摘要")
    r.remark = remark.strip()
    r.update_by = user.id
    r.update_time = datetime.now()
    db.flush()
    return r


# ---------------- AI 全文辅助（结论草稿 / 校对 / 完整性检查；仅结论采用后落库） ----------------


def _assist_context(db: Session, r: Report) -> str:
    """任务/条目/报告文件文本上下文（与摘要共用提取通道，截断由 extract_text 保证）。"""
    from app.modules.task.models import Task
    from app.services import ai as ai_svc

    item = db.get(TaskItem, r.task_item_id)
    task = db.get(Task, r.task_id)
    context = [
        f"报告编号：{r.report_no}",
        f"任务：{task.task_name if task else ''}（{task.task_no or '' if task else ''}）",
        f"客户：{task.customer_name if task else ''}",
        f"条目：{item.name if item else ''}（依据标准：{item.std if item else ''}）",
        f"工作内容：{(task.content or '')[:500] if task else ''}",
        f"已有结论段：{(r.conclusion or '')[:500]}",
    ]
    text_note = ""
    f = db.get(ReportFile, r.file_id)
    if f:
        try:
            path = file_path(f)
            if path.exists():
                extracted = ai_svc.extract_text(f.file_name, path.read_bytes())
                text_note = f"\n\n报告文件文本（节选）：\n{extracted}"
        except BizException:
            text_note = "\n\n（报告文件文本不可提取，请基于任务信息判断并标注待补充）"
    return "\n".join(context) + text_note


def _parse_issues(raw: str, *, limit: int = 50) -> list[dict]:
    """proofread 输出清洗：保留 original/suggestion 非空的项，字段截断，条数封顶。"""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 校对结果解析失败，请重试") from exc
    issues = data.get("issues") if isinstance(data, dict) else None
    if not isinstance(issues, list):
        raise BizException(R.AI_PARSE_FAILED, "AI 校对结果结构不符，请重试")
    out = []
    for it in issues:
        if not isinstance(it, dict):
            continue
        original = str(it.get("original") or "").strip()
        suggestion = str(it.get("suggestion") or "").strip()
        if not original or not suggestion:
            continue
        out.append(
            {
                "position": str(it.get("position") or "")[:100],
                "original": original[:500],
                "suggestion": suggestion[:500],
            }
        )
        if len(out) >= limit:
            break
    return out


def _completeness_rules(db: Session, r: Report) -> list[dict]:
    """确定性规则检查（编号一致性/签章信息/日期/条目缺漏），先于 AI 文本检查。"""
    from app.modules.task.models import Task

    items: list[dict] = []
    items.append(
        {
            "key": "reportNo",
            "ok": bool(r.report_no),
            "detail": f"报告编号：{r.report_no}" if r.report_no else "缺少报告编号",
        }
    )
    item = db.get(TaskItem, r.task_item_id)
    no_match_ok = bool(item and item.report_no == r.report_no)
    items.append(
        {
            "key": "noMatch",
            "ok": no_match_ok,
            "detail": "报告编号与条目编号一致"
            if no_match_ok
            else f"编号不一致：报告 {r.report_no} / 条目 {item.report_no if item else '-'}",
        }
    )
    task = db.get(Task, r.task_id)
    date_ok = bool(task and task.plan_finish_date)
    items.append(
        {
            "key": "dates",
            "ok": date_ok,
            "detail": f"任务计划完成日期：{task.plan_finish_date}" if date_ok else "任务缺少计划完成日期",
        }
    )
    seal_ok = bool(r.seal_by and r.seal_time)
    items.append(
        {
            "key": "sealInfo",
            "ok": seal_ok,
            "detail": "已签章" if seal_ok else "尚未签章（签章人/签章时间缺失）",
        }
    )
    missing = list(
        db.scalars(
            select(TaskItem).where(
                TaskItem.task_id == r.task_id,
                TaskItem.deleted == 0,
                TaskItem.need_report == 1,
                TaskItem.report_no != "",
                TaskItem.id != r.task_item_id,
                ~select(Report.id).where(Report.task_item_id == TaskItem.id, Report.deleted == 0).exists(),
            )
        )
    )
    items.append(
        {
            "key": "missingItems",
            "ok": not missing,
            "detail": "任务内应出报告的条目均已上传"
            if not missing
            else "条目缺漏：" + "、".join(i.report_no or i.name for i in missing[:5]),
        }
    )
    return items


def ai_assist(db: Session, r: Report, user: User, kind: str) -> dict:
    """AI 全文辅助：conclusion 结论草稿 / proofread 校对清单 / completeness 完整性清单（规则+AI）。

    只返回草稿与清单，不落库；结论由人工编辑后经 PUT conclusion 采用。
    """
    from app.services import ai as ai_svc

    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置，请联系管理员")
    # 功能停用由 gateway_chat 抛 AiFeatureDisabled（65002），与配额 65003 一并透传

    system = prompts.get(f"report_assist.{kind}")["system"]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": _assist_context(db, r)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="report_assist", messages=messages, user=user,
            biz_type="report", biz_id=r.id, prompt_version=prompts.feature_version("report_assist"),
            json_mode=True, max_tokens=2000,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc

    if kind == "conclusion":
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise BizException(R.AI_PARSE_FAILED, "AI 结论草稿解析失败，请重试") from exc
        conclusion = str(data.get("conclusion") or "").strip() if isinstance(data, dict) else ""
        if not conclusion:
            raise BizException(R.AI_PARSE_FAILED, "AI 未返回结论草稿，请重试")
        return {"kind": kind, "conclusion": conclusion[:4000]}

    if kind == "proofread":
        return {"kind": kind, "issues": _parse_issues(raw)}

    items = _completeness_rules(db, r)
    try:
        data = json.loads(raw)
        ai_issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(ai_issues, list):
            raise ValueError("issues not list")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 完整性检查结果解析失败，请重试") from exc
    ai_issues = [str(x).strip()[:300] for x in ai_issues if str(x).strip()][:20]
    if ai_issues:
        items.extend({"key": "aiCheck", "ok": False, "detail": x} for x in ai_issues)
    else:
        items.append({"key": "aiCheck", "ok": True, "detail": "AI 未发现其他缺失要素"})
    return {"kind": kind, "items": items}


def update_conclusion(db: Session, r: Report, conclusion: str, user: User) -> Report:
    """采用结论段（AI 草稿人工编辑后）：仅 uploaded/rejected 可改（审批中/已签章锁定）。"""
    assert_report_editable(db, r)
    if r.status not in ("uploaded", "rejected"):
        raise BizException(R.REPORT_INVALID_STATE, "当前报告状态不允许修改结论")
    r.conclusion = conclusion.strip()
    r.update_by = user.id
    r.update_time = datetime.now()
    db.flush()
    return r
