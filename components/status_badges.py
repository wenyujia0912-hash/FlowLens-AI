"""
状态徽章与颜色语义组件。

颜色语义约定（固定不随主题变化，需求文档 §4.3 第 6 条）：
    高风险/逾期/异常 → 错误色
    处理中/运输中    → 主色（进行中）
    完成/正常/已解决 → 成功色
    待处理/待发货    → 警告色
    已取消/已关闭/误报 → 中性灰

视觉约定（重设计 §2 "状态标签采用浅色背景和低饱和度文字"）：
    标签一律为"浅色底 + 同色系深文字"，无边框、无阴影、无彩色实心块，
    具体色值全部来自 config/theme.py 的 CSS 变量（.fl-badge-*），
    本模块只负责"状态文案 → 语义类名"的映射，不硬编码颜色。

本模块不包含任何状态流转的业务判断逻辑。状态文案通过 config.i18n.t()
翻译为当前语言，但映射 key 始终使用数据库存储的原始中文枚举值。
"""

from __future__ import annotations

import html

import streamlit as st

from config.i18n import t

# --- 枚举值（用于校验传入值合法性，避免页面出现枚举外的状态文案） ---

ORDER_STATUSES: tuple[str, ...] = ("待确认", "待发货", "运输中", "已签收", "已取消")
LOGISTICS_STATUSES: tuple[str, ...] = ("待揽收", "运输中", "派送中", "已签收", "异常")
ANOMALY_STATUSES: tuple[str, ...] = ("待确认", "处理中", "已解决", "已关闭", "误报")
TASK_STATUSES: tuple[str, ...] = ("待处理", "处理中", "已完成", "已取消")
RISK_LEVELS: tuple[str, ...] = ("高", "中", "低")
PRIORITIES: tuple[str, ...] = ("P1", "P2", "P3")

# --- 语义类名 ---

_NEUTRAL = "fl-badge-neutral"
_SUCCESS = "fl-badge-success"
_WARNING = "fl-badge-warning"
_ERROR = "fl-badge-error"
_PRIMARY = "fl-badge-primary"

_STATUS_CLASS_MAP: dict[str, str] = {
    # 订单状态
    "待确认": _WARNING,
    "待发货": _WARNING,
    "运输中": _PRIMARY,
    "已签收": _SUCCESS,
    "已取消": _NEUTRAL,
    # 物流状态
    "待揽收": _WARNING,
    "派送中": _PRIMARY,
    "异常": _ERROR,
    # 异常状态
    "处理中": _PRIMARY,
    "已解决": _SUCCESS,
    "已关闭": _NEUTRAL,
    "误报": _NEUTRAL,
    # 任务状态
    "待处理": _WARNING,
    "已完成": _SUCCESS,
}

_RISK_CLASS_MAP: dict[str, str] = {"高": _ERROR, "中": _WARNING, "低": _SUCCESS}

_PRIORITY_CLASS_MAP: dict[str, str] = {"P1": _ERROR, "P2": _WARNING, "P3": _NEUTRAL}


def badge_html(label: str, css_class: str) -> str:
    """返回一段状态标签 HTML（供表格单元格等需要行内内嵌的场景复用）。"""
    return f'<span class="fl-badge {css_class}">{html.escape(label)}</span>'


def render_badge(label: str, css_class: str) -> None:
    st.markdown(badge_html(label, css_class), unsafe_allow_html=True)


def render_status_badge(status: str) -> None:
    """渲染订单/物流/异常/任务状态标签，按统一颜色语义着色。

    传入的 status 使用数据库原始中文枚举值；显示文案通过 t() 翻译为
    当前语言，颜色映射始终以原始中文值为 key。
    """
    render_badge(t(f"status.{status}"), _STATUS_CLASS_MAP.get(status, _NEUTRAL))


def render_risk_badge(risk_level: str) -> None:
    """渲染风险等级标签（高/中/低）。"""
    render_badge(t(f"risk.{risk_level}"), _RISK_CLASS_MAP.get(risk_level, _NEUTRAL))


def render_priority_badge(priority: str) -> None:
    """渲染任务优先级标签（P1/P2/P3，跨语言通用，不需要翻译）。"""
    render_badge(priority, _PRIORITY_CLASS_MAP.get(priority, _NEUTRAL))


def status_badge_html(status: str) -> str:
    """状态标签的 HTML 形式（用于 st.markdown 的表格内嵌）。"""
    return badge_html(t(f"status.{status}"), _STATUS_CLASS_MAP.get(status, _NEUTRAL))


def risk_badge_html(risk_level: str) -> str:
    return badge_html(t(f"risk.{risk_level}"), _RISK_CLASS_MAP.get(risk_level, _NEUTRAL))


def priority_badge_html(priority: str) -> str:
    return badge_html(priority, _PRIORITY_CLASS_MAP.get(priority, _NEUTRAL))
