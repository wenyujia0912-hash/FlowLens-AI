"""
设计系统（Design System）：颜色 / 字体 / 间距 / 圆角 / 组件样式。

本模块是整个产品视觉语言的唯一来源：
    - 颜色、字号、间距、圆角、边框等设计令牌（design tokens）集中在这里定义；
    - build_theme_css() 依据令牌生成全局 <style>，由 components/layout.py 注入；
    - 页面与组件只引用 CSS 变量（--fl-*）或本模块导出的常量，不各自硬编码色值。

设计原则（Premium Minimalist / Clean Enterprise）：
    - 页面以白色与浅灰为主，主色只用于关键操作、选中态与关键数据。
    - 能用留白解决的问题不加边框；能用字体层级解决的问题不加颜色；
      能用文字解决的问题不加图标。
    - 成功/警告/错误色只用于业务状态，且以浅色底 + 低饱和文字呈现。
    - 侧边栏使用浅色（#FAFAFA），不再是深色/主色块。

主题切换与字号档位：
    - 四套预设主题只改变"主色"这一项，页面背景、文字、边框等中性色保持统一，
      使切换主题不会破坏整体视觉框架。
    - 自定义主色同样只替换主色，并通过对比度计算决定主色块上的文字颜色。
    - 字号档位（小/标准/大）通过 --fl-scale 整体缩放设计规范的基准字号。
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Template

# ----------------------------------------------------------------------
# 一、中性色（不随主题变化）
# ----------------------------------------------------------------------

COLOR_BG = "#FFFFFF"                 # 页面背景
COLOR_SIDEBAR_BG = "#FAFAFA"         # 侧边栏背景
COLOR_TEXT = "#171717"               # 主文字
COLOR_TEXT_SECONDARY = "#737373"     # 次级文字
COLOR_TEXT_MUTED = "#A3A3A3"         # 辅助文字
COLOR_BORDER = "#EAEAEA"             # 分割线 / 边框
COLOR_BORDER_STRONG = "#DCDCDC"      # 需要强调的边框（输入框聚焦前的悬停等）
COLOR_HOVER = "#F5F5F5"              # 悬停背景
COLOR_SELECTED = "#F0F3F8"           # 选中背景
COLOR_SURFACE = "#FFFFFF"            # 卡片/面板表面
COLOR_SURFACE_SUBTLE = "#FAFAFA"     # 轻量面板（如事实区、代码块）
COLOR_OVERLAY = "rgba(23, 23, 23, 0.04)"

# ----------------------------------------------------------------------
# 二、业务语义色（不随主题变化，保证状态识别一致）
# ----------------------------------------------------------------------

COLOR_SUCCESS = "#27845B"
COLOR_WARNING = "#B7791F"
COLOR_ERROR = "#C44747"
COLOR_NEUTRAL_STATUS = "#6B6B6B"

# 语义色的浅色底（状态标签用），低饱和度，避免彩虹色界面。
COLOR_SUCCESS_TINT = "#EFF5F1"
COLOR_WARNING_TINT = "#F8F2E7"
COLOR_ERROR_TINT = "#F8EFEF"
COLOR_NEUTRAL_TINT = "#F4F4F4"
COLOR_PRIMARY_TINT = "#EEF1FA"

# 兼容旧命名（components/status_badges.py 等历史引用），值已统一到新调色板。
COLOR_CARD_BG = COLOR_SURFACE

# ----------------------------------------------------------------------
# 三、字体与排版
# ----------------------------------------------------------------------

# 不引入外部网络字体：优先使用系统中可用的现代无衬线字体。
FONT_STACK = (
    '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", '
    '"Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif'
)
FONT_STACK_MONO = '"SF Mono", "JetBrains Mono", Menlo, Consolas, monospace'

# 基准字号（px）。字号档位通过 --fl-scale 缩放这些基准值。
TYPE_SCALE = {
    "page-title": (24, 600),     # 页面主标题
    "page-subtitle": (13, 400),  # 页面副标题
    "section-title": (16, 600),  # 区域标题
    "card-title": (13, 500),     # 卡片/面板标题
    "body": (14, 400),           # 正文
    "caption": (12, 400),        # 辅助文字
    "kpi": (28, 600),            # KPI 数字
    "table": (13, 400),          # 表格正文
    "button": (13, 500),         # 按钮
    "label": (12, 500),          # 表单标签
}

LINE_HEIGHT_BODY = 1.6
LINE_HEIGHT_TIGHT = 1.3

# ----------------------------------------------------------------------
# 四、间距与形状
# ----------------------------------------------------------------------

SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 32, "3xl": 48}
RADIUS = {"sm": 4, "md": 6, "lg": 8}

# ----------------------------------------------------------------------
# 五、主题预设（只影响主色）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ThemePreset:
    key: str
    name_zh: str
    name_en: str
    primary: str
    accent: str      # 图表次要系列色（低饱和）
    background: str  # 与预设配套的页面背景；当前统一为白色


THEME_ORDER: tuple[str, ...] = ("navy", "tech_blue", "forest_green", "graphite")

DEFAULT_THEME = "navy"

THEMES: dict[str, ThemePreset] = {
    "navy": ThemePreset(
        key="navy",
        name_zh="靛蓝",
        name_en="Indigo",
        primary="#3B5CCC",
        accent="#7C8DB5",
        background=COLOR_BG,
    ),
    "tech_blue": ThemePreset(
        key="tech_blue",
        name_zh="石板蓝",
        name_en="Slate",
        primary="#3E6B8F",
        accent="#8AA5B8",
        background=COLOR_BG,
    ),
    "forest_green": ThemePreset(
        key="forest_green",
        name_zh="松柏绿",
        name_en="Pine",
        primary="#2F6B57",
        accent="#87A79B",
        background=COLOR_BG,
    ),
    "graphite": ThemePreset(
        key="graphite",
        name_zh="石墨灰",
        name_en="Graphite",
        primary="#464A4F",
        accent="#9A9DA1",
        background=COLOR_BG,
    ),
}

# ----------------------------------------------------------------------
# 六、字号档位
# ----------------------------------------------------------------------

FONT_SIZE_ORDER: tuple[str, ...] = ("small", "medium", "large")

DEFAULT_FONT_SIZE = "medium"

FONT_SIZE_LABELS_ZH = {"small": "小", "medium": "标准", "large": "大"}
FONT_SIZE_LABELS_EN = {"small": "Small", "medium": "Medium", "large": "Large"}

# 相对基准字号的整体缩放比例；三档均以新的排版规范为基准缩放。
_FONT_SCALE = {"small": 0.92, "medium": 1.0, "large": 1.1}


# ----------------------------------------------------------------------
# 七、颜色工具函数
# ----------------------------------------------------------------------


def get_theme(theme_key: str) -> ThemePreset:
    """按 key 获取主题预设，key 非法时回退到默认主题。"""
    return THEMES.get(theme_key, THEMES[DEFAULT_THEME])


def is_valid_hex_color(value: str | None) -> bool:
    if not value or not value.startswith("#"):
        return False
    hex_part = value[1:]
    if len(hex_part) not in (3, 6):
        return False
    try:
        int(hex_part, 16)
    except ValueError:
        return False
    return True


def normalize_hex(hex_color: str) -> str:
    """把 #abc 形式展开为 #aabbcc；非法输入返回原值。"""
    if not is_valid_hex_color(hex_color):
        return hex_color
    body = hex_color[1:]
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    return f"#{body.upper()}"


