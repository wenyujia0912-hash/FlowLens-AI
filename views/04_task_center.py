"""
运营任务中心（Operations Tasks）。

页面结构：任务列表（筛选）↔ 任务详情（基本信息 + 关联异常/订单 +
处理记录 + 状态更新）。

视觉（重设计 §6.04）：
    - 列表为统一数据表格，选中一行进入详情；状态/优先级以浅色标签文字呈现。
    - 详情页顶部是一组成对的字段，之后按"关联信息 → 更新任务 → 处理记录"
      的顺序展开，每个动作区之间只用留白与区域标题分隔，不嵌套彩色卡片。

闭环串联点（业务逻辑未改变）：
    - 驾驶舱待办区"查看"按钮 → 设置 pending_filter={"task_id": ...}，
      本页面读取并直接定位到该任务详情。
    - 异常详情页创建任务成功后 switch_page 到本页 → 同样通过
      pending_filter 定位到刚创建的任务。
    - 任务详情页提供"查看关联异常"/"查看关联订单"反向跳转。

核心约束（未改变）：
    - 完成任务必须填写处理结果（task_service 层已强制校验）。
    - 取消任务可填写取消原因。
    - 任务日志追加式记录，不覆盖历史。
    - 任务状态和异常状态完全独立。

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
    render_kv_list,
    render_page_header,
    render_section,
)
from components.filters import render_reset_button
from components.status_badges import priority_badge_html, status_badge_html
from config.i18n import t
from config.settings import get_config
from database.connection import get_connection
from repositories import task_repository
from services import task_service

inject_base_styles()

render_page_header(title_key="task_center.title", subtitle_key="task_center.subtitle")

config = get_config()

if not guard_database_initialized():
    st.stop()

# 消费从驾驶舱或异常详情页传来的筛选/定位条件（一次性，用后清除）。
pending_filter = st.session_state.pop("pending_filter", {})

if "selected_task_id" not in st.session_state:
    st.session_state["selected_task_id"] = None

if pending_filter.get("task_id") and not st.session_state["selected_task_id"]:
    st.session_state["selected_task_id"] = pending_filter["task_id"]

_FILTER_SPACER = '<div style="height: 26px"></div>'


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else t(f"status.{value}") if value in (
        "待处理", "处理中", "已完成", "已取消"
    ) else value


# ======================================================================
# 任务详情视图
# ======================================================================

if st.session_state["selected_task_id"]:
    task_id = st.session_state["selected_task_id"]

    if st.button(f"← {t('common.back')}", key="back_from_task_detail"):
        st.session_state["selected_task_id"] = None
        st.rerun()

    try:
        with get_connection(config.database_path) as conn:
            task = task_repository.get_by_id(conn, task_id)
            logs = task_repository.list_logs_for_task(conn, task_id) if task else []
    except sqlite3.Error as exc:
        st.error(f"{t('common.loading_failed')}：{exc}")
        task = None
        logs = []

    if task is None:
        render_empty_state("empty.task_not_found")
    else:
        st.markdown(
            f'<div class="fl-section"><div class="fl-section-title">{task.title}</div></div>',
            unsafe_allow_html=True,
        )

        render_kv_list(
            [
                (t("task_center.status_label"), status_badge_html(task.status)),
                (t("task_center.priority_label"), priority_badge_html(task.priority)),
                (t("task_center.assignee_label"), task.assignee),
                (t("task_center.due_label"), task.due_at[:10]),
            ],
            allow_html=True,
        )

        if task.description:
            st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
            render_section("task_center.description_title")
            st.markdown(
                f'<div style="font-size: var(--fl-fs-body); color: var(--fl-text); '
                f'white-space: pre-wrap; line-height: 1.65;">{task.description}</div>',
                unsafe_allow_html=True,
            )

        # --- 关联异常/订单（反向跳转）---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("task_center.related_info_title")
        link_cols = st.columns(2)
        with link_cols[0]:
            if task.anomaly_id:
                if st.button(t("task_center.view_related_anomaly", id=task.anomaly_id), key=f"goto_anomaly_{task.anomaly_id}"):
                    st.session_state["selected_anomaly_id"] = task.anomaly_id
                    st.session_state["selected_task_id"] = None
                    st.switch_page("views/03_anomaly_center.py")
            else:
                st.caption(t("task_center.no_related_anomaly"))
        with link_cols[1]:
            if task.order_id:
                if st.button(t("task_center.view_related_order", id=task.order_id), key=f"goto_order_{task.order_id}"):
                    st.session_state["selected_order_id"] = task.order_id
                    st.session_state["selected_task_id"] = None
                    st.switch_page("views/02_customers_orders.py")
            else:
                st.caption(t("task_center.no_related_order"))

        # --- 状态更新操作 ---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        if task.status in ("已完成", "已取消"):
            status_word = t("task_center.status_done") if task.status == "已完成" else t("task_center.status_cancelled")
            st.info(t("task_center.locked_status_note", status=status_word))
            if task.status == "已完成" and task.result:
                render_section("task_center.result_title")
                st.markdown(
                    f'<div style="font-size: var(--fl-fs-body); color: var(--fl-text); '
                    f'white-space: pre-wrap; line-height: 1.65;">{task.result}</div>',
                    unsafe_allow_html=True,
                )
        else:
            render_section("task_center.update_task_title")

            action_cols = st.columns(3, vertical_alignment="top")

            # 变更负责人
            with action_cols[0]:
                with st.expander(t("task_center.change_assignee_expander")):
                    new_assignee = st.text_input(t("task_center.new_assignee_label"), value=task.assignee, key=f"assignee_input_{task_id}")
                    if st.button(t("task_center.save_assignee"), key=f"save_assignee_{task_id}"):
                        if not new_assignee.strip():
                            st.error(t("task_center.assignee_required_error"))
                        else:
                            try:
                                with get_connection(config.database_path) as conn:
                                    task_service.update_assignee(
                                        conn, task_id, new_assignee, actor=task.assignee
                                    )
                                st.success(t("task_center.assignee_saved"))
                                st.rerun()
                            except task_service.TaskValidationError as exc:
                                st.error(str(exc))

            # 调整优先级
            with action_cols[1]:
                with st.expander(t("task_center.change_priority_expander")):
                    priority_opts = ["P1", "P2", "P3"]
                    new_priority = st.selectbox(
                        t("task_center.new_priority_label"), priority_opts,
                        index=priority_opts.index(task.priority),
                        key=f"priority_select_{task_id}",
                    )
                    if st.button(t("task_center.save_priority"), key=f"save_priority_{task_id}"):
                        try:
                            with get_connection(config.database_path) as conn:
                                task_service.update_priority(
                                    conn, task_id, new_priority, actor=task.assignee
                                )
                            st.success(t("task_center.priority_saved"))
                            st.rerun()
                        except task_service.TaskValidationError as exc:
                            st.error(str(exc))

            # 更新状态为"处理中"（如果当前是"待处理"）
            with action_cols[2]:
                if task.status == "待处理":
                    if st.button(t("task_center.mark_in_progress"), key=f"start_task_{task_id}"):
                        try:
                            with get_connection(config.database_path) as conn:
                                task_service.update_status(
                                    conn, task_id, "处理中", actor=task.assignee
                                )
                            st.success(t("task_center.mark_in_progress_success"))
                            st.rerun()
                        except task_service.TaskValidationError as exc:
                            st.error(str(exc))
                else:
                    st.caption(t("task_center.current_status_caption", status=t(f"status.{task.status}")))

            st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)

            # 追加处理记录
            render_section("task_center.append_progress_title")
            progress_note = st.text_area(t("task_center.progress_note_label"), key=f"progress_note_{task_id}", height=90)
            if st.button(t("task_center.save_progress"), key=f"save_progress_{task_id}"):
                if not progress_note.strip():
                    st.error(t("task_center.progress_required_error"))
                else:
                    try:
                        with get_connection(config.database_path) as conn:
                            task_service.add_progress_note(
                                conn, task_id, progress_note, actor=task.assignee
                            )
                        st.success(t("task_center.progress_saved"))
                        st.rerun()
                    except task_service.TaskValidationError as exc:
                        st.error(str(exc))

        # --- 完成任务（必须填写处理结果）---
        if task.status not in ("已完成", "已取消"):
            st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
            render_section("task_center.complete_task_title", "task_center.complete_task_caption")
            with st.form(key=f"complete_task_form_{task_id}"):
                result_text = st.text_area(t("task_center.result_input_label"), height=100)
                complete_submitted = st.form_submit_button(t("task_center.confirm_complete"), type="primary")
                if complete_submitted:
                    if not result_text.strip():
                        st.error(t("task_center.result_required_error"))
                    else:
                        try:
                            with get_connection(config.database_path) as conn:
                                task_service.update_status(
                                    conn, task_id, "已完成", actor=task.assignee, result=result_text
                                )
                            st.success(t("task_center.complete_success"))
                            st.rerun()
                        except task_service.TaskValidationError as exc:
                            st.error(str(exc))

            # 取消任务（可填写取消原因）
            st.markdown('<div style="height: 24px"></div>', unsafe_allow_html=True)
            render_section("task_center.cancel_task_title")
            with st.form(key=f"cancel_task_form_{task_id}"):
                cancel_reason_text = st.text_input(t("task_center.cancel_reason_label"))
                cancel_submitted = st.form_submit_button(t("task_center.confirm_cancel"))
                if cancel_submitted:
                    try:
                        with get_connection(config.database_path) as conn:
                            task_service.update_status(
                                conn, task_id, "已取消", actor=task.assignee,
                                cancel_reason=cancel_reason_text or None,
                            )
                        st.success(t("task_center.cancel_success"))
                        st.rerun()
                    except task_service.TaskValidationError as exc:
                        st.error(str(exc))

        # --- 处理记录时间线（追加式，按时间正序展示）---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("task_center.timeline_title")
        if not logs:
            render_empty_state("empty.no_progress_log")
        else:
            for log in logs:
                st.markdown(
                    f"""
                    <div style="padding: 12px 0; border-bottom: 1px solid var(--fl-border);">
                        <div style="font-size: var(--fl-fs-caption); color: var(--fl-text-muted);">
                            {log.created_at}
                        </div>
                        <div style="font-size: var(--fl-fs-body); color: var(--fl-text); margin-top: 3px;">
                            {log.action}
                            <span style="color: var(--fl-text-secondary);">
                                · {t("task_center.timeline_operator_label")}：{log.actor}
                            </span>
                        </div>
                        {f'<div style="font-size: var(--fl-fs-caption); color: var(--fl-text-secondary); margin-top: 4px;">{log.content}</div>' if log.content else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

else:
    # ==================================================================
    # 任务列表视图
    # ==================================================================

    filter_cols = st.columns([1.4, 1.2, 1.6, 1.4, 0.8])
    with filter_cols[0]:
        status_options = ["全部", "待处理", "处理中", "已完成", "已取消"]
        default_status = pending_filter.get("status", "全部")
        status_filter = st.selectbox(
            t("task_center.col.status"), status_options,
            index=status_options.index(default_status) if default_status in status_options else 0,
            format_func=_opt_label,
            key="task_status_filter",
        )
    with filter_cols[1]:
        priority_options = ["全部", "P1", "P2", "P3"]
        priority_filter = st.selectbox(t("task_center.col.priority"), priority_options, format_func=lambda v: t("common.all") if v == "全部" else v, key="task_priority_filter")
    with filter_cols[2]:
        assignee_filter = st.text_input(t("task_center.col.assignee"), key="task_assignee_filter")
    with filter_cols[3]:
        st.markdown('<div style="height: 26px"></div>', unsafe_allow_html=True)
        show_overdue_only = st.checkbox(
            t("task_center.only_overdue"),
            value=bool(pending_filter.get("overdue_only")),
            key="task_overdue_only",
        )
    with filter_cols[4]:
        st.markdown(_FILTER_SPACER, unsafe_allow_html=True)
        if render_reset_button(key="reset_task_filters"):
            for key in ("task_status_filter", "task_priority_filter", "task_assignee_filter", "task_overdue_only"):
                st.session_state.pop(key, None)
            st.rerun()

    try:
        with get_connection(config.database_path) as conn:
            now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            if show_overdue_only:
                tasks = task_repository.list_overdue(conn, now_iso)
            else:
                tasks = task_repository.list_all(
                    conn,
                    status=None if status_filter == "全部" else status_filter,
                    priority=None if priority_filter == "全部" else priority_filter,
                    assignee=assignee_filter or None,
                )
    except sqlite3.Error as exc:
        st.error(f"{t('common.loading_failed')}：{exc}")
        tasks = []

    if not tasks:
        render_empty_state("empty.no_tasks", hint_key="empty.task_hint_create_from_anomaly")
    else:
        st.caption(f"{t('customers_orders.customer_count_prefix')} {len(tasks)} {t('task_center.list_count_suffix')}")

        visible_tasks = tasks[:200]
        rows = []
        for task_item in visible_tasks:
            link_text = []
            if task_item.anomaly_id:
                link_text.append(t("task_center.related.anomaly"))
            if task_item.order_id:
                link_text.append(t("task_center.related.order"))
            rows.append(
                {
                    t("task_center.col.title"): task_item.title,
                    t("task_center.col.priority"): task_item.priority,
                    t("task_center.col.status"): t(f"status.{task_item.status}"),
                    t("task_center.col.assignee"): task_item.assignee,
                    t("task_center.col.due"): task_item.due_at[:10],
                    t("task_center.col.related"): " / ".join(link_text) if link_text else "—",
                }
            )

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tasks_table",
        )
        st.caption(t("task_center.row_select_hint"))

        try:
            selected_rows = st.session_state["tasks_table"].selection.rows
        except (AttributeError, KeyError, TypeError):
            selected_rows = []

        if selected_rows and 0 <= selected_rows[0] < len(visible_tasks):
            st.session_state["selected_task_id"] = visible_tasks[selected_rows[0]].task_id
            st.rerun()
