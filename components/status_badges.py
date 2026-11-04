"""
状态徽章与颜色语义组件。

颜色语义约定（固定不随主题变化，需求文档 §4.3 第 6 条）：
    高风险/逾期/异常 → 错误色（红）
    处理中/运输中    → 强调色（蓝）
    完成/正常/已解决 → 成功色（绿）
    待处理/待发货    → 警告色（橙）
    已取消/已关闭/误报 → 中性灰

本模块只提供"状态文案 → 颜色/样式"的映射与渲染函数，不包含任何状态流转的
业务判断逻辑。状态文案通过 config.i18n.t() 翻译为当前语言，但颜色映射的
key 始终使用中文枚举值（与数据库存储的原始值一致），不受显示语言影响。
"""

from __future__ import annotations

import streamlit as st

from config.i18n import t
from config.theme import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING

# --- 枚举值（原文摘录，用于校验传入值合法性，避免页面出现枚举外的状态文案） ---

ORDER_STATUSES: tuple[str, ...] = ("待确认", "待发货", "运输中", "已签收", "已取消")
LOGISTICS_STATUSES: tuple[str, ...] = ("待揽收", "运输中", "派送中", "已签收", "异常")
ANOMALY_STATUSES: tuple[str, ...] = ("待确认", "处理中", "已解决", "已关闭", "误报")
TASK_STATUSES: tuple[str, ...] = ("待处理", "处理中", "已完成", "已取消")
RISK_LEVELS: tuple[str, ...] = ("高", "中", "低")
PRIORITIES: tuple[str, ...] = ("P1", "P2", "P3")

# --- 颜色语义映射：基于主题固定语义色（config/theme.py），不随主题预设变化 ---

_COLOR_BLUE = ("#1a56db", "#e8f0fe")  # 强调色沿用蓝色系，语义为"进行中"
_COLOR_GRAY = ("#5b6472", "#eef0f3")


def _tint(hex_color: str) -> str:
    """为语义色生成浅色背景（简单透明度叠加，避免引入颜色处理依赖）。"""
    _BG_MAP = {
        COLOR_SUCCESS: "#e6f4ea",
        COLOR_WARNING: "#fef3e2",
        COLOR_ERROR: "#fdecea",
    }
    return _BG_MAP.get(hex_color, "#eef0f3")


_COLOR_SUCCESS_PAIR = (COLOR_SUCCESS, _tint(COLOR_SUCCESS))
_COLOR_WARNING_PAIR = (COLOR_WARNING, _tint(COLOR_WARNING))
_COLOR_ERROR_PAIR = (COLOR_ERROR, _tint(COLOR_ERROR))

_STATUS_COLOR_MAP: dict[str, tuple[str, str]] = {
    # 订单状态
    "待确认": _COLOR_WARNING_PAIR,
    "待发货": _COLOR_WARNING_PAIR,
    "运输中": _COLOR_BLUE,
    "已签收": _COLOR_SUCCESS_PAIR,
    "已取消": _COLOR_GRAY,
    # 物流状态
    "待揽收": _COLOR_WARNING_PAIR,
    "派送中": _COLOR_BLUE,
    "异常": _COLOR_ERROR_PAIR,
    # 异常状态
    "处理中": _COLOR_BLUE,
    "已解决": _COLOR_SUCCESS_PAIR,
    "已关闭": _COLOR_GRAY,
    "误报": _COLOR_GRAY,
    # 任务状态
    "待处理": _COLOR_WARNING_PAIR,
    "已完成": _COLOR_SUCCESS_PAIR,
}

_RISK_COLOR_MAP: dict[str, tuple[str, str]] = {
    "高": _COLOR_ERROR_PAIR,
    "中": _COLOR_WARNING_PAIR,
    "低": _COLOR_SUCCESS_PAIR,
}

_PRIORITY_COLOR_MAP: dict[str, tuple[str, str]] = {
    "P1": _COLOR_ERROR_PAIR,
    "P2": _COLOR_WARNING_PAIR,
    "P3": _COLOR_GRAY,
}


def _render_badge(label: str, text_color: str, bg_color: str) -> None:
    st.markdown(
        f"""
        <span style="
            display: inline-block;
            padding: 0.15rem 0.6rem;
            border-radius: 999px;
            font-size: 0.8em;
            font-weight: 500;
            color: {text_color};
            background-color: {bg_color};
            white-space: nowrap;
        ">{label}</span>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(status: str) -> None:
    """渲染订单/物流/异常/任务状态徽章，按统一颜色语义着色。

    传入的 status 使用数据库原始中文枚举值；显示文案通过 t() 翻译为
    当前语言，颜色映射始终以原始中文值为 key。
    """
    text_color, bg_color = _STATUS_COLOR_MAP.get(status, _COLOR_GRAY)
    _render_badge(t(f"status.{status}"), text_color, bg_color)


def render_risk_badge(risk_level: str) -> None:
    """渲染风险等级徽章（高/中/低）。"""
    text_color, bg_color = _RISK_COLOR_MAP.get(risk_level, _COLOR_GRAY)
    _render_badge(t(f"risk.{risk_level}"), text_color, bg_color)


def render_priority_badge(priority: str) -> None:
    """渲染任务优先级徽章（P1/P2/P3，跨语言通用，不需要翻译）。"""
    text_color, bg_color = _PRIORITY_COLOR_MAP.get(priority, _COLOR_GRAY)
    _render_badge(priority, text_color, bg_color)
