import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "public" / "index.html"
).read_text(encoding="utf-8")


class DashboardMarkupTests(unittest.TestCase):
    def test_dashboard_page_uses_specialized_sections_and_renderers(self) -> None:
        self.assertIn("dashboard-hero", INDEX_HTML)
        self.assertIn("metrics-grid", INDEX_HTML)
        self.assertIn("function renderStageChart(items)", INDEX_HTML)
        self.assertIn("function renderTrendChart(trend)", INDEX_HTML)
        self.assertIn("function renderAmountChart(items)", INDEX_HTML)
        self.assertIn("function renderSummaryCards(items)", INDEX_HTML)
        self.assertIn("function renderReminderCards(items)", INDEX_HTML)
        self.assertIn("summaryCards", INDEX_HTML)

    def test_dashboard_contains_workbench_header_and_summary_regions(self) -> None:
        self.assertIn('class="page-header page-header--split"', INDEX_HTML)
        self.assertIn('class="page-toolbar"', INDEX_HTML)
        self.assertIn('class="dashboard-shell"', INDEX_HTML)
        self.assertIn('id="summaryList"', INDEX_HTML)
        self.assertIn('id="reminderList"', INDEX_HTML)

    def test_dashboard_contains_rebalanced_hero_kpi_and_action_regions(self) -> None:
        self.assertIn('class="hero-decision"', INDEX_HTML)
        self.assertIn('class="hero-signal-grid"', INDEX_HTML)
        self.assertIn('class="metrics-grid metrics-grid--priority"', INDEX_HTML)
        self.assertIn('metric-card metric-card-primary', INDEX_HTML)
        self.assertIn('metric-card metric-card-strong', INDEX_HTML)
        self.assertIn('class="dashboard-main-grid"', INDEX_HTML)
        self.assertIn('chart-card chart-card-featured', INDEX_HTML)
        self.assertIn('class="dashboard-side-rail"', INDEX_HTML)
        self.assertIn('class="action-strip"', INDEX_HTML)
        self.assertIn('id="actionList"', INDEX_HTML)

    def test_dashboard_hero_copy_is_shorter_and_page_width_is_wider(self) -> None:
        self.assertIn("--page-max-width: 1680px;", INDEX_HTML)
        self.assertIn("<h2>交付总览</h2>", INDEX_HTML)
        self.assertNotIn("首页先回答当前业务规模、本周需要优先推进的交付事项", INDEX_HTML)
        self.assertNotIn('class="hero-points"', INDEX_HTML)
        self.assertNotIn("优先盯临近交付项目", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
