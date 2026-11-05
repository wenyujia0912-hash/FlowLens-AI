"""
统一布局组件：侧边栏（品牌区 + 文字导航 + 底部偏好）、页面头部、区域标题、
定义列表、空状态与数据库守卫。

导航结构（对应视觉重设计需求 §4）：
    - FlowLens AI 位于侧边栏最顶部，作为独立品牌介绍区，不是可点击导航项，
      与五个业务模块不构成平级关系。
    - 五个业务模块归入统一的 Workspace 分组，纯文字导航，无图标、无 emoji。
    - 个性化设置单独放在侧边栏底部，与业务导航之间以留白和分隔线区分。

实现方式：使用 st.navigation(position="hidden") 保留 Streamlit 原生路由与
页面状态（st.switch_page、pending_filter 等机制不受影响），侧边栏内容由本模块
自行绘制；当前页面用静态的选中态元素表示，其余页面用 st.page_link 跳转。

所有文案通过 config.i18n.t() 获取，不在本模块内硬编码任何语言的字面文案。
样式一律引用 config/theme.py 生成的 --fl-* 变量，本模块不自定义颜色。
"""

from __future__ import annotations

import html

import streamlit as st

from config.i18n import t
from config.settings import get_config
from config.theme import build_theme_css, DEFAULT_FONT_SIZE, DEFAULT_THEME
from services.preferences_service import sync_preferences_into_session, get_current_preferences

# ----------------------------------------------------------------------
# 一级导航结构：五个业务模块（顺序固定）+ 底部个性化设置。
# url_path 显式指定，保证地址稳定、便于侧边栏底部定位。
# ----------------------------------------------------------------------

NAV_ITEMS: tuple[dict, ...] = (
    {"key": "dashboard", "label_key": "nav.dashboard", "page": "views/01_dashboard.py", "url_path": "overview"},
    {"key": "customers_orders", "label_key": "nav.customers_orders", "page": "views/02_customers_orders.py", "url_path": "customers"},
    {"key": "anomaly_center", "label_key": "nav.anomaly_center", "page": "views/03_anomaly_center.py", "url_path": "anomalies"},
    {"key": "task_center", "label_key": "nav.task_center", "page": "views/04_task_center.py", "url_path": "tasks"},
    {"key": "analytics", "label_key": "nav.analytics", "page": "views/05_analytics.py", "url_path": "analytics"},
)

SETTINGS_ITEM: dict = {
    "key": "settings",
    "label_key": "nav.settings",
    "page": "views/06_settings.py",
    "url_path": "settings",
}


def configure_page(page_title_key: str, page_icon: str = "📊") -> None:
    """【已废弃】旧版多页面模式下每页调用一次 st.set_page_config()。

    自迁移到 st.navigation / st.Page（见 app.py）后，页面级配置只能在入口
    文件 app.py 中调用一次，子页面不应再调用本函数。保留仅为向后兼容。
    """
    return None


