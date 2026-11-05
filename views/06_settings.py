"""
个性化设置页面。

对应需求文档 §4："新增个性化设置功能"，重设计后仅调整本页的呈现方式：
    - 语言（简体中文 / English）
    - 字体大小（小 / 标准 / 大）
    - 主题颜色（四套预设 + 可选自定义主色）

所有已有的设置能力都保留：读取、修改、保存、持久化、恢复默认。
视觉上改为按分组的两栏布局（左侧控件、右侧说明/预览），不使用彩色卡片；
主题选择以小尺寸色块预览呈现，而非大面积色块。

持久化：services/preferences_service.py，写入 config/user_preferences.json。
保存后立即更新 session_state 并 st.rerun()，使本次会话立即生效。

不包含任何业务数据读取，不影响规则引擎/AI诊断/任务流转等业务逻辑。
"""

from __future__ import annotations

import html

import streamlit as st

from components.layout import inject_base_styles, render_kv_list, render_page_header, render_section
from config.i18n import LANGUAGE_LABELS, SUPPORTED_LANGUAGES, t
from config.settings import get_config
from config.theme import (
    FONT_SIZE_LABELS_EN,
    FONT_SIZE_LABELS_ZH,
    FONT_SIZE_ORDER,
    THEME_ORDER,
    THEMES,
    contrast_text_color,
    font_scale,
    get_theme,
    is_valid_hex_color,
)
from database.connection import check_connection
from services.preferences_service import get_current_preferences, reset_to_defaults, update_preferences

inject_base_styles()

render_page_header(title_key="settings.title", subtitle_key="settings.subtitle")

preferences = get_current_preferences()
current_language = preferences.language

font_labels_map = FONT_SIZE_LABELS_ZH if current_language == "zh" else FONT_SIZE_LABELS_EN

save_feedback_slot = st.empty()


def _theme_label(key: str) -> str:
    preset = get_theme(key)
    return preset.name_zh if current_language == "zh" else preset.name_en


# ======================================================================
# 区域一：语言设置
# ======================================================================

render_section("settings.section.language")

lang_cols = st.columns([1.6, 3.4], gap="large")
with lang_cols[0]:
    language_options = list(SUPPORTED_LANGUAGES)
    selected_language = st.selectbox(
        t("settings.language_select"),
        options=language_options,
        index=language_options.index(current_language) if current_language in language_options else 0,
        format_func=lambda key: LANGUAGE_LABELS.get(key, key),
        key="settings_language_select",
    )
with lang_cols[1]:
    st.markdown('<div style="height: 26px"></div>', unsafe_allow_html=True)
    st.caption(t("settings.current_language", language=LANGUAGE_LABELS.get(current_language, current_language)))

st.divider()


# ======================================================================
# 区域二：字体设置
# ======================================================================

render_section("settings.section.font")

font_cols = st.columns([1.6, 3.4], gap="large")
with font_cols[0]:
    font_options = list(FONT_SIZE_ORDER)
    selected_font_size = st.selectbox(
        t("settings.font_select"),
        options=font_options,
        index=font_options.index(preferences.font_size) if preferences.font_size in font_options else 1,
        format_func=lambda key: font_labels_map.get(key, key),
        key="settings_font_select",
    )
with font_cols[1]:
    _preview_scale = font_scale(selected_font_size)
    preview_html = (
        '<div style="padding:2px 0 10px 0;">'
        '<div style="font-size:calc(11px * var(--fl-scale));color:var(--fl-text-muted);margin-bottom:8px;">'
        f'{html.escape(t("settings.font_preview_label"))}</div>'
        f'<div style="font-size:calc(15px * {_preview_scale});color:var(--fl-text);line-height:1.6;'
        'padding:12px 16px;background:var(--fl-surface-subtle);border:1px solid var(--fl-border);'
        f'border-radius:var(--fl-radius-lg);">{html.escape(t("settings.font_preview_text"))}</div>'
        "</div>"
    )
    st.markdown(preview_html, unsafe_allow_html=True)

st.divider()


# ======================================================================
# 区域三：主题颜色
# ======================================================================

render_section("settings.section.theme")

theme_options = list(THEME_ORDER)

