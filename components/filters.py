"""
通用筛选控件组件。

只提供与具体业务字段无关的通用筛选控件（如时间范围选择、重置按钮），
不包含任何读取数据库的筛选逻辑。文案通过 config.i18n.t() 翻译。
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from config.i18n import t

# 时间范围选项的 i18n key，与显示文案分离，便于在双语下保持选项顺序一致。
_TIME_RANGE_KEYS: tuple[str, ...] = ("analytics.time_range.7d", "analytics.time_range.30d", "analytics.time_range.all")


def render_time_range_selector(key: str, default_index: int = 0) -> str:
    """渲染时间范围单选控件，返回选中的选项文案（当前语言下的显示文案）。"""
    options = [t(k) for k in _TIME_RANGE_KEYS]
    return st.radio(
        t("analytics.time_range_label"),
        options=options,
        index=default_index,
        horizontal=True,
        key=key,
    )


def time_range_to_dates(option: str, today: date | None = None) -> tuple[date | None, date | None]:
    """将时间范围选项转换为 (起始日期, 结束日期)。

    通过比较当前语言下 "近 7 天"/"近 30 天" 对应的翻译文案来判断，
    兼容中英文两种显示文案。"全部" 返回 (None, None)。
    """
    today = today or date.today()
    if option in (t("analytics.time_range.7d"), "近 7 天"):
        return today - timedelta(days=6), today
    if option in (t("analytics.time_range.30d"), "近 30 天"):
        return today - timedelta(days=29), today
    return None, None


def render_reset_button(label: str | None = None, key: str | None = None) -> bool:
    """渲染"重置筛选"按钮，返回本次是否被点击。"""
    return st.button(label or t("common.reset_filter"), key=key)
