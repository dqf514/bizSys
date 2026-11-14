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


# ---------------- AI 全文辅助（结论草稿 / 校对 / 完整性检查；仅结论采用后落库） ----------------

ASSIST_PROMPT_VERSION = "v1"

CONCLUSION_SYSTEM = (
    "你是检测报告结论撰写助手。根据任务/条目信息与报告文本，撰写「结论与测量不确定度」段落草稿："
    "包含检测结论（样品是否满足依据标准的技术要求）与测量不确定度说明；信息不足处用【待补充：…】标注，"
    "不得编造数值。仅输出 JSON：{\"conclusion\": \"段落文本\"}。"
)

PROOFREAD_SYSTEM = (
    "你是检测报告校对助手。检查报告文本的错别字、标点误用、数字与单位格式、明显语病。"
    "仅输出 JSON：{\"issues\": [{\"position\": \"章节或位置\", \"original\": \"原文片段\", "
    "\"suggestion\": \"修改建议\"}]}；未发现问题时 issues 输出空数组。只列问题，不要改写全文。"
)

COMPLETENESS_SYSTEM = (
    "你是检测报告完整性审查助手。检查报告文本是否缺少以下要素：报告编号、检测日期、签名/签章信息、"
    "依据标准、结论段、测量不确定度说明、样品信息。仅输出 JSON：{\"issues\": [\"缺失项描述\", ...]}；"
    "无缺失时输出空数组。"
)


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

    system = {"conclusion": CONCLUSION_SYSTEM, "proofread": PROOFREAD_SYSTEM, "completeness": COMPLETENESS_SYSTEM}[
        kind
    ]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": _assist_context(db, r)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="report_assist", messages=messages, user=user,
            biz_type="report", biz_id=r.id, prompt_version=ASSIST_PROMPT_VERSION,
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
    if r.status not in ("uploaded", "rejected"):
        raise BizException(R.REPORT_INVALID_STATE, "当前报告状态不允许修改结论")
    r.conclusion = conclusion.strip()
    r.update_by = user.id
    r.update_time = datetime.now()
    db.flush()
    return r