theme_cols = st.columns([1.6, 3.4], gap="large")
with theme_cols[0]:
    selected_theme = st.selectbox(
        t("settings.theme_select"),
        options=theme_options,
        index=theme_options.index(preferences.theme) if preferences.theme in theme_options else 0,
        format_func=_theme_label,
        key="settings_theme_select",
    )
with theme_cols[1]:
    st.markdown(
        f'<div style="font-size:calc(11px * var(--fl-scale));color:var(--fl-text-muted);'
        f'margin:4px 0 8px 0;">{html.escape(t("settings.theme_preview_label"))}</div>',
        unsafe_allow_html=True,
    )
    preview_cols = st.columns(len(theme_options), gap="small")
    for col, key in zip(preview_cols, theme_options):
        preset = THEMES[key]
        is_selected = key == selected_theme
        with col:
            # 必须从行首开始输出、且不使用缩进：缩进的 HTML 会被 Markdown
            # 当作代码块原样显示（而不是渲染成色块）。
            swatch_html = (
                f'<div class="fl-swatch{" is-selected" if is_selected else ""}" '
                f'style="background:{preset.primary};color:{contrast_text_color(preset.primary)}">'
                f'{"Aa" if is_selected else ""}</div>'
                f'<div style="font-size:calc(11px * var(--fl-scale));'
                f'color:{"var(--fl-text)" if is_selected else "var(--fl-text-muted)"};'
                f'margin-top:6px;text-align:center;">{html.escape(_theme_label(key))}</div>'
            )
            st.markdown(swatch_html, unsafe_allow_html=True)

st.markdown('<div style="height: 16px"></div>', unsafe_allow_html=True)

custom_color_enabled = st.checkbox(
    t("settings.custom_color_toggle"),
    value=bool(preferences.custom_primary_color),
    key="settings_custom_color_toggle",
)

selected_custom_color: str | None = None
if custom_color_enabled:
    picker_col, note_col = st.columns([1.6, 3.4], gap="large")
    with picker_col:
        default_color = preferences.custom_primary_color or get_theme(selected_theme).primary
        selected_custom_color = st.color_picker(
            t("settings.custom_color_picker"),
            value=default_color if is_valid_hex_color(default_color) else "#3B5CCC",
            key="settings_custom_color_picker",
        )
    with note_col:
        st.markdown('<div style="height: 26px"></div>', unsafe_allow_html=True)
        st.caption(t("settings.custom_color_hint"))

st.divider()


# ======================================================================
# 区域四：设置操作
# ======================================================================

render_section("settings.section.actions")
st.caption(t("settings.save_hint"))

action_cols = st.columns([1, 1, 2], gap="small")

with action_cols[0]:
    save_clicked = st.button(t("common.save"), key="settings_save_button", type="primary")

with action_cols[1]:
    reset_clicked = st.button(t("common.reset_default"), key="settings_reset_button")

if save_clicked:
    new_preferences, ok = update_preferences(
        language=selected_language,
        font_size=selected_font_size,
        theme=selected_theme,
        custom_primary_color=selected_custom_color if custom_color_enabled else None,
    )
    if ok:
        save_feedback_slot.success(t("common.save_success"))
        st.rerun()
    else:
        save_feedback_slot.error(t("common.save_failed"))

if reset_clicked:
    ok = reset_to_defaults()
    if ok:
        save_feedback_slot.success(t("settings.reset_success"))
        st.rerun()
    else:
        save_feedback_slot.error(t("common.save_failed"))

st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
render_section("settings.current_preview_title")
preview_rows = [
    (t("settings.preview.language"), LANGUAGE_LABELS.get(preferences.language, preferences.language)),
    (t("settings.preview.font"), font_labels_map.get(preferences.font_size, preferences.font_size)),
    (t("settings.preview.theme"), _theme_label(preferences.theme)),
]
render_kv_list(preview_rows)

st.divider()

# ======================================================================
# 区域五：运行环境自检（原首页的开发调试信息）
# ======================================================================

with st.expander(t("settings.env_expander")):
    _config = get_config()
    render_kv_list(
        [
            ("APP_ENV", _config.app_env),
            ("AI_MODE", _config.ai_mode),
            ("DATABASE_PATH", str(_config.database_path)),
            ("DEMO_MODE", str(_config.demo_mode)),
        ]
    )
    if check_connection():
        st.caption(t("settings.env_db_ok"))
    else:
        st.error(t("settings.env_db_failed"))