def resolve_primary_color(theme_key: str, custom_primary: str | None) -> str:
    """返回最终生效的主色：自定义主色优先于预设主题主色。"""
    if custom_primary and is_valid_hex_color(custom_primary):
        return normalize_hex(custom_primary)
    return get_theme(theme_key).primary


def _relative_luminance(hex_color: str) -> float:
    """相对亮度（WCAG 定义），用于判断某底色上应使用深色还是浅色文字。"""
    hex_part = normalize_hex(hex_color).lstrip("#")
    if len(hex_part) != 6:
        return 0.0
    r, g, b = (int(hex_part[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = channel(r), channel(g), channel(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 对比度，用于在自定义主色上选择可读的文字颜色。"""
    l1, l2 = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_text_color(background: str) -> str:
    """给定底色，返回对比度更高、可读的文字色（主文字色或白色）。

    用于主色按钮/主色块：用户可能选择任意浅色自定义主色，固定白字会导致
    文字几乎不可读，这里按 WCAG 对比度在深色文字与白色之间二选一。
    """
    dark, light = COLOR_TEXT, "#FFFFFF"
    return dark if contrast_ratio(dark, background) >= contrast_ratio(light, background) else light


def mix_towards(hex_color: str, target: str, weight: float) -> str:
    """把颜色按权重混合到目标色，用于生成悬停/激活态（避免引入颜色库）。"""
    if not (is_valid_hex_color(hex_color) and is_valid_hex_color(target)):
        return hex_color
    src, dst = normalize_hex(hex_color)[1:], normalize_hex(target)[1:]
    mixed = []
    for i in (0, 2, 4):
        a, b = int(src[i:i + 2], 16), int(dst[i:i + 2], 16)
        mixed.append(round(a + (b - a) * weight))
    return "#" + "".join(f"{c:02X}" for c in mixed)


def darken(hex_color: str, weight: float = 0.08) -> str:
    return mix_towards(hex_color, "#000000", weight)


def font_scale(font_size_key: str) -> float:
    """返回字号档位对应的缩放比例，非法档位回退到标准档。"""
    return _FONT_SCALE.get(font_size_key, _FONT_SCALE[DEFAULT_FONT_SIZE])


def rgba(hex_color: str, alpha: float) -> str:
    body = normalize_hex(hex_color).lstrip("#")
    if len(body) != 6:
        return hex_color
    r, g, b = (int(body[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


# ----------------------------------------------------------------------
# 八、全局样式生成
# ----------------------------------------------------------------------

# 使用 string.Template 而非 f-string：CSS 中的花括号无需转义，模板更易维护。
_CSS_TEMPLATE = Template(
    """
<style>
    :root {
        /* 主色（随主题 / 自定义主色变化） */
        --fl-primary: $primary;
        --fl-primary-hover: $primary_hover;
        --fl-primary-text: $primary_text;
        --fl-primary-tint: $primary_tint;
        --fl-accent: $accent;

        /* 中性色 */
        --fl-bg: $bg;
        --fl-sidebar-bg: $sidebar_bg;
        --fl-surface: $surface;
        --fl-surface-subtle: $surface_subtle;
        --fl-text: $text;
        --fl-text-secondary: $text_secondary;
        --fl-text-muted: $text_muted;
        --fl-border: $border;
        --fl-border-strong: $border_strong;
        --fl-hover: $hover;
        --fl-selected: $selected;

        /* 语义色 */
        --fl-success: $success;
        --fl-success-tint: $success_tint;
        --fl-warning: $warning;
        --fl-warning-tint: $warning_tint;
        --fl-error: $error;
        --fl-error-tint: $error_tint;
        --fl-neutral: $neutral;
        --fl-neutral-tint: $neutral_tint;

        /* 字体 */
        --fl-font: $font_stack;
        --fl-font-mono: $font_stack_mono;
        --fl-scale: $scale;
        --fl-fs-page-title: calc($fs_page_title * var(--fl-scale));
        --fl-fs-page-subtitle: calc($fs_page_subtitle * var(--fl-scale));
        --fl-fs-section: calc($fs_section * var(--fl-scale));
        --fl-fs-card-title: calc($fs_card_title * var(--fl-scale));
        --fl-fs-body: calc($fs_body * var(--fl-scale));
        --fl-fs-caption: calc($fs_caption * var(--fl-scale));
        --fl-fs-kpi: calc($fs_kpi * var(--fl-scale));
        --fl-fs-table: calc($fs_table * var(--fl-scale));
        --fl-fs-button: calc($fs_button * var(--fl-scale));
        --fl-fs-label: calc($fs_label * var(--fl-scale));

        /* 间距 / 圆角 */
        --fl-space-xs: 4px;
        --fl-space-sm: 8px;
        --fl-space-md: 12px;
        --fl-space-lg: 16px;
        --fl-space-xl: 24px;
        --fl-space-2xl: 32px;
        --fl-radius-sm: 4px;
        --fl-radius-md: 6px;
        --fl-radius-lg: 8px;
    }

    /* ---------- 基础排版 ---------- */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
        font-family: var(--fl-font);
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
    }
    html, body, [data-testid="stAppViewContainer"] {
        background: var(--fl-bg);
        color: var(--fl-text);
        font-size: var(--fl-fs-body);
        line-height: $line_height_body;
    }
    [data-testid="stAppViewContainer"] .main,
    [data-testid="stAppViewContainer"] > .main {
        background: var(--fl-bg);
    }
    /* 去掉 Streamlit 自带的顶栏装饰、菜单与页脚，保留干净的画布 */
    [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer,
    [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
        display: none !important;
    }
    [data-testid="stAppViewBlockContainer"], .block-container {
        padding: 2.5rem 3rem 4rem 3rem;
        max-width: 1240px;
    }
    @media (max-width: 900px) {
        [data-testid="stAppViewBlockContainer"], .block-container {
            padding: 1.5rem 1rem 3rem 1rem;
        }
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: var(--fl-font);
        color: var(--fl-text);
        letter-spacing: -0.01em;
    }
    h1 { font-size: var(--fl-fs-page-title); font-weight: 600; line-height: 1.25; }
    h2 { font-size: var(--fl-fs-section); font-weight: 600; line-height: 1.35; }
    h3 {
        font-size: var(--fl-fs-section); font-weight: 600; line-height: 1.35;
        margin: 0 0 var(--fl-space-md) 0;
    }
    p, li, span, div { line-height: $line_height_body; }
    a { color: var(--fl-primary); text-decoration: none; }
    a:hover { text-decoration: underline; }
    strong { font-weight: 600; }
    code {
        font-family: var(--fl-font-mono);
        font-size: 0.9em;
        background: var(--fl-surface-subtle);
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-sm);
        padding: 0.1em 0.35em;
    }
    ::selection { background: var(--fl-primary-tint); color: var(--fl-text); }

    /* ---------- 侧边栏 ---------- */
    [data-testid="stSidebar"] {
        background: var(--fl-sidebar-bg);
        border-right: 1px solid var(--fl-border);
        width: 252px !important;
        min-width: 252px !important;
        /* 滚动条出现/消失时预留固定槽位，避免切换页面时内容宽度变化导致左右位移 */
        scrollbar-gutter: stable;
    }
    [data-testid="stSidebarContent"] {
        scrollbar-gutter: stable;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 0;
    }
    [data-testid="stSidebarUserContent"] {
        padding: 1.35rem 0.85rem 1.25rem 1.1rem;
        display: flex;
        flex-direction: column;
        min-height: calc(100vh - 2rem);
    }
    [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
        gap: 0 !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="element-container"] {
        margin: 0 !important;
        padding: 0 !important;
        min-height: 0;
    }
    /* 导航项等高：当前页用 st.markdown 渲染，其余项用 st.page_link 渲染，
       两者的外层容器高度天然不同（实测 markdown 容器 20px、page_link 容器
       34.8px）。切换页面时"当前项"换了位置，整列导航就会被推上推下一次。
       这里把两种外层盒子压成同一高度，保证切换前后布局完全一致。 */
    [data-testid="stSidebarUserContent"] [data-testid="element-container"]:has(.fl-nav-item),
    [data-testid="stSidebarUserContent"] [data-testid="stPageLink"] {
        height: 32px !important;
        min-height: 32px !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    [data-testid="stSidebarUserContent"] [data-testid="element-container"]:has(.fl-nav-item) > div,
    [data-testid="stSidebarUserContent"] [data-testid="element-container"]:has(.fl-nav-item) [data-testid="stMarkdownContainer"],
    [data-testid="stSidebarUserContent"] [data-testid="element-container"]:has(.fl-nav-item) [data-testid="stMarkdownContainer"] > div,
    [data-testid="stSidebarUserContent"] [data-testid="stPageLink-NavLink"],
    [data-testid="stSidebarUserContent"] .fl-nav-item {
        height: 32px !important;
        min-height: 32px !important;
        margin: 0 !important;
        padding-top: 0 !important;
        padding-bottom: 0 !important;
        box-sizing: border-box !important;
    }
    /* 让"偏好/设置"分组沉到侧边栏底部：
       先把 Streamlit 侧边栏的内容容器链撑满整列高度（它们默认按内容收缩），
       再给设置入口所在的元素容器一个 auto 上边距，即可推到最底部。
       注意：Streamlit 1.38 的元素容器 testid 是 element-container。 */
    [data-testid="stSidebarUserContent"] > div,
    [data-testid="stSidebarUserContent"] > div > div {
        flex: 1 1 auto;
        display: flex;
        flex-direction: column;
        min-height: 0;
    }
    [data-testid="stSidebarUserContent"] > div > div > [data-testid="stVerticalBlock"] {
        flex: 1 1 auto;
    }
    [data-testid="stSidebarUserContent"] [data-testid="element-container"]:has(.fl-nav-sep) {
        margin-top: auto !important;
        padding-top: 0.9rem;
    }
    .fl-nav-sep {
        display: block;
        height: 1px;
        background: var(--fl-border);
        margin: 0 0.35rem;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { margin: 0; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
        color: var(--fl-text-muted);
        font-size: calc(11px * var(--fl-scale));
        line-height: 1.5;
    }
    [data-testid="stSidebar"] hr { display: none; }

    /* 品牌区 */
    .fl-brand {
        padding: 0 0.35rem 1rem 0.35rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid var(--fl-border);
    }
    .fl-brand-name {
        font-size: calc(15px * var(--fl-scale));
        font-weight: 600;
        color: var(--fl-text);
        letter-spacing: -0.01em;
        line-height: 1.3;
    }
    .fl-brand-eyebrow {
        font-size: calc(10.5px * var(--fl-scale));
        font-weight: 500;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--fl-text-muted);
        margin-top: 3px;
    }
    .fl-brand-desc {
        font-size: calc(12px * var(--fl-scale));
        font-weight: 400;
        color: var(--fl-text-secondary);
        line-height: 1.55;
        margin-top: 10px;
    }

    /* 导航分组标题 */
    .fl-nav-group {
        font-size: calc(11px * var(--fl-scale));
        font-weight: 500;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--fl-text-muted);
        padding: 0 0.35rem;
        margin: 0.25rem 0 0.4rem 0;
    }

    /* 文字导航项：原生 st.page_link 与当前页 HTML 项共用同一套度量 */
    [data-testid="stPageLink"] { width: 100%; margin: 0; }
    [data-testid="stPageLink-NavLink"],
    .fl-nav-item {
        display: flex;
        align-items: center;
        box-sizing: border-box;
        width: 100%;
        min-height: 32px;
        padding: 6px 10px;
        border-radius: var(--fl-radius-md);
        font-size: calc(13px * var(--fl-scale));
        font-weight: 400;
        line-height: 1.4;
        color: var(--fl-text-secondary) !important;
        background: transparent;
        transition: background-color 0.12s ease, color 0.12s ease;
        margin: 1px 0;
    }
    [data-testid="stPageLink-NavLink"] p {
        font-size: inherit !important;
        font-weight: inherit !important;
        margin: 0 !important;
        color: inherit !important;
    }
    [data-testid="stPageLink-NavLink"]:hover,
    .fl-nav-item:hover {
        background: var(--fl-hover);
        color: var(--fl-text) !important;
        text-decoration: none;
    }
    .fl-nav-item.is-active {
        background: var(--fl-selected);
        color: var(--fl-text) !important;
        font-weight: 500;
    }

    /* 侧边栏底部信息 */
    .fl-sidebar-meta {
        padding: 0.75rem 0.35rem 0 0.35rem;
        margin-top: 0.5rem;
        border-top: 1px solid var(--fl-border);
        font-size: calc(11px * var(--fl-scale));
        color: var(--fl-text-muted);
        line-height: 1.6;
    }

    /* ---------- 页面头部 ---------- */
    .fl-page-header {
        margin: 0 0 var(--fl-space-xl) 0;
        padding-bottom: var(--fl-space-lg);
        border-bottom: 1px solid var(--fl-border);
    }
    .fl-page-header h1 {
        font-size: var(--fl-fs-page-title);
        font-weight: 600;
        color: var(--fl-text);
        margin: 0;
        line-height: 1.25;
        letter-spacing: -0.015em;
    }
    .fl-page-header p {
        margin: 6px 0 0 0;
        font-size: var(--fl-fs-page-subtitle);
        font-weight: 400;
        color: var(--fl-text-secondary);
    }
    .fl-page-header .fl-page-actions {
        margin-top: var(--fl-space-md);
        display: flex;
        gap: var(--fl-space-sm);
        align-items: center;
        flex-wrap: wrap;
    }

    /* ---------- 区域标题 ---------- */
    .fl-section {
        margin: 0 0 var(--fl-space-md) 0;
    }
    .fl-section-title {
        font-size: var(--fl-fs-section);
        font-weight: 600;
        color: var(--fl-text);
        line-height: 1.35;
        letter-spacing: -0.005em;
    }
    .fl-section-caption {
        font-size: var(--fl-fs-caption);
        font-weight: 400;
        color: var(--fl-text-secondary);
        margin-top: 4px;
        line-height: 1.5;
    }
    .fl-section + div { margin-top: 0; }

    /* ---------- 通用面板 / 定义列表 ---------- */
    .fl-panel {
        background: var(--fl-surface);
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-lg);
        padding: var(--fl-space-lg) var(--fl-space-xl);
    }
    .fl-panel-subtle {
        background: var(--fl-surface-subtle);
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-lg);
        padding: var(--fl-space-lg) var(--fl-space-xl);
    }
    .fl-panel-label {
        font-size: var(--fl-fs-card-title);
        font-weight: 500;
        color: var(--fl-text);
        margin-bottom: var(--fl-space-md);
    }
    .fl-panel-note {
        font-size: var(--fl-fs-caption);
        color: var(--fl-text-secondary);
        line-height: 1.5;
        margin-top: 4px;
    }

    .fl-kv { display: flex; flex-direction: column; gap: 0; }
    .fl-kv-row {
        display: flex;
        align-items: baseline;
        gap: var(--fl-space-lg);
        padding: 9px 0;
        border-bottom: 1px solid var(--fl-border);
    }
    .fl-kv-row:last-child { border-bottom: none; }
    .fl-kv-key {
        flex: 0 0 148px;
        font-size: var(--fl-fs-caption);
        color: var(--fl-text-secondary);
        font-weight: 400;
    }
    .fl-kv-val {
        flex: 1 1 auto;
        font-size: var(--fl-fs-body);
        color: var(--fl-text);
        font-weight: 400;
        word-break: break-word;
    }
    .fl-kv-val strong { font-weight: 600; }

    /* ---------- KPI ---------- */
    .fl-kpi {
        border-top: 1px solid var(--fl-border);
        padding-top: 10px;
    }
    .fl-kpi-label {
        font-size: var(--fl-fs-caption);
        color: var(--fl-text-secondary);
        font-weight: 400;
        line-height: 1.4;
    }
    .fl-kpi-value {
        font-size: var(--fl-fs-kpi);
        font-weight: 600;
        color: var(--fl-text);
        line-height: 1.15;
        letter-spacing: -0.02em;
        margin-top: 6px;
        font-variant-numeric: tabular-nums;
    }
    .fl-kpi-meta {
        font-size: var(--fl-fs-caption);
        color: var(--fl-text-muted);
        margin-top: 4px;
        line-height: 1.45;
    }
    /* 可点击的 KPI 用按钮实现（保留"点击跳转并带筛选"能力），
       去掉按钮外观，回到与 .fl-kpi 完全一致的度量：上边线 + 灰色小标签 + 大号数字。
       标签为两段 Markdown，因此按钮内恰好是两个 <p>。 */
    .stButton button:has([data-testid="stMarkdownContainer"] p + p) {
        display: block;
        width: 100%;
        text-align: left;
        background: transparent !important;
        border: none !important;
        border-top: 1px solid var(--fl-border) !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        padding: 10px 0 0 0 !important;
        min-height: 0 !important;
        height: auto !important;
        line-height: 1.35 !important;
    }
    .stButton button:has([data-testid="stMarkdownContainer"] p + p):hover,
    .stButton button:has([data-testid="stMarkdownContainer"] p + p):focus {
        background: transparent !important;
        border-top-color: var(--fl-border) !important;
        box-shadow: none !important;
    }
    .stButton button:has([data-testid="stMarkdownContainer"] p + p) [data-testid="stMarkdownContainer"] p:first-child {
        font-size: var(--fl-fs-caption) !important;
        color: var(--fl-text-secondary) !important;
        font-weight: 400 !important;
        margin: 0 !important;
        line-height: 1.4 !important;
    }
    .stButton button:has([data-testid="stMarkdownContainer"] p + p) [data-testid="stMarkdownContainer"] p:last-child {
        font-size: var(--fl-fs-kpi) !important;
        color: var(--fl-text) !important;
        font-weight: 600 !important;
        letter-spacing: -0.02em;
        margin: 6px 0 0 0 !important;
        line-height: 1.15 !important;
        font-variant-numeric: tabular-nums;
    }
    .stButton button:has([data-testid="stMarkdownContainer"] p + p) [data-testid="stMarkdownContainer"] p:last-child strong {
        font-weight: 600 !important;
    }
    .stButton button:has([data-testid="stMarkdownContainer"] p + p):hover [data-testid="stMarkdownContainer"] p:last-child {
        color: var(--fl-primary) !important;
    }

    /* Streamlit 原生 metric（详情页等处） */
    [data-testid="stMetric"] { padding: 0; }
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] p {
        font-size: var(--fl-fs-caption) !important;
        color: var(--fl-text-secondary) !important;
        font-weight: 400 !important;
    }
    [data-testid="stMetricValue"] {
        font-size: calc(22px * var(--fl-scale)) !important;
        font-weight: 600 !important;
        color: var(--fl-text) !important;
        line-height: 1.25 !important;
        font-variant-numeric: tabular-nums;
    }
    [data-testid="stMetricDelta"] { font-size: var(--fl-fs-caption) !important; }

    /* ---------- 按钮 ---------- */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
        font-family: var(--fl-font);
        font-size: var(--fl-fs-button);
        font-weight: 500;
        border-radius: var(--fl-radius-md);
        min-height: 32px;
        height: auto;
        padding: 6px 14px;
        border: 1px solid var(--fl-border);
        background: var(--fl-surface);
        color: var(--fl-text);
        box-shadow: none;
        transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
        background: var(--fl-hover);
        border-color: var(--fl-border-strong);
        color: var(--fl-text);
    }
    .stButton > button:focus, .stDownloadButton > button:focus, .stFormSubmitButton > button:focus {
        outline: none;
        box-shadow: 0 0 0 3px var(--fl-primary-tint);
        border-color: var(--fl-primary);
    }
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"] {
        background: var(--fl-primary);
        border-color: var(--fl-primary);
        color: var(--fl-primary-text);
    }
    .stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover {
        background: var(--fl-primary-hover);
        border-color: var(--fl-primary-hover);
        color: var(--fl-primary-text);
    }
    .stButton > button:disabled, .stFormSubmitButton > button:disabled {
        background: var(--fl-surface);
        color: var(--fl-text-muted);
        border-color: var(--fl-border);
        cursor: not-allowed;
    }

    /* ---------- 表单控件 ---------- */
    [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
        border-radius: var(--fl-radius-md) !important;
        border-color: var(--fl-border) !important;
        background: var(--fl-surface) !important;
        font-family: var(--fl-font) !important;
        font-size: var(--fl-fs-body) !important;
    }
    [data-baseweb="input"]:hover, [data-baseweb="select"] > div:hover {
        border-color: var(--fl-border-strong) !important;
    }
    [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within,
    [data-baseweb="textarea"]:focus-within {
        border-color: var(--fl-primary) !important;
        box-shadow: 0 0 0 3px var(--fl-primary-tint) !important;
    }
    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        font-family: var(--fl-font) !important;
        font-size: var(--fl-fs-body) !important;
        color: var(--fl-text) !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: var(--fl-text-muted) !important;
    }
    [data-testid="stWidgetLabel"] p, .stSelectbox label p, .stTextInput label p,
    .stTextArea label p, .stDateInput label p, .stCheckbox label p,
    .stRadio label p, .stMultiSelect label p {
        font-size: var(--fl-fs-label) !important;
        font-weight: 500 !important;
        color: var(--fl-text-secondary) !important;
    }
    [data-testid="stVerticalBlock"] { gap: 0.65rem; }
    [data-baseweb="popover"] li, [role="option"] {
        font-family: var(--fl-font) !important;
        font-size: var(--fl-fs-body) !important;
    }

    /* 单选横向（时间范围等） */
    .stRadio [role="radiogroup"] { gap: var(--fl-space-lg); }
    .stRadio [role="radiogroup"] label p {
        font-size: var(--fl-fs-body) !important;
        color: var(--fl-text-secondary) !important;
        font-weight: 400 !important;
    }

    /* 复选框 */
    .stCheckbox label p {
        font-size: var(--fl-fs-body) !important;
        color: var(--fl-text) !important;
        font-weight: 400 !important;
    }

    /* ---------- Tabs ---------- */
    .stTabs [data-baseweb="tab-list"] {
        gap: var(--fl-space-xl);
        border-bottom: 1px solid var(--fl-border);
        margin-bottom: var(--fl-space-lg);
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        padding: 0 0 10px 0;
        height: auto;
        color: var(--fl-text-secondary);
        font-size: var(--fl-fs-button);
        font-weight: 500;
    }
    .stTabs [data-baseweb="tab"] p {
        font-size: var(--fl-fs-button) !important;
        font-weight: 500 !important;
        color: inherit !important;
    }
    .stTabs [data-baseweb="tab"]:hover { color: var(--fl-text); }
    .stTabs [aria-selected="true"] { color: var(--fl-text) !important; }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: var(--fl-primary);
        height: 2px;
    }
    .stTabs [data-baseweb="tab-border"] { display: none; }

    /* ---------- 表格 ---------- */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-lg);
        overflow: hidden;
        font-size: var(--fl-fs-table);
    }
    [data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] { font-size: var(--fl-fs-table); }
    .stTable table, table {
        border-collapse: collapse;
        font-size: var(--fl-fs-table);
        width: 100%;
    }
    .stTable thead th, table thead th {
        background: var(--fl-surface-subtle);
        color: var(--fl-text-secondary);
        font-size: var(--fl-fs-caption);
        font-weight: 500;
        text-align: left;
        border: none;
        border-bottom: 1px solid var(--fl-border);
        padding: 8px 12px;
    }
    .stTable tbody td, table tbody td {
        border: none;
        border-bottom: 1px solid var(--fl-border);
        padding: 9px 12px;
        color: var(--fl-text);
        font-size: var(--fl-fs-table);
    }
    .stTable tbody tr:last-child td, table tbody tr:last-child td { border-bottom: none; }
    .stTable tbody tr:hover, table tbody tr:hover { background: var(--fl-hover); }

    /* ---------- 图表 ---------- */
    [data-testid="stPlotlyChart"] {
        background: transparent;
        border: none;
    }
    .js-plotly-plot .plotly .modebar { opacity: 0.35; }
    .js-plotly-plot .plotly .modebar:hover { opacity: 1; }

    /* ---------- 提示 / 空状态 ---------- */
    [data-testid="stAlert"], .stAlert {
        border-radius: var(--fl-radius-lg);
        border: 1px solid var(--fl-border);
        box-shadow: none;
        font-size: var(--fl-fs-body);
        padding: 12px 16px;
    }
    [data-testid="stAlert"] p { font-size: var(--fl-fs-body) !important; }
    .fl-empty {
        border: 1px dashed var(--fl-border);
        border-radius: var(--fl-radius-lg);
        padding: var(--fl-space-xl);
        text-align: center;
        background: var(--fl-surface-subtle);
    }
    .fl-empty-title {
        font-size: var(--fl-fs-body);
        font-weight: 500;
        color: var(--fl-text-secondary);
    }
    .fl-empty-hint {
        font-size: var(--fl-fs-caption);
        color: var(--fl-text-muted);
        margin-top: 6px;
    }

    /* ---------- 展开区 ---------- */
    [data-testid="stExpander"] {
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-lg);
        background: var(--fl-surface);
        box-shadow: none;
    }
    [data-testid="stExpander"] details summary {
        font-size: var(--fl-fs-card-title);
        font-weight: 500;
        color: var(--fl-text);
        padding: 10px 14px;
    }
    [data-testid="stExpander"] details summary:hover { background: var(--fl-hover); }
    [data-testid="stExpander"] details[open] summary { border-bottom: 1px solid var(--fl-border); }

    /* ---------- 分割线 ---------- */
    hr, [data-testid="stDivider"] hr {
        border: none;
        border-top: 1px solid var(--fl-border);
        margin: var(--fl-space-xl) 0;
    }

    /* ---------- 说明文字 ---------- */
    [data-testid="stCaptionContainer"] p, .stCaption, small {
        font-size: var(--fl-fs-caption) !important;
        color: var(--fl-text-secondary);
        line-height: 1.5;
    }
    [data-testid="stMarkdownContainer"] p { margin-bottom: 0.6rem; }
    [data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol {
        margin-top: 0.2rem;
        padding-left: 1.15rem;
    }
    [data-testid="stMarkdownContainer"] li { margin-bottom: 0.25rem; }

    /* ---------- 状态标签 ---------- */
    .fl-badge {
        display: inline-block;
        padding: 1px 7px;
        border-radius: var(--fl-radius-sm);
        font-size: calc(11.5px * var(--fl-scale));
        font-weight: 500;
        line-height: 1.6;
        white-space: nowrap;
        background: var(--fl-neutral-tint);
        color: var(--fl-neutral);
    }
    .fl-badge-success { background: var(--fl-success-tint); color: var(--fl-success); }
    .fl-badge-warning { background: var(--fl-warning-tint); color: var(--fl-warning); }
    .fl-badge-error { background: var(--fl-error-tint); color: var(--fl-error); }
    .fl-badge-primary { background: var(--fl-primary-tint); color: var(--fl-primary); }
    .fl-badge-neutral { background: var(--fl-neutral-tint); color: var(--fl-neutral); }

    /* 正文中的弱化标记（如"AI 推测"说明） */
    .fl-tag {
        display: inline-block;
        font-size: calc(11px * var(--fl-scale));
        font-weight: 500;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        color: var(--fl-text-muted);
        border: 1px solid var(--fl-border);
        border-radius: var(--fl-radius-sm);
        padding: 0 6px;
        line-height: 1.7;
        vertical-align: middle;
    }

    /* ---------- 主题色彩预览块（设置页） ---------- */
    .fl-swatch {
        height: 30px;
        border-radius: var(--fl-radius-md);
        border: 1px solid var(--fl-border);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: calc(11px * var(--fl-scale));
        font-weight: 500;
    }
    .fl-swatch.is-selected {
        box-shadow: 0 0 0 2px var(--fl-bg), 0 0 0 3px var(--fl-text-muted);
    }
</style>
"""
)


def build_theme_css(theme_key: str, font_size_key: str, custom_primary: str | None = None) -> str:
    """根据主题 + 字号生成全局样式（含 <style> 标签）。

    所有颜色/字号/间距都通过 CSS 变量集中输出，组件与页面引用变量而不是
    各自硬编码色值，保证全产品视觉语言一致（需求：统一设计系统）。
    """
    preset = get_theme(theme_key)
    primary = resolve_primary_color(theme_key, custom_primary)
    return _CSS_TEMPLATE.substitute(
        primary=primary,
        primary_hover=darken(primary, 0.1),
        primary_text=contrast_text_color(primary),
        primary_tint=COLOR_PRIMARY_TINT if primary == THEMES[DEFAULT_THEME].primary else rgba(primary, 0.08),
        accent=preset.accent,
        bg=COLOR_BG,
        sidebar_bg=COLOR_SIDEBAR_BG,
        surface=COLOR_SURFACE,
        surface_subtle=COLOR_SURFACE_SUBTLE,
        text=COLOR_TEXT,
        text_secondary=COLOR_TEXT_SECONDARY,
        text_muted=COLOR_TEXT_MUTED,
        border=COLOR_BORDER,
        border_strong=COLOR_BORDER_STRONG,
        hover=COLOR_HOVER,
        selected=COLOR_SELECTED,
        success=COLOR_SUCCESS,
        success_tint=COLOR_SUCCESS_TINT,
        warning=COLOR_WARNING,
        warning_tint=COLOR_WARNING_TINT,
        error=COLOR_ERROR,
        error_tint=COLOR_ERROR_TINT,
        neutral=COLOR_NEUTRAL_STATUS,
        neutral_tint=COLOR_NEUTRAL_TINT,
        font_stack=FONT_STACK,
        font_stack_mono=FONT_STACK_MONO,
        scale=font_scale(font_size_key),
        fs_page_title=f"{TYPE_SCALE['page-title'][0]}px",
        fs_page_subtitle=f"{TYPE_SCALE['page-subtitle'][0]}px",
        fs_section=f"{TYPE_SCALE['section-title'][0]}px",
        fs_card_title=f"{TYPE_SCALE['card-title'][0]}px",
        fs_body=f"{TYPE_SCALE['body'][0]}px",
        fs_caption=f"{TYPE_SCALE['caption'][0]}px",
        fs_kpi=f"{TYPE_SCALE['kpi'][0]}px",
        fs_table=f"{TYPE_SCALE['table'][0]}px",
        fs_button=f"{TYPE_SCALE['button'][0]}px",
        fs_label=f"{TYPE_SCALE['label'][0]}px",
        line_height_body=LINE_HEIGHT_BODY,
    )