def inject_base_styles() -> None:
    """同步用户偏好到 session_state，并注入全局设计系统样式。

    每个页面渲染最开始调用一次，确保语言/字体/主题在任意页面刷新或直接
    访问时都保持一致。
    """
    sync_preferences_into_session()
    preferences = get_current_preferences()
    css = build_theme_css(
        theme_key=preferences.theme or DEFAULT_THEME,
        font_size_key=preferences.font_size or DEFAULT_FONT_SIZE,
        custom_primary=preferences.custom_primary_color,
    )
    st.markdown(css, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 侧边栏
# ----------------------------------------------------------------------


def render_brand() -> None:
    """侧边栏顶部品牌区：产品名 + 英文定位 + 一行中文介绍。

    不是导航项，不可点击，不放置大型 Logo 图标。
    """
    st.sidebar.markdown(
        f"""
        <div class="fl-brand">
            <div class="fl-brand-name">{html.escape(t('app.name'))}</div>
            <div class="fl-brand-eyebrow">{html.escape(t('nav.brand.eyebrow'))}</div>
            <div class="fl-brand-desc">{html.escape(t('nav.brand.desc'))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_primary_nav(active_key: str | None = None, pages: dict | None = None) -> None:
    """渲染 Workspace 分组与五个业务导航项（纯文字，无图标）。

    当前页面使用非常浅的灰蓝背景 + 较深文字表示选中，其余项为可点击链接。

    参数:
        active_key: 当前页面 key。
        pages: app.py 中创建好的 {key: st.Page} 映射。直接传 st.Page 对象给
            st.page_link，可以稳定解析出 url_path（传文件路径字符串在
            st.navigation 自定义路由下无法匹配页面，会退化成错误的 href）。
    """
    pages = pages or {}
    st.sidebar.markdown(
        f'<div class="fl-nav-group">{html.escape(t("nav.workspace"))}</div>',
        unsafe_allow_html=True,
    )
    for item in NAV_ITEMS:
        label = t(item["label_key"])
        if item["key"] == active_key:
            st.sidebar.markdown(
                f'<div class="fl-nav-item is-active">{html.escape(label)}</div>',
                unsafe_allow_html=True,
            )
        elif item["key"] in pages:
            st.sidebar.page_link(pages[item["key"]], label=label, use_container_width=True)
        else:
            st.sidebar.markdown(
                f'<div class="fl-nav-item">{html.escape(label)}</div>', unsafe_allow_html=True
            )


def render_secondary_nav(active_key: str | None = None, pages: dict | None = None) -> None:
    """渲染侧边栏底部的个性化设置入口。

    与业务导航采用相同的文字风格，通过位置、留白与分隔线体现层级区别。
    """
    pages = pages or {}
    st.sidebar.markdown('<div class="fl-nav-sep"></div>', unsafe_allow_html=True)
    label = t(SETTINGS_ITEM["label_key"])
    if active_key == SETTINGS_ITEM["key"]:
        st.sidebar.markdown(
            f'<div class="fl-nav-item is-active">{html.escape(label)}</div>',
            unsafe_allow_html=True,
        )
    elif SETTINGS_ITEM["key"] in pages:
        st.sidebar.page_link(pages[SETTINGS_ITEM["key"]], label=label, use_container_width=True)
    else:
        st.sidebar.markdown(f'<div class="fl-nav-item">{html.escape(label)}</div>', unsafe_allow_html=True)


def render_sidebar(active_key: str | None = None, pages: dict | None = None) -> None:
    """渲染完整侧边栏：品牌区 → 业务导航 → （底部）个性化设置 → 底部信息。

    由 app.py 在 navigation.run() 之前调用一次，各页面不再重复渲染导航。

    底部信息也在这里渲染，而不是在 navigation.run() 之后：页面脚本内部的
    st.stop()（数据库守卫、空数据提前返回）会中断后续语句，若底部信息放在
    run() 之后，不同页面的侧栏元素数量就会不同，切换时整条侧栏高度变化、
    产生上下位移。放在 run() 之前可保证每个页面的侧栏结构完全一致。
    """
    render_brand()
    render_primary_nav(active_key, pages)
    render_secondary_nav(active_key, pages)
    render_sidebar_meta()


def render_sidebar_footer() -> None:
    """渲染侧边栏底部运行环境信息（环境名 / AI 模式）。

    采用低对比度小字，不使用分割线与卡片，保持侧边栏干净。
    """
    config = get_config()
    lines = [f"{t('common.env_label')} · {html.escape(config.app_env)}"]
    if config.ai_mode == "mock":
        lines.append(html.escape(t("common.ai_mock_mode")))
    st.sidebar.markdown(
        f'<div class="fl-sidebar-meta">{"<br>".join(lines)}</div>',
        unsafe_allow_html=True,
    )


# 兼容旧调用名（部分页面仍使用 render_sidebar_footer 的语义）。
render_sidebar_meta = render_sidebar_footer


# ----------------------------------------------------------------------
# 页面内容
# ----------------------------------------------------------------------


def render_page_header(title_key: str, subtitle_key: str | None = None) -> None:
    """渲染统一样式的页面头部：主标题 + 一行说明。

    不使用图标、装饰色块或大面积背景；标题与说明之间以固定间距分隔，
    底部一条极浅分隔线，将头部与页面内容分层。
    """
    title = html.escape(t(title_key))
    subtitle_html = f"<p>{html.escape(t(subtitle_key))}</p>" if subtitle_key else ""
    st.markdown(
        f"""
        <div class="fl-page-header">
            <h1>{title}</h1>
            {subtitle_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section(title_key: str | None = None, caption_key: str | None = None, **kwargs) -> None:
    """渲染区域标题（可选一行说明）。

    用于替代 st.subheader()：统一字号（16px / 600）与上下留白，
    区域之间不额外加卡片或边框。
    """
    if title_key is None:
        return
    title = html.escape(t(title_key, **kwargs))
    caption_html = (
        f'<div class="fl-section-caption">{html.escape(t(caption_key, **kwargs))}</div>'
        if caption_key
        else ""
    )
    st.markdown(
        f'<div class="fl-section"><div class="fl-section-title">{title}</div>{caption_html}</div>',
        unsafe_allow_html=True,
    )


def render_kv_list(rows: list[tuple[str, str]], *, allow_html: bool = False, panel: bool = False) -> None:
    """渲染成对的"标签 — 值"定义列表，用于详情页信息位。

    以极浅的行分隔线组织信息，不使用卡片边框或彩色标签；值本身可以使用
    简单的行内标记（allow_html=True 时按原样输出，调用方须自行转义）。

    panel=True 时整块放进浅灰面板中（用于"系统确认的事实"这类需要与
    周围内容区分、但又不该用彩色卡片表达的区块）。面板与内容必须在同一次
    markdown 调用里输出——Streamlit 的每次 st.markdown 是独立容器，
    分三次调用会导致面板只剩一个空框。
    """
    items = []
    for key, value in rows:
        key_html = html.escape(str(key))
        value_html = str(value) if allow_html else html.escape(str(value))
        items.append(
            f'<div class="fl-kv-row"><div class="fl-kv-key">{key_html}</div>'
            f'<div class="fl-kv-val">{value_html}</div></div>'
        )
    body = f'<div class="fl-kv">{"".join(items)}</div>'
    if panel:
        st.markdown(f'<div class="fl-panel-subtle">{body}</div>', unsafe_allow_html=True)
    else:
        st.markdown(body, unsafe_allow_html=True)


def render_panel_label(text: str, note: str | None = None) -> None:
    """渲染轻量面板中的小标题与说明。"""
    note_html = f'<div class="fl-panel-note">{html.escape(note)}</div>' if note else ""
    st.markdown(
        f'<div class="fl-panel-label">{html.escape(text)}</div>{note_html}',
        unsafe_allow_html=True,
    )


def render_kpi_stat(label: str, value: str, meta: str | None = None, *, help: str | None = None) -> None:
    """渲染单个 KPI 指标（标签 / 大号数字 / 可选辅助说明）。

    与可点击 KPI 使用同一套度量：上边线分隔、灰色小标签、突出数字，
    因此两者可以出现在同一行而不会出现两种视觉。
    """
    meta_html = f'<div class="fl-kpi-meta">{html.escape(meta)}</div>' if meta else ""
    st.markdown(
        f"""
        <div class="fl-kpi" title="{html.escape(help or '')}">
            <div class="fl-kpi-label">{html.escape(label)}</div>
            <div class="fl-kpi-value">{html.escape(str(value))}</div>
            {meta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(message_key: str, hint_key: str | None = None, **kwargs) -> None:
    """统一的空状态展示：一句主提示 + 可选的一行建议，居中、无彩色背景。"""
    message = html.escape(t(message_key, **kwargs))
    hint_html = (
        f'<div class="fl-empty-hint">{html.escape(t(hint_key, **kwargs))}</div>' if hint_key else ""
    )
    st.markdown(
        f'<div class="fl-empty"><div class="fl-empty-title">{message}</div>{hint_html}</div>',
        unsafe_allow_html=True,
    )


def render_not_implemented_notice(feature_name: str) -> None:
    """标记"该功能尚未实现"的占位提示（保留给未来扩展使用）。"""
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
    st.info(t("common.db_init_hint") + "\n\n```bash\npython -m database.seed_data\n```")
    return False
