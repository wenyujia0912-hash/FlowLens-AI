"""
FlowLens AI · 应用入口。

使用 Streamlit 1.38+ 的 st.navigation / st.Page API 构建多页面应用：
    - 五个业务模块分为一组（"业务模块"），个性化设置单独分为一组（"个人设置"），
      在侧边栏视觉上与业务模块区分（需求文档 §4 "建议将其放在左侧导航栏的底部，
      与五个业务模块进行视觉区分"）。
    - 导航标签统一通过 config.i18n.t() 读取当前语言对应的文案，不再出现
      "运营驾驶舱"等旧名称，也不会出现中英文混杂。
    - 每个子页面文件内不再调用 st.set_page_config()（该调用只能在入口脚本执行
      一次），改为由本文件统一设置。

本文件本身：
    1. 统一设置页面级配置、初始化用户偏好（语言/字体/主题）；
    2. 构建导航结构并路由到各业务页面模块；
    3. 展示欢迎信息（首页）。
"""

from __future__ import annotations

import streamlit as st

from config.i18n import t
from config.theme import build_theme_css, DEFAULT_FONT_SIZE, DEFAULT_THEME
from config.settings import get_config
from database.connection import check_connection
from services.preferences_service import sync_preferences_into_session, get_current_preferences

st.set_page_config(
    page_title=f"{t('app.name')}",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 必须在任何页面内容渲染前完成一次偏好同步，确保导航标签本身也使用正确语言。
sync_preferences_into_session()
_preferences = get_current_preferences()
st.markdown(
    build_theme_css(
        theme_key=_preferences.theme or DEFAULT_THEME,
        font_size_key=_preferences.font_size or DEFAULT_FONT_SIZE,
        custom_primary=_preferences.custom_primary_color,
    ),
    unsafe_allow_html=True,
)

home_page = st.Page("pages/00_home.py", title=t("app.name"), icon="🧭", default=True)
dashboard_page = st.Page("pages/01_dashboard.py", title=t("nav.dashboard"), icon="📊")
customers_orders_page = st.Page("pages/02_customers_orders.py", title=t("nav.customers_orders"), icon="📦")
anomaly_center_page = st.Page("pages/03_anomaly_center.py", title=t("nav.anomaly_center"), icon="🔍")
task_center_page = st.Page("pages/04_task_center.py", title=t("nav.task_center"), icon="✅")
analytics_page = st.Page("pages/05_analytics.py", title=t("nav.analytics"), icon="📈")
settings_page = st.Page("pages/06_settings.py", title=t("nav.settings"), icon="⚙️")

navigation = st.navigation(
    {
        t("nav.section.business"): [
            home_page,
            dashboard_page,
            customers_orders_page,
            anomaly_center_page,
            task_center_page,
            analytics_page,
        ],
        t("nav.section.personal"): [settings_page],
    }
)

navigation.run()
