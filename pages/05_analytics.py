"""
运营分析与复盘（Operations Analytics）。

页面结构：统一时间筛选 + 履约/异常/任务三个主题分区。每个图表都提供
"查看明细"和"导出当前筛选结果为Excel"。

指标口径说明（服务层已实现的默认假设，详见
services/analytics_service.py 顶部文档字符串）：
    - 履约完成率：已签收且按时的订单 / 已到预计送达时间的有效订单
    - 平均履约时长：发货到签收的平均时间（不是下单到签收）
    - 延迟订单占比：命中DELIVERY_OVERDUE规则的订单 / 已签收订单总数
    - 逾期任务：due_at已过且状态非已完成/已取消

导出实现：services/export_service.py 生成真实可用的 .xlsx。

文案全部通过 config.i18n.t() 翻译。
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
from config.i18n import t
from config.settings import get_config
from database.connection import get_connection
from services import analytics_service, export_service

inject_base_styles()

render_page_header(title_key="analytics.title", subtitle_key="analytics.subtitle")

config = get_config()

if not guard_database_initialized():
    st.stop()

# 统一时间筛选。当前各统计口径本身不依赖"统计区间"做窗口筛选——
# 例如履约完成率看的是"已到预计送达时间的全部有效订单"，不是"某时间段内
# 下单的订单"。这里提供的时间筛选主要影响"订单量趋势"等按日期分布的图表。
_TIME_RANGE_OPTIONS = ["近7天", "近30天", "全部"]
_TIME_RANGE_KEY_MAP = {"近7天": "analytics.time_range.7d", "近30天": "analytics.time_range.30d", "全部": "analytics.time_range.all"}

time_range = st.selectbox(
    t("analytics.time_range_label"), _TIME_RANGE_OPTIONS,
    index=2,
    format_func=lambda v: t(_TIME_RANGE_KEY_MAP[v]),
    key="analytics_time_range",
)
days_map = {"近7天": 7, "近30天": 30, "全部": 9999}
trend_days = days_map[time_range]

try:
    with get_connection(config.database_path) as conn:
        now = datetime.now()
        fulfillment = analytics_service.get_fulfillment_analytics(conn, now)
        anomaly_stats = analytics_service.get_anomaly_analytics(conn)
        customer_anomaly = analytics_service.get_customer_anomaly_analytics(conn, top_n=10)
        task_stats = analytics_service.get_task_analytics(conn, now)
        trend = analytics_service.get_order_trend(conn, days=min(trend_days, 365))
except sqlite3.Error as exc:
    st.error(f"{t('common.loading_failed')}：{exc}")
    st.stop()

tab_fulfillment, tab_anomaly, tab_task = st.tabs([t("analytics.tab.fulfillment"), t("analytics.tab.anomaly"), t("analytics.tab.task")])


# ======================================================================
# 履约分析
# ======================================================================

with tab_fulfillment:
    st.caption(t("analytics.fulfillment.caption"))

    metric_cols = st.columns(3)
    rate_display = f"{fulfillment['fulfillment_rate']}%" if fulfillment["fulfillment_rate"] is not None else t("common.not_available")
    metric_cols[0].metric(t("analytics.fulfillment_rate"), rate_display)

    hours_display = (
        f"{fulfillment['avg_fulfillment_hours']:.1f} {t('analytics.hours_suffix')}"
        if fulfillment["avg_fulfillment_hours"] is not None
        else t("common.not_available")
    )
    metric_cols[1].metric(
        t("analytics.avg_fulfillment_hours"), hours_display,
        help=t("analytics.avg_fulfillment_hours_help", count=fulfillment["sample_size"]["avg_fulfillment_hours_sample"]),
    )

    delay_display = (
        f"{fulfillment['delayed_order_ratio']}%" if fulfillment["delayed_order_ratio"] is not None else t("common.not_available")
    )
    metric_cols[2].metric(
        t("analytics.delayed_order_ratio"), delay_display,
        help=t("analytics.delayed_order_ratio_help", count=fulfillment["sample_size"]["delivered_order_count"]),
    )

    if fulfillment["sample_size"]["delivered_order_count"] == 0:
        st.info(t("analytics.no_delivered_note"))

    st.divider()
    st.markdown(f"**{t('analytics.order_trend_title')}**")
    if not trend:
        render_empty_state("empty.no_trend_data")
    else:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[item["day"] for item in trend], y=[item["count"] for item in trend], mode="lines+markers"))
            fig.update_layout(
                height=260, margin=dict(l=20, r=20, t=20, b=20),
                xaxis_title=t("dashboard.chart.date_axis"), yaxis_title=t("dashboard.chart.order_count_axis"),
            )
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.warning(t("analytics.plotly_missing"))
            st.table(trend)

    with st.expander(t("analytics.delivered_detail_expander")):
        try:
            with get_connection(config.database_path) as conn:
                delivered_orders = conn.execute(
                    """SELECT order_id, customer_id, shipped_at, delivered_at, expected_delivery_at, amount
                       FROM orders WHERE status = '已签收' ORDER BY delivered_at DESC LIMIT 100"""
                ).fetchall()
            if not delivered_orders:
                render_empty_state("empty.no_delivered_orders")
            else:
                detail_rows = [
                    {
                        t("analytics.col.order_id"): r["order_id"], t("analytics.col.customer_id"): r["customer_id"],
                        t("analytics.col.shipped_at"): r["shipped_at"], t("analytics.col.delivered_at"): r["delivered_at"],
                        t("analytics.col.expected_delivery"): r["expected_delivery_at"], t("analytics.col.amount"): r["amount"],
                    }
                    for r in delivered_orders
                ]
                st.table(detail_rows)

                if st.button(t("analytics.export_fulfillment"), key="export_fulfillment"):
                    headers = [
                        t("analytics.col.order_id"), t("analytics.col.customer_id"), t("analytics.col.shipped_at"),
                        t("analytics.col.delivered_at"), t("analytics.col.expected_delivery"), t("analytics.col.amount"),
                    ]
                    rows = [
                        [r["order_id"], r["customer_id"], r["shipped_at"], r["delivered_at"], r["expected_delivery_at"], r["amount"]]
                        for r in delivered_orders
                    ]
                    try:
                        content = export_service.export_rows_to_xlsx(headers, rows, sheet_name=t("analytics.delivered_detail_expander")[:31])
                        st.download_button(
                            t("analytics.download_file"), data=content,
                            file_name=export_service.build_export_filename("fulfillment_detail"),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_fulfillment",
                        )
                    except ValueError as exc:
                        st.error(t("analytics.export_failed", error=exc))
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")


# ======================================================================
# 异常分析
# ======================================================================

with tab_anomaly:
    st.caption(t("analytics.anomaly_total_caption", count=anomaly_stats["total_count"]))

    dist_col, risk_col = st.columns(2)

    with dist_col:
        st.markdown(f"**{t('analytics.anomaly_type_dist_title')}**")
        if not anomaly_stats["type_distribution"]:
            render_empty_state("empty.no_anomaly_data")
        else:
            try:
                import plotly.graph_objects as go

                fig = go.Figure(
                    data=[go.Bar(
                        x=[d["anomaly_type"] for d in anomaly_stats["type_distribution"]],
                        y=[d["count"] for d in anomaly_stats["type_distribution"]],
                    )]
                )
                fig.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.table(anomaly_stats["type_distribution"])

    with risk_col:
        st.markdown(f"**{t('analytics.risk_dist_title')}**")
        if not anomaly_stats["risk_distribution"]:
            render_empty_state("empty.no_risk_data")
        else:
            try:
                import plotly.graph_objects as go

                fig = go.Figure(
                    data=[go.Pie(
                        labels=[t(f"risk.{d['severity']}") for d in anomaly_stats["risk_distribution"]],
                        values=[d["count"] for d in anomaly_stats["risk_distribution"]],
                    )]
                )
                fig.update_layout(height=260, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.table(anomaly_stats["risk_distribution"])

    st.divider()
    st.markdown(f"**{t('analytics.top_customer_anomaly_title')}**")
    if not customer_anomaly:
        render_empty_state("empty.no_customer_anomaly_data")
    else:
        display_rows = [
            {
                t("analytics.col.customer_name"): c["name"], t("analytics.col.customer_tier"): c["tier"],
                t("analytics.col.anomaly_count"): c["anomaly_count"],
            }
            for c in customer_anomaly
        ]
        st.table(display_rows)

        if st.button(t("analytics.export_anomaly"), key="export_anomaly"):
            headers = [t("anomaly_center.anomaly_type"), t("analytics.col.anomaly_count")]
            rows = [[d["anomaly_type"], d["count"]] for d in anomaly_stats["type_distribution"]]
            try:
                content = export_service.export_rows_to_xlsx(headers, rows, sheet_name=t("analytics.anomaly_type_dist_title")[:31])
                st.download_button(
                    t("analytics.download_file"), data=content,
                    file_name=export_service.build_export_filename("anomaly_analysis"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_anomaly",
                )
            except ValueError as exc:
                st.error(t("analytics.export_failed", error=exc))


# ======================================================================
# 任务分析
# ======================================================================

with tab_task:
    st.caption(t("analytics.task_summary_caption"))

    task_cols = st.columns(4)
    task_cols[0].metric(t("analytics.total_tasks"), task_stats["total_tasks"])

    completion_display = f"{task_stats['completion_rate']}%" if task_stats["completion_rate"] is not None else t("common.not_available")
    task_cols[1].metric(t("analytics.completion_rate"), completion_display)

    avg_hours_display = (
        f"{task_stats['avg_processing_hours']:.1f} {t('analytics.hours_suffix')}"
        if task_stats["avg_processing_hours"] is not None else t("common.not_available")
    )
    task_cols[2].metric(
        t("analytics.avg_processing_hours"), avg_hours_display,
        help=t("analytics.avg_processing_hours_help", count=task_stats["sample_size"]["avg_processing_hours_sample"]),
    )

    task_cols[3].metric(t("analytics.overdue_count"), task_stats["overdue_count"])

    if task_stats["total_tasks"] == 0:
        st.info(t("analytics.no_tasks_note"))

    st.divider()
    with st.expander(t("analytics.task_detail_expander")):
        try:
            with get_connection(config.database_path) as conn:
                all_tasks = conn.execute(
                    "SELECT task_id, title, priority, assignee, status, due_at, completed_at FROM operation_tasks ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
            if not all_tasks:
                render_empty_state("empty.no_task_data")
            else:
                task_rows = [
                    {
                        t("analytics.col.task_id"): r["task_id"], t("analytics.col.task_title"): r["title"],
                        t("analytics.col.task_priority"): r["priority"], t("analytics.col.task_assignee"): r["assignee"],
                        t("analytics.col.task_status"): t(f"status.{r['status']}"), t("analytics.col.task_due"): r["due_at"],
                        t("analytics.col.task_completed"): r["completed_at"] or "—",
                    }
                    for r in all_tasks
                ]
                st.table(task_rows)

                if st.button(t("analytics.export_task"), key="export_task"):
                    headers = [
                        t("analytics.col.task_id"), t("analytics.col.task_title"), t("analytics.col.task_priority"),
                        t("analytics.col.task_assignee"), t("analytics.col.task_status"), t("analytics.col.task_due"),
                        t("analytics.col.task_completed"),
                    ]
                    rows = [
                        [r["task_id"], r["title"], r["priority"], r["assignee"], r["status"], r["due_at"], r["completed_at"] or ""]
                        for r in all_tasks
                    ]
                    try:
                        content = export_service.export_rows_to_xlsx(headers, rows, sheet_name=t("analytics.task_detail_expander")[:31])
                        st.download_button(
                            t("analytics.download_file"), data=content,
                            file_name=export_service.build_export_filename("task_detail"),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_task",
                        )
                    except ValueError as exc:
                        st.error(t("analytics.export_failed", error=exc))
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")

render_sidebar_footer()
