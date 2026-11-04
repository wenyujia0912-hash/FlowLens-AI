"""
运营任务中心（Operations Tasks）。

页面结构：任务列表（筛选/排序）↔ 任务详情（基本信息 + 关联异常/订单 +
处理记录时间线 + 状态更新）。

闭环串联点：
    - 驾驶舱待办区"查看"按钮 → 设置 pending_filter={"task_id": ...}，
      本页面读取并直接定位到该任务详情。
    - 异常详情页创建任务成功后 switch_page 到本页 → 同样通过
      pending_filter 定位到刚创建的任务。
    - 任务详情页提供"查看关联异常"/"查看关联订单"反向跳转。

核心约束：
    - 完成任务必须填写处理结果（task_service 层已强制校验）。
    - 取消任务可填写取消原因。
    - 任务日志追加式记录，不覆盖历史。
    - 任务状态和异常状态完全独立。

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
from components.filters import render_reset_button
from components.status_badges import render_status_badge, render_priority_badge
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


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else t(f"status.{value}") if value in (
        "待处理", "处理中", "已完成", "已取消"
    ) else value


# ======================================================================
# 任务详情视图
# ======================================================================

if st.session_state["selected_task_id"]:
    task_id = st.session_state["selected_task_id"]

    if st.button(t("common.back"), key="back_from_task_detail"):
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
        st.subheader(task.title)

        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.write(t("task_center.status_label"))
            render_status_badge(task.status)
        with summary_cols[1]:
            st.write(t("task_center.priority_label"))
            render_priority_badge(task.priority)
        summary_cols[2].metric(t("task_center.assignee_label"), task.assignee)
        summary_cols[3].metric(t("task_center.due_label"), task.due_at[:10])

        if task.description:
            st.markdown(f"**{t('task_center.description_title')}**")
            st.write(task.description)

        st.divider()

        # --- 关联异常/订单（反向跳转）---
        st.markdown(f"**{t('task_center.related_info_title')}**")
        link_cols = st.columns(2)
        with link_cols[0]:
            if task.anomaly_id:
                if st.button(t("task_center.view_related_anomaly", id=task.anomaly_id), key=f"goto_anomaly_{task.anomaly_id}"):
                    st.session_state["selected_anomaly_id"] = task.anomaly_id
                    st.session_state["selected_task_id"] = None
                    st.switch_page("pages/03_anomaly_center.py")
            else:
                st.caption(t("task_center.no_related_anomaly"))
        with link_cols[1]:
            if task.order_id:
                if st.button(t("task_center.view_related_order", id=task.order_id), key=f"goto_order_{task.order_id}"):
                    st.session_state["selected_order_id"] = task.order_id
                    st.session_state["selected_task_id"] = None
                    st.switch_page("pages/02_customers_orders.py")
            else:
                st.caption(t("task_center.no_related_order"))

        st.divider()

        # --- 状态更新操作 ---
        if task.status in ("已完成", "已取消"):
            status_word = t("task_center.status_done") if task.status == "已完成" else t("task_center.status_cancelled")
            st.info(t("task_center.locked_status_note", status=status_word))
            if task.status == "已完成" and task.result:
                st.markdown(f"**{t('task_center.result_title')}**")
                st.write(task.result)
        else:
            st.markdown(f"### {t('task_center.update_task_title')}")

            action_cols = st.columns(3)

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

            st.divider()

            # 追加处理记录
            st.markdown(f"**{t('task_center.append_progress_title')}**")
            progress_note = st.text_area(t("task_center.progress_note_label"), key=f"progress_note_{task_id}", height=80)
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

            st.divider()

            # 完成任务（必须填写处理结果）
            st.markdown(f"### {t('task_center.complete_task_title')}")
            st.caption(t("task_center.complete_task_caption"))
            with st.form(key=f"complete_task_form_{task_id}"):
                result_text = st.text_area(t("task_center.result_input_label"), height=100)
                complete_submitted = st.form_submit_button(t("task_center.confirm_complete"))
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
            st.markdown(f"### {t('task_center.cancel_task_title')}")
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

        st.divider()

        # --- 处理记录时间线（追加式，按时间正序展示） ---
        st.markdown(f"### {t('task_center.timeline_title')}")
        if not logs:
            render_empty_state("empty.no_progress_log")
        else:
            for log in logs:
                st.markdown(f"**{log.created_at}** · {log.action} · {t('task_center.timeline_operator_label')}：{log.actor}")
                if log.content:
                    st.caption(log.content)
                st.divider()

else:
    # ==================================================================
    # 任务列表视图
    # ==================================================================

    filter_cols = st.columns([2, 2, 2, 2, 1])
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
        show_overdue_only = st.checkbox(
            t("task_center.only_overdue"), value=bool(pending_filter.get("overdue_only")), key="task_overdue_only"
        )
    with filter_cols[4]:
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
        header = st.columns([3, 1.5, 1.5, 2, 2, 2, 1])
        header_labels = [
            "task_center.col.title", "task_center.col.priority", "task_center.col.status",
            "task_center.col.assignee", "task_center.col.due", "task_center.col.related",
        ]
        for col, label_key in zip(header, header_labels):
            col.markdown(f"**{t(label_key)}**")
        header[-1].markdown("")

        for task_item in tasks[:200]:
            row = st.columns([3, 1.5, 1.5, 2, 2, 2, 1])
            row[0].write(task_item.title)
            with row[1]:
                render_priority_badge(task_item.priority)
            with row[2]:
                render_status_badge(task_item.status)
            row[3].write(task_item.assignee)
            row[4].write(task_item.due_at[:10])
            link_text = []
            if task_item.anomaly_id:
                link_text.append(t("task_center.related.anomaly"))
            if task_item.order_id:
                link_text.append(t("task_center.related.order"))
            row[5].write(" / ".join(link_text) if link_text else "—")
            if row[6].button(t("common.detail"), key=f"task_detail_{task_item.task_id}"):
                st.session_state["selected_task_id"] = task_item.task_id
                st.rerun()

render_sidebar_footer()
