"""
国际化（i18n）翻译字典与查词函数。

设计原则（对应需求文档 §4.1）：
    - 统一的语言字典机制，不在页面里散落硬编码的双语字符串替换。
    - 页面代码调用 t("some.key") 获取当前语言下的文案，不直接拼接
      中/英文字符串。
    - 业务数据（客户名称、订单内容等）不在此字典中维护，这里只收录
      系统 UI 文案（导航、标题、按钮、表头、状态、提示信息等）。
    - 未登记的 key 或缺失的语言条目会回退到 key 本身（并在开发时容易
      发现遗漏），不会导致页面崩溃。

当前语言的存取通过 get_current_language() / set_current_language()
读写 st.session_state，由 services/preferences_service.py 在应用启动时
把持久化的用户偏好写入 session_state，页面内只需要调用 t()。
"""

from __future__ import annotations

import streamlit as st

LANG_ZH = "zh"
LANG_EN = "en"
SUPPORTED_LANGUAGES: tuple[str, ...] = (LANG_ZH, LANG_EN)
DEFAULT_LANGUAGE = LANG_ZH

_SESSION_KEY = "flowlens_language"

LANGUAGE_LABELS = {
    LANG_ZH: "简体中文",
    LANG_EN: "English",
}

# ------------------------------------------------------------------
# 翻译字典。key 命名采用 "模块.用途" 的两段式命名，便于查找和维护。
# ------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- 应用通用 ---
    "app.name": {LANG_ZH: "FlowLens AI", LANG_EN: "FlowLens AI"},
    "app.tagline": {
        LANG_ZH: "B2B 智能履约与运营分析平台",
        LANG_EN: "AI-Powered B2B Commerce Operations Platform",
    },

    # --- 导航 ---
    "nav.dashboard": {LANG_ZH: "运营总览", LANG_EN: "Operations Overview"},
    "nav.customers_orders": {LANG_ZH: "客户与订单", LANG_EN: "Customers & Orders"},
    "nav.anomaly_center": {LANG_ZH: "AI 异常诊断", LANG_EN: "AI Anomaly Diagnosis"},
    "nav.task_center": {LANG_ZH: "运营任务", LANG_EN: "Operations Tasks"},
    "nav.analytics": {LANG_ZH: "运营分析", LANG_EN: "Operations Analytics"},
    "nav.settings": {LANG_ZH: "个性化设置", LANG_EN: "Personalization Settings"},
    "nav.section.business": {LANG_ZH: "业务模块", LANG_EN: "Business Modules"},
    "nav.section.personal": {LANG_ZH: "个人设置", LANG_EN: "Personal"},

    # --- 通用控件文案 ---
    "common.save": {LANG_ZH: "保存设置", LANG_EN: "Save Settings"},
    "common.reset_default": {LANG_ZH: "恢复默认设置", LANG_EN: "Restore Defaults"},
    "common.reset_filter": {LANG_ZH: "重置筛选", LANG_EN: "Reset Filters"},
    "common.back": {LANG_ZH: "← 返回列表", LANG_EN: "← Back to List"},
    "common.detail": {LANG_ZH: "详情", LANG_EN: "Details"},
    "common.all": {LANG_ZH: "全部", LANG_EN: "All"},
    "common.yes": {LANG_ZH: "是", LANG_EN: "Yes"},
    "common.no": {LANG_ZH: "否", LANG_EN: "No"},
    "common.none": {LANG_ZH: "无", LANG_EN: "None"},
    "common.not_available": {LANG_ZH: "暂无数据", LANG_EN: "No data"},
    "common.loading_failed": {LANG_ZH: "查询失败", LANG_EN: "Query failed"},
    "common.save_success": {LANG_ZH: "设置已保存。", LANG_EN: "Settings saved."},
    "common.save_failed": {LANG_ZH: "保存失败，请重试。", LANG_EN: "Save failed, please try again."},
    "common.env_label": {LANG_ZH: "环境", LANG_EN: "Environment"},
    "common.ai_mock_mode": {
        LANG_ZH: "AI 模式：Mock（未调用真实大模型）",
        LANG_EN: "AI Mode: Mock (no real LLM calls)",
    },
    "common.db_not_initialized": {LANG_ZH: "数据库尚未初始化。", LANG_EN: "Database not initialized yet."},
    "common.db_init_hint": {
        LANG_ZH: "请在项目根目录运行以下命令生成模拟数据后刷新本页：",
        LANG_EN: "Please run the following command in the project root to generate sample data, then refresh this page:",
    },

    # --- 空状态与提示 ---
    "empty.no_customers": {LANG_ZH: "没有符合条件的客户。", LANG_EN: "No customers match the filters."},
    "empty.no_orders": {LANG_ZH: "没有符合条件的订单。", LANG_EN: "No orders match the filters."},
    "empty.no_anomalies": {LANG_ZH: "没有符合条件的异常。", LANG_EN: "No anomalies match the filters."},
    "empty.no_tasks": {LANG_ZH: "没有符合条件的任务。", LANG_EN: "No tasks match the filters."},
    "empty.adjust_filter_hint": {
        LANG_ZH: "可以尝试调整筛选条件或点击重置。",
        LANG_EN: "Try adjusting the filters or click reset.",
    },
    "empty.customer_not_found": {LANG_ZH: "未找到该客户，可能已被删除。", LANG_EN: "Customer not found (may have been deleted)."},
    "empty.order_not_found": {LANG_ZH: "未找到该订单，可能已被删除。", LANG_EN: "Order not found (may have been deleted)."},
    "empty.anomaly_not_found": {LANG_ZH: "未找到该异常，可能已被删除。", LANG_EN: "Anomaly not found (may have been deleted)."},
    "empty.task_not_found": {LANG_ZH: "未找到该任务，可能已被删除。", LANG_EN: "Task not found (may have been deleted)."},
    "empty.no_customer_orders": {LANG_ZH: "该客户暂无订单记录。", LANG_EN: "This customer has no orders yet."},
    "empty.no_customer_anomalies": {LANG_ZH: "该客户暂无异常记录。", LANG_EN: "This customer has no anomalies yet."},
    "empty.no_order_items": {LANG_ZH: "暂无商品明细。", LANG_EN: "No item details available."},
    "empty.no_trend_data": {LANG_ZH: "暂无趋势数据。", LANG_EN: "No trend data available."},
    "empty.no_anomaly_data": {LANG_ZH: "暂无异常数据。", LANG_EN: "No anomaly data available."},
    "empty.no_risk_data": {LANG_ZH: "暂无风险数据。", LANG_EN: "No risk data available."},
    "empty.no_customer_anomaly_data": {LANG_ZH: "暂无客户异常数据。", LANG_EN: "No customer anomaly data available."},
    "empty.no_delivered_orders": {LANG_ZH: "暂无已签收订单。", LANG_EN: "No delivered orders available."},
    "empty.no_task_data": {LANG_ZH: "暂无任务数据。", LANG_EN: "No task data available."},
    "empty.no_progress_log": {LANG_ZH: "暂无处理记录。", LANG_EN: "No progress log yet."},
    "empty.db_empty": {LANG_ZH: "数据库中还没有任何订单数据。", LANG_EN: "No order data in the database yet."},
    "empty.db_empty_hint": {
        LANG_ZH: "请在项目根目录运行 `python -m database.seed_data` 生成模拟数据后刷新本页。",
        LANG_EN: "Please run `python -m database.seed_data` in the project root to generate sample data, then refresh this page.",
    },
    "empty.no_todo_tasks": {LANG_ZH: "当前没有逾期或高优先级待处理任务。", LANG_EN: "No overdue or high-priority pending tasks."},
    "empty.no_todo_tasks_hint": {
        LANG_ZH: "所有任务都在正常处理节奏内，或者还没有创建任务。",
        LANG_EN: "All tasks are on track, or no tasks have been created yet.",
    },
    "empty.task_hint_create_from_anomaly": {
        LANG_ZH: "可以在「AI 异常诊断」从异常创建任务，或调整筛选条件。",
        LANG_EN: "You can create a task from an anomaly in \"AI Anomaly Diagnosis\", or adjust the filters.",
    },

    # --- 运营总览（Dashboard） ---
    "dashboard.title": {LANG_ZH: "运营总览", LANG_EN: "Operations Overview"},
    "dashboard.subtitle": {
        LANG_ZH: "整体业务运行状态及需要优先关注的风险",
        LANG_EN: "Overall business status and risks that need attention",
    },
    "dashboard.kpi_hint": {
        LANG_ZH: "点击任意 KPI 卡片可跳转到对应列表并带入筛选条件。履约完成率的具体口径见「运营分析」页面说明。",
        LANG_EN: "Click any KPI card to jump to the related list with filters applied. See \"Operations Analytics\" for the fulfillment rate definition.",
    },
    "dashboard.kpi.total_orders": {LANG_ZH: "订单总量", LANG_EN: "Total Orders"},
    "dashboard.kpi.anomaly_orders": {LANG_ZH: "异常订单数", LANG_EN: "Anomaly Orders"},
    "dashboard.kpi.pending_anomalies": {LANG_ZH: "待处理异常", LANG_EN: "Pending Anomalies"},
    "dashboard.kpi.fulfillment_rate": {LANG_ZH: "履约完成率", LANG_EN: "Fulfillment Rate"},
    "dashboard.kpi.fulfillment_rate_help": {
        LANG_ZH: "已签收且按时的订单 / 已到预计送达时间的有效订单",
        LANG_EN: "On-time delivered orders / valid orders past expected delivery date",
    },
    "dashboard.kpi.overdue_tasks": {LANG_ZH: "逾期任务数", LANG_EN: "Overdue Tasks"},
    "dashboard.trend_title": {LANG_ZH: "订单量趋势（近 7 天）", LANG_EN: "Order Volume Trend (Last 7 Days)"},
    "dashboard.anomaly_dist_title": {LANG_ZH: "异常类型分布", LANG_EN: "Anomaly Type Distribution"},
    "dashboard.risk_dist_title": {LANG_ZH: "风险分布", LANG_EN: "Risk Distribution"},
    "dashboard.todo_title": {LANG_ZH: "待办任务", LANG_EN: "To-Do Tasks"},
    "dashboard.assignee_label": {LANG_ZH: "负责人", LANG_EN: "Assignee"},
    "dashboard.view_button": {LANG_ZH: "查看", LANG_EN: "View"},
    "dashboard.plotly_missing": {LANG_ZH: "Plotly 未安装，暂以表格形式展示趋势数据。", LANG_EN: "Plotly not installed; showing trend as a table."},
    "dashboard.chart.date_axis": {LANG_ZH: "日期", LANG_EN: "Date"},
    "dashboard.chart.order_count_axis": {LANG_ZH: "订单数量", LANG_EN: "Order Count"},
    "dashboard.chart.order_count_series": {LANG_ZH: "订单量", LANG_EN: "Orders"},
    "dashboard.count_suffix": {LANG_ZH: "条", LANG_EN: ""},
    "dashboard.severity_high": {LANG_ZH: "高风险", LANG_EN: "High Risk"},
    "dashboard.severity_medium": {LANG_ZH: "中风险", LANG_EN: "Medium Risk"},
    "dashboard.severity_low": {LANG_ZH: "低风险", LANG_EN: "Low Risk"},

    # --- 客户与订单 ---
    "customers_orders.title": {LANG_ZH: "客户与订单", LANG_EN: "Customers & Orders"},
    "customers_orders.subtitle": {
        LANG_ZH: "查询业务对象和履约上下文",
        LANG_EN: "Browse customers, orders and fulfillment context",
    },
    "customers_orders.tab.customers": {LANG_ZH: "客户列表", LANG_EN: "Customers"},
    "customers_orders.tab.orders": {LANG_ZH: "订单列表", LANG_EN: "Orders"},
    "customers_orders.search_customer_name": {LANG_ZH: "搜索客户名称", LANG_EN: "Search customer name"},
    "customers_orders.industry": {LANG_ZH: "行业", LANG_EN: "Industry"},
    "customers_orders.tier": {LANG_ZH: "客户等级", LANG_EN: "Customer Tier"},
    "customers_orders.coop_status": {LANG_ZH: "合作状态", LANG_EN: "Cooperation Status"},
    "customers_orders.total_amount": {LANG_ZH: "累计采购金额", LANG_EN: "Total Purchase Amount"},
    "customers_orders.related_orders": {LANG_ZH: "关联订单", LANG_EN: "Related Orders"},
    "customers_orders.related_anomalies": {LANG_ZH: "关联异常", LANG_EN: "Related Anomalies"},
    "customers_orders.realtime_note": {
        LANG_ZH: "（以下数据实时查询自数据库）",
        LANG_EN: "(data below is queried from the database in real time)",
    },
    "customers_orders.jump_anomaly_hint": {
        LANG_ZH: "点击「AI 异常诊断」导航查看异常详情与诊断（本页不重复实现异常详情）。",
        LANG_EN: "Go to \"AI Anomaly Diagnosis\" to view anomaly details and diagnosis.",
    },
    "customers_orders.col.customer_name": {LANG_ZH: "客户名称", LANG_EN: "Customer"},
    "customers_orders.col.order_count": {LANG_ZH: "订单数", LANG_EN: "Orders"},
    "customers_orders.col.anomaly_count": {LANG_ZH: "异常数", LANG_EN: "Anomalies"},
    "customers_orders.customer_count_prefix": {LANG_ZH: "共", LANG_EN: "Total"},
    "customers_orders.customer_count_suffix": {LANG_ZH: "个客户", LANG_EN: "customers"},
    "customers_orders.order_count_suffix": {LANG_ZH: "条订单（展示前 100 条）", LANG_EN: "orders (showing first 100)"},
    "customers_orders.search_order_id": {LANG_ZH: "搜索订单编号", LANG_EN: "Search order ID"},
    "customers_orders.order_status": {LANG_ZH: "订单状态", LANG_EN: "Order Status"},
    "customers_orders.logistics_status": {LANG_ZH: "物流状态", LANG_EN: "Logistics Status"},
    "customers_orders.col.order_id": {LANG_ZH: "订单编号", LANG_EN: "Order ID"},
    "customers_orders.col.customer": {LANG_ZH: "客户", LANG_EN: "Customer"},
    "customers_orders.col.amount": {LANG_ZH: "金额", LANG_EN: "Amount"},
    "customers_orders.col.order_date": {LANG_ZH: "下单日期", LANG_EN: "Order Date"},
    "customers_orders.col.anomaly": {LANG_ZH: "异常", LANG_EN: "Anomaly"},
    "customers_orders.order_summary.customer": {LANG_ZH: "客户", LANG_EN: "Customer"},
    "customers_orders.order_summary.amount": {LANG_ZH: "金额", LANG_EN: "Amount"},
    "customers_orders.order_summary.order_status": {LANG_ZH: "订单状态", LANG_EN: "Order Status"},
    "customers_orders.order_summary.logistics_status": {LANG_ZH: "物流状态", LANG_EN: "Logistics Status"},
    "customers_orders.no_logistics": {LANG_ZH: "暂无物流记录", LANG_EN: "No logistics record"},
    "customers_orders.anomaly_warning": {
        LANG_ZH: "⚠️ 该订单关联 {count} 条异常记录，请到「AI 异常诊断」查看详情。",
        LANG_EN: "⚠️ This order has {count} related anomalies. See \"AI Anomaly Diagnosis\" for details.",
    },
    "customers_orders.item_details_title": {LANG_ZH: "商品明细", LANG_EN: "Order Items"},
    "customers_orders.item.product": {LANG_ZH: "商品", LANG_EN: "Product"},
    "customers_orders.item.quantity": {LANG_ZH: "数量", LANG_EN: "Qty"},
    "customers_orders.item.unit_price": {LANG_ZH: "单价", LANG_EN: "Unit Price"},
    "customers_orders.item.subtotal": {LANG_ZH: "小计", LANG_EN: "Subtotal"},
    "customers_orders.timeline_title": {LANG_ZH: "履约时间线", LANG_EN: "Fulfillment Timeline"},
    "customers_orders.timeline.order_placed": {LANG_ZH: "下单", LANG_EN: "Order Placed"},
    "customers_orders.timeline.expected_ship": {LANG_ZH: "预计发货", LANG_EN: "Expected Ship"},
    "customers_orders.timeline.actual_ship": {LANG_ZH: "实际发货", LANG_EN: "Actual Ship"},
    "customers_orders.timeline.expected_delivery": {LANG_ZH: "预计送达", LANG_EN: "Expected Delivery"},
    "customers_orders.timeline.actual_delivery": {LANG_ZH: "实际签收", LANG_EN: "Actual Delivery"},
    "customers_orders.timeline.not_yet": {LANG_ZH: "尚未发生", LANG_EN: "Not yet"},
    "customers_orders.logistics_events_title": {LANG_ZH: "物流节点", LANG_EN: "Logistics Events"},
    "customers_orders.supplier_title": {LANG_ZH: "供应商信息", LANG_EN: "Supplier Information"},
    "customers_orders.supplier.name": {LANG_ZH: "供应商", LANG_EN: "Supplier"},
    "customers_orders.supplier.category": {LANG_ZH: "类别", LANG_EN: "Category"},
    "customers_orders.supplier.lead_time": {LANG_ZH: "备货周期", LANG_EN: "Lead Time"},
    "customers_orders.supplier.days_suffix": {LANG_ZH: "天", LANG_EN: "days"},
    "customers_orders.view_customer_detail": {LANG_ZH: "查看客户详情 →", LANG_EN: "View Customer Detail →"},

    # --- AI 异常诊断 ---
    "anomaly_center.title": {LANG_ZH: "AI 异常诊断中心", LANG_EN: "AI Anomaly Diagnosis Center"},
    "anomaly_center.subtitle": {
        LANG_ZH: "识别、理解和确认异常 — 规则引擎负责判断，AI 仅提供辅助分析",
        LANG_EN: "Identify, understand, and confirm anomalies — the rule engine judges, AI only assists",
    },
    "anomaly_center.scan_button": {LANG_ZH: "🔄 扫描新异常", LANG_EN: "🔄 Scan for New Anomalies"},
    "anomaly_center.scan_help": {
        LANG_ZH: "对全部订单重新运行规则引擎，发现新异常",
        LANG_EN: "Re-run the rule engine against all orders to find new anomalies",
    },
    "anomaly_center.scan_result": {
        LANG_ZH: "扫描完成：共扫描 {scanned} 条订单，命中 {violations} 条规则违规，新建 {created} 条异常，{skipped} 条因已存在活跃异常被跳过（未重复创建）。",
        LANG_EN: "Scan complete: {scanned} orders scanned, {violations} rule violations found, {created} new anomalies created, {skipped} skipped (already has an active anomaly).",
    },
    "anomaly_center.risk_level": {LANG_ZH: "风险等级", LANG_EN: "Risk Level"},
    "anomaly_center.current_status": {LANG_ZH: "当前状态", LANG_EN: "Current Status"},
    "anomaly_center.order_label": {LANG_ZH: "订单", LANG_EN: "Order"},
    "anomaly_center.detected_at_label": {LANG_ZH: "发现时间", LANG_EN: "Detected At"},
    "anomaly_center.edit_severity_expander": {LANG_ZH: "修改风险等级（人工操作）", LANG_EN: "Edit Risk Level (Manual)"},
    "anomaly_center.new_severity": {LANG_ZH: "新风险等级", LANG_EN: "New Risk Level"},
    "anomaly_center.save_severity": {LANG_ZH: "保存风险等级", LANG_EN: "Save Risk Level"},
    "anomaly_center.severity_saved": {LANG_ZH: "风险等级已更新。", LANG_EN: "Risk level updated."},
    "anomaly_center.section.facts": {LANG_ZH: "📋 已知事实", LANG_EN: "📋 Known Facts"},
    "anomaly_center.section.facts_caption": {
        LANG_ZH: "以下内容来自系统规则判断和数据库字段，不经过AI加工。",
        LANG_EN: "The following comes from rule-engine checks and database fields — not AI-generated.",
    },
    "anomaly_center.rule_stale_warning": {
        LANG_ZH: "⚠️ 该订单当前数据已不满足触发该异常时的规则条件（例如可能已被处理）。以下仅展示异常记录本身的信息，规则依据可能已失效。",
        LANG_EN: "⚠️ This order's current data no longer meets the condition that triggered this anomaly (it may have been resolved already). Only the anomaly record itself is shown below; the rule evidence may be stale.",
    },
    "anomaly_center.triggered_rule_code": {LANG_ZH: "触发规则代码", LANG_EN: "Triggered Rule Code"},
    "anomaly_center.triggered_rule": {LANG_ZH: "触发规则", LANG_EN: "Triggered Rule"},
    "anomaly_center.evidence_title": {LANG_ZH: "关键字段依据：", LANG_EN: "Key Field Evidence:"},
    "anomaly_center.full_info_expander": {
        LANG_ZH: "查看订单/客户/供应商/物流完整信息",
        LANG_EN: "View Full Order/Customer/Supplier/Logistics Info",
    },
    "anomaly_center.full_info.customer": {LANG_ZH: "客户", LANG_EN: "Customer"},
    "anomaly_center.full_info.supplier": {LANG_ZH: "供应商", LANG_EN: "Supplier"},
    "anomaly_center.full_info.amount": {LANG_ZH: "订单金额", LANG_EN: "Order Amount"},
    "anomaly_center.full_info.order_status": {LANG_ZH: "订单状态", LANG_EN: "Order Status"},
    "anomaly_center.full_info.logistics_status": {LANG_ZH: "物流状态", LANG_EN: "Logistics Status"},
    "anomaly_center.full_info.logistics_updated": {LANG_ZH: "物流最后更新", LANG_EN: "Logistics Last Updated"},
    "anomaly_center.section.ai_diagnosis": {LANG_ZH: "🤖 AI 诊断（推测，非确定事实）", LANG_EN: "🤖 AI Diagnosis (Inference, Not Fact)"},
    "anomaly_center.run_diagnosis": {LANG_ZH: "▶️ 运行 AI 诊断", LANG_EN: "▶️ Run AI Diagnosis"},
    "anomaly_center.rerun_diagnosis": {LANG_ZH: "🔄 重新分析", LANG_EN: "🔄 Re-analyze"},
    "anomaly_center.diagnosis_success": {LANG_ZH: "诊断已完成。", LANG_EN: "Diagnosis completed."},
    "anomaly_center.diagnosis_failed": {
        LANG_ZH: "AI 诊断失败：{error}\n\n规则判断结果和事实依据仍然可用，你可以直接基于已知事实手动创建任务。",
        LANG_EN: "AI diagnosis failed: {error}\n\nRule-engine results and known facts are still available; you can create a task manually based on them.",
    },
    "anomaly_center.no_diagnosis_yet": {LANG_ZH: "还没有运行过AI诊断。", LANG_EN: "AI diagnosis has not been run yet."},
    "anomaly_center.no_diagnosis_hint": {
        LANG_ZH: "点击上方「运行AI诊断」按钮生成摘要、可能原因和处理建议（当前为Mock模式，不调用真实大模型）。",
        LANG_EN: "Click \"Run AI Diagnosis\" above to generate a summary, possible causes, and recommendations (Mock mode, no real LLM calls).",
    },
    "anomaly_center.mode_mock": {LANG_ZH: "Mock（未调用真实大模型）", LANG_EN: "Mock (no real LLM calls)"},
    "anomaly_center.mode_real": {LANG_ZH: "真实模型", LANG_EN: "Real Model"},
    "anomaly_center.current_mode_label": {LANG_ZH: "当前模式", LANG_EN: "Current Mode"},
    "anomaly_center.last_generated_label": {LANG_ZH: "最近生成于", LANG_EN: "Last generated at"},
    "anomaly_center.history_count_suffix": {LANG_ZH: "次历史诊断记录", LANG_EN: "historical diagnoses"},
    "anomaly_center.summary_label": {LANG_ZH: "摘要", LANG_EN: "Summary"},
    "anomaly_center.causes_title": {
        LANG_ZH: "可能原因（标注置信度，均为AI推测，非确定结论）：",
        LANG_EN: "Possible Causes (with confidence, all AI inference, not confirmed facts):",
    },
    "anomaly_center.confidence_label": {LANG_ZH: "置信度", LANG_EN: "Confidence"},
    "anomaly_center.evidence_label": {LANG_ZH: "依据", LANG_EN: "Evidence"},
    "anomaly_center.impact_label": {LANG_ZH: "客户影响分析", LANG_EN: "Customer Impact Analysis"},
    "anomaly_center.risk_suggestion_label": {
        LANG_ZH: "AI建议风险等级：{level}（供参考，最终以上方人工设置的风险等级为准）",
        LANG_EN: "AI-suggested risk level: {level} (for reference only, the manually set level above is authoritative)",
    },
    "anomaly_center.history_versions_expander": {
        LANG_ZH: "查看历史诊断版本（共{count}条）",
        LANG_EN: "View historical diagnosis versions ({count} total)",
    },
    "anomaly_center.history_version_label": {LANG_ZH: "版本", LANG_EN: "Version"},
    "anomaly_center.section.recommendations": {LANG_ZH: "✅ 建议操作", LANG_EN: "✅ Recommended Actions"},
    "anomaly_center.section.recommendations_caption": {
        LANG_ZH: "以下建议由AI生成，均需人工确认后才会生效，不会自动执行。",
        LANG_EN: "The following suggestions are AI-generated. They require manual confirmation and are never auto-executed.",
    },
    "anomaly_center.no_recommendations_yet": {
        LANG_ZH: "运行AI诊断后，这里会显示可操作的建议。",
        LANG_EN: "Actionable recommendations will appear here after running AI diagnosis.",
    },
    "anomaly_center.recommendations_title": {LANG_ZH: "AI 建议措施：", LANG_EN: "AI Suggested Actions:"},
    "anomaly_center.comm_draft_title": {
        LANG_ZH: "沟通参考文本（仅供参考，不会自动发送给任何人）：",
        LANG_EN: "Communication Draft (for reference only, never sent automatically):",
    },
    "anomaly_center.comm_draft_edit_label": {LANG_ZH: "可编辑后自行复制使用", LANG_EN: "Editable — copy to use"},
    "anomaly_center.section.verification": {LANG_ZH: "❓ 待核实事项", LANG_EN: "❓ Items to Verify"},
    "anomaly_center.section.verification_caption": {
        LANG_ZH: "以下信息AI没有把握，标记为需要人工核实，仅供参考，不可直接采信为事实。",
        LANG_EN: "AI is not confident about the following items; they require manual verification and should not be treated as fact.",
    },
    "anomaly_center.no_diagnosis_placeholder": {LANG_ZH: "（尚无诊断结果）", LANG_EN: "(No diagnosis yet)"},
    "anomaly_center.section.create_task": {LANG_ZH: "📝 创建运营任务", LANG_EN: "📝 Create Operations Task"},
    "anomaly_center.task_title_label": {LANG_ZH: "任务标题 *", LANG_EN: "Task Title *"},
    "anomaly_center.default_task_title": {
        LANG_ZH: "处理异常：{anomaly_type}（{order_id}）",
        LANG_EN: "Resolve anomaly: {anomaly_type} ({order_id})",
    },
    "anomaly_center.task_description_label": {LANG_ZH: "任务描述", LANG_EN: "Task Description"},
    "anomaly_center.adopted_recommendations_prefix": {LANG_ZH: "已采纳的AI建议：", LANG_EN: "Adopted AI recommendations:"},
    "anomaly_center.priority_label": {LANG_ZH: "优先级", LANG_EN: "Priority"},
    "anomaly_center.assignee_label": {LANG_ZH: "负责人 *", LANG_EN: "Assignee *"},
    "anomaly_center.due_date_label": {LANG_ZH: "截止日期 *", LANG_EN: "Due Date *"},
    "anomaly_center.confirm_create_task": {LANG_ZH: "确认创建任务", LANG_EN: "Confirm Create Task"},
    "anomaly_center.task_required_error": {LANG_ZH: "任务标题和负责人为必填项。", LANG_EN: "Task title and assignee are required."},
    "anomaly_center.task_create_success": {
        LANG_ZH: "任务已创建：{task_id}，异常状态已更新为「处理中」。",
        LANG_EN: "Task created: {task_id}. Anomaly status updated to \"In Progress\".",
    },
    "anomaly_center.related_full_info_warning": {
        LANG_ZH: "关联订单数据不存在，无法展示事实依据。",
        LANG_EN: "Related order data not found; cannot display evidence.",
    },
    "anomaly_center.anomaly_type": {LANG_ZH: "异常类型", LANG_EN: "Anomaly Type"},
    "anomaly_center.related_task": {LANG_ZH: "关联任务", LANG_EN: "Related Task"},
    "anomaly_center.no_task_created": {LANG_ZH: "未创建任务", LANG_EN: "No task created"},
    "anomaly_center.list_count_suffix": {LANG_ZH: "条异常（默认优先展示高风险和待确认）", LANG_EN: "anomalies (high-risk and pending shown first)"},
    "anomaly_center.col.anomaly_id": {LANG_ZH: "异常编号", LANG_EN: "Anomaly ID"},
    "anomaly_center.col.order_id": {LANG_ZH: "订单编号", LANG_EN: "Order ID"},
    "anomaly_center.col.anomaly_type": {LANG_ZH: "异常类型", LANG_EN: "Type"},
    "anomaly_center.col.detected_at": {LANG_ZH: "发现时间", LANG_EN: "Detected At"},
    "anomaly_center.col.risk": {LANG_ZH: "风险", LANG_EN: "Risk"},
    "anomaly_center.col.status": {LANG_ZH: "状态", LANG_EN: "Status"},
    "anomaly_center.col.related_task": {LANG_ZH: "关联任务", LANG_EN: "Related Task"},
    "anomaly_center.detect_time_filter_note": {
        LANG_ZH: "发现时间筛选暂未提供独立控件，可在列表中按发现时间人工核对。",
        LANG_EN: "No dedicated filter for detection time yet; check the list manually.",
    },

    # --- 运营任务 ---
    "task_center.title": {LANG_ZH: "运营任务中心", LANG_EN: "Operations Task Center"},
    "task_center.subtitle": {LANG_ZH: "分配、跟进和关闭运营任务", LANG_EN: "Assign, follow up, and close operations tasks"},
    "task_center.status_label": {LANG_ZH: "当前状态", LANG_EN: "Current Status"},
    "task_center.priority_label": {LANG_ZH: "优先级", LANG_EN: "Priority"},
    "task_center.assignee_label": {LANG_ZH: "负责人", LANG_EN: "Assignee"},
    "task_center.due_label": {LANG_ZH: "截止时间", LANG_EN: "Due Date"},
    "task_center.description_title": {LANG_ZH: "任务描述", LANG_EN: "Task Description"},
    "task_center.related_info_title": {LANG_ZH: "关联信息", LANG_EN: "Related Information"},
    "task_center.view_related_anomaly": {LANG_ZH: "🔍 查看关联异常 {id}", LANG_EN: "🔍 View Related Anomaly {id}"},
    "task_center.no_related_anomaly": {LANG_ZH: "未关联异常（手动创建的一般任务）", LANG_EN: "No related anomaly (manually created task)"},
    "task_center.view_related_order": {LANG_ZH: "📦 查看关联订单 {id}", LANG_EN: "📦 View Related Order {id}"},
    "task_center.no_related_order": {LANG_ZH: "未关联订单", LANG_EN: "No related order"},
    "task_center.locked_status_note": {LANG_ZH: "该任务已{status}，不可再修改状态。", LANG_EN: "This task is already {status} and cannot be modified."},
    "task_center.status_done": {LANG_ZH: "完成", LANG_EN: "completed"},
    "task_center.status_cancelled": {LANG_ZH: "取消", LANG_EN: "cancelled"},
    "task_center.result_title": {LANG_ZH: "处理结果", LANG_EN: "Result"},
    "task_center.update_task_title": {LANG_ZH: "更新任务", LANG_EN: "Update Task"},
    "task_center.change_assignee_expander": {LANG_ZH: "变更负责人", LANG_EN: "Change Assignee"},
    "task_center.new_assignee_label": {LANG_ZH: "新负责人", LANG_EN: "New Assignee"},
    "task_center.save_assignee": {LANG_ZH: "保存负责人", LANG_EN: "Save Assignee"},
    "task_center.assignee_required_error": {LANG_ZH: "负责人不能为空。", LANG_EN: "Assignee cannot be empty."},
    "task_center.assignee_saved": {LANG_ZH: "负责人已更新。", LANG_EN: "Assignee updated."},
    "task_center.change_priority_expander": {LANG_ZH: "调整优先级", LANG_EN: "Adjust Priority"},
    "task_center.new_priority_label": {LANG_ZH: "新优先级", LANG_EN: "New Priority"},
    "task_center.save_priority": {LANG_ZH: "保存优先级", LANG_EN: "Save Priority"},
    "task_center.priority_saved": {LANG_ZH: "优先级已更新。", LANG_EN: "Priority updated."},
    "task_center.mark_in_progress": {LANG_ZH: "标记为处理中", LANG_EN: "Mark as In Progress"},
    "task_center.mark_in_progress_success": {LANG_ZH: "任务状态已更新为处理中。", LANG_EN: "Task status updated to In Progress."},
    "task_center.current_status_caption": {LANG_ZH: "当前状态：{status}", LANG_EN: "Current status: {status}"},
    "task_center.append_progress_title": {LANG_ZH: "追加处理记录", LANG_EN: "Add Progress Note"},
    "task_center.progress_note_label": {LANG_ZH: "记录本次处理过程", LANG_EN: "Describe this update"},
    "task_center.save_progress": {LANG_ZH: "保存处理记录", LANG_EN: "Save Progress Note"},
    "task_center.progress_required_error": {LANG_ZH: "处理记录内容不能为空。", LANG_EN: "Progress note cannot be empty."},
    "task_center.progress_saved": {LANG_ZH: "处理记录已保存。", LANG_EN: "Progress note saved."},
    "task_center.complete_task_title": {LANG_ZH: "✅ 完成任务", LANG_EN: "✅ Complete Task"},
    "task_center.complete_task_caption": {LANG_ZH: "完成任务必须填写处理结果。", LANG_EN: "You must fill in a result to complete the task."},
    "task_center.result_input_label": {LANG_ZH: "处理结果 *", LANG_EN: "Result *"},
    "task_center.confirm_complete": {LANG_ZH: "确认完成", LANG_EN: "Confirm Complete"},
    "task_center.result_required_error": {LANG_ZH: "处理结果不能为空，无法完成任务。", LANG_EN: "Result cannot be empty; task cannot be completed."},
    "task_center.complete_success": {LANG_ZH: "任务已完成。", LANG_EN: "Task completed."},
    "task_center.cancel_task_title": {LANG_ZH: "❌ 取消任务", LANG_EN: "❌ Cancel Task"},
    "task_center.cancel_reason_label": {LANG_ZH: "取消原因（可选）", LANG_EN: "Cancellation Reason (optional)"},
    "task_center.confirm_cancel": {LANG_ZH: "确认取消任务", LANG_EN: "Confirm Cancel Task"},
    "task_center.cancel_success": {LANG_ZH: "任务已取消。", LANG_EN: "Task cancelled."},
    "task_center.timeline_title": {LANG_ZH: "📜 处理记录时间线", LANG_EN: "📜 Progress Timeline"},
    "task_center.timeline_operator_label": {LANG_ZH: "操作人", LANG_EN: "Operator"},
    "task_center.only_overdue": {LANG_ZH: "只看逾期任务", LANG_EN: "Overdue only"},
    "task_center.col.title": {LANG_ZH: "任务标题", LANG_EN: "Title"},
    "task_center.col.priority": {LANG_ZH: "优先级", LANG_EN: "Priority"},
    "task_center.col.status": {LANG_ZH: "状态", LANG_EN: "Status"},
    "task_center.col.assignee": {LANG_ZH: "负责人", LANG_EN: "Assignee"},
    "task_center.col.due": {LANG_ZH: "截止时间", LANG_EN: "Due Date"},
    "task_center.col.related": {LANG_ZH: "关联", LANG_EN: "Related"},
    "task_center.related.anomaly": {LANG_ZH: "异常", LANG_EN: "Anomaly"},
    "task_center.related.order": {LANG_ZH: "订单", LANG_EN: "Order"},
    "task_center.list_count_suffix": {LANG_ZH: "条任务", LANG_EN: "tasks"},

    # --- 运营分析 ---
    "analytics.title": {LANG_ZH: "运营分析与复盘", LANG_EN: "Operations Analytics & Review"},
    "analytics.subtitle": {LANG_ZH: "观察履约表现并进行复盘", LANG_EN: "Review fulfillment performance and operations"},
    "analytics.time_range_label": {LANG_ZH: "时间范围", LANG_EN: "Time Range"},
    "analytics.time_range.7d": {LANG_ZH: "近7天", LANG_EN: "Last 7 Days"},
    "analytics.time_range.30d": {LANG_ZH: "近30天", LANG_EN: "Last 30 Days"},
    "analytics.time_range.all": {LANG_ZH: "全部", LANG_EN: "All"},
    "analytics.tab.fulfillment": {LANG_ZH: "履约分析", LANG_EN: "Fulfillment"},
    "analytics.tab.anomaly": {LANG_ZH: "异常分析", LANG_EN: "Anomalies"},
    "analytics.tab.task": {LANG_ZH: "任务分析", LANG_EN: "Tasks"},
    "analytics.fulfillment.caption": {
        LANG_ZH: "履约完成率 = 已签收且按时的订单 / 已到预计送达时间的有效订单（不含已取消）。平均履约时长统计的是「发货到签收」的时间，不是「下单到签收」。",
        LANG_EN: "Fulfillment rate = on-time delivered orders / valid orders past expected delivery date (excluding cancelled). Avg. fulfillment time is measured from ship to delivery, not from order to delivery.",
    },
    "analytics.fulfillment_rate": {LANG_ZH: "履约完成率", LANG_EN: "Fulfillment Rate"},
    "analytics.avg_fulfillment_hours": {LANG_ZH: "平均履约时长（发货→签收）", LANG_EN: "Avg. Fulfillment Time (Ship→Delivery)"},
    "analytics.avg_fulfillment_hours_help": {LANG_ZH: "样本量：{count} 条已签收订单", LANG_EN: "Sample size: {count} delivered orders"},
    "analytics.delayed_order_ratio": {LANG_ZH: "延迟订单占比", LANG_EN: "Delayed Order Ratio"},
    "analytics.delayed_order_ratio_help": {LANG_ZH: "已签收订单总数：{count}", LANG_EN: "Total delivered orders: {count}"},
    "analytics.hours_suffix": {LANG_ZH: "小时", LANG_EN: "hrs"},
    "analytics.no_delivered_note": {
        LANG_ZH: "当前没有已签收订单，以上指标暂无法计算，不代表履约表现为0。",
        LANG_EN: "No delivered orders yet; the metrics above cannot be calculated. This does not mean fulfillment performance is zero.",
    },
    "analytics.order_trend_title": {LANG_ZH: "订单量趋势", LANG_EN: "Order Volume Trend"},
    "analytics.plotly_missing": {LANG_ZH: "Plotly 未安装，以表格形式展示。", LANG_EN: "Plotly not installed; showing as a table."},
    "analytics.delivered_detail_expander": {LANG_ZH: "查看已签收订单明细", LANG_EN: "View Delivered Order Details"},
    "analytics.col.order_id": {LANG_ZH: "订单编号", LANG_EN: "Order ID"},
    "analytics.col.customer_id": {LANG_ZH: "客户ID", LANG_EN: "Customer ID"},
    "analytics.col.shipped_at": {LANG_ZH: "发货时间", LANG_EN: "Shipped At"},
    "analytics.col.delivered_at": {LANG_ZH: "签收时间", LANG_EN: "Delivered At"},
    "analytics.col.expected_delivery": {LANG_ZH: "预计送达", LANG_EN: "Expected Delivery"},
    "analytics.col.amount": {LANG_ZH: "金额", LANG_EN: "Amount"},
    "analytics.export_fulfillment": {LANG_ZH: "📥 导出履约明细为Excel", LANG_EN: "📥 Export Fulfillment Detail to Excel"},
    "analytics.download_file": {LANG_ZH: "⬇️ 下载文件", LANG_EN: "⬇️ Download File"},
    "analytics.export_failed": {LANG_ZH: "导出失败：{error}", LANG_EN: "Export failed: {error}"},
    "analytics.anomaly_total_caption": {
        LANG_ZH: "共 {count} 条异常记录。以下统计均来自数据库实时查询。",
        LANG_EN: "{count} anomaly records in total. All stats below are queried live from the database.",
    },
    "analytics.anomaly_type_dist_title": {LANG_ZH: "异常类型分布", LANG_EN: "Anomaly Type Distribution"},
    "analytics.risk_dist_title": {LANG_ZH: "风险等级分布", LANG_EN: "Risk Level Distribution"},
    "analytics.top_customer_anomaly_title": {
        LANG_ZH: "重点客户异常情况（异常数最多的前10个客户）",
        LANG_EN: "Top Customers by Anomaly Count (Top 10)",
    },
    "analytics.col.customer_name": {LANG_ZH: "客户名称", LANG_EN: "Customer"},
    "analytics.col.customer_tier": {LANG_ZH: "客户等级", LANG_EN: "Tier"},
    "analytics.col.anomaly_count": {LANG_ZH: "异常数量", LANG_EN: "Anomaly Count"},
    "analytics.export_anomaly": {LANG_ZH: "📥 导出异常分析为Excel", LANG_EN: "📥 Export Anomaly Analysis to Excel"},
    "analytics.task_summary_caption": {
        LANG_ZH: "任务完成率、平均处理时长（创建到完成）、逾期任务数。",
        LANG_EN: "Task completion rate, average processing time (creation to completion), and overdue task count.",
    },
    "analytics.total_tasks": {LANG_ZH: "任务总数", LANG_EN: "Total Tasks"},
    "analytics.completion_rate": {LANG_ZH: "任务完成率", LANG_EN: "Completion Rate"},
    "analytics.avg_processing_hours": {LANG_ZH: "平均处理时长", LANG_EN: "Avg. Processing Time"},
    "analytics.avg_processing_hours_help": {
        LANG_ZH: "样本量：{count} 条已完成任务（仅统计已完成任务，未完成任务不计入）",
        LANG_EN: "Sample size: {count} completed tasks (only completed tasks are counted)",
    },
    "analytics.overdue_count": {LANG_ZH: "逾期任务数", LANG_EN: "Overdue Tasks"},
    "analytics.no_tasks_note": {
        LANG_ZH: "当前还没有任何任务，以上指标暂无法计算。可以在「AI异常诊断中心」从异常创建任务。",
        LANG_EN: "No tasks yet; the metrics above cannot be calculated. Create tasks from anomalies in \"AI Anomaly Diagnosis\".",
    },
    "analytics.task_detail_expander": {LANG_ZH: "查看任务明细", LANG_EN: "View Task Details"},
    "analytics.col.task_id": {LANG_ZH: "任务编号", LANG_EN: "Task ID"},
    "analytics.col.task_title": {LANG_ZH: "标题", LANG_EN: "Title"},
    "analytics.col.task_priority": {LANG_ZH: "优先级", LANG_EN: "Priority"},
    "analytics.col.task_assignee": {LANG_ZH: "负责人", LANG_EN: "Assignee"},
    "analytics.col.task_status": {LANG_ZH: "状态", LANG_EN: "Status"},
    "analytics.col.task_due": {LANG_ZH: "截止时间", LANG_EN: "Due Date"},
    "analytics.col.task_completed": {LANG_ZH: "完成时间", LANG_EN: "Completed At"},
    "analytics.export_task": {LANG_ZH: "📥 导出任务明细为Excel", LANG_EN: "📥 Export Task Detail to Excel"},

    # --- 状态 / 风险 / 优先级（值本身的翻译） ---
    "status.待确认": {LANG_ZH: "待确认", LANG_EN: "Pending Confirmation"},
    "status.待发货": {LANG_ZH: "待发货", LANG_EN: "Awaiting Shipment"},
    "status.运输中": {LANG_ZH: "运输中", LANG_EN: "In Transit"},
    "status.已签收": {LANG_ZH: "已签收", LANG_EN: "Delivered"},
    "status.已取消": {LANG_ZH: "已取消", LANG_EN: "Cancelled"},
    "status.待揽收": {LANG_ZH: "待揽收", LANG_EN: "Awaiting Pickup"},
    "status.派送中": {LANG_ZH: "派送中", LANG_EN: "Out for Delivery"},
    "status.异常": {LANG_ZH: "异常", LANG_EN: "Exception"},
    "status.处理中": {LANG_ZH: "处理中", LANG_EN: "In Progress"},
    "status.已解决": {LANG_ZH: "已解决", LANG_EN: "Resolved"},
    "status.已关闭": {LANG_ZH: "已关闭", LANG_EN: "Closed"},
    "status.误报": {LANG_ZH: "误报", LANG_EN: "False Positive"},
    "status.待处理": {LANG_ZH: "待处理", LANG_EN: "Pending"},
    "status.已完成": {LANG_ZH: "已完成", LANG_EN: "Completed"},
    "risk.高": {LANG_ZH: "高", LANG_EN: "High"},
    "risk.中": {LANG_ZH: "中", LANG_EN: "Medium"},
    "risk.低": {LANG_ZH: "低", LANG_EN: "Low"},

    # --- 个性化设置页面 ---
    "settings.title": {LANG_ZH: "个性化设置", LANG_EN: "Personalization Settings"},
    "settings.subtitle": {
        LANG_ZH: "根据个人使用习惯调整系统显示方式",
        LANG_EN: "Adjust how the system looks based on your preferences",
    },
    "settings.section.language": {LANG_ZH: "语言设置", LANG_EN: "Language"},
    "settings.language_select": {LANG_ZH: "选择语言", LANG_EN: "Select Language"},
    "settings.current_language": {LANG_ZH: "当前语言：{language}", LANG_EN: "Current language: {language}"},
    "settings.section.font": {LANG_ZH: "字体设置", LANG_EN: "Font Size"},
    "settings.font_select": {LANG_ZH: "选择字体大小", LANG_EN: "Select Font Size"},
    "settings.font_preview_label": {LANG_ZH: "示例文字预览", LANG_EN: "Preview"},
    "settings.font_preview_text": {
        LANG_ZH: "FlowLens AI 运营看板示例文字 Aa 123",
        LANG_EN: "FlowLens AI Dashboard Preview Text Aa 123",
    },
    "settings.section.theme": {LANG_ZH: "主题颜色", LANG_EN: "Theme Color"},
    "settings.theme_select": {LANG_ZH: "选择预设主题", LANG_EN: "Select Preset Theme"},
    "settings.theme_preview_label": {LANG_ZH: "主题预览", LANG_EN: "Theme Preview"},
    "settings.custom_color_toggle": {LANG_ZH: "启用自定义主色", LANG_EN: "Enable Custom Primary Color"},
    "settings.custom_color_picker": {LANG_ZH: "自定义主色", LANG_EN: "Custom Primary Color"},
    "settings.section.actions": {LANG_ZH: "设置操作", LANG_EN: "Actions"},
    "settings.current_preview_title": {LANG_ZH: "当前设置预览", LANG_EN: "Current Settings Preview"},
    "settings.preview.language": {LANG_ZH: "语言", LANG_EN: "Language"},
    "settings.preview.font": {LANG_ZH: "字体大小", LANG_EN: "Font Size"},
    "settings.preview.theme": {LANG_ZH: "主题", LANG_EN: "Theme"},
    "settings.reset_success": {LANG_ZH: "已恢复默认设置。", LANG_EN: "Defaults restored."},
    "settings.save_hint": {
        LANG_ZH: "调整后会立即生效并自动保存，刷新页面或重启应用后依然保留。",
        LANG_EN: "Changes apply immediately and are saved automatically; they persist across refreshes and restarts.",
    },
}


def get_current_language() -> str:
    """读取当前语言。若 session_state 未设置，回退到默认语言。"""
    return st.session_state.get(_SESSION_KEY, DEFAULT_LANGUAGE)


def set_current_language(language: str) -> None:
    """设置当前语言到 session_state（不负责持久化，持久化由 preferences_service 负责）。"""
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    st.session_state[_SESSION_KEY] = language


def t(key: str, **kwargs) -> str:
    """翻译函数：按当前语言返回 key 对应的文案。

    用法：
        t("dashboard.title")
        t("anomaly_center.scan_result", scanned=10, violations=2, created=1, skipped=1)

    未登记的 key 直接返回 key 本身，便于开发时定位遗漏的翻译条目，
    不会导致页面崩溃。
    """
    language = get_current_language()
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(language, entry.get(DEFAULT_LANGUAGE, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
