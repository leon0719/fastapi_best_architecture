"""匯出:xlsx 標題列樣式與公式注入防護、中文 PDF、ZIP、RFC 5987 檔名。"""

import io
import zipfile

import pytest
from openpyxl import load_workbook

from app.common.exports import build_pdf_table, build_xlsx, build_zip, content_disposition

pytestmark = pytest.mark.unit


def test_xlsx_header_style_width_and_freeze():
    data = build_xlsx(["名稱", "金額"], [["很長的中文名稱很長的中文名稱", 120]], sheet_title="明細")

    ws = load_workbook(io.BytesIO(data)).active
    assert ws.title == "明細"
    assert ws["A1"].font.bold
    assert ws.freeze_panes == "A2"
    assert ws.column_dimensions["A"].width > ws.column_dimensions["B"].width  # 中文字算兩格寬
    assert ws["B2"].value == 120


def test_xlsx_does_not_turn_user_input_into_formula():
    data = build_xlsx(["x"], [['=HYPERLINK("http://evil","click")'], ["bad\x07char"]])

    ws = load_workbook(io.BytesIO(data)).active
    assert ws["A2"].data_type == "s"
    assert ws["A3"].value == "badchar"


def test_pdf_with_chinese_text():
    data = build_pdf_table("報表 <測試> & 標題", ["名稱"], [["中文內容"]])

    assert data.startswith(b"%PDF-")


def test_zip_keeps_chinese_filenames():
    archive = zipfile.ZipFile(io.BytesIO(build_zip({"報表.xlsx": b"1", "明細.pdf": b"2"})))

    assert sorted(archive.namelist()) == ["報表.xlsx", "明細.pdf"]


def test_content_disposition_rfc5987():
    header = content_disposition('報表 "1".xlsx')

    assert header == "attachment; filename=\"__ _1_.xlsx\"; filename*=UTF-8''%E5%A0%B1%E8%A1%A8%20%221%22.xlsx"
    assert content_disposition("a.pdf", inline=True).startswith("inline;")
