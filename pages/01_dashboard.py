"""
运营总览（Operations Overview）。

- KPI 卡片：订单总量、异常订单数、待处理异常数、履约完成率、逾期任务数
- 趋势图：按日展示订单量
- 异常分布：按类型统计
- 风险分布：按高/中/低统计
- 待办区：优先级较高或即将逾期的任务
- 点击统计项可跳转到对应列表并带入筛选条件

数据来源：全部通过 services.analytics_service 从数据库实时查询，
不使用任何静态/编造数字。

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
    inject_base_styles,
    render_page_header,
    render_sidebar_footer,
    render_empty_state,
    guard_database_initialized,
)
from components.status_badges import render_priority_badge
from config.i18n import t
from config.settings import get_config
from database.connection import get_connection
from services import analytics_service

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
    render_sidebar_footer()
    st.stop()

# ------------------------------------------------------------------
# KPI 卡片行
# ------------------------------------------------------------------

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    if st.button(f"📦 {t('dashboard.kpi.total_orders')}\n\n# {kpis['total_orders']}", use_container_width=True, key="kpi_total_orders"):
        _navigate_with_filter("pages/02_customers_orders.py", {"tab": "orders"})

with col2:
    if st.button(
        f"⚠️ {t('dashboard.kpi.anomaly_orders')}\n\n# {kpis['anomaly_order_count']}",
        use_container_width=True,
        key="kpi_anomaly_orders",
    ):
        _navigate_with_filter("pages/03_anomaly_center.py", {})

with col3:
    if st.button(
        f"🔍 {t('dashboard.kpi.pending_anomalies')}\n\n# {kpis['pending_anomaly_count']}",
        use_container_width=True,
        key="kpi_pending_anomalies",
    ):
        _navigate_with_filter("pages/03_anomaly_center.py", {"status": "待确认"})

with col4:
    rate_display = f"{kpis['fulfillment_rate']}%" if kpis["fulfillment_rate"] is not None else t("common.not_available")
    st.metric(f"✅ {t('dashboard.kpi.fulfillment_rate')}", rate_display, help=t("dashboard.kpi.fulfillment_rate_help"))

with col5:
    if st.button(
        f"⏰ {t('dashboard.kpi.overdue_tasks')}\n\n# {kpis['overdue_task_count']}",
        use_container_width=True,
        key="kpi_overdue_tasks",
    ):
        _navigate_with_filter("pages/04_task_center.py", {"overdue_only": True})

st.caption(t("dashboard.kpi_hint"))

st.divider()

# ------------------------------------------------------------------
# 趋势图 + 异常分布
# ------------------------------------------------------------------

trend_col, dist_col = st.columns([3, 2])

with trend_col:
    st.subheader(t("dashboard.trend_title"))
    if not trend:
        render_empty_state("empty.no_trend_data")
    else:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=[item["day"] for item in trend],
                    y=[item["count"] for item in trend],
                    mode="lines+markers",
                    name=t("dashboard.chart.order_count_series"),
                )
            )
            fig.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=280,
                xaxis_title=t("dashboard.chart.date_axis"),
                yaxis_title=t("dashboard.chart.order_count_axis"),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.warning(t("dashboard.plotly_missing"))
            st.table(trend)

with dist_col:
    st.subheader(t("dashboard.anomaly_dist_title"))
    if not anomaly_dist:
        render_empty_state("empty.no_anomaly_data")
    else:
        for item in anomaly_dist:
            label = item["anomaly_type"]
            count = item["count"]
            if st.button(f"{label}：{count} {t('dashboard.count_suffix')}", key=f"anomaly_type_{label}", use_container_width=True):
                _navigate_with_filter("pages/03_anomaly_center.py", {"anomaly_type": label})

st.divider()

# ------------------------------------------------------------------
# 风险分布 + 待办任务
# ------------------------------------------------------------------

risk_col, todo_col = st.columns([2, 3])

_SEVERITY_LABEL_KEYS = {"高": "dashboard.severity_high", "中": "dashboard.severity_medium", "低": "dashboard.severity_low"}

with risk_col:
    st.subheader(t("dashboard.risk_dist_title"))
    if not risk_dist:
        render_empty_state("empty.no_risk_data")
    else:
        for item in risk_dist:
            severity = item["severity"]
            count = item["count"]
            label = t(_SEVERITY_LABEL_KEYS.get(severity, "dashboard.severity_low"))
            if st.button(f"{label}：{count} {t('dashboard.count_suffix')}", key=f"risk_{severity}", use_container_width=True):
                _navigate_with_filter("pages/03_anomaly_center.py", {"severity": severity})

with todo_col:
    st.subheader(t("dashboard.todo_title"))
    if not todo_tasks:
        render_empty_state("empty.no_todo_tasks", hint_key="empty.no_todo_tasks_hint")
    else:
        for task in todo_tasks:
            cols = st.columns([1, 4, 2, 2])
            with cols[0]:
                render_priority_badge(task.priority)
            with cols[1]:
                st.write(task.title)
            with cols[2]:
                st.caption(f"{t('dashboard.assignee_label')}：{task.assignee}")
            with cols[3]:
                if st.button(t("dashboard.view_button"), key=f"todo_task_{task.task_id}"):
                    _navigate_with_filter("pages/04_task_center.py", {"task_id": task.task_id})

render_sidebar_footer()
