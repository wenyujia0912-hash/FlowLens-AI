"""
UI 回归测试：锁定视觉重设计的验收项，防止后续改动悄悄退回到旧样式。

覆盖范围（对应视觉重设计需求 §4 / §11）：
    - 导航结构：五个业务模块名称固定、都在 Workspace 分组内、设置单列底部；
      FlowLens AI 是品牌区而不是可点击导航项；导航项不带图标/emoji。
    - 文案：所有 UI 文案不含 emoji。
    - 设计令牌：颜色、字号、间距规范在 CSS 中输出；页面背景/侧边栏为浅色。
    - 组件：状态标签只使用浅底语义类；表格转义单元格文本。
    - 图表：样式函数不改变传入数据。

这些测试只做纯函数/静态检查，不启动浏览器，可在 CI 中直接运行。
"""

from __future__ import annotations

import re
import unittest

import config.i18n as i18n
from components.layout import NAV_ITEMS, SETTINGS_ITEM
from config.theme import (
    COLOR_BG,
    COLOR_BORDER,
    COLOR_ERROR,
    COLOR_HOVER,
    COLOR_SELECTED,
    COLOR_SIDEBAR_BG,
    COLOR_SUCCESS,
    COLOR_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    TYPE_SCALE,
    build_theme_css,
)

# 覆盖常见 emoji 区间，并单独列出原本用于导航/按钮的装饰性符号。
# 注意：数学箭头等排版符号（如"发货→签收"）不是装饰性图标，不在此列。
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # 各类 emoji
    "\U0001F000-\U0001F0FF"
    "\uFE0F"                    # emoji 变体选择符
    "\u2705\u274C\u2753\u26A0\u23F0\u23F1\u25B6\u25C0\u2B50\u2728"
    "]"
)


class TestNavigationStructure(unittest.TestCase):
    def test_workspace_has_exactly_the_five_modules_in_order(self):
        self.assertEqual(
            [item["label_key"] for item in NAV_ITEMS],
            [
                "nav.dashboard",
                "nav.customers_orders",
                "nav.anomaly_center",
                "nav.task_center",
                "nav.analytics",
            ],
        )

    def test_settings_is_not_part_of_workspace(self):
        self.assertNotIn(SETTINGS_ITEM["key"], [item["key"] for item in NAV_ITEMS])
        self.assertEqual(SETTINGS_ITEM["label_key"], "nav.settings")

    def test_no_nav_item_declares_an_icon(self):
        for item in (*NAV_ITEMS, SETTINGS_ITEM):
            self.assertNotIn("icon", item, f"{item['key']} 不应再声明导航图标")

    def test_every_nav_item_has_a_unique_url_path_and_page(self):
        url_paths = [item["url_path"] for item in (*NAV_ITEMS, SETTINGS_ITEM)]
        pages = [item["page"] for item in (*NAV_ITEMS, SETTINGS_ITEM)]
        self.assertEqual(len(url_paths), len(set(url_paths)))
        self.assertEqual(len(pages), len(set(pages)))

    def test_pages_are_routed_from_views_directory(self):
        """页面目录不能叫 pages/：那会被 Streamlit 当作遗留多页路由，
        与 st.navigation 的 url_path 冲突（直接访问该 URL 时会绕过入口脚本）。"""
        for item in (*NAV_ITEMS, SETTINGS_ITEM):
            self.assertTrue(item["page"].startswith("views/"), item["page"])

    def test_brand_copy_exists_for_the_sidebar_brand_block(self):
        self.assertTrue(i18n.t("nav.brand.eyebrow"))
        self.assertTrue(i18n.t("nav.brand.desc"))
        self.assertEqual(i18n.t("nav.workspace"), "Workspace")


class TestNoEmojiInUiCopy(unittest.TestCase):
    def test_translation_values_contain_no_emoji(self):
        offenders = []
        for key, entry in i18n.TRANSLATIONS.items():
            for language, text in entry.items():
                if isinstance(text, str) and _EMOJI_PATTERN.search(text):
                    offenders.append(f"{key}[{language}]={text}")
        self.assertEqual(offenders, [], "UI 文案中不应再出现 emoji：" + "; ".join(offenders))


