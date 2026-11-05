"""
AI 异常诊断中心（AI Anomaly Diagnosis）。

页面结构：异常列表（筛选）↔ 异常详情（诊断）。

详情页分四区，物理上互不混淆（清晰区分"已知事实""AI推测""建议动作"
"需要核实"）：

    1. 【已知事实】触发规则 + evidence —— 来自 rule_engine，不经过AI，
       是数据库里的真实字段值。
    2. 【AI诊断（推测）】summary / possible_causes（标注confidence）/
       customer_impact —— 这是AI的归纳，每条原因都标注置信度。
    3. 【建议操作】recommendations / communication_draft —— AI给的建议，
       用户可以编辑、采纳或拒绝，采纳不会自动执行任何动作。
    4. 【待核实事项】verification_required —— 纯展示，提示用户哪些信息
       AI没有把握，需要人工去核实，不可操作。

视觉区分方式（重设计 §6.03）：不使用彩色卡片，而是通过区域标题、
一行说明文字、以及"已知事实"区单独的浅灰底色面板来表达
"系统确认" 与 "AI 推测" 的区别。

核心约束（未改变）：
    - AI 不会被自动触发——用户必须点击"运行 AI 诊断"按钮。
    - 创建任务前必须人工填写并确认表单，不会被诊断结果自动创建。
    - 页面不会把AI的任何输出包装成"系统事实"。

文案全部通过 config.i18n.t() 翻译。
"""

from __future__ import annotations

import html
import json
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
from config.i18n import t
from config.settings import get_config
from database.connection import get_connection
from repositories import anomaly_repository, order_repository
from services import anomaly_service, order_service, task_service

inject_base_styles()

render_page_header(title_key="anomaly_center.title", subtitle_key="anomaly_center.subtitle")

config = get_config()

if not guard_database_initialized():
    st.stop()

# 消费从驾驶舱传来的筛选条件。
pending_filter = st.session_state.pop("pending_filter", {})

if "selected_anomaly_id" not in st.session_state:
    st.session_state["selected_anomaly_id"] = None

CONFIDENCE_KEY_MAP = {"low": "risk.低", "medium": "risk.中", "high": "risk.高"}
RISK_LEVEL_KEY_MAP = {"low": "risk.低", "medium": "risk.中", "high": "risk.高"}

_FILTER_SPACER = '<div style="height: 26px"></div>'


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else value


def _badge(text_value: str, css_class: str) -> str:
    return f'<span class="fl-badge {css_class}">{html.escape(text_value)}</span>'


def _risk_css(severity: str) -> str:
    return {"高": "fl-badge-error", "中": "fl-badge-warning", "低": "fl-badge-success"}.get(
        severity, "fl-badge-neutral"
    )


def _status_css(status: str) -> str:
    return {
        "待确认": "fl-badge-warning",
        "处理中": "fl-badge-primary",
        "已解决": "fl-badge-success",
        "已关闭": "fl-badge-neutral",
        "误报": "fl-badge-neutral",
    }.get(status, "fl-badge-neutral")


# ----------------------------------------------------------------------
# 扫描入口：触发规则引擎对全部订单重新扫描。
# ----------------------------------------------------------------------

if not st.session_state["selected_anomaly_id"]:
    scan_col, info_col = st.columns([1.2, 4.8], vertical_alignment="center")
    with scan_col:
        if st.button(t("anomaly_center.scan_button"), key="run_anomaly_scan", help=t("anomaly_center.scan_help")):
            try:
                with get_connection(config.database_path) as conn:
                    scan_result = anomaly_service.scan_and_create_anomalies(conn)
                st.session_state["last_scan_result"] = scan_result
                st.rerun()
            except sqlite3.Error as exc:
                st.error(f"{t('common.loading_failed')}：{exc}")

    last_scan = st.session_state.pop("last_scan_result", None)
    if last_scan:
        with info_col:
            st.success(
                t(
                    "anomaly_center.scan_result",
                    scanned=last_scan["scanned"],
                    violations=last_scan["violations_found"],
                    created=last_scan["created"],
                    skipped=last_scan["skipped_duplicate"],
                )
            )


# ======================================================================
# 异常详情视图
# ======================================================================

