"""
AI 异常诊断中心（AI Anomaly Diagnosis）。

页面结构：异常列表（筛选）↔ 异常详情（诊断）。

详情页严格分四区展示，物理上互不混淆（清晰区分"已知事实""AI推测"
"建议动作""需要核实"）：

    1. 【已知事实】触发规则 + evidence —— 来自 rule_engine，不经过AI，
       是数据库里的真实字段值。
    2. 【AI诊断（推测）】summary / possible_causes（标注confidence）/
       customer_impact —— 这是AI的归纳，每条原因都标注置信度。
    3. 【建议操作】recommendations / communication_draft —— AI给的建议，
       用户可以编辑、采纳或拒绝，采纳不会自动执行任何动作。
    4. 【待核实事项】verification_required —— 纯展示，提示用户哪些信息
       AI没有把握，需要人工去核实，不可操作。

核心约束：
    - AI 不会被自动触发——用户必须点击"运行AI诊断"按钮。
    - 创建任务前必须人工填写并确认表单，不会被诊断结果自动创建。
    - 页面不会把AI的任何输出包装成"系统事实"。

文案全部通过 config.i18n.t() 翻译。
"""

from __future__ import annotations

import json
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
from components.status_badges import render_status_badge, render_risk_badge, render_priority_badge
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


def _opt_label(value: str) -> str:
    return t("common.all") if value == "全部" else value


# ----------------------------------------------------------------------
# 扫描入口：触发规则引擎对全部订单重新扫描。
# ----------------------------------------------------------------------

if not st.session_state["selected_anomaly_id"]:
    scan_col, info_col = st.columns([1, 4])
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

    if st.button(t("common.back"), key="back_from_anomaly_detail"):
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
        st.subheader(f"{anomaly.anomaly_type}（{anomaly.anomaly_id}）")

        summary_cols = st.columns(4)
        summary_cols[0].write(f"{t('anomaly_center.order_label')}：{anomaly.order_id}")
        with summary_cols[1]:
            st.write(t("anomaly_center.current_status"))
            render_status_badge(anomaly.status)
        with summary_cols[2]:
            st.write(t("anomaly_center.risk_level"))
            render_risk_badge(anomaly.severity)
        summary_cols[3].write(f"{t('anomaly_center.detected_at_label')}：{anomaly.detected_at[:16]}")

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

        st.divider()

        # --- 分区一：已知事实（来自规则引擎，不经过AI）---
        st.markdown(f"### {t('anomaly_center.section.facts')}")
        st.caption(t("anomaly_center.section.facts_caption"))

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
                st.write(f"{t('anomaly_center.triggered_rule')}：**{violation.rule_code}**")
                st.markdown(f"**{t('anomaly_center.evidence_title')}**")
                for key, value in violation.evidence.items():
                    st.caption(f"· {key} = {value}")

        with st.expander(t("anomaly_center.full_info_expander")):
            try:
                with get_connection(config.database_path) as conn:
                    order_detail = order_service.get_order_detail(conn, anomaly.order_id)
                if order_detail:
                    st.write(f"{t('anomaly_center.full_info.customer')}：{order_detail.customer.name}（{order_detail.customer.tier}）")
                    st.write(f"{t('anomaly_center.full_info.supplier')}：{order_detail.supplier.name}")
                    st.write(f"{t('anomaly_center.full_info.amount')}：¥{order_detail.order.amount:,.2f}")
                    st.write(f"{t('anomaly_center.full_info.order_status')}：{order_detail.order.status}")
                    if order_detail.logistics:
                        st.write(f"{t('anomaly_center.full_info.logistics_status')}：{order_detail.logistics.current_status}")
                        st.write(f"{t('anomaly_center.full_info.logistics_updated')}：{order_detail.logistics.last_updated_at}")
                    else:
                        st.caption(t("customers_orders.no_logistics"))
            except (sqlite3.Error, RuntimeError) as exc:
                st.error(f"{t('common.loading_failed')}：{exc}")

        st.divider()

        # --- 分区二：AI 诊断（推测）---
        st.markdown(f"### {t('anomaly_center.section.ai_diagnosis')}")

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
                f"{t('anomaly_center.current_mode_label')}：**{mode_label}** · "
                f"{t('anomaly_center.last_generated_label')} {latest_diagnosis.generated_at}{extra}"
            )

            st.markdown(f"**{t('anomaly_center.summary_label')}**：{latest_diagnosis.summary}")

            st.markdown(f"**{t('anomaly_center.causes_title')}**")
            causes = json.loads(latest_diagnosis.causes_json)
            for c in causes:
                conf_label = t(CONFIDENCE_KEY_MAP.get(c["confidence"], "risk.低"))
                st.write(f"- {c['cause']} — {t('anomaly_center.confidence_label')}：**{conf_label}**")
                if c.get("evidence"):
                    st.caption(f"  {t('anomaly_center.evidence_label')}：{'; '.join(c['evidence'])}")

            st.markdown(f"**{t('anomaly_center.impact_label')}**：{latest_diagnosis.impact}")

            risk_label = t(RISK_LEVEL_KEY_MAP.get(latest_diagnosis.risk_suggestion, "risk.低"))
            st.markdown(t("anomaly_center.risk_suggestion_label", level=risk_label))

            if len(history) > 1:
                with st.expander(t("anomaly_center.history_versions_expander", count=len(history))):
                    for i, h in enumerate(history):
                        st.caption(f"{t('anomaly_center.history_version_label')} {len(history) - i} · {h.generated_at}：{h.summary}")

        st.divider()

        # --- 分区三：建议操作 ---
        st.markdown(f"### {t('anomaly_center.section.recommendations')}")
        st.caption(t("anomaly_center.section.recommendations_caption"))

        if latest_diagnosis is None:
            render_empty_state("anomaly_center.no_recommendations_yet")
            recommendations = []
            communication_draft = ""
        else:
            recommendations = json.loads(latest_diagnosis.recommendations_json)
            communication_draft = latest_diagnosis.communication_draft

        if recommendations:
            st.markdown(f"**{t('anomaly_center.recommendations_title')}**")
            accepted_recommendations = []
            for i, rec in enumerate(recommendations):
                checked = st.checkbox(rec, key=f"rec_{anomaly_id}_{i}")
                if checked:
                    accepted_recommendations.append(rec)
        else:
            accepted_recommendations = []

        if communication_draft:
            st.markdown(f"**{t('anomaly_center.comm_draft_title')}**")
            edited_draft = st.text_area(
                t("anomaly_center.comm_draft_edit_label"), value=communication_draft,
                key=f"comm_draft_{anomaly_id}", height=80,
            )

        st.divider()

        # --- 分区四：待核实事项（纯展示，不可操作）---
        st.markdown(f"### {t('anomaly_center.section.verification')}")
        st.caption(t("anomaly_center.section.verification_caption"))
        if latest_diagnosis is None:
            st.caption(t("anomaly_center.no_diagnosis_placeholder"))
        else:
            verification_items = json.loads(latest_diagnosis.verification_json)
            if not verification_items:
                st.caption(t("common.none"))
            else:
                for item in verification_items:
                    st.write(f"· {item}")

        st.divider()

        # --- 任务创建入口 ---
        st.markdown(f"### {t('anomaly_center.section.create_task')}")
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

            submitted = st.form_submit_button(t("anomaly_center.confirm_create_task"))

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
                        st.switch_page("pages/04_task_center.py")
                    except task_service.TaskValidationError as exc:
                        st.error(f"{t('common.loading_failed')}：{exc}")
                    except sqlite3.Error as exc:
                        st.error(f"{t('common.loading_failed')}：{exc}")

