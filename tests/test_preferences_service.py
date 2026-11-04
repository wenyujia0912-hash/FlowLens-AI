"""
用户偏好持久化服务单元测试。

覆盖范围（对应需求文档 §8.4）：
    - 用户设置读取与保存。
    - 文件不存在时自动创建默认配置。
    - 非法配置值处理（回退到默认值，不抛异常）。
    - 默认设置恢复。
    - Session State 与持久化文件同步。

本测试通过 monkeypatch 将 PREFERENCES_PATH 重定向到临时文件，
不污染项目实际的 config/user_preferences.json。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services import preferences_service as prefs
from config.theme import DEFAULT_FONT_SIZE, DEFAULT_THEME
from config.i18n import DEFAULT_LANGUAGE


class FakeSessionState(dict):
    """最小化模拟 st.session_state：支持字典式访问。"""


class BasePreferencesTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._original_path = prefs.PREFERENCES_PATH
        prefs.PREFERENCES_PATH = Path(self._tmpdir.name) / "user_preferences.json"

        import streamlit as st

        self._original_session_state = st.session_state
        st.session_state = FakeSessionState()

    def tearDown(self):
        prefs.PREFERENCES_PATH = self._original_path
        self._tmpdir.cleanup()

        import streamlit as st

        st.session_state = self._original_session_state


class TestLoadPreferences(BasePreferencesTest):
    def test_file_not_exists_creates_default(self):
        self.assertFalse(prefs.PREFERENCES_PATH.exists())
        result = prefs.load_preferences()
        self.assertEqual(result, prefs.DEFAULT_PREFERENCES)
        self.assertTrue(prefs.PREFERENCES_PATH.exists())

    def test_valid_file_loads_correctly(self):
        prefs.PREFERENCES_PATH.write_text(
            json.dumps({"language": "en", "font_size": "large", "theme": "tech_blue", "custom_primary_color": None})
        )
        result = prefs.load_preferences()
        self.assertEqual(result.language, "en")
        self.assertEqual(result.font_size, "large")
        self.assertEqual(result.theme, "tech_blue")

    def test_malformed_json_falls_back_to_default(self):
        prefs.PREFERENCES_PATH.write_text("{not valid json!!")
        result = prefs.load_preferences()
        self.assertEqual(result, prefs.DEFAULT_PREFERENCES)

    def test_non_dict_json_falls_back_to_default(self):
        prefs.PREFERENCES_PATH.write_text(json.dumps([1, 2, 3]))
        result = prefs.load_preferences()
        self.assertEqual(result, prefs.DEFAULT_PREFERENCES)

    def test_invalid_language_value_falls_back(self):
        prefs.PREFERENCES_PATH.write_text(json.dumps({"language": "french", "font_size": "medium", "theme": "navy"}))
        result = prefs.load_preferences()
        self.assertEqual(result.language, DEFAULT_LANGUAGE)

    def test_invalid_font_size_value_falls_back(self):
        prefs.PREFERENCES_PATH.write_text(json.dumps({"language": "zh", "font_size": "huge", "theme": "navy"}))
        result = prefs.load_preferences()
        self.assertEqual(result.font_size, DEFAULT_FONT_SIZE)

    def test_invalid_theme_value_falls_back(self):
        prefs.PREFERENCES_PATH.write_text(json.dumps({"language": "zh", "font_size": "medium", "theme": "rainbow"}))
        result = prefs.load_preferences()
        self.assertEqual(result.theme, DEFAULT_THEME)

    def test_invalid_custom_color_falls_back_to_none(self):
        prefs.PREFERENCES_PATH.write_text(
            json.dumps({"language": "zh", "font_size": "medium", "theme": "navy", "custom_primary_color": "not-a-hex"})
        )
        result = prefs.load_preferences()
        self.assertIsNone(result.custom_primary_color)

    def test_valid_custom_color_preserved(self):
        prefs.PREFERENCES_PATH.write_text(
            json.dumps({"language": "zh", "font_size": "medium", "theme": "navy", "custom_primary_color": "#ABCDEF"})
        )
        result = prefs.load_preferences()
        self.assertEqual(result.custom_primary_color, "#ABCDEF")


class TestSavePreferences(BasePreferencesTest):
    def test_save_creates_readable_file(self):
        preferences = prefs.UserPreferences(language="en", font_size="small", theme="graphite", custom_primary_color=None)
        ok = prefs.save_preferences(preferences)
        self.assertTrue(ok)
        reloaded = prefs.load_preferences()
        self.assertEqual(reloaded, preferences)

    def test_save_handles_unwritable_directory_gracefully(self):
        # 指向一个不存在且无法创建的路径（父目录是文件而非目录）。
        bad_parent = Path(self._tmpdir.name) / "not_a_dir"
        bad_parent.write_text("i am a file, not a directory")
        prefs.PREFERENCES_PATH = bad_parent / "user_preferences.json"
        ok = prefs.save_preferences(prefs.DEFAULT_PREFERENCES)
        self.assertFalse(ok)


class TestUpdateAndReset(BasePreferencesTest):
    def test_update_preferences_persists_and_syncs_session(self):
        prefs.sync_preferences_into_session()
        new_prefs, ok = prefs.update_preferences(language="en", font_size="large", theme="forest_green")
        self.assertTrue(ok)
        self.assertEqual(new_prefs.language, "en")
        self.assertEqual(new_prefs.font_size, "large")
        self.assertEqual(new_prefs.theme, "forest_green")

        reloaded = prefs.load_preferences()
        self.assertEqual(reloaded, new_prefs)

        current = prefs.get_current_preferences()
        self.assertEqual(current.language, "en")

    def test_update_preferences_partial_update_keeps_other_fields(self):
        prefs.sync_preferences_into_session()
        prefs.update_preferences(language="en", font_size="large", theme="forest_green")
        new_prefs, ok = prefs.update_preferences(font_size="small")
        self.assertTrue(ok)
        self.assertEqual(new_prefs.language, "en")
        self.assertEqual(new_prefs.font_size, "small")
        self.assertEqual(new_prefs.theme, "forest_green")

    def test_custom_primary_color_unset_sentinel_preserves_value(self):
        prefs.sync_preferences_into_session()
        prefs.update_preferences(custom_primary_color="#123456")
        new_prefs, ok = prefs.update_preferences(font_size="large")
        self.assertTrue(ok)
        self.assertEqual(new_prefs.custom_primary_color, "#123456")

    def test_custom_primary_color_explicit_none_clears_value(self):
        prefs.sync_preferences_into_session()
        prefs.update_preferences(custom_primary_color="#123456")
        new_prefs, ok = prefs.update_preferences(custom_primary_color=None)
        self.assertTrue(ok)
        self.assertIsNone(new_prefs.custom_primary_color)

    def test_reset_to_defaults_restores_all_fields(self):
        prefs.sync_preferences_into_session()
        prefs.update_preferences(language="en", font_size="large", theme="forest_green", custom_primary_color="#123456")

        ok = prefs.reset_to_defaults()
        self.assertTrue(ok)

        current = prefs.get_current_preferences()
        self.assertEqual(current.language, DEFAULT_LANGUAGE)
        self.assertEqual(current.font_size, DEFAULT_FONT_SIZE)
        self.assertEqual(current.theme, DEFAULT_THEME)
        self.assertIsNone(current.custom_primary_color)

        reloaded = prefs.load_preferences()
        self.assertEqual(reloaded, prefs.DEFAULT_PREFERENCES)


class TestSessionSync(BasePreferencesTest):
    def test_sync_only_loads_from_disk_once_per_session(self):
        prefs.PREFERENCES_PATH.write_text(
            json.dumps({"language": "en", "font_size": "large", "theme": "navy", "custom_primary_color": None})
        )
        first = prefs.sync_preferences_into_session()
        self.assertEqual(first.language, "en")

        # 修改磁盘文件后再次调用 sync；由于本次会话已标记为"已加载"，
        # 不应重新从磁盘读取，应保持 session_state 中已有的值。
        prefs.PREFERENCES_PATH.write_text(
            json.dumps({"language": "zh", "font_size": "small", "theme": "graphite", "custom_primary_color": None})
        )
        second = prefs.sync_preferences_into_session()
        self.assertEqual(second.language, "en")

    def test_apply_preferences_to_session_sets_language(self):
        from config.i18n import get_current_language

        preferences = prefs.UserPreferences(language="en", font_size="medium", theme="navy", custom_primary_color=None)
        prefs.apply_preferences_to_session(preferences)
        self.assertEqual(get_current_language(), "en")


if __name__ == "__main__":
    unittest.main()
