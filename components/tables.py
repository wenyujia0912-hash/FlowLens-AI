"""
统一的数据表格组件。

使用 st.markdown 输出原生 HTML 表格（而不是 st.dataframe），原因：
    - 业务列表需要在单元格内嵌"浅色底 + 低饱和文字"的状态标签，
      st.dataframe 是 canvas 渲染，无法混入 HTML 标签；
    - 需要与设计系统的表头/行高/分隔线完全一致，避免 canvas 表格与页面
      其余部分出现两套视觉语言。

样式全部来自 config/theme.py 的 --fl-* 变量（.fl-table），本模块只负责
结构生成与转义，不定义任何颜色，也不读取数据库。

安全约定：所有单元格内容默认按纯文本转义；只有调用方显式传入
Cell(html=...) 时才按 HTML 原样输出（仅供已经由本模块生成的状态标签使用）。
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class Cell:
    """表格单元格。

    text:  纯文本内容（会被转义）；
    html:  已生成好的安全 HTML（如状态标签），优先于 text；
    align: "left" | "right" | "center"，用于数字列右对齐。
    """

    text: str = ""
    html: str | None = None
    align: str = "left"

    @classmethod
    def of(cls, value, align: str = "left") -> "Cell":
        return cls(text="" if value is None else str(value), align=align)

    @classmethod
    def markup(cls, markup: str, align: str = "left") -> "Cell":
        return cls(html=markup, align=align)


# 表格纵向/横向可读性：列宽按内容自适应，长文本列允许换行。
_CSS = """
<style>
    .fl-table-wrap {
        width: 100%;
        overflow-x: auto;
        border-top: 1px solid var(--fl-border);
    }
    .fl-table {
        width: 100%;
        border-collapse: collapse;
        font-family: var(--fl-font);
        font-size: var(--fl-fs-table);
        font-variant-numeric: tabular-nums;
    }
    .fl-table thead th {
        position: sticky;
        top: 0;
        background: var(--fl-bg);
        color: var(--fl-text-secondary);
        font-size: var(--fl-fs-caption);
        font-weight: 500;
        text-align: left;
        white-space: nowrap;
        padding: 8px 14px 8px 0;
        border-bottom: 1px solid var(--fl-border);
    }
    .fl-table thead th:last-child { padding-right: 0; }
    .fl-table tbody td {
        padding: 10px 14px 10px 0;
        border-bottom: 1px solid var(--fl-border);
        color: var(--fl-text);
        vertical-align: middle;
        line-height: 1.45;
    }
    .fl-table tbody td:last-child { padding-right: 0; }
    .fl-table tbody tr:last-child td { border-bottom: none; }
    .fl-table tbody tr:hover { background: var(--fl-hover); }
    .fl-table .is-right { text-align: right; }
    .fl-table .is-center { text-align: center; }
    .fl-table .is-muted { color: var(--fl-text-secondary); }
    .fl-table .is-strong { font-weight: 500; }
    .fl-table .is-nowrap { white-space: nowrap; }
    .fl-table--empty { color: var(--fl-text-muted); }
</style>
"""


def _align_class(align: str) -> str:
    return {"right": " is-right", "center": " is-center"}.get(align, "")


def render_table(
    headers: list[str],
    rows: list[list[Cell | str]],
    *,
    empty_key: str | None = None,
    numeric_columns: tuple[int, ...] = (),
) -> None:
    """渲染一张统一风格的表格。

    参数:
        headers: 表头文案（已翻译），数量应与每行单元格数一致。
        rows: 每行的单元格列表，元素可为 Cell 或普通字符串（字符串自动转义）。
        empty_key: 无数据时的 i18n key；为空时渲染占位行而不是空表格。
        numeric_columns: 需要右对齐的列索引（通常是金额/数量）。
    """
    if empty_key is not None and not rows:
        from components.layout import render_empty_state

        render_empty_state(empty_key)
        return

    head_cells = "".join(
        f'<th class="{_align_class("right" if i in numeric_columns else "left").strip()}">'
        f"{html.escape(str(h))}</th>"
        for i, h in enumerate(headers)
    )

    body_rows = []
    for row in rows:
        cells = []
        for i, raw in enumerate(row):
            cell = raw if isinstance(raw, Cell) else Cell.of(raw)
            align = cell.align
            if i in numeric_columns and align == "left":
                align = "right"
            css = _align_class(align)
            content = cell.html if cell.html is not None else html.escape(cell.text)
            cells.append(f'<td class="{css.strip()}">{content}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="fl-table-wrap"><table class="fl-table">'
        f"<thead><tr>{head_cells}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>",
        unsafe_allow_html=True,
    )
