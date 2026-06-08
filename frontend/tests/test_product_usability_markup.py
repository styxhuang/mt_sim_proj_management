import unittest
from pathlib import Path


INDEX_HTML = (
    Path(__file__).resolve().parents[1] / "public" / "index.html"
).read_text(encoding="utf-8")


class ProductUsabilityMarkupTests(unittest.TestCase):
    def test_transitional_copy_is_removed_and_detail_edit_controls_exist(self) -> None:
        self.assertNotIn("首页只回答四个问题", INDEX_HTML)
        self.assertNotIn("四个 KPI 保留", INDEX_HTML)
        self.assertNotIn("第一版先完成项目台账录入", INDEX_HTML)
        self.assertNotIn("可以在后续版本接入打包动作", INDEX_HTML)
        self.assertIn('id="detailEditForm"', INDEX_HTML)
        self.assertIn('id="detailStage"', INDEX_HTML)
        self.assertIn('id="detailProgress"', INDEX_HTML)
        self.assertIn('id="detailPackageStatus"', INDEX_HTML)

    def test_checklist_package_and_list_controls_exist(self) -> None:
        self.assertIn("function updateChecklistStatus", INDEX_HTML)
        self.assertIn('id="packageRecordForm"', INDEX_HTML)
        self.assertIn('id="packageVersion"', INDEX_HTML)
        self.assertIn('id="packageDate"', INDEX_HTML)
        self.assertIn('id="packageType"', INDEX_HTML)
        self.assertIn('id="packageFilter"', INDEX_HTML)
        self.assertIn('id="sortFilter"', INDEX_HTML)

    def test_feedback_and_settings_controls_exist(self) -> None:
        self.assertIn('id="settingsButton"', INDEX_HTML)
        self.assertIn('id="settingsPanel"', INDEX_HTML)
        self.assertIn('id="defaultPageSelect"', INDEX_HTML)
        self.assertIn('id="defaultSortSelect"', INDEX_HTML)
        self.assertIn('id="densitySelect"', INDEX_HTML)
        self.assertIn('id="helperTextToggle"', INDEX_HTML)
        self.assertIn('id="toastRegion"', INDEX_HTML)
        self.assertIn("function loadPreferences", INDEX_HTML)
        self.assertIn("function savePreferences", INDEX_HTML)
        self.assertIn("function showToast", INDEX_HTML)
        self.assertIn("localStorage.setItem", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
