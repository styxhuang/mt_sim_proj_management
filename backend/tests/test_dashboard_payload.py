import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import dashboard, projects  # noqa: E402


class DashboardPayloadTests(unittest.TestCase):
    def test_dashboard_payload_exposes_ordered_chart_data_and_summary_cards(self) -> None:
        original_projects = projects.PROJECTS
        projects.PROJECTS = [
            {
                "name": "项目 A",
                "amount": 10,
                "currentStage": "交付",
                "status": "临近交付",
                "packageStatus": "可打包",
            },
            {
                "name": "项目 B",
                "amount": 30,
                "currentStage": "方案确认",
                "status": "进行中",
                "packageStatus": "待打包",
            },
            {
                "name": "项目 C",
                "amount": 20,
                "currentStage": "建模",
                "status": "进行中",
                "packageStatus": "未开始",
            },
        ]

        try:
            payload = dashboard.get_dashboard_payload()
        finally:
            projects.PROJECTS = original_projects

        self.assertEqual(
            [item["label"] for item in payload["stageDistribution"]],
            ["立项", "需求解析", "方案确认", "建模", "模拟计算", "交付"],
        )
        self.assertEqual(
            [item["value"] for item in payload["stageDistribution"]],
            [0, 0, 1, 1, 0, 1],
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
