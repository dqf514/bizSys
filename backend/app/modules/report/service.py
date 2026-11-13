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

from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, ApprovalWithdrawn, subscribe
from app.core import response as R
from app.core.config import settings
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.report.models import Report, ReportFile
from app.modules.task.models import TaskItem

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


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)


# ---------------- AI 报告摘要（草稿 → 人工编辑 → 采用才写 remark） ----------------

SUMMARY_PROMPT_VERSION = "v1"
SUMMARY_SYSTEM = (
    "你是检测报告摘要助手。根据报告文本与任务信息撰写「报告摘要/结论草稿」，"
    "要求：客观、200-400 字、包含检测对象/依据标准/主要结果/结论建议；信息不足时基于任务信息概括并标注待补充。"
    "直接输出摘要文本，不要输出标题以外的格式标记。"
)


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
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": "\n".join(context) + text_note},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="report_summary", messages=messages, user=user,
            biz_type="report", biz_id=r.id, prompt_version=SUMMARY_PROMPT_VERSION,
            json_mode=False, max_tokens=1200,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    return {"summary": raw.strip()[:4000], "source": "ai"}


def update_remark(db: Session, r: Report, remark: str, user: User) -> Report:
    """采用 AI 摘要/人工编辑结论：仅 uploaded/rejected 可改（审批中/已签章锁定）。"""
    if r.status not in ("uploaded", "rejected"):
        raise BizException(R.REPORT_INVALID_STATE, "当前报告状态不允许修改摘要")
    r.remark = remark.strip()
    r.update_by = user.id
    r.update_time = datetime.now()
    db.flush()
    return r
