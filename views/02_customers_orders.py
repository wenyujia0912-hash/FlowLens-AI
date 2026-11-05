"""
客户与订单管理（Customers & Orders）。

页面结构：两个 Tab（客户列表 / 订单列表），每个 Tab 内支持"列表 ↔ 详情"
切换（通过 st.session_state 保存当前选中的 customer_id / order_id）。

本次仅重排信息层级与视觉：
    - 列表使用统一的数据表格（浅灰表头、极浅行分隔、行悬停、可排序、
      内容多时可横向滚动），选中一行即可进入详情，不再每行一个按钮；
    - 详情页用"定义列表"组织字段，用区域标题分组，不再堆叠卡片；
    - 筛选区统一为一行紧凑的输入控件。

数据来源：全部通过 services.customer_service / services.order_service
从数据库实时查询（客户详情中的订单与异常数量必须由数据库关联数据计算，
不得使用互不关联的静态数字）。查询条件、展示条数上限与业务逻辑均未改变。

文案全部通过 config.i18n.t() 翻译。
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from components.layout import (
    guard_database_initialized,
    inject_base_styles,
    render_empty_state,
    render_kv_list,
    render_page_header,
    render_section,
)
from components.filters import render_reset_button
from components.status_badges import status_badge_html
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

tab_customers, tab_orders = st.tabs([t("customers_orders.tab.customers"), t("customers_orders.tab.orders")])

_INDUSTRY_OPTIONS = ["全部", "智能制造", "快消零售", "医疗器械", "新能源", "跨境电商",
                      "办公文具", "家居建材", "数码配件", "食品饮料", "美妆个护"]
_TIER_OPTIONS = ["全部", "战略客户", "重点客户", "普通客户"]
_COOP_STATUS_OPTIONS = ["全部", "合作中", "暂停合作", "已终止"]

_FILTER_SPACER = '<div style="height: 26px"></div>'


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else value


def _back(key: str) -> bool:
    """详情页顶部的返回入口：文字按钮，不加图标。"""
    return st.button(f"← {t('common.back')}", key=key)


def _selected_row(table_key: str) -> int | None:
    """读取表格当前选中的行号；无选中或读取失败时返回 None。"""
    try:
        state = st.session_state.get(table_key)
        rows = state.selection.rows if state else []
    except (AttributeError, KeyError, TypeError):
        return None
    return rows[0] if rows else None


def _show_table(df: pd.DataFrame, table_key: str) -> None:
    """渲染统一风味的只读数据表格（可排序、可横向滚动、行悬停高亮）。"""
    st.dataframe(df, use_container_width=True, hide_index=True, key=table_key)


def _detail_picker(
    label: str,
    options: list[str],
    format_func,
    *,
    select_key: str,
    button_key: str,
    on_open,
    hint_key: str = "customers_orders.row_select_hint",
) -> None:
    """列表下方的"选择一行 → 查看详情"入口。

    表格本身只承载只读信息（便于排序/对齐/横向滚动），详情跳转通过一个
    明确的选择控件 + 按钮完成，交互路径清晰，也避免依赖 canvas 表格里
    不易被发现的行选中态。
    """
    st.caption(t(hint_key))
    pick_col, button_col = st.columns([3, 1])
    with pick_col:
        picked = st.selectbox(label, options=options, format_func=format_func, key=select_key)
    with button_col:
        st.markdown('<div style="height: 26px"></div>', unsafe_allow_html=True)
        if st.button(t("common.detail"), key=button_key):
            on_open(picked)


def _open_customer(customer_id: str) -> None:
    st.session_state["selected_customer_id"] = customer_id
    st.rerun()


def _open_order(order_id: str) -> None:
    st.session_state["selected_order_id"] = order_id
    st.rerun()


def _open_order_from_customer(order_id: str) -> None:
    st.session_state["selected_order_id"] = order_id
    st.session_state["selected_customer_id"] = None
    st.rerun()


# ======================================================================
# 客户列表 / 详情
# ======================================================================

with tab_customers:
    if "selected_customer_id" not in st.session_state:
        st.session_state["selected_customer_id"] = None

    if st.session_state["selected_customer_id"]:
        # --- 客户详情视图 ---
        customer_id = st.session_state["selected_customer_id"]
        if _back("back_from_customer_detail"):
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
            st.markdown(
                f'<div class="fl-section"><div class="fl-section-title">{c.name}</div></div>',
                unsafe_allow_html=True,
            )

            render_kv_list(
                [
                    (t("customers_orders.industry"), c.industry),
                    (t("customers_orders.tier"), c.tier),
                    (t("customers_orders.coop_status"), c.status),
                    (t("customers_orders.total_amount"), f"¥{detail['total_amount']:,.2f}"),
                    (
                        t("customers_orders.related_orders"),
                        f"{detail['order_count']} · {t('customers_orders.related_anomalies')} {detail['anomaly_count']}",
                    ),
                ]
            )
            st.caption(t("customers_orders.realtime_note"))

            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("customers_orders.related_orders")
            if not detail["orders"]:
                render_empty_state("empty.no_customer_orders")
            else:
                orders_df = pd.DataFrame(
                    [
                        {
                            t("customers_orders.col.order_id"): order.order_id,
                            t("customers_orders.col.order_date"): order.order_date[:10],
                            t("customers_orders.col.amount"): f"¥{order.amount:,.2f}",
                            t("customers_orders.order_status"): t(f"status.{order.status}"),
                        }
                        for order in detail["orders"]
                    ]
                )
                _show_table(orders_df, f"customer_orders_table_{customer_id}")
                _detail_picker(
                    t("customers_orders.col.order_id"),
                    options=[order.order_id for order in detail["orders"]],
                    format_func=lambda oid: oid,
                    select_key=f"customer_orders_pick_{customer_id}",
                    button_key=f"customer_order_open_{customer_id}",
                    on_open=_open_order_from_customer,
                )

            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("customers_orders.related_anomalies")
            if not detail["anomalies"]:
                render_empty_state("empty.no_customer_anomalies")
            else:
                anomalies_df = pd.DataFrame(
                    [
                        {
                            t("anomaly_center.col.anomaly_id"): anomaly.anomaly_id,
                            t("anomaly_center.col.anomaly_type"): anomaly.anomaly_type,
                            t("anomaly_center.col.risk"): t(f"risk.{anomaly.severity}"),
                            t("anomaly_center.col.status"): t(f"status.{anomaly.status}"),
                        }
                        for anomaly in detail["anomalies"]
                    ]
                )
                st.dataframe(anomalies_df, use_container_width=True, hide_index=True)
                st.caption(t("customers_orders.jump_anomaly_hint"))

    else:
        # --- 客户列表视图 ---
        search_col, industry_col, tier_col, status_col, reset_col = st.columns([2.4, 1.4, 1.4, 1.4, 0.8])
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
            st.markdown(_FILTER_SPACER, unsafe_allow_html=True)
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
            customers_df = pd.DataFrame(
                [
                    {
                        t("customers_orders.col.customer_name"): item["customer"].name,
                        t("customers_orders.industry"): item["customer"].industry,
                        t("customers_orders.tier"): item["customer"].tier,
                        t("customers_orders.coop_status"): item["customer"].status,
                        t("customers_orders.col.order_count"): item["order_count"],
                        t("customers_orders.col.anomaly_count"): item["anomaly_count"],
                    }
                    for item in customers
                ]
            )
            _show_table(customers_df, "customers_table")
            _detail_picker(
                t("customers_orders.col.customer_name"),
                options=[item["customer"].customer_id for item in customers],
                format_func=lambda cid: next(
                    (item["customer"].name for item in customers if item["customer"].customer_id == cid), cid
                ),
                select_key="customer_detail_pick",
                button_key="open_customer_detail",
                on_open=_open_customer,
            )


# ======================================================================
# 订单列表 / 详情
# ======================================================================

with tab_orders:
    if "selected_order_id" not in st.session_state:
        st.session_state["selected_order_id"] = None

    if st.session_state["selected_order_id"]:
        # --- 订单详情视图 ---
        order_id = st.session_state["selected_order_id"]
        if _back("back_from_order_detail"):
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
            st.markdown(
                f'<div class="fl-section"><div class="fl-section-title">'
                f"{t('customers_orders.col.order_id')} {detail.order.order_id}</div></div>",
                unsafe_allow_html=True,
            )

            logistics_value = (
                status_badge_html(detail.logistics.current_status)
                if detail.logistics
                else f'<span class="is-muted">{t("customers_orders.no_logistics")}</span>'
            )
            render_kv_list(
                [
                    (t("customers_orders.order_summary.customer"), detail.customer.name),
                    (t("customers_orders.order_summary.amount"), f"¥{detail.order.amount:,.2f}"),
                    (t("customers_orders.order_summary.order_status"), status_badge_html(detail.order.status)),
                    (t("customers_orders.order_summary.logistics_status"), logistics_value),
                ],
                allow_html=True,
            )

            if detail.anomaly_ids:
                st.warning(t("customers_orders.anomaly_warning", count=len(detail.anomaly_ids)))

            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("customers_orders.item_details_title")
            if not detail.items:
                render_empty_state("empty.no_order_items")
            else:
                items_df = pd.DataFrame(
                    [
                        {
                            t("customers_orders.item.product"): i.product_name,
                            t("customers_orders.item.quantity"): i.quantity,
                            t("customers_orders.item.unit_price"): f"¥{i.unit_price:,.2f}",
                            t("customers_orders.item.subtotal"): f"¥{i.quantity * i.unit_price:,.2f}",
                        }
                        for i in detail.items
                    ]
                )
                st.dataframe(items_df, use_container_width=True, hide_index=True)

            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("customers_orders.timeline_title")
            timeline_items = [
                (t("customers_orders.timeline.order_placed"), detail.order.order_date),
                (t("customers_orders.timeline.expected_ship"), detail.order.expected_ship_at),
                (t("customers_orders.timeline.actual_ship"), detail.order.shipped_at),
                (t("customers_orders.timeline.expected_delivery"), detail.order.expected_delivery_at),
                (t("customers_orders.timeline.actual_delivery"), detail.order.delivered_at),
            ]
            render_kv_list(
                [
                    (label, value if value is not None else t("customers_orders.timeline.not_yet"))
                    for label, value in timeline_items
                ]
            )

            if detail.logistics and detail.logistics.events:
                st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
                render_section("customers_orders.logistics_events_title")
                for event in detail.logistics.events:
                    st.caption(f"{event.event_time} · {event.location} · {event.event_status}")

            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("customers_orders.supplier_title")
            render_kv_list(
                [
                    (t("customers_orders.supplier.name"), detail.supplier.name),
                    (t("customers_orders.supplier.category"), detail.supplier.category),
                    (
                        t("customers_orders.supplier.lead_time"),
                        f"{detail.supplier.lead_time_days} {t('customers_orders.supplier.days_suffix')}",
                    ),
                ]
            )

            st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
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

        search_col, status_col, logistics_col, reset_col = st.columns([2.4, 1.6, 1.6, 0.8])
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
            st.markdown(_FILTER_SPACER, unsafe_allow_html=True)
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

            from repositories import customer_repository as _customer_repo

            with get_connection(config.database_path) as conn:
                visible_orders = orders[:100]
                order_rows = []
                for item in visible_orders:
                    order = item["order"]
                    customer = _customer_repo.get_by_id(conn, order.customer_id)
                    order_rows.append(
                        {
                            t("customers_orders.col.order_id"): order.order_id,
                            t("customers_orders.col.customer"): customer.name if customer else order.customer_id,
                            t("customers_orders.col.amount"): f"¥{order.amount:,.2f}",
                            t("customers_orders.col.order_date"): order.order_date[:10],
                            t("customers_orders.order_status"): t(f"status.{order.status}"),
                            t("customers_orders.col.anomaly"): t("common.yes") if item["has_anomaly"] else "—",
                        }
                    )

            _show_table(pd.DataFrame(order_rows), "orders_table")

            _order_id_by_customer: dict[str, str] = {
                item["order"].order_id: item["order"].customer_id for item in visible_orders
            }
            _order_options = list(_order_id_by_customer.keys())
            _detail_picker(
                t("customers_orders.col.order_id"),
                options=_order_options,
                format_func=lambda oid: oid,
                select_key="order_detail_pick",
                button_key="open_order_detail",
                on_open=_open_order,
            )
