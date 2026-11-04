"""
主题配置模块。

提供预设主题（配色方案）和字体大小档位的集中定义，供
components/layout.py 根据用户偏好生成全局 CSS 注入。

设计原则：
    - 本模块只负责“主题数据 + CSS 生成”，不涉及 Streamlit 渲染调用，
      也不涉及用户偏好的读取/持久化（见 services/preferences_service.py）。
    - 业务状态色（成功/警告/错误）在所有主题下保持固定语义，不随主题变化，
      避免用户切换主题后无法识别风险等级/任务状态（需求文档 §4.3 第 6 条）。
"""

from __future__ import annotations

from dataclasses import dataclass

# --- 主题预设 ---

THEME_ORDER: tuple[str, ...] = ("navy", "tech_blue", "forest_green", "graphite")

DEFAULT_THEME = "navy"


@dataclass(frozen=True)
class ThemePreset:
    key: str
    name_zh: str
    name_en: str
    primary: str
    accent: str
    background: str


THEMES: dict[str, ThemePreset] = {
    "navy": ThemePreset(
        key="navy",
        name_zh="海军蓝",
        name_en="Navy Blue",
        primary="#172B4D",
        accent="#167D8D",
        background="#F5F7FA",
    ),
    "tech_blue": ThemePreset(
        key="tech_blue",
        name_zh="科技蓝",
        name_en="Tech Blue",
        primary="#2563EB",
        accent="#0EA5E9",
        background="#F5F8FF",
    ),
    "forest_green": ThemePreset(
        key="forest_green",
        name_zh="森林绿",
        name_en="Forest Green",
        primary="#176B57",
        accent="#43A68B",
        background="#F3F8F5",
    ),
    "graphite": ThemePreset(
        key="graphite",
        name_zh="石墨灰",
        name_en="Graphite Gray",
        primary="#374151",
        accent="#64748B",
        background="#F5F6F7",
    ),
}

# --- 固定语义色（不随主题变化） ---

COLOR_SUCCESS = "#16A36A"
COLOR_WARNING = "#E5A13B"
COLOR_ERROR = "#D9534F"
COLOR_TEXT = "#263445"
COLOR_TEXT_SECONDARY = "#738094"
COLOR_CARD_BG = "#FFFFFF"

# --- 字体大小档位 ---

FONT_SIZE_ORDER: tuple[str, ...] = ("small", "medium", "large")

DEFAULT_FONT_SIZE = "medium"

FONT_SIZE_LABELS_ZH = {"small": "小", "medium": "标准", "large": "大"}
FONT_SIZE_LABELS_EN = {"small": "Small", "medium": "Medium", "large": "Large"}

# 基准字号（px），作为 rem 换算基础；三档整体按比例缩放。
_FONT_SCALE = {"small": 0.9, "medium": 1.0, "large": 1.15}
_BASE_FONT_PX = 16


def get_theme(theme_key: str) -> ThemePreset:
    """按 key 获取主题预设，key 非法时回退到默认主题。"""
    return THEMES.get(theme_key, THEMES[DEFAULT_THEME])


def resolve_primary_color(theme_key: str, custom_primary: str | None) -> str:
    """返回最终生效的主色：自定义主色优先于预设主题主色。"""
    if custom_primary and is_valid_hex_color(custom_primary):
        return custom_primary
    return get_theme(theme_key).primary


def is_valid_hex_color(value: str) -> bool:
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


def font_scale(font_size_key: str) -> float:
    """返回字号档位对应的缩放比例，非法档位回退到标准档。"""
    return _FONT_SCALE.get(font_size_key, _FONT_SCALE[DEFAULT_FONT_SIZE])


