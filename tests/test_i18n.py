"""
国际化（i18n）翻译字典单元测试。

覆盖范围（对应需求文档 §8.4"测试与验收 - 补充测试重点"）：
    - 语言映射：t() 在中/英文下返回正确文案。
    - 占位符格式化。
    - 未登记 key 的安全回退（不抛异常）。
    - 语言切换对 t() 返回值的影响。
"""

from __future__ import annotations

import unittest

from config.i18n import (
    DEFAULT_LANGUAGE,
    LANG_EN,
    LANG_ZH,
    SUPPORTED_LANGUAGES,
    get_current_language,
    set_current_language,
    t,
)


class FakeSessionState(dict):
    """最小化模拟 st.session_state：支持字典式访问。"""


class TestI18nTranslation(unittest.TestCase):
    def setUp(self):
        import streamlit as st

        self._original_session_state = st.session_state
        st.session_state = FakeSessionState()

    def tearDown(self):
        import streamlit as st

        st.session_state = self._original_session_state

    def test_default_language_is_zh(self):
        self.assertEqual(get_current_language(), DEFAULT_LANGUAGE)
        self.assertEqual(DEFAULT_LANGUAGE, LANG_ZH)

    def test_set_and_get_language(self):
        set_current_language(LANG_EN)
        self.assertEqual(get_current_language(), LANG_EN)

    def test_invalid_language_falls_back_to_default(self):
        set_current_language("fr")
        self.assertEqual(get_current_language(), DEFAULT_LANGUAGE)

    def test_translation_returns_chinese_by_default(self):
        set_current_language(LANG_ZH)
        self.assertEqual(t("dashboard.title"), "运营总览")

    def test_translation_switches_with_language(self):
        set_current_language(LANG_EN)
        self.assertEqual(t("dashboard.title"), "Operations Overview")

    def test_unregistered_key_falls_back_to_key_itself(self):
        set_current_language(LANG_ZH)
        self.assertEqual(t("this.key.does.not.exist"), "this.key.does.not.exist")

    def test_placeholder_formatting(self):
        set_current_language(LANG_ZH)
        result = t("anomaly_center.task_create_success", task_id="TASK-001")
        self.assertIn("TASK-001", result)

    def test_placeholder_formatting_english(self):
        set_current_language(LANG_EN)
        result = t("anomaly_center.task_create_success", task_id="TASK-001")
        self.assertIn("TASK-001", result)

    def test_missing_placeholder_does_not_raise(self):
        set_current_language(LANG_ZH)
        # 缺少必要的格式化参数时应安全返回原文案，不抛异常。
        result = t("anomaly_center.task_create_success")
        self.assertIsInstance(result, str)

    def test_all_supported_languages_have_coverage_for_key_sample(self):
        sample_keys = ["nav.dashboard", "nav.customers_orders", "nav.anomaly_center",
                       "nav.task_center", "nav.analytics", "nav.settings"]
        from config.i18n import TRANSLATIONS

        for key in sample_keys:
            for lang in SUPPORTED_LANGUAGES:
                self.assertIn(lang, TRANSLATIONS[key], f"{key} missing {lang} translation")
                self.assertTrue(TRANSLATIONS[key][lang], f"{key} has empty {lang} translation")

    def test_module_names_match_requirement_fixed_names(self):
        """导航名称必须与需求文档固定的五个模块名称一一对应。"""
        set_current_language(LANG_ZH)
        self.assertEqual(t("nav.dashboard"), "运营总览")
        self.assertEqual(t("nav.customers_orders"), "客户与订单")
        self.assertEqual(t("nav.anomaly_center"), "AI 异常诊断")
        self.assertEqual(t("nav.task_center"), "运营任务")
        self.assertEqual(t("nav.analytics"), "运营分析")

        set_current_language(LANG_EN)
        self.assertEqual(t("nav.dashboard"), "Operations Overview")
        self.assertEqual(t("nav.customers_orders"), "Customers & Orders")
        self.assertEqual(t("nav.anomaly_center"), "AI Anomaly Diagnosis")
        self.assertEqual(t("nav.task_center"), "Operations Tasks")
        self.assertEqual(t("nav.analytics"), "Operations Analytics")


if __name__ == "__main__":
    unittest.main()