else:
    # ==================================================================
    # 异常列表视图
    # ==================================================================

    filter_cols = st.columns([2, 2, 2, 2, 1])
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
        st.caption(t("anomaly_center.detect_time_filter_note"))
    with filter_cols[4]:
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
        header = st.columns([2, 2, 2, 2, 1.5, 1.5, 2, 1])
        header_labels = [
            "anomaly_center.col.anomaly_id", "anomaly_center.col.order_id", "anomaly_center.col.anomaly_type",
            "anomaly_center.col.detected_at", "anomaly_center.col.risk", "anomaly_center.col.status",
            "anomaly_center.col.related_task",
        ]
        for col, label_key in zip(header, header_labels):
            col.markdown(f"**{t(label_key)}**")
        header[-1].markdown("")

        for a in anomalies[:200]:
            row = st.columns([2, 2, 2, 2, 1.5, 1.5, 2, 1])
            row[0].write(a.anomaly_id)
            row[1].write(a.order_id)
            row[2].write(a.anomaly_type)
            row[3].write(a.detected_at[:16])
            with row[4]:
                render_risk_badge(a.severity)
            with row[5]:
                render_status_badge(a.status)
            task_status_display = anomaly_task_status.get(a.anomaly_id, t("anomaly_center.no_task_created"))
            row[6].write(task_status_display)
            if row[7].button(t("common.detail"), key=f"anomaly_detail_{a.anomaly_id}"):
                st.session_state["selected_anomaly_id"] = a.anomaly_id
                st.rerun()

render_sidebar_footer()
