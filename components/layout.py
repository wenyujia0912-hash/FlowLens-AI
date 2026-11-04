"""
统一页面布局组件。

提供跨页面复用的页面配置、页头、侧边栏骨架、全局主题样式注入和
国际化导航结构。所有文案通过 config.i18n.t() 获取，不在本模块内
硬编码任何中/英文字符串字面量（除日志/异常信息外）。

视觉原则（对应需求文档 §2）：
    - 浅色背景为默认主题，卡片白底深色文字，有限强调色。
    - 导航结构、页头、KPI、表格、按钮、图表统一通过 config/theme.py
      生成的 CSS 变量驱动，不同页面不各自定义一套颜色。
"""

from __future__ import annotations

import streamlit as st

from config.i18n import t
from config.settings import get_config
from config.theme import build_theme_css, DEFAULT_FONT_SIZE, DEFAULT_THEME
from services.preferences_service import sync_preferences_into_session, get_current_preferences

# 一级导航结构：与 pages/ 目录下的文件一一对应，icon 语义明确且跨语言通用。
# label 通过 i18n key 间接获取，不在此处写死任何语言的文案。
NAV_SECTIONS: tuple[dict, ...] = (
    {"key": "dashboard", "icon": "📊", "label_key": "nav.dashboard", "page": "pages/01_dashboard.py"},
    {"key": "customers_orders", "icon": "📦", "label_key": "nav.customers_orders", "page": "pages/02_customers_orders.py"},
    {"key": "anomaly_center", "icon": "🔍", "label_key": "nav.anomaly_center", "page": "pages/03_anomaly_center.py"},
    {"key": "task_center", "icon": "✅", "label_key": "nav.task_center", "page": "pages/04_task_center.py"},
    {"key": "analytics", "icon": "📈", "label_key": "nav.analytics", "page": "pages/05_analytics.py"},
)

SETTINGS_NAV: dict = {"key": "settings", "icon": "⚙️", "label_key": "nav.settings", "page": "pages/06_settings.py"}


def configure_page(page_title_key: str, page_icon: str = "📊") -> None:
    """【已废弃】旧版多页面模式下每页调用一次 st.set_page_config()。

    自迁移到 st.navigation / st.Page（见 app.py）后，页面级配置只能且只需要
    在入口文件 app.py 中调用一次，子页面不应再调用本函数（重复调用会抛出
    StreamlitAPIException）。保留此函数仅为向后兼容，函数体为空操作。
    """
    return None


def inject_base_styles() -> None:
    """同步用户偏好到 session_state，并注入全局主题样式。

    应在 configure_page 之后、页面内容渲染之前调用。这是每个页面统一的
    入口，确保语言/字体/主题在任意页面刷新或直接访问时都保持一致。
    """
    sync_preferences_into_session()
    preferences = get_current_preferences()
    css = build_theme_css(
        theme_key=preferences.theme or DEFAULT_THEME,
        font_size_key=preferences.font_size or DEFAULT_FONT_SIZE,
        custom_primary=preferences.custom_primary_color,
    )
    st.markdown(css, unsafe_allow_html=True)


def render_page_header(title_key: str, subtitle_key: str | None = None) -> None:
    """渲染统一样式的页面标题区域。

    参数:
        title_key: 页面主标题的 i18n key。
        subtitle_key: 可选的副标题/说明文字的 i18n key。
    """
    title = t(title_key)
    subtitle_html = f"<p>{t(subtitle_key)}</p>" if subtitle_key else ""
    st.markdown(
        f"""
        <div class="flowlens-page-header">
            <h1>{title}</h1>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_footer() -> None:
    """渲染侧边栏底部的通用信息：应用名称、运行环境标识。"""
    config = get_config()
    st.sidebar.divider()
    st.sidebar.caption(f"{t('app.name')} · {t('common.env_label')}: {config.app_env}")
    if config.ai_mode == "mock":
        st.sidebar.caption(t("common.ai_mock_mode"))


def render_empty_state(message_key: str, hint_key: str | None = None, **kwargs) -> None:
    """统一的空状态展示。用于列表无数据、筛选结果为空等场景。

    message_key / hint_key 均为 i18n key；kwargs 透传给 t() 做占位符替换。
    """
    message = t(message_key, **kwargs)
    hint = t(hint_key, **kwargs) if hint_key else None
    st.info(f"{message}" + (f"\n\n{hint}" if hint else ""))


def render_not_implemented_notice(feature_name: str) -> None:
    """标记"该功能尚未实现"的占位提示（仅用于开发期页面骨架，当前业务页面均已实现，保留以防未来扩展使用）。"""
    st.warning(f"「{feature_name}」尚未实现，将在后续开发阶段接入真实数据与逻辑。")


def guard_database_initialized() -> bool:
    """在页面查询业务数据前调用，检查数据库是否已建好业务表。

    返回:
        True 表示数据库已正确初始化，页面可以继续渲染业务内容；
        False 表示已显示提示，调用方应该 st.stop()。
    """
    from database.connection import is_schema_initialized

    if is_schema_initialized():
        return True

    st.error(t("common.db_not_initialized"))
    st.info(
        t("common.db_init_hint") + "\n\n```bash\npython -m database.seed_data\n```"
    )
    return False
