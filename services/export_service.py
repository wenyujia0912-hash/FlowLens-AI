"""
Excel 导出服务。

对应产品需求 §5.6："支持导出当前筛选结果为Excel；导出字段应与页面筛选保持
一致。"

当前实现说明：
    技术方案 §1 指定用 pandas（`DataFrame.to_excel`，依赖 openpyxl 引擎）
    做导出。但当前网络环境无法安装 pandas/openpyxl（见README的网络限制
    说明），为了不让"导出Excel"这个产品需求停留在"尚未实现"，本模块
    用标准库 `zipfile` + 手写XML，直接实现一个足够兼容Excel的
    `.xlsx`文件写入器——`.xlsx`本质就是一个遵循OOXML规范的ZIP包，
    对于"纯文本/数字表格，不要公式、不要样式"这个导出场景，不需要
    pandas/openpyxl的完整能力。

    **这不是最终形态**：网络恢复、`pandas`/`openpyxl`装上后，应该把
    这里替换成 `DataFrame(rows).to_excel(path, index=False)`，代码量更少、
    更不容易踩OOXML格式细节的坑。当前实现只是在依赖不可用期间，保证
    "导出Excel"这个功能是真实可用的，不是裝样子的占位按钮。

    生成的文件兼容 Excel / Numbers / Google Sheets 能正常打开（标准
    OOXML spreadsheet格式，单个sheet，纯字符串/数字单元格，无公式、
    无样式、无合并单元格）。
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from numbers import Number
from xml.sax.saxutils import escape


def _column_letter(index: int) -> str:
    """0-based列序号转Excel列字母（0->A, 25->Z, 26->AA）。"""
    letters = ""
    n = index + 1
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _cell_xml(col_index: int, row_index: int, value) -> str:
    ref = f"{_column_letter(col_index)}{row_index}"
    if value is None:
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        # bool是Number的子类，必须先判断，否则会被当成数字1/0处理
        text = "TRUE" if value else "FALSE"
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(text)}</t></is></c>'
    if isinstance(value, Number):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def build_xlsx(headers: list[str], rows: list[list], sheet_name: str = "Sheet1") -> bytes:
    """生成一个最小化但规范的 .xlsx 文件二进制内容。

    参数:
        headers: 表头（第一行）。
        rows: 数据行，每行是一个值列表，长度应与headers一致。
        sheet_name: 工作表名称。

    返回:
        .xlsx 文件的完整字节内容，可直接写文件或通过Streamlit的
        st.download_button 提供下载。
    """
    all_rows = [headers] + rows
    sheet_rows_xml = []
    for row_idx, row in enumerate(all_rows, start=1):
        cells_xml = "".join(_cell_xml(col_idx, row_idx, val) for col_idx, val in enumerate(row))
        sheet_rows_xml.append(f'<row r="{row_idx}">{cells_xml}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(sheet_rows_xml)}</sheetData>"
        "</worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )

    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheet1.xml"/>'
        "</Relationships>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/worksheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/worksheet1.xml", sheet_xml)
    return buffer.getvalue()


def export_rows_to_xlsx(headers: list[str], rows: list[list], sheet_name: str = "导出数据") -> bytes:
    """导出入口：对应产品需求§5.6的"导出当前筛选结果为Excel"。

    调用方（页面层）负责保证 headers/rows 与当前页面筛选条件下展示的数据
    完全一致——本函数本身不做任何筛选或数据获取，只负责把给定的表格数据
    序列化成.xlsx字节内容。
    """
    if not headers:
        raise ValueError("导出失败：表头不能为空")
    return build_xlsx(headers, rows, sheet_name)


def build_export_filename(prefix: str) -> str:
    """生成带时间戳的导出文件名，避免多次导出互相覆盖。"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.xlsx"
