"""
KPI 指标组件。

视觉规范（重设计 §5.2 "KPI 指标"）：
    - 不使用卡片、彩色背景、阴影或图标；
    - 指标之间只用一条极浅的上边线分隔；
    - 指标名称用灰色小字，数字突出显示，辅助变化信息放在数字下方；
    - 通过字号与字重建立层级，而不是通过颜色。

本模块不读取数据库、不计算业务指标：数值由页面从 service 层取得后传入。
"""

from __future__ import annotations

import html

import streamlit as st


def render_kpi(label: str, value: str, meta: str | None = None, *, help: str | None = None) -> None:
    """渲染一个不可点击的 KPI 指标。"""
    from components.layout import render_kpi_stat

    render_kpi_stat(label=label, value=value, meta=meta, help=help)


def render_kpi_row(items: list[dict]) -> None:
    """渲染一行不可点击的 KPI 指标。

    参数:
        items: 每个元素形如 {"label": ..., "value": ..., "meta": 可选, "help": 可选}
    """
    if not items:
        return
    columns = st.columns(len(items))
    for col, item in zip(columns, items):
        with col:
            render_kpi(
                label=item.get("label", ""),
                value=item.get("value", "—"),
                meta=item.get("meta"),
                help=item.get("help"),
            )


def render_clickable_kpi_row(items: list[dict], on_click) -> None:
    """渲染一行"可点击跳转"的 KPI（保留驾驶舱点击带入筛选的能力）。

    可点击指标用透明按钮实现：去掉了按钮外观，只保留"标签 + 大号数字"，
    悬停时数字变为主色以提示可点击。点击回调接收该指标的 dict。

    参数:
        items: 每个元素形如 {"label": ..., "value": ..., "meta": 可选,
                            "clickable": 可选 bool（默认 True）}
        on_click: 回调，签名为 on_click(item: dict)。
    """
    if not items:
        return
    columns = st.columns(len(items))
    for col, item in zip(columns, items):
        with col:
            if item.get("clickable", True):
                # 两段式 Markdown（标签段 + 数值段）会渲染成两个 <p>，设计系统据此
                # 把按钮还原成"灰色小标签 + 突出数字"的 KPI 外观（见 --fl-kpi）。
                # 不能用 "# 数值"：按钮标签不支持标题语法，会被拆成纯文本。
                label = str(item.get("label", ""))
                value = str(item.get("value", "—"))
                if st.button(
                    f"{label}\n\n**{value}**",
                    key=item.get("key") or f"kpi_{abs(hash(label))}",
                    help=item.get("help"),
                    use_container_width=True,
                ):
                    on_click(item)
            else:
                render_kpi(
                    label=item.get("label", ""),
                    value=item.get("value", "—"),
                    meta=item.get("meta"),
                    help=item.get("help"),
                )