if st.session_state["selected_anomaly_id"]:
    anomaly_id = st.session_state["selected_anomaly_id"]

    if st.button(f"← {t('common.back')}", key="back_from_anomaly_detail"):
        st.session_state["selected_anomaly_id"] = None
        st.rerun()

    try:
        with get_connection(config.database_path) as conn:
            anomaly = anomaly_repository.get_by_id(conn, anomaly_id)
    except sqlite3.Error as exc:
        st.error(f"{t('common.loading_failed')}：{exc}")
        anomaly = None

    if anomaly is None:
        render_empty_state("empty.anomaly_not_found")
    else:
        # --- 异常摘要（风险等级可人工修改并保存）---
        st.markdown(
            f"""
            <div class="fl-section">
                <div class="fl-section-title">{html.escape(anomaly.anomaly_type)}
                    <span class="fl-tag" style="margin-left:8px;">{html.escape(anomaly.anomaly_id)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        render_kv_list(
            [
                (t("anomaly_center.order_label"), html.escape(anomaly.order_id)),
                (t("anomaly_center.current_status"), _badge(t(f"status.{anomaly.status}"), _status_css(anomaly.status))),
                (t("anomaly_center.risk_level"), _badge(t(f"risk.{anomaly.severity}"), _risk_css(anomaly.severity))),
                (t("anomaly_center.detected_at_label"), html.escape(anomaly.detected_at[:16])),
            ],
            allow_html=True,
        )

        with st.expander(t("anomaly_center.edit_severity_expander")):
            severity_opts = ["高", "中", "低"]
            new_severity = st.selectbox(
                t("anomaly_center.new_severity"), severity_opts,
                index=severity_opts.index(anomaly.severity),
                format_func=lambda v: t(f"risk.{v}"),
                key=f"severity_select_{anomaly_id}",
            )
            if st.button(t("anomaly_center.save_severity"), key=f"save_severity_{anomaly_id}"):
                try:
                    with get_connection(config.database_path) as conn:
                        anomaly_service.update_severity(conn, anomaly_id, new_severity)
                    st.success(t("anomaly_center.severity_saved"))
                    st.rerun()
                except (sqlite3.Error, ValueError) as exc:
                    st.error(f"{t('common.loading_failed')}：{exc}")

        # --- 分区一：已知事实（来自规则引擎，不经过AI）---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("anomaly_center.section.facts", "anomaly_center.section.facts_caption")

        try:
            with get_connection(config.database_path) as conn:
                order_rows = order_repository.list_all_with_logistics(conn)
                order_row = next((r for r in order_rows if r["order_id"] == anomaly.order_id), None)
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            order_row = None

        if order_row is None:
            st.warning(t("anomaly_center.related_full_info_warning"))
            violations = []
        else:
            violations = anomaly_service.get_anomaly_evidence(order_row)
            matching = [v for v in violations if v.rule_code == anomaly.rule_code]

            if not matching:
                st.warning(t("anomaly_center.rule_stale_warning"))
                st.write(f"{t('anomaly_center.triggered_rule_code')}：{anomaly.rule_code}")
            else:
                violation = matching[0]
                fact_rows = [(t("anomaly_center.triggered_rule"), f"<strong>{html.escape(violation.rule_code)}</strong>")]
                fact_rows += [(str(key), html.escape(str(value))) for key, value in violation.evidence.items()]
                render_kv_list(fact_rows, allow_html=True, panel=True)

        with st.expander(t("anomaly_center.full_info_expander")):
            try:
                with get_connection(config.database_path) as conn:
                    order_detail = order_service.get_order_detail(conn, anomaly.order_id)
                if order_detail:
                    full_rows = [
                        (t("anomaly_center.full_info.customer"), f"{order_detail.customer.name}（{order_detail.customer.tier}）"),
                        (t("anomaly_center.full_info.supplier"), order_detail.supplier.name),
                        (t("anomaly_center.full_info.amount"), f"¥{order_detail.order.amount:,.2f}"),
                        (t("anomaly_center.full_info.order_status"), order_detail.order.status),
                    ]
                    if order_detail.logistics:
                        full_rows.append((t("anomaly_center.full_info.logistics_status"), order_detail.logistics.current_status))
                        full_rows.append((t("anomaly_center.full_info.logistics_updated"), order_detail.logistics.last_updated_at))
                    else:
                        full_rows.append((t("anomaly_center.full_info.logistics_status"), t("customers_orders.no_logistics")))
                    render_kv_list(full_rows)
            except (sqlite3.Error, RuntimeError) as exc:
                st.error(f"{t('common.loading_failed')}：{exc}")

        # --- 分区二：AI 诊断（推测）---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("anomaly_center.section.ai_diagnosis")

        try:
            with get_connection(config.database_path) as conn:
                history = anomaly_service.get_diagnosis_history(conn, anomaly_id)
        except sqlite3.Error as exc:
            st.error(f"{t('common.loading_failed')}：{exc}")
            history = []

        rerun_label = t("anomaly_center.rerun_diagnosis") if history else t("anomaly_center.run_diagnosis")
        if st.button(rerun_label, key=f"run_diagnosis_{anomaly_id}", disabled=order_row is None):
            try:
                with get_connection(config.database_path) as conn:
                    anomaly_service.run_diagnosis(conn, anomaly_id)
                st.success(t("anomaly_center.diagnosis_success"))
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))
            except Exception as exc:  # noqa: BLE001 — AI服务不可用时需明确提示而非崩溃
                st.error(t("anomaly_center.diagnosis_failed", error=exc))

        if not history:
            render_empty_state("anomaly_center.no_diagnosis_yet", hint_key="anomaly_center.no_diagnosis_hint")
            latest_diagnosis = None
        else:
            latest_diagnosis = history[0]
            mode_label = t("anomaly_center.mode_mock") if latest_diagnosis.model_type == "mock" else t("anomaly_center.mode_real")
            extra = f" · {t('anomaly_center.history_count_suffix')}: {len(history)}" if len(history) > 1 else ""
            st.caption(
                f"{t('anomaly_center.current_mode_label')}：{mode_label} · "
                f"{t('anomaly_center.last_generated_label')} {latest_diagnosis.generated_at}{extra}"
            )

            st.markdown(
                f'<div class="fl-panel-label" style="margin-top:14px;">{t("anomaly_center.summary_label")}</div>'
                f'<div style="font-size: var(--fl-fs-body); color: var(--fl-text); line-height: 1.6;">'
                f"{html.escape(latest_diagnosis.summary)}</div>",
                unsafe_allow_html=True,
            )

            causes = json.loads(latest_diagnosis.causes_json)
            st.markdown(
                f'<div class="fl-panel-label" style="margin-top:20px;">{t("anomaly_center.causes_title")}</div>',
                unsafe_allow_html=True,
            )
            for c in causes:
                conf_class = {"high": "fl-badge-success", "medium": "fl-badge-warning", "low": "fl-badge-neutral"}.get(
                    c["confidence"], "fl-badge-neutral"
                )
                evidence_html = (
                    f'<div class="fl-panel-note">{html.escape(t("anomaly_center.evidence_label"))}：'
                    f"{html.escape('; '.join(c['evidence']))}</div>"
                    if c.get("evidence")
                    else ""
                )
                st.markdown(
                    f"""
                    <div style="padding: 10px 0; border-bottom: 1px solid var(--fl-border);">
                        <div style="display:flex; align-items:baseline; gap:10px;">
                            <span style="font-size: var(--fl-fs-body); color: var(--fl-text);">{html.escape(c['cause'])}</span>
                            <span class="fl-badge {conf_class}">{html.escape(t('anomaly_center.confidence_label'))}
                                {html.escape(t(CONFIDENCE_KEY_MAP.get(c['confidence'], 'risk.低')))}</span>
                        </div>
                        {evidence_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.markdown(
                f'<div class="fl-panel-label" style="margin-top:20px;">{t("anomaly_center.impact_label")}</div>'
                f'<div style="font-size: var(--fl-fs-body); color: var(--fl-text); line-height: 1.6;">'
                f"{html.escape(latest_diagnosis.impact)}</div>"
                f'<div class="fl-panel-note" style="margin-top:10px;">'
                f"{html.escape(t('anomaly_center.risk_suggestion_label', level=t(RISK_LEVEL_KEY_MAP.get(latest_diagnosis.risk_suggestion, 'risk.低'))))}"
                f"</div>",
                unsafe_allow_html=True,
            )

            if len(history) > 1:
                with st.expander(t("anomaly_center.history_versions_expander", count=len(history))):
                    for i, h in enumerate(history):
                        st.caption(f"{t('anomaly_center.history_version_label')} {len(history) - i} · {h.generated_at}：{h.summary}")

        # --- 分区三：建议操作 ---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("anomaly_center.section.recommendations", "anomaly_center.section.recommendations_caption")

        if latest_diagnosis is None:
            render_empty_state("anomaly_center.no_recommendations_yet")
            recommendations = []
            communication_draft = ""
        else:
            recommendations = json.loads(latest_diagnosis.recommendations_json)
            communication_draft = latest_diagnosis.communication_draft

        if recommendations:
            accepted_recommendations = []
            for i, rec in enumerate(recommendations):
                if st.checkbox(rec, key=f"rec_{anomaly_id}_{i}"):
                    accepted_recommendations.append(rec)
        else:
            accepted_recommendations = []

        if communication_draft:
            st.markdown(
                f'<div class="fl-panel-label" style="margin-top:20px;">{t("anomaly_center.comm_draft_title")}</div>',
                unsafe_allow_html=True,
            )
            edited_draft = st.text_area(
                t("anomaly_center.comm_draft_edit_label"), value=communication_draft,
                key=f"comm_draft_{anomaly_id}", height=90,
            )

        # --- 分区四：待核实事项（纯展示，不可操作）---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("anomaly_center.section.verification", "anomaly_center.section.verification_caption")
        if latest_diagnosis is None:
            st.caption(t("anomaly_center.no_diagnosis_placeholder"))
        else:
            verification_items = json.loads(latest_diagnosis.verification_json)
            if not verification_items:
                st.caption(t("common.none"))
            else:
                for item in verification_items:
                    st.markdown(
                        f'<div style="font-size: var(--fl-fs-body); color: var(--fl-text-secondary); '
                        f'padding: 6px 0; border-bottom: 1px solid var(--fl-border);">· {html.escape(item)}</div>',
                        unsafe_allow_html=True,
                    )

        # --- 任务创建入口 ---
        st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
        render_section("anomaly_center.section.create_task")
        with st.form(key=f"create_task_form_{anomaly_id}"):
            default_title = t("anomaly_center.default_task_title", anomaly_type=anomaly.anomaly_type, order_id=anomaly.order_id)
            task_title = st.text_input(t("anomaly_center.task_title_label"), value=default_title)
            task_description_default = ""
            if accepted_recommendations:
                task_description_default = (
                    t("anomaly_center.adopted_recommendations_prefix") + "\n" +
                    "\n".join(f"- {r}" for r in accepted_recommendations)
                )
            task_description = st.text_area(t("anomaly_center.task_description_label"), value=task_description_default, height=100)
            form_cols = st.columns(3)
            with form_cols[0]:
                task_priority = st.selectbox(t("anomaly_center.priority_label"), ["P1", "P2", "P3"], index=0)
            with form_cols[1]:
                task_assignee = st.text_input(t("anomaly_center.assignee_label"))
            with form_cols[2]:
                task_due_date = st.date_input(t("anomaly_center.due_date_label"))

            submitted = st.form_submit_button(t("anomaly_center.confirm_create_task"), type="primary")

            if submitted:
                if not task_title.strip() or not task_assignee.strip():
                    st.error(t("anomaly_center.task_required_error"))
                else:
                    try:
                        due_at = datetime.combine(task_due_date, datetime.min.time()).strftime("%Y-%m-%dT%H:%M:%S")
                        with get_connection(config.database_path) as conn:
                            task = task_service.create_task(
                                conn,
                                title=task_title.strip(),
                                assignee=task_assignee.strip(),
                                due_at=due_at,
                                priority=task_priority,
                                description=task_description or None,
                                anomaly_id=anomaly_id,
                                order_id=anomaly.order_id,
                            )
                            anomaly_service.mark_in_progress(conn, anomaly_id)
                        st.success(t("anomaly_center.task_create_success", task_id=task.task_id))
                        st.session_state["selected_anomaly_id"] = None
                        st.session_state["pending_filter"] = {"task_id": task.task_id}
                        st.switch_page("views/04_task_center.py")
                    except task_service.TaskValidationError as exc:
                        st.error(f"{t('common.loading_failed')}：{exc}")
                    except sqlite3.Error as exc:
                        st.error(f"{t('common.loading_failed')}：{exc}")

else:
    # ==================================================================
    # 异常列表视图
    # ==================================================================

    filter_cols = st.columns([1.6, 1.2, 1.2, 2.2, 0.8])
    with filter_cols[0]:
        type_options = ["全部", "超时未发货", "物流延迟", "履约超时", "供应商备货异常", "订单状态异常"]
        default_type = pending_filter.get("anomaly_type", "全部")
        type_filter = st.selectbox(
            t("anomaly_center.anomaly_type"), type_options,
            index=type_options.index(default_type) if default_type in type_options else 0,
            format_func=_opt_label,
            key="anomaly_type_filter",
        )
    with filter_cols[1]:
        severity_options = ["全部", "高", "中", "低"]
        default_severity = pending_filter.get("severity", "全部")
        severity_filter = st.selectbox(
            t("anomaly_center.risk_level"), severity_options,
            index=severity_options.index(default_severity) if default_severity in severity_options else 0,
            format_func=lambda v: t("common.all") if v == "全部" else t(f"risk.{v}"),
            key="anomaly_severity_filter",
        )
    with filter_cols[2]:
        status_options = ["全部", "待确认", "处理中", "已解决", "已关闭", "误报"]
        default_status = pending_filter.get("status", "全部")
        status_filter = st.selectbox(
            t("anomaly_center.current_status"), status_options,
            index=status_options.index(default_status) if default_status in status_options else 0,
            format_func=lambda v: t("common.all") if v == "全部" else t(f"status.{v}"),
            key="anomaly_status_filter",
        )
    with filter_cols[3]:
        st.markdown('<div style="height: 26px"></div>', unsafe_allow_html=True)
        st.caption(t("anomaly_center.detect_time_filter_note"))
    with filter_cols[4]:
        st.markdown(_FILTER_SPACER, unsafe_allow_html=True)
        if render_reset_button(key="reset_anomaly_filters"):
            for key in ("anomaly_type_filter", "anomaly_severity_filter", "anomaly_status_filter"):
                st.session_state.pop(key, None)
            st.rerun()

    try:
        with get_connection(config.database_path) as conn:
            anomalies = anomaly_repository.list_all(
                conn,
                anomaly_type=None if type_filter == "全部" else type_filter,
                severity=None if severity_filter == "全部" else severity_filter,
                status=None if status_filter == "全部" else status_filter,
            )

            from repositories import task_repository

            anomaly_task_status: dict[str, str] = {}
            for a in anomalies:
                tasks = task_repository.list_by_anomaly(conn, a.anomaly_id)
                anomaly_task_status[a.anomaly_id] = tasks[0].status if tasks else t("anomaly_center.no_task_created")

    except sqlite3.Error as exc:
        st.error(f"{t('common.loading_failed')}：{exc}")
        anomalies = []
        anomaly_task_status = {}

    if not anomalies:
        render_empty_state("empty.no_anomalies", hint_key="empty.adjust_filter_hint")
    else:
        st.caption(f"{t('customers_orders.customer_count_prefix')} {len(anomalies)} {t('anomaly_center.list_count_suffix')}")

        visible_anomalies = anomalies[:200]
        rows = []
        for a in visible_anomalies:
            task_status_display = anomaly_task_status.get(a.anomaly_id, t("anomaly_center.no_task_created"))
            rows.append(
                {
                    t("anomaly_center.col.anomaly_id"): a.anomaly_id,
                    t("anomaly_center.col.order_id"): a.order_id,
                    t("anomaly_center.col.anomaly_type"): a.anomaly_type,
                    t("anomaly_center.col.detected_at"): a.detected_at[:16],
                    t("anomaly_center.col.risk"): t(f"risk.{a.severity}"),
                    t("anomaly_center.col.status"): t(f"status.{a.status}"),
                    t("anomaly_center.col.related_task"): (
                        task_status_display
                        if task_status_display == t("anomaly_center.no_task_created")
                        else t(f"status.{task_status_display}")
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="anomalies_table",
        )
        st.caption(t("anomaly_center.row_select_hint"))

        try:
            selected_rows = st.session_state["anomalies_table"].selection.rows
        except (AttributeError, KeyError, TypeError):
            selected_rows = []

        if selected_rows and 0 <= selected_rows[0] < len(visible_anomalies):
            st.session_state["selected_anomaly_id"] = visible_anomalies[selected_rows[0]].anomaly_id
            st.rerun()
