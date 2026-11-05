"""
运营总览（Operations Overview）。

阅读顺序（重设计 §6.01）：整体指标 → 运营趋势 → 风险与待办。
    - KPI 指标行：订单总量、异常订单数、待处理异常数、履约完成率、逾期任务数。
      可点击指标（保留原有能力）跳转到对应列表并带入筛选条件。
    - 运营趋势：近 7 天订单量折线图。
    - 异常分布 / 风险分布：以紧凑的列表行呈现，点击可带入筛选。
    - 待办任务：逾期或高优先级、未完成的任务。

数据来源：全部通过 services.analytics_service 从数据库实时查询，
不使用任何静态/编造数字；本次仅调整信息层级与视觉呈现，指标口径未变。

跳转机制：Streamlit 原生多页面之间无法直接传参，本项目使用
st.session_state 存储"待应用的筛选条件"，目标页面在渲染时读取并应用，
用后清除。

文案全部通过 config.i18n.t() 翻译，不在页面内硬编码任何语言的字面文案。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import streamlit as st

from components.layout import (
    guard_database_initialized,
    inject_base_styles,
    render_empty_state,
    render_page_header,
    render_section,
)
from components.metrics import render_clickable_kpi_row
from config.i18n import t
from config.settings import get_config
from config.theme import get_theme
from database.connection import get_connection
from services import analytics_service
from services.preferences_service import get_current_preferences

inject_base_styles()

render_page_header(title_key="dashboard.title", subtitle_key="dashboard.subtitle")


def _navigate_with_filter(target_page: str, filters: dict) -> None:
    """设置待应用的筛选条件并跳转到目标页面。"""
    st.session_state["pending_filter"] = filters
    st.switch_page(target_page)


# ------------------------------------------------------------------
# 数据库连接与错误处理
# ------------------------------------------------------------------

config = get_config()

if not guard_database_initialized():
    st.stop()

try:
    with get_connection(config.database_path) as conn:
        now = datetime.now()
        kpis = analytics_service.get_dashboard_kpis(conn, now)
        trend = analytics_service.get_order_trend(conn, days=7)
        anomaly_dist = analytics_service.get_anomaly_type_distribution(conn)
        risk_dist = analytics_service.get_risk_distribution(conn)

        # 待办区：取逾期或高优先级、未完成的任务，最多展示 8 条。
        from repositories import task_repository

        now_iso = now.strftime("%Y-%m-%dT%H:%M:%S")
        overdue_tasks = task_repository.list_overdue(conn, now_iso)
        high_priority_pending = task_repository.list_all(conn, priority="P1", status="待处理")
        todo_tasks = overdue_tasks + [t_ for t_ in high_priority_pending if t_ not in overdue_tasks]
        todo_tasks = todo_tasks[:8]

except sqlite3.Error as exc:
    st.error(f"{t('common.loading_failed')}：{exc}")
    st.stop()
except FileNotFoundError:
    st.error(t("empty.db_empty_hint"))
    st.stop()

# ------------------------------------------------------------------
# 空数据检查：如果订单总量为 0，说明还没有种子数据
# ------------------------------------------------------------------

if kpis["total_orders"] == 0:
    render_empty_state("empty.db_empty", hint_key="empty.db_empty_hint")
    st.stop()

_prefs = get_current_preferences()
_preset = get_theme(_prefs.theme)

# ------------------------------------------------------------------
# 一、KPI 指标行
# ------------------------------------------------------------------

rate_display = f"{kpis['fulfillment_rate']}%" if kpis["fulfillment_rate"] is not None else t("common.not_available")

_kpi_items = [
    {
        "key": "kpi_total_orders",
        "target": ("views/02_customers_orders.py", {"tab": "orders"}),
        "label": t("dashboard.kpi.total_orders"),
        "value": kpis["total_orders"],
    },
    {
        "key": "kpi_anomaly_orders",
        "target": ("views/03_anomaly_center.py", {}),
        "label": t("dashboard.kpi.anomaly_orders"),
        "value": kpis["anomaly_order_count"],
    },
    {
        "key": "kpi_pending_anomalies",
        "target": ("views/03_anomaly_center.py", {"status": "待确认"}),
        "label": t("dashboard.kpi.pending_anomalies"),
        "value": kpis["pending_anomaly_count"],
    },
    {
        "key": "kpi_fulfillment_rate",
        "label": t("dashboard.kpi.fulfillment_rate"),
        "value": rate_display,
        "meta": t("dashboard.kpi.fulfillment_rate_help"),
        "clickable": False,
    },
    {
        "key": "kpi_overdue_tasks",
        "target": ("views/04_task_center.py", {"overdue_only": True}),
        "label": t("dashboard.kpi.overdue_tasks"),
        "value": kpis["overdue_task_count"],
    },
]


def _on_kpi_click(item: dict) -> None:
    target_page, filters = item["target"]
    _navigate_with_filter(target_page, filters)


render_clickable_kpi_row(_kpi_items, _on_kpi_click)
st.caption(t("dashboard.kpi_hint"))

# ------------------------------------------------------------------
# 二、运营趋势
# ------------------------------------------------------------------

st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
render_section("dashboard.trend_title")

if not trend:
    render_empty_state("empty.no_trend_data")
else:
    try:
        from components.charts import line_chart, plotly_config

        fig = line_chart(
            [item["day"] for item in trend],
            [item["count"] for item in trend],
            primary=_preset.primary,
            x_title=t("dashboard.chart.date_axis"),
            y_title=t("dashboard.chart.order_count_axis"),
            height=240,
            font_size_key=_prefs.font_size,
        )
        st.plotly_chart(fig, use_container_width=True, config=plotly_config())
    except ImportError:
        st.warning(t("dashboard.plotly_missing"))
        st.table(trend)

# ------------------------------------------------------------------
# 三、异常分布 / 风险分布
# ------------------------------------------------------------------

st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
dist_col, risk_col = st.columns([1, 1], gap="large")

_SEVERITY_LABEL_KEYS = {"高": "dashboard.severity_high", "中": "dashboard.severity_medium", "低": "dashboard.severity_low"}


def _render_distribution(items: list[dict], label_key, table_key: str, target_page: str, filter_key: str) -> None:
    """以紧凑表格呈现分布数据（名称 / 数量），选中一行即带筛选跳转。

    表格是只读信息的最佳载体：对齐清晰、无边框、无彩色块，行悬停有轻微底色，
    与列表页保持同一视觉语言；点击行为与原来的"分布按钮"完全一致。
    """
    import pandas as pd

    df = pd.DataFrame(
        {
            t("anomaly_center.anomaly_type") if filter_key == "anomaly_type" else t("anomaly_center.risk_level"): [
                label_key(item) for item in items
            ],
            t("analytics.col.anomaly_count"): [item["count"] for item in items],
        }
    )
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
    )
    st.caption(t("dashboard.select_row_hint"))

    try:
        selected = st.session_state[table_key].selection.rows
    except (AttributeError, KeyError, TypeError):
        selected = []

    if selected and 0 <= selected[0] < len(items):
        _navigate_with_filter(target_page, {filter_key: items[selected[0]][filter_key]})


with dist_col:
    render_section("dashboard.anomaly_dist_title")
    if not anomaly_dist:
        render_empty_state("empty.no_anomaly_data")
    else:
        _render_distribution(
            anomaly_dist,
            lambda item: item["anomaly_type"],
            "dashboard_anomaly_dist",
            "views/03_anomaly_center.py",
            "anomaly_type",
        )

with risk_col:
    render_section("dashboard.risk_dist_title")
    if not risk_dist:
        render_empty_state("empty.no_risk_data")
    else:
        _render_distribution(
            risk_dist,
            lambda item: t(_SEVERITY_LABEL_KEYS.get(item["severity"], "dashboard.severity_low")),
            "dashboard_risk_dist",
            "views/03_anomaly_center.py",
            "severity",
        )

# ------------------------------------------------------------------
# 四、待办任务
# ------------------------------------------------------------------

st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
render_section("dashboard.todo_title")

if not todo_tasks:
    render_empty_state("empty.no_todo_tasks", hint_key="empty.no_todo_tasks_hint")
else:
    import pandas as pd

    todo_df = pd.DataFrame(
        {
            t("task_center.col.title"): [task.title for task in todo_tasks],
            t("task_center.col.priority"): [task.priority for task in todo_tasks],
            t("dashboard.assignee_label"): [task.assignee for task in todo_tasks],
            t("task_center.col.due"): [task.due_at[:10] for task in todo_tasks],
        }
    )
    st.dataframe(
        todo_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="dashboard_todo_tasks",
    )
    st.caption(t("dashboard.select_row_hint"))

    try:
        _selected_todo = st.session_state["dashboard_todo_tasks"].selection.rows
    except (AttributeError, KeyError, TypeError):
        _selected_todo = []

    if _selected_todo and 0 <= _selected_todo[0] < len(todo_tasks):
        _navigate_with_filter("views/04_task_center.py", {"task_id": todo_tasks[_selected_todo[0]].task_id})
