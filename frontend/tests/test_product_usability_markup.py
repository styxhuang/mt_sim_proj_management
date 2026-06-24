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
        self.assertIn("function deleteJson", INDEX_HTML)
        self.assertIn('id="deleteSelectedProjectsButton"', INDEX_HTML)
        self.assertIn('class="project-select"', INDEX_HTML)
        self.assertIn("selectedProjectIds", INDEX_HTML)

    def test_project_list_redesign_regions_exist(self) -> None:
        self.assertIn("function getProjectListSummary", INDEX_HTML)
        self.assertIn('class="project-list-summary"', INDEX_HTML)
        self.assertIn('class="project-filter-panel"', INDEX_HTML)
        self.assertIn('class="project-bulk-bar"', INDEX_HTML)
        self.assertIn('class="table project-table"', INDEX_HTML)
        self.assertIn('class="project-table-card-head"', INDEX_HTML)
        self.assertIn(".project-table .table-header {", INDEX_HTML)
        self.assertIn("display: none;", INDEX_HTML)
        self.assertIn('class="project-row-main"', INDEX_HTML)
        self.assertIn('class="project-row-meta"', INDEX_HTML)
        self.assertIn('class="project-mobile-label"', INDEX_HTML)
        self.assertIn('id="clearSelectedProjectsButton"', INDEX_HTML)
        self.assertIn('class="button-link open-project-button"', INDEX_HTML)
        self.assertIn("data-open-project", INDEX_HTML)
        self.assertNotIn('row.addEventListener("click", () => navigateTo', INDEX_HTML)
        self.assertIn("function renderProjectPreview", INDEX_HTML)
        self.assertIn('id="projectPreviewModal"', INDEX_HTML)
        self.assertIn('id="projectPreviewContent"', INDEX_HTML)
        self.assertIn("openProjectPreview", INDEX_HTML)
        self.assertIn("closeProjectPreview", INDEX_HTML)
        self.assertNotIn('navigateTo("workspace", { id: project.id', INDEX_HTML)
        self.assertIn('navigateTo("workspace", project.id, { tab: "overview" })', INDEX_HTML)
        self.assertNotIn('id="projectPreviewPanel"', INDEX_HTML)
        self.assertIn("projectPreviewId", INDEX_HTML)

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
