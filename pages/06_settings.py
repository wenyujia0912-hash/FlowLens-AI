"""
个性化设置页面。

对应需求文档 §4："新增个性化设置功能"。

本页面让用户调整：
    - 语言（简体中文 / English）
    - 字体大小（小 / 标准 / 大）
    - 主题颜色（四套预设 + 可选自定义主色）

持久化：services/preferences_service.py，写入 config/user_preferences.json。
保存后立即更新 session_state 并 st.rerun()，使本次会话立即生效，同时刷新页面
让用户看到"已保存"的明确反馈（需求文档 §4.4、§4.5）。

不包含任何业务数据读取，不影响规则引擎/AI诊断/任务流转等业务逻辑。
"""

from __future__ import annotations

import streamlit as st

from components.layout import inject_base_styles, render_page_header, render_sidebar_footer
from config.i18n import LANGUAGE_LABELS, SUPPORTED_LANGUAGES, t
from config.theme import (
    FONT_SIZE_LABELS_EN,
    FONT_SIZE_LABELS_ZH,
    FONT_SIZE_ORDER,
    THEME_ORDER,
    THEMES,
    get_theme,
    is_valid_hex_color,
)
from services.preferences_service import get_current_preferences, reset_to_defaults, update_preferences

inject_base_styles()

render_page_header(title_key="settings.title", subtitle_key="settings.subtitle")

preferences = get_current_preferences()
current_language = preferences.language

font_labels_map = FONT_SIZE_LABELS_ZH if current_language == "zh" else FONT_SIZE_LABELS_EN

save_feedback_slot = st.empty()


# ======================================================================
# 区域一：语言设置
# ======================================================================

st.markdown(f"### {t('settings.section.language')}")

lang_cols = st.columns([2, 3])
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
    st.caption(t("settings.current_language", language=LANGUAGE_LABELS.get(current_language, current_language)))

st.divider()


# ======================================================================
# 区域二：字体设置
# ======================================================================

st.markdown(f"### {t('settings.section.font')}")

font_cols = st.columns([2, 3])
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
    _preview_scale = {"small": 0.9, "medium": 1.0, "large": 1.15}.get(selected_font_size, 1.0)
    st.caption(t("settings.font_preview_label"))
    st.markdown(
        f'<div style="font-size: {1.1 * _preview_scale:.2f}rem; padding: 0.5rem 0;">'
        f'{t("settings.font_preview_text")}</div>',
        unsafe_allow_html=True,
    )

st.divider()


# ======================================================================
# 区域三：主题颜色
# ======================================================================

st.markdown(f"### {t('settings.section.theme')}")

theme_options = list(THEME_ORDER)


def _theme_label(key: str) -> str:
    preset = get_theme(key)
    return preset.name_zh if current_language == "zh" else preset.name_en


theme_cols = st.columns([2, 3])
with theme_cols[0]:
    selected_theme = st.selectbox(
        t("settings.theme_select"),
        options=theme_options,
        index=theme_options.index(preferences.theme) if preferences.theme in theme_options else 0,
        format_func=_theme_label,
        key="settings_theme_select",
    )
with theme_cols[1]:
    st.caption(t("settings.theme_preview_label"))
    preview_cols = st.columns(len(theme_options))
    for col, key in zip(preview_cols, theme_options):
        preset = THEMES[key]
        with col:
            st.markdown(
                f"""
                <div style="text-align:center;">
                    <div style="
                        display:flex; border-radius:6px; overflow:hidden;
                        border: {'2px solid #263445' if key == selected_theme else '1px solid #e6e9ee'};
                        height: 28px; margin-bottom: 4px;
                    ">
                        <div style="flex:1; background:{preset.primary};"></div>
                        <div style="flex:1; background:{preset.accent};"></div>
                    </div>
                    <div style="font-size:0.75rem; color:#738094;">{_theme_label(key)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

custom_color_enabled = st.checkbox(
    t("settings.custom_color_toggle"),
    value=bool(preferences.custom_primary_color),
    key="settings_custom_color_toggle",
)

selected_custom_color: str | None = None
if custom_color_enabled:
    default_color = preferences.custom_primary_color or get_theme(selected_theme).primary
    selected_custom_color = st.color_picker(
        t("settings.custom_color_picker"),
        value=default_color if is_valid_hex_color(default_color) else "#172B4D",
        key="settings_custom_color_picker",
    )

st.divider()


# ======================================================================
# 区域四：设置操作
# ======================================================================

st.markdown(f"### {t('settings.section.actions')}")
st.caption(t("settings.save_hint"))

action_cols = st.columns([1, 1, 3])

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

with action_cols[2]:
    pass

st.markdown(f"**{t('settings.current_preview_title')}**")
preview_display_cols = st.columns(3)
with preview_display_cols[0]:
    st.metric(t("settings.preview.language"), LANGUAGE_LABELS.get(preferences.language, preferences.language))
with preview_display_cols[1]:
    st.metric(t("settings.preview.font"), font_labels_map.get(preferences.font_size, preferences.font_size))
with preview_display_cols[2]:
    st.metric(t("settings.preview.theme"), _theme_label(preferences.theme))

render_sidebar_footer()
