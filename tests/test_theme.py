"""
主题配置模块单元测试。

覆盖范围：
    - 主题预设查询与非法 key 回退。
    - 自定义主色校验（合法/非法十六进制颜色）。
    - 字体缩放比例映射与非法档位回退。
    - CSS 生成不抛异常，且包含预期的颜色/字号变量。
"""

from __future__ import annotations

import unittest

from config.theme import (
    DEFAULT_FONT_SIZE,
    DEFAULT_THEME,
    THEME_ORDER,
    build_theme_css,
    font_scale,
    get_theme,
    is_valid_hex_color,
    resolve_primary_color,
)


class TestThemePresets(unittest.TestCase):
    def test_get_theme_valid_key(self):
        preset = get_theme("tech_blue")
        self.assertEqual(preset.primary, "#2563EB")

    def test_get_theme_invalid_key_falls_back_to_default(self):
        preset = get_theme("not_a_real_theme")
        self.assertEqual(preset.key, DEFAULT_THEME)

    def test_all_four_presets_exist(self):
        self.assertEqual(len(THEME_ORDER), 4)
        self.assertIn("navy", THEME_ORDER)
        self.assertIn("tech_blue", THEME_ORDER)
        self.assertIn("forest_green", THEME_ORDER)
        self.assertIn("graphite", THEME_ORDER)


class TestHexColorValidation(unittest.TestCase):
    def test_valid_6_digit_hex(self):
        self.assertTrue(is_valid_hex_color("#172B4D"))

    def test_valid_3_digit_hex(self):
        self.assertTrue(is_valid_hex_color("#fff"))

    def test_invalid_missing_hash(self):
        self.assertFalse(is_valid_hex_color("172B4D"))

    def test_invalid_non_hex_characters(self):
        self.assertFalse(is_valid_hex_color("#ZZZZZZ"))

    def test_invalid_wrong_length(self):
        self.assertFalse(is_valid_hex_color("#1234"))

    def test_invalid_empty_string(self):
        self.assertFalse(is_valid_hex_color(""))

    def test_invalid_none(self):
        self.assertFalse(is_valid_hex_color(None))


class TestResolvePrimaryColor(unittest.TestCase):
    def test_custom_color_takes_precedence(self):
        result = resolve_primary_color("navy", "#ABCDEF")
        self.assertEqual(result, "#ABCDEF")

    def test_invalid_custom_color_falls_back_to_theme(self):
        result = resolve_primary_color("navy", "not-a-color")
        self.assertEqual(result, get_theme("navy").primary)

    def test_none_custom_color_uses_theme(self):
        result = resolve_primary_color("tech_blue", None)
        self.assertEqual(result, get_theme("tech_blue").primary)


class TestFontScale(unittest.TestCase):
    def test_small_is_less_than_medium(self):
        self.assertLess(font_scale("small"), font_scale("medium"))

    def test_large_is_greater_than_medium(self):
        self.assertGreater(font_scale("large"), font_scale("medium"))

    def test_invalid_font_size_falls_back_to_default(self):
        self.assertEqual(font_scale("huge"), font_scale(DEFAULT_FONT_SIZE))


class TestBuildThemeCss(unittest.TestCase):
    def test_css_contains_theme_colors(self):
        css = build_theme_css("navy", "medium")
        self.assertIn("#172B4D", css)
        self.assertIn("<style>", css)

    def test_css_contains_custom_primary_when_provided(self):
        css = build_theme_css("navy", "medium", custom_primary="#ABCDEF")
        self.assertIn("#ABCDEF", css)

    def test_css_does_not_raise_for_any_theme_and_font_combo(self):
        for theme_key in THEME_ORDER:
            for font_key in ("small", "medium", "large"):
                css = build_theme_css(theme_key, font_key)
                self.assertIsInstance(css, str)
                self.assertGreater(len(css), 0)

    def test_semantic_colors_present_regardless_of_theme(self):
        """成功/警告/错误色不随主题变化，所有主题下都应出现在CSS中。"""
        from config.theme import COLOR_ERROR, COLOR_SUCCESS, COLOR_WARNING

        for theme_key in THEME_ORDER:
            css = build_theme_css(theme_key, "medium")
            self.assertIn(COLOR_SUCCESS, css)
            self.assertIn(COLOR_WARNING, css)
            self.assertIn(COLOR_ERROR, css)


if __name__ == "__main__":
    unittest.main()
