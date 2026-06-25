import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import config, projects, requirements  # noqa: E402
from sim_backend.llm import cli_client, client  # noqa: E402


class WorkspaceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_file = config.DB_FILE
        config.DB_FILE = pathlib.Path(self.temp_dir.name) / "projects.db"
        self.original_projects = projects.PROJECTS
        projects.PROJECTS = [
            {
                "id": "p-900",
                "name": "测试项目",
                "customer": "测试客户",
                "amount": 10,
                "currentStage": "立项",
                "progress": 5,
                "plannedDeliveryDate": "2026-06-30",
                "status": "进行中",
                "packageStatus": "未开始",
                "rootDirectory": "/tmp/p-900",
                "template": "标准计算项目",
                "description": "",
                "stageTimeline": projects.build_stage_timeline("立项"),
                "deliveryChecklist": [],
                "packageRecords": [],
            }
        ]
        projects.save_projects(projects.PROJECTS)

    def tearDown(self) -> None:
        config.DB_FILE = self.original_db_file
        projects.PROJECTS = self.original_projects
        self.temp_dir.cleanup()

    def test_requirement_task_persists_and_links_project(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "需求.md",
                "fileType": "text/markdown",
                "content": "需求内容",
                "projectId": "p-900",
            }
        )
        self.assertEqual(task["projectId"], "p-900")

        found = requirements.find_requirement_task_by_project("p-900")
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], task["id"])
        self.assertEqual(found["projectId"], "p-900")

    def test_find_requirement_task_by_project_handles_missing(self) -> None:
        self.assertIsNone(requirements.find_requirement_task_by_project("p-unknown"))
        self.assertIsNone(requirements.find_requirement_task_by_project(""))

    def test_advance_project_stage_moves_forward_only(self) -> None:
        projects.advance_project_stage("p-900", "方案确认")
        self.assertEqual(projects.find_project("p-900")["currentStage"], "方案确认")

        # 不回退：尝试退回更早阶段应被忽略。
        projects.advance_project_stage("p-900", "需求解析")
        self.assertEqual(projects.find_project("p-900")["currentStage"], "方案确认")

        # 未知阶段被忽略。
        self.assertIsNone(projects.advance_project_stage("p-900", "不存在的阶段"))
        self.assertEqual(projects.find_project("p-900")["currentStage"], "方案确认")

    def test_advance_project_stage_updates_timeline_and_progress(self) -> None:
        updated = projects.advance_project_stage("p-900", "建模")
        self.assertEqual(updated["currentStage"], "建模")
        self.assertGreaterEqual(updated["progress"], projects.STAGE_PROGRESS["建模"])
        self.assertEqual(
            [stage["name"] for stage in updated["stageTimeline"]],
            ["立项", "需求解析", "方案确认", "建模", "模拟计算", "交付"],
        )
        self.assertEqual(updated["stageTimeline"][3]["status"], "进行中")

    def test_requirement_steps_auto_advance_linked_project_stage(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "需求.md",
                "fileType": "text/markdown",
                "content": "需要扩散模拟",
                "projectId": "p-900",
            }
        )

        with patch.object(cli_client, "call", return_value="# 需求解析\n内容"):
            requirements.run_next_requirement_step(task["id"])
        self.assertEqual(projects.find_project("p-900")["currentStage"], "需求解析")

        with patch.object(cli_client, "call", return_value="# 实施方案\n内容"):
            requirements.run_next_requirement_step(task["id"])
        self.assertEqual(projects.find_project("p-900")["currentStage"], "方案确认")


if __name__ == "__main__":
    unittest.main()
