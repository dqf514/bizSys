"""Excel 导入导出中心（openpyxl；列元数据驱动，列头走调用方 i18n 键或中文）。"""

import io
from collections.abc import Callable
from datetime import datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HeaderFill = PatternFill("solid", fgColor="D9E2F3")
HeaderFont = Font(bold=True)


def export_xlsx(
    rows: list[dict[str, Any]],
    columns: list[dict],
    filename: str,
    sheet_name: str = "data",
) -> bytes:
    """columns: [{key, label, width?, formatter?(callable)}]"""
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(sheet_name)
    ws.append([c["label"] for c in columns])
    for row in rows:
        values = []
        for c in columns:
            v = row.get(c["key"], "")
            fmt = c.get("formatter")
            values.append(fmt(v, row) if fmt else v)
        ws.append(values)
    # write_only 模式下列宽在 append 前设置无效，此处用普通模式补一次轻量实现：
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_xlsx_styled(
    rows: list[dict[str, Any]],
    columns: list[dict],
    filename: str,
    sheet_name: str = "data",
) -> bytes:
    """普通模式（带表头样式/列宽），中小数据量导出用。"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    headers = [c["label"] for c in columns]
    ws.append(headers)
    for i, c in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.fill = HeaderFill
        cell.font = HeaderFont
        cell.alignment = Alignment(vertical="center")
        ws.column_dimensions[get_column_letter(i)].width = c.get("width", 16)
    for row in rows:
        ws.append(
            [
                (c.get("formatter")(row.get(c["key"], ""), row) if c.get("formatter") else row.get(c["key"], ""))
                for c in columns
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_xlsx(columns: list[dict], filename: str = "template.xlsx") -> bytes:
    """导入模板：表头 + 一行示例空行。"""
    return export_xlsx_styled([], columns, filename, "template")


def import_rows(
    data: bytes,
    columns: list[dict],
    validators: dict[str, Callable] | None = None,
) -> tuple[list[dict], list[dict]]:
    """解析上传的 xlsx（首行表头按 columns.label 匹配）。

    返回 (ok_rows, errors)；errors: [{row, field, message}]（row 为文件行号，含表头偏移）。
    """
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return [], [{"row": 1, "field": "", "message": "空文件"}]

    label_to_col = {c["label"]: i for i, c in enumerate(columns)}
    col_idx = {}
    for i, h in enumerate(header):
        if h in label_to_col:
            col_idx[label_to_col[h]] = i
    missing = [columns[i]["label"] for i in range(len(columns)) if i not in col_idx]
    if missing:
        return [], [{"row": 1, "field": "", "message": f"缺少表头列：{', '.join(missing)}"}]

    ok_rows: list[dict] = []
    errors: list[dict] = []
    validators = validators or {}
    for rno, raw in enumerate(rows_iter, start=2):
        if raw is None or all(v in (None, "") for v in raw):
            continue
        row: dict = {}
        row_errors = []
        for i, c in enumerate(columns):
            v = raw[col_idx[i]] if col_idx[i] < len(raw) else None
            row[c["key"]] = v
            fn = validators.get(c["key"])
            if fn:
                msg = fn(v, row)
                if msg:
                    row_errors.append({"row": rno, "field": c["label"], "message": msg})
        if row_errors:
            errors.extend(row_errors)
        else:
            ok_rows.append(row)
    return ok_rows, errors


def now_filename(prefix: str, ext: str = "xlsx") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