def build_theme_css(theme_key: str, font_size_key: str, custom_primary: str | None = None) -> str:
    """根据主题 + 字体大小生成全局 CSS 注入内容（含 <style> 标签）。

    颜色通过 CSS 变量（design tokens）集中定义，组件样式引用变量而不是
    各自硬编码色值，便于统一维护（需求文档 §6 技术实现原则第 2 条）。
    字号通过统一的 --flowlens-font-scale 变量控制整体比例，而不是在
    各页面散落硬编码字号（需求文档 §4.2 第 7 条）。
    """
    preset = get_theme(theme_key)
    primary = resolve_primary_color(theme_key, custom_primary)
    accent = preset.accent
    background = preset.background
    scale = font_scale(font_size_key)
    base_px = round(_BASE_FONT_PX * scale, 1)

    return f"""
<style>
    :root {{
        --flowlens-primary: {primary};
        --flowlens-accent: {accent};
        --flowlens-background: {background};
        --flowlens-card-bg: {COLOR_CARD_BG};
        --flowlens-success: {COLOR_SUCCESS};
        --flowlens-warning: {COLOR_WARNING};
        --flowlens-error: {COLOR_ERROR};
        --flowlens-text: {COLOR_TEXT};
        --flowlens-text-secondary: {COLOR_TEXT_SECONDARY};
        --flowlens-font-scale: {scale};
        --flowlens-font-base: {base_px}px;
    }}

    html, body, [data-testid="stAppViewContainer"] {{
        font-size: var(--flowlens-font-base);
        color: var(--flowlens-text);
        font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial,
            "Segoe UI", Roboto, sans-serif;
    }}

    [data-testid="stAppViewContainer"] {{
        background: var(--flowlens-background);
    }}

    [data-testid="stSidebar"] {{
        background: var(--flowlens-primary);
    }}
    [data-testid="stSidebar"] * {{
        color: #ffffff !important;
    }}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{
        color: rgba(255,255,255,0.7) !important;
    }}
    [data-testid="stSidebar"] a {{
        color: #ffffff !important;
    }}
    [data-testid="stSidebarNavLink"][aria-current="page"] {{
        background-color: var(--flowlens-accent) !important;
        border-radius: 6px;
    }}

    .block-container {{
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1280px;
        font-size: 1em;
    }}

    .flowlens-page-header {{
        margin-bottom: 1.25rem;
    }}
    .flowlens-page-header h1 {{
        font-size: calc(1.6em * var(--flowlens-font-scale));
        font-weight: 600;
        margin-bottom: 0.15rem;
        color: var(--flowlens-text);
    }}
    .flowlens-page-header p {{
        color: var(--flowlens-text-secondary);
        font-size: calc(0.92em * var(--flowlens-font-scale));
        margin: 0;
    }}

    .flowlens-card {{
        background: var(--flowlens-card-bg);
        border: 1px solid #e6e9ee;
        border-radius: 10px;
        padding: 1rem 1.25rem;
    }}

    [data-testid="stMetricValue"] {{
        font-size: calc(1.6em * var(--flowlens-font-scale));
        color: var(--flowlens-text);
    }}
    [data-testid="stMetricLabel"] {{
        font-size: calc(0.85em * var(--flowlens-font-scale));
        color: var(--flowlens-text-secondary);
    }}

    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        border-radius: 6px;
        font-size: calc(1em * var(--flowlens-font-scale));
    }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        background-color: var(--flowlens-primary);
        border-color: var(--flowlens-primary);
    }}

    [data-testid="stDataFrame"], .stTable, table {{
        font-size: calc(0.95em * var(--flowlens-font-scale));
    }}

    h1, h2, h3 {{
        color: var(--flowlens-text);
    }}
    h2 {{ font-size: calc(1.3em * var(--flowlens-font-scale)); }}
    h3 {{ font-size: calc(1.1em * var(--flowlens-font-scale)); }}

    [data-testid="stCaptionContainer"] {{
        font-size: calc(0.85em * var(--flowlens-font-scale));
        color: var(--flowlens-text-secondary);
    }}

    .flowlens-settings-divider {{
        margin: 0.75rem 0;
        border-top: 1px solid rgba(255,255,255,0.18);
    }}
</style>
"""
