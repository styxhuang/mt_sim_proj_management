import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("backend_main", MODULE_PATH)
backend_main = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(backend_main)


class ProjectUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_file = backend_main.DATA_FILE
        backend_main.DATA_FILE = Path(self.temp_dir.name) / "projects.json"
        self.original_projects = backend_main.PROJECTS
        backend_main.PROJECTS = [
            {
                "id": "p-001",
                "name": "测试项目",
                "customer": "测试客户",
                "amount": 42,
                "currentStage": "模拟计算",
                "progress": 64,
                "plannedDeliveryDate": "2026-06-14",
                "status": "进行中",
                "packageStatus": "待打包",
                "rootDirectory": "/data/projects/p-001",
                "template": "标准扩散模板",
                "description": "测试描述",
                "stageTimeline": [
                    {"name": "立项", "status": "已完成"},
                    {"name": "建模", "status": "已完成"},
                    {"name": "模拟计算", "status": "进行中"},
                    {"name": "结果分析", "status": "未开始"},
                    {"name": "报告交付", "status": "未开始"},
                ],
                "deliveryChecklist": [
                    {"name": "分析报告", "status": "待完成"},
                    {"name": "结果图表", "status": "已完成"},
                ],
                "packageRecords": [],
            }
        ]

    def tearDown(self) -> None:
        backend_main.PROJECTS = self.original_projects
        backend_main.DATA_FILE = self.original_data_file
        self.temp_dir.cleanup()

    def test_update_project_fields_syncs_core_summary_and_stage_timeline(self) -> None:
        updated = backend_main.update_project_fields(
            "p-001",
            {
                "amount": 50,
                "currentStage": "结果分析",
                "progress": 88,
                "plannedDeliveryDate": "2026-06-12",
                "status": "临近交付",
                "packageStatus": "可打包",
                "rootDirectory": "/new/root",
            },
        )

        self.assertEqual(updated["amount"], 50)
        self.assertEqual(updated["currentStage"], "结果分析")
        self.assertEqual(updated["progress"], 88)
        self.assertEqual(updated["plannedDeliveryDate"], "2026-06-12")
        self.assertEqual(updated["status"], "临近交付")
        self.assertEqual(updated["packageStatus"], "可打包")
        self.assertEqual(updated["rootDirectory"], "/new/root")
        self.assertEqual(
            updated["stageTimeline"],
            [
                {"name": "立项", "status": "已完成"},
                {"name": "建模", "status": "已完成"},
                {"name": "模拟计算", "status": "已完成"},
                {"name": "结果分析", "status": "进行中"},
                {"name": "报告交付", "status": "未开始"},
            ],
        )

    def test_replace_delivery_checklist_updates_project_checklist(self) -> None:
        updated = backend_main.replace_delivery_checklist(
            "p-001",
            [
                {"name": "分析报告", "status": "已完成"},
                {"name": "结果图表", "status": "已完成"},
                {"name": "说明文档", "status": "待确认"},
            ],
        )

        self.assertEqual(
            updated["deliveryChecklist"],
            [
                {"name": "分析报告", "status": "已完成"},
                {"name": "结果图表", "status": "已完成"},
                {"name": "说明文档", "status": "待确认"},
            ],
        )

    def test_add_package_record_appends_new_record(self) -> None:
        updated = backend_main.add_package_record(
            "p-001",
            {"version": "v1.0", "date": "2026-06-10", "type": "客户交付包"},
        )

        self.assertEqual(
            updated["packageRecords"],
            [{"version": "v1.0", "date": "2026-06-10", "type": "客户交付包"}],
        )


if __name__ == "__main__":
    unittest.main()
