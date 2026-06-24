import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import config, projects  # noqa: E402


class ProjectUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_file = config.DB_FILE
        config.DB_FILE = pathlib.Path(self.temp_dir.name) / "projects.db"
        self.original_legacy_data_file = config.LEGACY_DATA_FILE
        config.LEGACY_DATA_FILE = pathlib.Path(self.temp_dir.name) / "projects.json"
        self.original_projects = projects.PROJECTS
        projects.PROJECTS = [
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
        projects.PROJECTS = self.original_projects
        config.DB_FILE = self.original_db_file
        config.LEGACY_DATA_FILE = self.original_legacy_data_file
        self.temp_dir.cleanup()

    def test_update_project_fields_syncs_core_summary_and_stage_timeline(self) -> None:
        updated = projects.update_project_fields(
            "p-001",
            {
                "amount": 50,
                "currentStage": "建模",
                "progress": 88,
                "plannedDeliveryDate": "2026-06-12",
                "status": "临近交付",
                "packageStatus": "可打包",
                "rootDirectory": "/new/root",
            },
        )

        self.assertEqual(updated["amount"], 50)
        self.assertEqual(updated["currentStage"], "建模")
        self.assertEqual(updated["progress"], 88)
        self.assertEqual(updated["plannedDeliveryDate"], "2026-06-12")
        self.assertEqual(updated["status"], "临近交付")
        self.assertEqual(updated["packageStatus"], "可打包")
        self.assertEqual(updated["rootDirectory"], "/new/root")
        self.assertEqual(
            updated["stageTimeline"],
            [
                {"name": "立项", "status": "已完成"},
                {"name": "需求解析", "status": "已完成"},
                {"name": "方案确认", "status": "已完成"},
                {"name": "建模", "status": "进行中"},
                {"name": "模拟计算", "status": "未开始"},
                {"name": "交付", "status": "未开始"},
            ],
        )

    def test_update_project_fields_persists_to_sqlite_database(self) -> None:
        projects.save_projects(projects.PROJECTS)

        projects.update_project_fields(
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

        self.assertTrue(config.DB_FILE.exists())
        with sqlite3.connect(config.DB_FILE) as connection:
            row = connection.execute(
                """
                SELECT amount, current_stage, progress, planned_delivery_date,
                       status, package_status, root_directory
                FROM projects
                WHERE id = ?
                """,
                ("p-001",),
            ).fetchone()

        self.assertEqual(row, (50, "结果分析", 88, "2026-06-12", "临近交付", "可打包", "/new/root"))

    def test_project_root_directory_uses_ascii_slug_when_chinese_name_is_provided(self) -> None:
        project = projects.build_new_project(
            {
                "name": "环氧化蓖麻油-固化机理研究",
                "customer": "测试客户",
                "amount": 1,
                "plannedDeliveryDate": "2026-06-30",
                "rootDirectory": "/data/projects/环氧化蓖麻油-固化机理研究",
            },
            "p-004",
        )

        self.assertEqual(project["rootDirectory"], "/data/projects/p-004")

        updated = projects.update_project_fields(
            "p-001",
            {"rootDirectory": "/data/projects/环氧化蓖麻油-固化机理研究"},
        )

        self.assertEqual(updated["rootDirectory"], "/data/projects/p-001")

    def test_delete_projects_removes_selected_projects_and_persists(self) -> None:
        projects.PROJECTS.append(
            {
                **projects.PROJECTS[0],
                "id": "p-002",
                "name": "第二个测试项目",
            }
        )
        projects.save_projects(projects.PROJECTS)

        deleted = projects.delete_projects(["p-001"])

        self.assertEqual(deleted, ["p-001"])
        self.assertEqual([project["id"] for project in projects.PROJECTS], ["p-002"])
        with sqlite3.connect(config.DB_FILE) as connection:
            rows = connection.execute("SELECT id FROM projects ORDER BY id").fetchall()
        self.assertEqual(rows, [("p-002",)])

    def test_load_projects_migrates_existing_json_records_into_sqlite_database(self) -> None:
        legacy_projects = [
            {
                "id": "p-099",
                "name": "旧数据项目",
                "customer": "历史客户",
                "amount": 99,
                "currentStage": "报告交付",
                "progress": 100,
                "plannedDeliveryDate": "2026-06-30",
                "status": "已交付",
                "packageStatus": "已打包",
                "rootDirectory": "/legacy/project",
                "template": "历史模板",
                "description": "从 JSON 迁移来的项目。",
                "stageTimeline": [{"name": "报告交付", "status": "已完成"}],
                "deliveryChecklist": [{"name": "分析报告", "status": "已完成"}],
                "packageRecords": [{"version": "v1.0", "date": "2026-06-30", "type": "归档包"}],
            }
        ]
        config.LEGACY_DATA_FILE.write_text(
            json.dumps(legacy_projects, ensure_ascii=False),
            encoding="utf-8",
        )

        loaded = projects.load_projects()

        self.assertEqual(loaded, legacy_projects)
        with sqlite3.connect(config.DB_FILE) as connection:
            row = connection.execute("SELECT id, name FROM projects").fetchone()
        self.assertEqual(row, ("p-099", "旧数据项目"))

    def test_replace_delivery_checklist_updates_project_checklist(self) -> None:
        updated = projects.replace_delivery_checklist(
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
        updated = projects.add_package_record(
            "p-001",
            {"version": "v1.0", "date": "2026-06-10", "type": "客户交付包"},
        )

        self.assertEqual(
            updated["packageRecords"],
            [{"version": "v1.0", "date": "2026-06-10", "type": "客户交付包"}],
        )


if __name__ == "__main__":
    unittest.main()
