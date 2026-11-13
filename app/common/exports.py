"""匯出:xlsx(openpyxl)、中文 PDF(reportlab)、多檔 ZIP,以及下載回應。

    headers, rows = ["名稱", "金額"], [["午餐", 120]]
    return file_response(build_xlsx(headers, rows, sheet_title="明細"), "報表_2026-11.xlsx", XLSX)

產檔是同步、吃 CPU 的工作:放在同步 endpoint(FastAPI 丟 threadpool)或長任務裡跑,不要放在 async 函式。
"""

import io
import unicodedata
import zipfile
from collections.abc import Iterable, Sequence
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi.responses import StreamingResponse
from loguru import logger
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.common.core.config import config

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
ZIP = "application/zip"

Cell = str | int | float | bool | None


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    PDF = "pdf"
    ZIP = "zip"  # xlsx + pdf 打包


_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="305496")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_MAX_COL_WIDTH = 60
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _display_width(value: Cell) -> int:
    """估算欄寬:全形(中日韓)字算 2。"""
    text = "" if value is None else str(value)
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def build_xlsx(
    headers: Sequence[str],
    rows: Iterable[Sequence[Cell]],
    *,
    sheet_title: str = "Sheet1",
    column_widths: Sequence[float] | None = None,
) -> bytes:
    """標題列粗體、底色、凍結,欄寬依內容估算(或用 column_widths 指定)。

    字串一律存成文字:openpyxl 會把 = 開頭當公式,使用者輸入的「=HYPERLINK(...)」就成了公式注入。
    """
    wb = Workbook()
    ws = cast(Worksheet, wb.active)
    ws.title = sheet_title[:31]  # Excel 工作表名稱上限 31 字
    ws.append(list(headers))
    widths = [_display_width(h) for h in headers]
    for row in rows:
        ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in row])
        for i, value in enumerate(row[: len(widths)]):
            widths[i] = max(widths[i], _display_width(value))

    for cell in ws[1]:
        cell.font, cell.fill, cell.border = _HEADER_FONT, _HEADER_FILL, _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for data_row in ws.iter_rows(min_row=2):
        for cell in data_row:
            cell.border = _BORDER
            if isinstance(cell.value, str) and cell.value.startswith(_FORMULA_PREFIXES):
                cell.data_type = "s"
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    final_widths = column_widths or [min(w + 2, _MAX_COL_WIDTH) for w in widths]
    for i, width in enumerate(final_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@cache
def cjk_font() -> str:
    """註冊中文字型,回傳字型名稱。

    嵌入 TrueType 字型(Dockerfile 安裝 fonts-arphic-uming):不嵌入的 CID 字型靠閱讀器替代,
    Chrome 等閱讀器缺繁體字時整個字會空白。reportlab 不支援 CFF 外框的 OTF/TTC(例如 Noto Sans CJK)。
    找不到字型檔(macOS 本機開發)時退回不嵌入的 MSung-Light。
    """
    path = Path(config.pdf_font_path)
    if path.exists():
        pdfmetrics.registerFont(TTFont("CJK", str(path), subfontIndex=config.pdf_font_subfont_index))
        return "CJK"
    logger.warning(f"[Export] PDF font not found, falling back to non-embedded CID font - path: {path}")
    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def build_pdf_table(
    title: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[Cell]],
    *,
    col_widths: Sequence[float] | None = None,
    landscape_mode: bool = False,
) -> bytes:
    """一個標題 + 一張表格(跨頁自動重複表頭)。客製版面請直接用 reportlab 的 canvas,字型用 cjk_font()。"""
    font = cjk_font()
    pagesize = landscape(A4) if landscape_mode else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=pagesize, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm
    )
    cell_style = ParagraphStyle("cell", fontName=font, fontSize=9, leading=12, wordWrap="CJK")
    title_style = ParagraphStyle("title", fontName=font, fontSize=16, leading=20, spaceAfter=6)

    def para(value: Cell) -> Paragraph:
        text = "" if value is None else str(value)
        # Paragraph 吃簡易 XML:跳脫 &<> 才不會被當成標籤
        return Paragraph(escape(text), cell_style)

    data: list[list[Any]] = [[para(h) for h in headers], *([para(v) for v in row] for row in rows)]
    table = Table(data, colWidths=list(col_widths) if col_widths else None, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFBFBF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    doc.build([Paragraph(escape(title), title_style), Spacer(1, 4 * mm), table])
    return buf.getvalue()


def build_zip(files: dict[str, bytes]) -> bytes:
    """多檔打包。中文檔名 zipfile 會自動設 UTF-8 旗標,Windows 檔案總管與 macOS 都讀得到。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def content_disposition(filename: str, *, inline: bool = False) -> str:
    """RFC 6266 + RFC 5987:filename 給舊瀏覽器 ASCII 備援,filename* 給 UTF-8 原檔名(中文)。"""
    disposition = "inline" if inline else "attachment"
    fallback = "".join(ch if ch.isascii() and ch.isprintable() and ch not in '"\\;' else "_" for ch in filename)
    return f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def file_response(data: bytes, filename: str, media_type: str, *, inline: bool = False) -> StreamingResponse:
    """下載回應。CORS 已 expose Content-Disposition,跨網域前端讀得到檔名。"""
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={
            "Content-Disposition": content_disposition(filename, inline=inline),
            "Content-Length": str(len(data)),
            "Cache-Control": "no-store",  # 匯出內容常含個資,不讓瀏覽器或 proxy 快取
        },
    )


def table_export_response(
    fmt: ExportFormat, title: str, headers: Sequence[str], rows: Sequence[Sequence[Cell]], basename: str
) -> StreamingResponse:
    """同一份表格資料依格式回 xlsx / pdf / zip(兩者打包)的下載回應。basename 不含副檔名,可以是中文。"""
    if fmt == ExportFormat.XLSX:
        return file_response(build_xlsx(headers, rows, sheet_title=title), f"{basename}.xlsx", XLSX)
    if fmt == ExportFormat.PDF:
        return file_response(build_pdf_table(title, headers, rows), f"{basename}.pdf", PDF)
    archive = build_zip(
        {
            f"{basename}.xlsx": build_xlsx(headers, rows, sheet_title=title),
            f"{basename}.pdf": build_pdf_table(title, headers, rows),
        }
    )
    return file_response(archive, f"{basename}.zip", ZIP)
