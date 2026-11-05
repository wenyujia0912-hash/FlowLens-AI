"""
FlowLens AI · 应用入口。

路由：使用 Streamlit 1.38+ 的 st.navigation / st.Page 构建多页面应用，但以
position="hidden" 关闭其原生侧边栏导航，改由 components/layout.py 绘制
自定义侧边栏（品牌区 → Workspace 文字导航 → 底部个性化设置）。这样可保留
原生路由能力（st.switch_page、页面 URL、per-session 页面状态），同时实现
需求要求的视觉层级。

    - 五个业务模块归入 Workspace 分组，纯文字、无图标。
    - 个性化设置放在侧边栏底部，与业务导航视觉区分。
    - 当前页面由 layout.render_sidebar(active_key=...) 标记选中态。

本文件本身：
    1. 统一设置页面级配置、初始化用户偏好（语言/字体/主题）；
    2. 注入全局设计系统样式；
    3. 绘制侧边栏并路由到各业务页面模块。
"""

from __future__ import annotations

import streamlit as st

from components.layout import (
    NAV_ITEMS,
    SETTINGS_ITEM,
    inject_base_styles,
    render_sidebar,
)
from config.i18n import t
from database.connection import ensure_database_seeded

# 页面配置必须最先执行（且只在整个应用执行一次）。
st.set_page_config(
    page_title=t("app.name"),
    page_icon="◧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 偏好同步 + 全局样式必须在导航标签生成前完成，确保语言/字体/主题立即生效。
inject_base_styles()

# 云端部署时仓库里没有 database/*.db（已被 .gitignore 排除），首次启动需要
# 自动建表并写入模拟数据，否则访客只能看到"数据库尚未初始化"的提示，而
# 托管环境没有终端可以手动执行 seed 脚本。已有数据时本函数直接返回，幂等。
# 失败不阻塞应用：各页面仍会显示原有的初始化提示，便于本地排查。
ensure_database_seeded()

pages = {
    item["key"]: st.Page(
        item["page"],
        title=t(item["label_key"]),
        url_path=item["url_path"],
    )
    for item in (*NAV_ITEMS, SETTINGS_ITEM)
}

navigation = st.navigation(
    list(pages.values()),
    position="hidden",
)

# 当前页面 key 与页面对象的映射，用于侧边栏选中态。
_current_page_key = next(
    (key for key, page in pages.items() if page.url_path == navigation.url_path),
    "dashboard",
)

render_sidebar(active_key=_current_page_key, pages=pages)

navigation.run()
