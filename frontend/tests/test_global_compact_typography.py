import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "public" / "index.html"
).read_text(encoding="utf-8")


class GlobalCompactTypographyTests(unittest.TestCase):
    def test_sidebar_goal_note_is_removed(self) -> None:
        self.assertNotIn('class="side-note"', INDEX_HTML)
        self.assertNotIn("当前目标", INDEX_HTML)
        self.assertNotIn("围绕项目进度、金额、交付和目录信息建立可持续扩展的内部管理骨架。", INDEX_HTML)

    def test_global_page_headers_do_not_show_status_or_eyebrow_pills(self) -> None:
        self.assertNotIn('class="eyebrow">运营工作台</div>', INDEX_HTML)
        self.assertNotIn('class="status-pill', INDEX_HTML)
        self.assertNotIn("后端已连接", INDEX_HTML)
        self.assertNotIn("当前显示本地示例数据", INDEX_HTML)

    def test_global_controls_and_titles_are_compact(self) -> None:
        self.assertIn("--control-height: 34px;", INDEX_HTML)
        self.assertIn("--control-height-sm: 28px;", INDEX_HTML)
        self.assertIn(".page-title h1 {\n      margin-top: 9px;\n      font-size: 26px;", INDEX_HTML)
        self.assertIn(".page-card h2 {\n      font-size: 18px;", INDEX_HTML)
        self.assertIn(".button-primary,\n    .button-secondary,\n    .button-link {\n      min-height: var(--control-height);", INDEX_HTML)
        self.assertIn("font-size: 12px;", INDEX_HTML)

    def test_dashboard_high_impact_numbers_are_scaled_down(self) -> None:
        self.assertIn(".metric-value {\n      font-size: 24px;", INDEX_HTML)
        self.assertIn(".metric-value-primary {\n      font-size: 29px;", INDEX_HTML)
        self.assertIn(".metric-value-strong {\n      font-size: 26px;", INDEX_HTML)
        self.assertIn(".hero-copy h2 {\n      margin: 0;\n      font-size: 26px;", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
