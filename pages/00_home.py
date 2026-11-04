"""
欢迎页（首页）。

从旧版 app.py 迁移而来：展示项目简介和环境自检信息，不包含业务数据读取。
本文件由 app.py 通过 st.navigation 路由，不单独调用 st.set_page_config()
（页面级配置已在 app.py 入口统一设置一次）。
"""

from __future__ import annotations

import streamlit as st

from components.layout import inject_base_styles, render_page_header, render_sidebar_footer
from config.i18n import t
from config.settings import get_config
from database.connection import check_connection

inject_base_styles()

render_page_header(
    title_key="app.name",
    subtitle_key="app.tagline",
)

_is_zh = st.session_state.get("flowlens_language", "zh") == "zh"

if _is_zh:
    st.markdown(
        """
        FlowLens AI 通过模拟订单、客户、供应商和物流数据，结合**确定性规则引擎**
        与**AI 辅助分析**，帮助运营人员发现履约异常、理解问题、评估客户影响、
        形成处理任务并跟踪闭环。

        请使用左侧导航进入以下模块：

        - **运营总览** — 整体指标、趋势、风险与待办
        - **客户与订单** — 查询业务对象和履约上下文
        - **AI 异常诊断** — 识别、理解和确认异常
        - **运营任务** — 分配、跟进和关闭运营任务
        - **运营分析** — 观察表现并进行复盘

        如需调整界面语言、字体大小或主题颜色，请前往左侧「个性化设置」。
        """
    )
else:
    st.markdown(
        """
        FlowLens AI simulates orders, customers, suppliers, and logistics data,
        combining a **deterministic rule engine** with **AI-assisted analysis**
        to help operations teams detect fulfillment anomalies, understand root
        causes, assess customer impact, and track resolution tasks to closure.

        Use the navigation on the left to explore:

        - **Operations Overview** — overall metrics, trends, risks, and to-dos
        - **Customers & Orders** — browse business objects and fulfillment context
        - **AI Anomaly Diagnosis** — identify, understand, and confirm anomalies
        - **Operations Tasks** — assign, follow up, and close operations tasks
        - **Operations Analytics** — review performance and retrospectives

        To change the display language, font size, or theme color, go to
        **Personalization Settings** on the left.
        """
    )

st.divider()

with st.expander("Debug / 环境自检" if not _is_zh else "环境自检（开发调试用）", expanded=False):
    config = get_config()
    st.write(
        {
            "APP_ENV": config.app_env,
            "AI_MODE": config.ai_mode,
            "DATABASE_PATH": str(config.database_path),
            "DEMO_MODE": config.demo_mode,
        }
    )
    db_ok = check_connection()
    if db_ok:
        st.success("Database connection OK." if not _is_zh else "数据库连接正常（当前无业务表，仅验证连接可用）。")
    else:
        st.error("Database connection failed." if not _is_zh else "数据库连接失败，请检查 DATABASE_PATH 配置或文件权限。")

render_sidebar_footer()
