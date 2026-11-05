"""
运营分析与复盘（Operations Analytics）。

页面结构：统一时间筛选 + 履约/异常/任务三个主题分区。每个图表都提供
"查看明细"和"导出当前筛选结果为Excel"。

视觉（重设计 §6.05）：
    - 指标以 KPI 行呈现，图表卡片化程度降到最低（无边框、无背景色块）；
    - 图表统一使用 components/charts.py 的低饱和样式与留白；
    - 明细表格使用统一数据表格，导出按钮为轻量按钮。
    图表所展示的数据、指标口径与统计逻辑完全未改变。

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

import pandas as pd
import streamlit as st

from components.layout import (
    guard_database_initialized,
    inject_base_styles,
    render_empty_state,
    render_kpi_stat,
    render_page_header,
    render_section,
)
from config.i18n import t
from config.settings import get_config
from config.theme import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING, get_theme
from database.connection import get_connection
from services import analytics_service, export_service
from services.preferences_service import get_current_preferences

inject_base_styles()

render_page_header(title_key="analytics.title", subtitle_key="analytics.subtitle")

config = get_config()

if not guard_database_initialized():
    st.stop()

_prefs = get_current_preferences()
_preset = get_theme(_prefs.theme)

# 统一时间筛选。当前各统计口径本身不依赖"统计区间"做窗口筛选——
# 例如履约完成率看的是"已到预计送达时间的全部有效订单"，不是"某时间段内
# 下单的订单"。这里提供的时间筛选主要影响"订单量趋势"等按日期分布的图表。
_TIME_RANGE_OPTIONS = ["近7天", "近30天", "全部"]
_TIME_RANGE_KEY_MAP = {"近7天": "analytics.time_range.7d", "近30天": "analytics.time_range.30d", "全部": "analytics.time_range.all"}

time_range_col, _ = st.columns([1.4, 3.6])
with time_range_col:
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


def _render_group_caption(caption_key: str) -> None:
    st.markdown(
        f'<div class="fl-section-caption" style="margin: 4px 0 18px 0;">{t(caption_key)}</div>',
        unsafe_allow_html=True,
    )


def _export_block(button_label_key: str, button_key: str, headers: list[str], rows: list[list], sheet_name: str,
                  file_prefix: str, download_key: str) -> None:
    """统一的"导出 Excel"操作：点击生成文件后给出下载按钮。

    保持原有实现路径（export_service.create xlsx + st.download_button），
    仅调整按钮层级与文案。
    """
    if st.button(t(button_label_key), key=button_key):
        try:
            content = export_service.export_rows_to_xlsx(headers, rows, sheet_name=sheet_name[:31])
            st.download_button(
                t("analytics.download_file"), data=content,
                file_name=export_service.build_export_filename(file_prefix),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=download_key,
                type="primary",
            )
        except ValueError as exc:
            st.error(t("analytics.export_failed", error=exc))


tab_fulfillment, tab_anomaly, tab_task = st.tabs([
    t("analytics.tab.fulfillment"), t("analytics.tab.anomaly"), t("analytics.tab.task"),
])


# ======================================================================
# 履约分析
# ======================================================================

with tab_fulfillment:
    _render_group_caption("analytics.fulfillment.caption")

    rate_display = f"{fulfillment['fulfillment_rate']}%" if fulfillment["fulfillment_rate"] is not None else t("common.not_available")
    hours_display = (
        f"{fulfillment['avg_fulfillment_hours']:.1f} {t('analytics.hours_suffix')}"
        if fulfillment["avg_fulfillment_hours"] is not None
        else t("common.not_available")
    )
    delay_display = (
        f"{fulfillment['delayed_order_ratio']}%" if fulfillment["delayed_order_ratio"] is not None else t("common.not_available")
    )

    kpi_cols = st.columns(3)
    with kpi_cols[0]:
        render_kpi_stat(t("analytics.fulfillment_rate"), rate_display)
    with kpi_cols[1]:
        render_kpi_stat(
            t("analytics.avg_fulfillment_hours"), hours_display,
            meta=t("analytics.avg_fulfillment_hours_help", count=fulfillment["sample_size"]["avg_fulfillment_hours_sample"]),
        )
    with kpi_cols[2]:
        render_kpi_stat(
            t("analytics.delayed_order_ratio"), delay_display,
            meta=t("analytics.delayed_order_ratio_help", count=fulfillment["sample_size"]["delivered_order_count"]),
        )

    if fulfillment["sample_size"]["delivered_order_count"] == 0:
        st.info(t("analytics.no_delivered_note"))

    st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
    render_section("analytics.order_trend_title")
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
            st.warning(t("analytics.plotly_missing"))
            st.table(trend)

    st.markdown('<div style="height: 12px"></div>', unsafe_allow_html=True)
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
                deliver_headers = [
                    t("analytics.col.order_id"), t("analytics.col.customer_id"), t("analytics.col.shipped_at"),
                    t("analytics.col.delivered_at"), t("analytics.col.expected_delivery"), t("analytics.col.amount"),
                ]
                detail_df = pd.DataFrame(
                    [
                        {
                            deliver_headers[0]: r["order_id"], deliver_headers[1]: r["customer_id"],
                            deliver_headers[2]: r["shipped_at"], deliver_headers[3]: r["delivered_at"],
                            deliver_headers[4]: r["expected_delivery_at"], deliver_headers[5]: r["amount"],
                        }
                        for r in delivered_orders
                    ]
                )
                st.dataframe(detail_df, use_container_width=True, hide_index=True)

                _export_block(
                    "analytics.export_fulfillment", "export_fulfillment",
                    deliver_headers,
                    [[r["order_id"], r["customer_id"], r["shipped_at"], r["delivered_at"], r["expected_delivery_at"], r["amount"]] for r in delivered_orders],
                    t("analytics.delivered_detail_expander"), "fulfillment_detail", "download_fulfillment",
                )
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")


# ======================================================================
# 异常分析
# ======================================================================

with tab_anomaly:
    st.markdown(
        f'<div class="fl-section-caption" style="margin: 4px 0 20px 0;">'
        f"{t('analytics.anomaly_total_caption', count=anomaly_stats['total_count'])}</div>",
        unsafe_allow_html=True,
    )

    dist_col, risk_col = st.columns(2, gap="large")

    with dist_col:
        render_section("analytics.anomaly_type_dist_title")
        if not anomaly_stats["type_distribution"]:
            render_empty_state("empty.no_anomaly_data")
        else:
            try:
                from components.charts import bar_chart, plotly_config

                fig = bar_chart(
                    [d["anomaly_type"] for d in anomaly_stats["type_distribution"]],
                    [d["count"] for d in anomaly_stats["type_distribution"]],
                    primary=_preset.primary,
                    height=260,
                    font_size_key=_prefs.font_size,
                )
                st.plotly_chart(fig, use_container_width=True, config=plotly_config())
            except ImportError:
                st.table(anomaly_stats["type_distribution"])

    with risk_col:
        render_section("analytics.risk_dist_title")
        if not anomaly_stats["risk_distribution"]:
            render_empty_state("empty.no_risk_data")
        else:
            try:
                from components.charts import donut_chart, plotly_config

                fig = donut_chart(
                    [t(f"risk.{d['severity']}") for d in anomaly_stats["risk_distribution"]],
                    [d["count"] for d in anomaly_stats["risk_distribution"]],
                    palette=(COLOR_ERROR, COLOR_WARNING, COLOR_SUCCESS),
                    height=260,
                    font_size_key=_prefs.font_size,
                )
                st.plotly_chart(fig, use_container_width=True, config=plotly_config())
            except ImportError:
                st.table(anomaly_stats["risk_distribution"])

    st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
    render_section("analytics.top_customer_anomaly_title")
    if not customer_anomaly:
        render_empty_state("empty.no_customer_anomaly_data")
    else:
        customer_headers = [
            t("analytics.col.customer_name"), t("analytics.col.customer_tier"), t("analytics.col.anomaly_count"),
        ]
        customer_df = pd.DataFrame(
            [
                {
                    customer_headers[0]: c["name"], customer_headers[1]: c["tier"],
                    customer_headers[2]: c["anomaly_count"],
                }
                for c in customer_anomaly
            ]
        )
        st.dataframe(customer_df, use_container_width=True, hide_index=True)

        st.markdown('<div style="height: 8px"></div>', unsafe_allow_html=True)
        _export_block(
            "analytics.export_anomaly", "export_anomaly",
            [t("anomaly_center.anomaly_type"), t("analytics.col.anomaly_count")],
            [[d["anomaly_type"], d["count"]] for d in anomaly_stats["type_distribution"]],
            t("analytics.anomaly_type_dist_title"), "anomaly_analysis", "download_anomaly",
        )


# ======================================================================
# 任务分析
# ======================================================================

with tab_task:
    _render_group_caption("analytics.task_summary_caption")

    completion_display = f"{task_stats['completion_rate']}%" if task_stats["completion_rate"] is not None else t("common.not_available")
    avg_hours_display = (
        f"{task_stats['avg_processing_hours']:.1f} {t('analytics.hours_suffix')}"
        if task_stats["avg_processing_hours"] is not None else t("common.not_available")
    )

    task_kpi_cols = st.columns(4)
    with task_kpi_cols[0]:
        render_kpi_stat(t("analytics.total_tasks"), task_stats["total_tasks"])
    with task_kpi_cols[1]:
        render_kpi_stat(t("analytics.completion_rate"), completion_display)
    with task_kpi_cols[2]:
        render_kpi_stat(
            t("analytics.avg_processing_hours"), avg_hours_display,
            meta=t("analytics.avg_processing_hours_help", count=task_stats["sample_size"]["avg_processing_hours_sample"]),
        )
    with task_kpi_cols[3]:
        render_kpi_stat(t("analytics.overdue_count"), task_stats["overdue_count"])

    if task_stats["total_tasks"] == 0:
        st.info(t("analytics.no_tasks_note"))

    st.markdown('<div style="height: 12px"></div>', unsafe_allow_html=True)
    with st.expander(t("analytics.task_detail_expander")):
        try:
            with get_connection(config.database_path) as conn:
                all_tasks = conn.execute(
                    "SELECT task_id, title, priority, assignee, status, due_at, completed_at FROM operation_tasks ORDER BY created_at DESC LIMIT 200"
                ).fetchall()
            if not all_tasks:
                render_empty_state("empty.no_task_data")
            else:
                task_headers = [
                    t("analytics.col.task_id"), t("analytics.col.task_title"), t("analytics.col.task_priority"),
                    t("analytics.col.task_assignee"), t("analytics.col.task_status"), t("analytics.col.task_due"),
                    t("analytics.col.task_completed"),
                ]
                task_df = pd.DataFrame(
                    [
                        {
                            task_headers[0]: r["task_id"], task_headers[1]: r["title"],
                            task_headers[2]: r["priority"], task_headers[3]: r["assignee"],
                            task_headers[4]: t(f"status.{r['status']}"), task_headers[5]: r["due_at"],
                            task_headers[6]: r["completed_at"] or "—",
                        }
                        for r in all_tasks
                    ]
                )
                st.dataframe(task_df, use_container_width=True, hide_index=True)

                _export_block(
                    "analytics.export_task", "export_task",
                    task_headers,
                    [[r["task_id"], r["title"], r["priority"], r["assignee"], r["status"], r["due_at"], r["completed_at"] or ""] for r in all_tasks],
                    t("analytics.task_detail_expander"), "task_detail", "download_task",
                )
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
