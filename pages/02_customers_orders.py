"""
客户与订单管理（Customers & Orders）。

页面结构：两个 Tab（客户列表 / 订单列表），每个 Tab 内支持"列表 ↔ 详情"
切换（通过 st.session_state 保存当前选中的 customer_id / order_id）。

数据来源：全部通过 services.customer_service / services.order_service
从数据库实时查询（客户详情中的订单与异常数量必须由数据库关联数据计算，
不得使用互不关联的静态数字）。

文案全部通过 config.i18n.t() 翻译。
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from components.layout import (
    inject_base_styles,
    render_page_header,
    render_sidebar_footer,
    render_empty_state,
    guard_database_initialized,
)
from components.filters import render_reset_button
from components.status_badges import render_status_badge
from config.i18n import t
from config.settings import get_config
from database.connection import get_connection
from services import customer_service, order_service

inject_base_styles()

render_page_header(title_key="customers_orders.title", subtitle_key="customers_orders.subtitle")

config = get_config()

if not guard_database_initialized():
    st.stop()

# 消费从驾驶舱传来的筛选条件（一次性，用后清除）。
pending_filter = st.session_state.pop("pending_filter", {})
default_tab_index = 1 if pending_filter.get("tab") == "orders" else 0

tab_customers, tab_orders = st.tabs([t("customers_orders.tab.customers"), t("customers_orders.tab.orders")])

_INDUSTRY_OPTIONS = ["全部", "智能制造", "快消零售", "医疗器械", "新能源", "跨境电商",
                      "办公文具", "家居建材", "数码配件", "食品饮料", "美妆个护"]
_TIER_OPTIONS = ["全部", "战略客户", "重点客户", "普通客户"]
_COOP_STATUS_OPTIONS = ["全部", "合作中", "暂停合作", "已终止"]


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else value


# ======================================================================
# 客户列表 / 详情
# ======================================================================

with tab_customers:
    if "selected_customer_id" not in st.session_state:
        st.session_state["selected_customer_id"] = None

    if st.session_state["selected_customer_id"]:
        # --- 客户详情视图 ---
        customer_id = st.session_state["selected_customer_id"]
        if st.button(t("common.back"), key="back_from_customer_detail"):
            st.session_state["selected_customer_id"] = None
            st.rerun()

        try:
            with get_connection(config.database_path) as conn:
                detail = customer_service.get_customer_detail(conn, customer_id)
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            detail = None

        if detail is None:
            render_empty_state("empty.customer_not_found")
        else:
            c = detail["customer"]
            st.subheader(c.name)

            info_cols = st.columns(4)
            info_cols[0].metric(t("customers_orders.industry"), c.industry)
            info_cols[1].metric(t("customers_orders.tier"), c.tier)
            info_cols[2].metric(t("customers_orders.coop_status"), c.status)
            info_cols[3].metric(t("customers_orders.total_amount"), f"¥{detail['total_amount']:,.2f}")

            st.caption(
                f"{t('customers_orders.related_orders')} {detail['order_count']} · "
                f"{t('customers_orders.related_anomalies')} {detail['anomaly_count']} "
                f"{t('customers_orders.realtime_note')}"
            )

            st.divider()
            st.markdown(f"**{t('customers_orders.related_orders')}**")
            if not detail["orders"]:
                render_empty_state("empty.no_customer_orders")
            else:
                for order in detail["orders"]:
                    row = st.columns([2, 2, 2, 2, 1])
                    row[0].write(order.order_id)
                    row[1].write(order.order_date[:10])
                    row[2].write(f"¥{order.amount:,.2f}")
                    with row[3]:
                        render_status_badge(order.status)
                    if row[4].button(t("common.detail"), key=f"goto_order_{order.order_id}_from_customer"):
                        st.session_state["selected_order_id"] = order.order_id
                        st.session_state["jump_to_orders_tab"] = True
                        st.rerun()

            st.divider()
            st.markdown(f"**{t('customers_orders.related_anomalies')}**")
            if not detail["anomalies"]:
                render_empty_state("empty.no_customer_anomalies")
            else:
                for anomaly in detail["anomalies"]:
                    row = st.columns([2, 2, 2, 2])
                    row[0].write(anomaly.anomaly_id)
                    row[1].write(anomaly.anomaly_type)
                    row[2].write(anomaly.severity)
                    with row[3]:
                        render_status_badge(anomaly.status)
                st.caption(t("customers_orders.jump_anomaly_hint"))

    else:
        # --- 客户列表视图 ---
        search_col, industry_col, tier_col, status_col, reset_col = st.columns([3, 2, 2, 2, 1])
        with search_col:
            name_query = st.text_input(t("customers_orders.search_customer_name"), key="customer_name_search")
        with industry_col:
            industry_filter = st.selectbox(
                t("customers_orders.industry"), _INDUSTRY_OPTIONS,
                format_func=_opt_label,
                key="customer_industry_filter",
            )
        with tier_col:
            tier_filter = st.selectbox(t("customers_orders.tier"), _TIER_OPTIONS, format_func=_opt_label, key="customer_tier_filter")
        with status_col:
            status_filter = st.selectbox(t("customers_orders.coop_status"), _COOP_STATUS_OPTIONS, format_func=_opt_label, key="customer_status_filter")
        with reset_col:
            if render_reset_button(key="reset_customer_filters"):
                for key in ("customer_name_search", "customer_industry_filter", "customer_tier_filter", "customer_status_filter"):
                    st.session_state.pop(key, None)
                st.rerun()

        try:
            with get_connection(config.database_path) as conn:
                customers = customer_service.search_customers(
                    conn,
                    name=name_query or None,
                    industry=None if industry_filter == "全部" else industry_filter,
                    tier=None if tier_filter == "全部" else tier_filter,
                    status=None if status_filter == "全部" else status_filter,
                )
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            customers = []

        if not customers:
            render_empty_state("empty.no_customers", hint_key="empty.adjust_filter_hint")
        else:
            st.caption(f"{t('customers_orders.customer_count_prefix')} {len(customers)} {t('customers_orders.customer_count_suffix')}")
            header = st.columns([3, 2, 2, 2, 2, 2, 1])
            header_labels = [
                "customers_orders.col.customer_name", "customers_orders.industry", "customers_orders.tier",
                "customers_orders.coop_status", "customers_orders.col.order_count", "customers_orders.col.anomaly_count",
            ]
            for col, label_key in zip(header, header_labels):
                col.markdown(f"**{t(label_key)}**")
            header[-1].markdown("")

            for item in customers:
                c = item["customer"]
                row = st.columns([3, 2, 2, 2, 2, 2, 1])
                row[0].write(c.name)
                row[1].write(c.industry)
                row[2].write(c.tier)
                row[3].write(c.status)
                row[4].write(str(item["order_count"]))
                row[5].write(str(item["anomaly_count"]))
                if row[6].button(t("common.detail"), key=f"customer_detail_{c.customer_id}"):
                    st.session_state["selected_customer_id"] = c.customer_id
                    st.rerun()


# ======================================================================
# 订单列表 / 详情
# ======================================================================

with tab_orders:
    if "selected_order_id" not in st.session_state:
        st.session_state["selected_order_id"] = None

    if st.session_state["selected_order_id"]:
        # --- 订单详情视图 ---
        order_id = st.session_state["selected_order_id"]
        if st.button(t("common.back"), key="back_from_order_detail"):
            st.session_state["selected_order_id"] = None
            st.rerun()

        try:
            with get_connection(config.database_path) as conn:
                detail = order_service.get_order_detail(conn, order_id)
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            detail = None
        except RuntimeError as exc:
            st.error(f"{exc}")
            detail = None

        if detail is None:
            render_empty_state("empty.order_not_found")
        else:
            st.subheader(f"{t('customers_orders.col.order_id')} {detail.order.order_id}")

            summary_cols = st.columns(4)
            summary_cols[0].metric(t("customers_orders.order_summary.customer"), detail.customer.name)
            summary_cols[1].metric(t("customers_orders.order_summary.amount"), f"¥{detail.order.amount:,.2f}")
            with summary_cols[2]:
                st.write(t("customers_orders.order_summary.order_status"))
                render_status_badge(detail.order.status)
            with summary_cols[3]:
                st.write(t("customers_orders.order_summary.logistics_status"))
                if detail.logistics:
                    render_status_badge(detail.logistics.current_status)
                else:
                    st.caption(t("customers_orders.no_logistics"))

            if detail.anomaly_ids:
                st.warning(t("customers_orders.anomaly_warning", count=len(detail.anomaly_ids)))

            st.divider()
            st.markdown(f"**{t('customers_orders.item_details_title')}**")
            if not detail.items:
                render_empty_state("empty.no_order_items")
            else:
                item_rows = [
                    {
                        t("customers_orders.item.product"): i.product_name,
                        t("customers_orders.item.quantity"): i.quantity,
                        t("customers_orders.item.unit_price"): f"¥{i.unit_price:,.2f}",
                        t("customers_orders.item.subtotal"): f"¥{i.quantity * i.unit_price:,.2f}",
                    }
                    for i in detail.items
                ]
                st.table(item_rows)

            st.divider()
            st.markdown(f"**{t('customers_orders.timeline_title')}**")
            timeline_items = [(t("customers_orders.timeline.order_placed"), detail.order.order_date)]
            timeline_items.append((t("customers_orders.timeline.expected_ship"), detail.order.expected_ship_at))
            if detail.order.shipped_at:
                timeline_items.append((t("customers_orders.timeline.actual_ship"), detail.order.shipped_at))
            else:
                timeline_items.append((t("customers_orders.timeline.actual_ship"), None))
            timeline_items.append((t("customers_orders.timeline.expected_delivery"), detail.order.expected_delivery_at))
            if detail.order.delivered_at:
                timeline_items.append((t("customers_orders.timeline.actual_delivery"), detail.order.delivered_at))
            else:
                timeline_items.append((t("customers_orders.timeline.actual_delivery"), None))

            for label, value in timeline_items:
                if value is None:
                    st.caption(f"○ {label}：{t('customers_orders.timeline.not_yet')}")
                else:
                    st.write(f"● {label}：{value}")

            if detail.logistics and detail.logistics.events:
                st.markdown(f"**{t('customers_orders.logistics_events_title')}**")
                for event in detail.logistics.events:
                    st.caption(f"{event.event_time} · {event.location} · {event.event_status}")

            st.divider()
            st.markdown(f"**{t('customers_orders.supplier_title')}**")
            supplier_cols = st.columns(3)
            supplier_cols[0].metric(t("customers_orders.supplier.name"), detail.supplier.name)
            supplier_cols[1].metric(t("customers_orders.supplier.category"), detail.supplier.category)
            supplier_cols[2].metric(
                t("customers_orders.supplier.lead_time"),
                f"{detail.supplier.lead_time_days} {t('customers_orders.supplier.days_suffix')}",
            )

            st.divider()
            if st.button(t("customers_orders.view_customer_detail"), key=f"goto_customer_{detail.customer.customer_id}"):
                st.session_state["selected_customer_id"] = detail.customer.customer_id
                st.session_state["selected_order_id"] = None
                st.rerun()

    else:
        # --- 订单列表视图 ---
        order_id_search = pending_filter.get("order_id")
        default_status = pending_filter.get("status", "全部")

        order_status_opts = ["全部", "待确认", "待发货", "运输中", "已签收", "已取消"]
        logistics_status_opts = ["全部", "待揽收", "运输中", "派送中", "已签收", "异常"]

        search_col, status_col, logistics_col, reset_col = st.columns([3, 2, 2, 1])
        with search_col:
            order_id_query = st.text_input(t("customers_orders.search_order_id"), value=order_id_search or "", key="order_id_search")
        with status_col:
            order_status_filter = st.selectbox(
                t("customers_orders.order_status"), order_status_opts,
                index=order_status_opts.index(default_status) if default_status in order_status_opts else 0,
                format_func=_opt_label, key="order_status_filter",
            )
        with logistics_col:
            logistics_status_filter = st.selectbox(
                t("customers_orders.logistics_status"), logistics_status_opts,
                format_func=_opt_label, key="logistics_status_filter",
            )
        with reset_col:
            if render_reset_button(key="reset_order_filters"):
                for key in ("order_id_search", "order_status_filter", "logistics_status_filter"):
                    st.session_state.pop(key, None)
                st.rerun()

        try:
            with get_connection(config.database_path) as conn:
                orders = order_service.search_orders(
                    conn,
                    order_id=order_id_query or None,
                    status=None if order_status_filter == "全部" else order_status_filter,
                    logistics_status=None if logistics_status_filter == "全部" else logistics_status_filter,
                )
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            orders = []

        if not orders:
            render_empty_state("empty.no_orders", hint_key="empty.adjust_filter_hint")
        else:
            st.caption(f"{t('customers_orders.customer_count_prefix')} {len(orders)} {t('customers_orders.order_count_suffix')}")
            header = st.columns([2, 2, 2, 2, 2, 1, 1])
            header_labels = [
                "customers_orders.col.order_id", "customers_orders.col.customer", "customers_orders.col.amount",
                "customers_orders.col.order_date", "customers_orders.order_status", "customers_orders.col.anomaly",
            ]
            for col, label_key in zip(header, header_labels):
                col.markdown(f"**{t(label_key)}**")
            header[-1].markdown("")

            from repositories import customer_repository as _customer_repo

            with get_connection(config.database_path) as conn:
                for item in orders[:100]:
                    order = item["order"]
                    customer = _customer_repo.get_by_id(conn, order.customer_id)
                    row = st.columns([2, 2, 2, 2, 2, 1, 1])
                    row[0].write(order.order_id)
                    row[1].write(customer.name if customer else order.customer_id)
                    row[2].write(f"¥{order.amount:,.2f}")
                    row[3].write(order.order_date[:10])
                    with row[4]:
                        render_status_badge(order.status)
                    row[5].write("⚠️" if item["has_anomaly"] else "—")
                    if row[6].button(t("common.detail"), key=f"order_detail_{order.order_id}"):
                        st.session_state["selected_order_id"] = order.order_id
                        st.rerun()

render_sidebar_footer()