class TestDesignTokens(unittest.TestCase):
    def setUp(self):
        self.css = build_theme_css("navy", "medium")

    def test_neutral_palette_matches_design_spec(self):
        expected = {
            "--fl-bg": COLOR_BG,
            "--fl-sidebar-bg": COLOR_SIDEBAR_BG,
            "--fl-text": COLOR_TEXT,
            "--fl-text-secondary": COLOR_TEXT_SECONDARY,
            "--fl-text-muted": COLOR_TEXT_MUTED,
            "--fl-border": COLOR_BORDER,
            "--fl-hover": COLOR_HOVER,
            "--fl-selected": COLOR_SELECTED,
        }
        for token, value in expected.items():
            self.assertIn(f"{token}: {value}", self.css)

    def test_default_palette_values(self):
        self.assertEqual(COLOR_BG, "#FFFFFF")
        self.assertEqual(COLOR_SIDEBAR_BG, "#FAFAFA")
        self.assertEqual(COLOR_TEXT, "#171717")
        self.assertEqual(COLOR_TEXT_SECONDARY, "#737373")
        self.assertEqual(COLOR_TEXT_MUTED, "#A3A3A3")
        self.assertEqual(COLOR_BORDER, "#EAEAEA")
        self.assertEqual(COLOR_HOVER, "#F5F5F5")
        self.assertEqual(COLOR_SELECTED, "#F0F3F8")

    def test_semantic_colors_match_design_spec(self):
        self.assertEqual(COLOR_SUCCESS, "#27845B")
        self.assertEqual(COLOR_WARNING, "#B7791F")
        self.assertEqual(COLOR_ERROR, "#C44747")

    def test_typography_scale_follows_the_spec(self):
        self.assertEqual(TYPE_SCALE["page-title"], (24, 600))
        self.assertEqual(TYPE_SCALE["page-subtitle"], (13, 400))
        self.assertEqual(TYPE_SCALE["section-title"], (16, 600))
        self.assertEqual(TYPE_SCALE["card-title"], (13, 500))
        self.assertEqual(TYPE_SCALE["body"], (14, 400))
        self.assertEqual(TYPE_SCALE["caption"], (12, 400))
        self.assertEqual(TYPE_SCALE["kpi"], (28, 600))
        self.assertEqual(TYPE_SCALE["table"], (13, 400))
        self.assertEqual(TYPE_SCALE["button"], (13, 500))

    def test_sidebar_is_light_not_a_dark_primary_block(self):
        self.assertNotIn("--fl-bg: #172B4D", self.css)
        self.assertIn("background: var(--fl-sidebar-bg)", self.css)

    def test_styles_are_driven_by_variables(self):
        """组件样式应引用变量，而不是散落硬编码色值。

        允许的硬编码只出现在 :root 令牌定义区；令牌区之后出现的色值必须
        保持极少数（仅结构性白色），否则说明某个组件绕过了设计系统。
        """
        style_body = self.css.split("<style>", 1)[1]
        declarations = style_body.split(":root {", 1)[1].split("}", 1)[1]
        hardcoded = re.findall(r"#[0-9A-Fa-f]{6}", declarations)
        self.assertLessEqual(
            len(hardcoded), 3,
            f"令牌定义区之外出现了硬编码色值：{sorted(set(hardcoded))}",
        )

    def test_css_includes_component_class_system(self):
        for selector in (".fl-brand", ".fl-nav-item", ".fl-kpi", ".fl-page-header",
                         ".fl-kv-row", ".fl-badge", ".fl-empty", ".fl-panel-subtle"):
            self.assertIn(selector, self.css)


class TestStatusBadgeMarkup(unittest.TestCase):
    def test_status_badge_uses_tint_class_not_inline_colors(self):
        from components.status_badges import status_badge_html

        markup = status_badge_html("已签收")
        self.assertIn("fl-badge", markup)
        self.assertIn("fl-badge-success", markup)
        self.assertNotIn("background-color:", markup)

    def test_unknown_status_falls_back_to_neutral(self):
        from components.status_badges import status_badge_html

        self.assertIn("fl-badge-neutral", status_badge_html("不存在的状态"))

    def test_priority_and_risk_share_one_badge_system(self):
        from components.status_badges import priority_badge_html, risk_badge_html

        self.assertIn("fl-badge-error", priority_badge_html("P1"))
        self.assertIn("fl-badge-warning", risk_badge_html("中"))


class TestTableCellSafety(unittest.TestCase):
    def test_cells_escape_user_supplied_text(self):
        from components.tables import Cell

        cell = Cell.of("<script>alert(1)</script>")
        self.assertEqual(cell.html, None)
        self.assertIn("<script>", cell.text)  # 文本原样保存，由渲染时转义

    def test_cell_subclasses_keep_alignment(self):
        from components.tables import Cell

        self.assertEqual(Cell.of(1, align="right").align, "right")
        self.assertIsNotNone(Cell.markup("<b>x</b>").html)


class TestChartStyleDoesNotTouchData(unittest.TestCase):
    def test_line_chart_receives_all_points_unchanged(self):
        try:
            from components.charts import line_chart
        except ImportError:  # pragma: no cover - plotly 为可选依赖
            self.skipTest("plotly 未安装")

        x = ["2026-01-01", "2026-01-02", "2026-01-03"]
        y = [3, 1, 7]
        fig = line_chart(x, y, primary="#3B5CCC")
        trace = fig.data[0]
        self.assertEqual(list(trace.x), x)
        self.assertEqual(list(trace.y), y)

    def test_donut_chart_keeps_labels_and_values(self):
        try:
            from components.charts import donut_chart
        except ImportError:  # pragma: no cover
            self.skipTest("plotly 未安装")

        labels, values = ["高", "中", "低"], [6, 9, 2]
        fig = donut_chart(labels, values, palette=("#C44747", "#B7791F", "#27845B"))
        trace = fig.data[0]
        self.assertEqual(list(trace.labels), labels)
        self.assertEqual(list(trace.values), values)


if __name__ == "__main__":
    unittest.main()
