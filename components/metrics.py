"""
KPI 指标卡片组件。

阶段 1 范围：
    提供通用的"指标卡片"渲染函数，接受外部传入的数值和标签——不读取
    数据库，不计算任何业务指标。真实的订单总量/异常订单数/履约率等
    统计口径将在阶段 3（统计查询服务）和阶段 7（指标口径确认，对应
    阶段 0 产出的 H1 歧义问题）实现后，由 pages/01_dashboard.py 调用
    service 层获得数值，再传入本组件渲染。
"""

from __future__ import annotations

import streamlit as st


def render_kpi_row(items: list[dict]) -> None:
    """渲染一行 KPI 卡片。

    参数:
        items: 每个元素形如
            {"label": "订单总量", "value": "—", "help": "可选说明文字"}
            阶段 1 阶段性调用时 value 统一传入占位符 "—"，不得传入编造的
            具体数字，避免被误认为真实统计结果。
    """
    columns = st.columns(len(items)) if items else []
    for col, item in zip(columns, items):
        with col:
            st.metric(
                label=item.get("label", ""),
                value=item.get("value", "—"),
                help=item.get("help"),
            )
