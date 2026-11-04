"""
用户个性化偏好的读取与持久化。

设计原则（对应需求文档 §4.4）：
    - 使用独立的本地 JSON 配置文件保存用户偏好（config/user_preferences.json），
      不修改原有业务数据库结构，不与业务数据/规则混在一起。
    - 文件不存在时自动创建默认配置；读取失败或内容非法时安全回退到默认值，
      不让页面因为一个坏的配置文件而崩溃。
    - 保存异常会被捕获并返回明确的失败信号，调用方（页面）负责向用户提示。
    - 本模块只负责“偏好数据的读写与校验”，不涉及任何 Streamlit UI 调用，
      也不涉及 CSS/主题渲染（那是 config/theme.py 和 components/layout.py 的职责）。

Session State 同步：
    - sync_preferences_into_session() 应在每个页面渲染最开始调用一次，
      确保 st.session_state 中的语言/字体/主题与持久化文件一致（主要用于
      多浏览器标签页或重启应用后的首次加载）。
    - 设置页面修改偏好后，直接调用 save_preferences() 持久化，并更新
      session_state，使当前会话立即生效，无需用户手动刷新。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import streamlit as st

from config.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, set_current_language
from config.theme import DEFAULT_FONT_SIZE, DEFAULT_THEME, FONT_SIZE_ORDER, THEME_ORDER, is_valid_hex_color

BASE_DIR = Path(__file__).resolve().parent.parent
PREFERENCES_PATH = BASE_DIR / "config" / "user_preferences.json"

_SESSION_FONT_KEY = "flowlens_font_size"
_SESSION_THEME_KEY = "flowlens_theme"
_SESSION_CUSTOM_PRIMARY_KEY = "flowlens_custom_primary"
_SESSION_LOADED_FLAG = "flowlens_preferences_loaded"


@dataclass(frozen=True)
class UserPreferences:
    language: str = DEFAULT_LANGUAGE
    font_size: str = DEFAULT_FONT_SIZE
    theme: str = DEFAULT_THEME
    custom_primary_color: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_PREFERENCES = UserPreferences()


def _validate(raw: dict) -> UserPreferences:
    """校验原始字典，非法值回退到默认值；不会抛出异常。"""
    language = raw.get("language")
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    font_size = raw.get("font_size")
    if font_size not in FONT_SIZE_ORDER:
        font_size = DEFAULT_FONT_SIZE

    theme = raw.get("theme")
    if theme not in THEME_ORDER:
        theme = DEFAULT_THEME

    custom_primary_color = raw.get("custom_primary_color")
    if custom_primary_color is not None and not is_valid_hex_color(custom_primary_color):
        custom_primary_color = None

    return UserPreferences(
        language=language,
        font_size=font_size,
        theme=theme,
        custom_primary_color=custom_primary_color,
    )


def load_preferences() -> UserPreferences:
    """从本地 JSON 文件读取用户偏好。

    文件不存在：自动创建默认配置文件并返回默认值。
    文件存在但内容非法（损坏的 JSON、字段类型错误等）：不覆盖原文件，
    直接安全回退到默认值返回，避免误删用户已有的（可能只是部分损坏的）配置。
    """
    if not PREFERENCES_PATH.exists():
        save_preferences(DEFAULT_PREFERENCES)
        return DEFAULT_PREFERENCES

    try:
        raw = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return DEFAULT_PREFERENCES
        return _validate(raw)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PREFERENCES


def save_preferences(preferences: UserPreferences) -> bool:
    """将用户偏好写入本地 JSON 文件。

    返回:
        True 表示保存成功；False 表示保存失败（调用方应向用户展示明确提示，
        不得静默吞掉失败）。
    """
    try:
        PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_PATH.write_text(
            json.dumps(preferences.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def sync_preferences_into_session() -> UserPreferences:
    """确保 st.session_state 中的偏好与持久化文件一致。

    只在本次会话第一次调用时真正从磁盘读取（通过 _SESSION_LOADED_FLAG 标记），
    避免每次 rerun 都重新读文件；设置页面保存后会直接更新 session_state 并
    保持该标记，不需要重新从磁盘加载。
    """
    if not st.session_state.get(_SESSION_LOADED_FLAG):
        preferences = load_preferences()
        apply_preferences_to_session(preferences)
        st.session_state[_SESSION_LOADED_FLAG] = True
        return preferences

    return get_current_preferences()


def apply_preferences_to_session(preferences: UserPreferences) -> None:
    """把偏好对象写入 session_state 的各个字段，使当前会话立即生效。"""
    set_current_language(preferences.language)
    st.session_state[_SESSION_FONT_KEY] = preferences.font_size
    st.session_state[_SESSION_THEME_KEY] = preferences.theme
    st.session_state[_SESSION_CUSTOM_PRIMARY_KEY] = preferences.custom_primary_color


def get_current_preferences() -> UserPreferences:
    """从 session_state 读取当前生效的偏好（不读取磁盘）。"""
    from config.i18n import get_current_language

    return UserPreferences(
        language=get_current_language(),
        font_size=st.session_state.get(_SESSION_FONT_KEY, DEFAULT_FONT_SIZE),
        theme=st.session_state.get(_SESSION_THEME_KEY, DEFAULT_THEME),
        custom_primary_color=st.session_state.get(_SESSION_CUSTOM_PRIMARY_KEY),
    )


def update_preferences(
    *,
    language: str | None = None,
    font_size: str | None = None,
    theme: str | None = None,
    custom_primary_color: str | None = "__unset__",
) -> tuple[UserPreferences, bool]:
    """更新偏好并立即持久化 + 同步到 session_state。

    参数为 None 表示“不修改该字段”；custom_primary_color 用哨兵值
    "__unset__" 区分“不修改”与“显式设置为 None（关闭自定义颜色）”。

    返回:
        (新的偏好对象, 是否保存成功)
    """
    current = get_current_preferences()
    new_preferences = UserPreferences(
        language=language if language is not None else current.language,
        font_size=font_size if font_size is not None else current.font_size,
        theme=theme if theme is not None else current.theme,
        custom_primary_color=(
            current.custom_primary_color if custom_primary_color == "__unset__" else custom_primary_color
        ),
    )
    validated = _validate(new_preferences.to_dict())
    ok = save_preferences(validated)
    if ok:
        apply_preferences_to_session(validated)
    return validated, ok


def reset_to_defaults() -> bool:
    """恢复默认设置：持久化默认值并同步到 session_state。"""
    ok = save_preferences(DEFAULT_PREFERENCES)
    if ok:
        apply_preferences_to_session(DEFAULT_PREFERENCES)
    return ok
