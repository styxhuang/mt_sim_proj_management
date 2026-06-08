import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "main.py"
SPEC = importlib.util.spec_from_file_location("backend_main", MODULE_PATH)
backend_main = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(backend_main)


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_payload_exposes_ordered_chart_data_and_summary_cards(self) -> None:
        original_projects = backend_main.PROJECTS
        backend_main.PROJECTS = [
            {
                "name": "项目 A",
                "amount": 10,
                "currentStage": "报告交付",
                "status": "临近交付",
                "packageStatus": "可打包",
            },
            {
                "name": "项目 B",
                "amount": 30,
                "currentStage": "建模",
                "status": "进行中",
                "packageStatus": "待打包",
            },
            {
                "name": "项目 C",
                "amount": 20,
                "currentStage": "模拟计算",
                "status": "进行中",
                "packageStatus": "未开始",
            },
        ]

        try:
            payload = backend_main.get_dashboard_payload()
        finally:
            backend_main.PROJECTS = original_projects

        self.assertEqual(
            [item["label"] for item in payload["stageDistribution"]],
            ["立项", "建模", "模拟计算", "结果分析", "报告交付"],
        )
        self.assertEqual(
            [item["value"] for item in payload["stageDistribution"]],
            [0, 1, 1, 0, 1],
        )
        self.assertEqual(payload["projectCount"], 3)
        self.assertEqual(payload["totalAmountWan"], 60)
        self.assertEqual(payload["nearDelivery"], 1)
        self.assertEqual(payload["readyToPack"], 1)
        self.assertEqual(payload["topAmounts"][0], {"label": "项目 B", "value": 30})
        self.assertEqual(payload["topAmounts"][1], {"label": "项目 C", "value": 20})
        self.assertIn("summaryCards", payload)
        self.assertEqual(len(payload["summaryCards"]), 3)


if __name__ == "__main__":
    unittest.main()
