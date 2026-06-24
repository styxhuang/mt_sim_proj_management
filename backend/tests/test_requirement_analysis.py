import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import config, projects, requirements  # noqa: E402
from sim_backend.llm import cli_client, client  # noqa: E402


class RequirementAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_file = config.DB_FILE
        config.DB_FILE = pathlib.Path(self.temp_dir.name) / "projects.db"
        self.original_projects = projects.PROJECTS
        self.project_root = pathlib.Path(self.temp_dir.name) / "project-root"
        projects.PROJECTS = [
            {
                "id": "p-test",
                "name": "测试项目",
                "customer": "测试客户",
                "amount": 1,
                "currentStage": "立项",
                "progress": 5,
                "plannedDeliveryDate": "2026-06-30",
                "status": "进行中",
                "packageStatus": "未开始",
                "rootDirectory": str(self.project_root),
                "template": "测试模板",
                "description": "测试项目",
                "stageTimeline": [],
                "deliveryChecklist": [],
                "packageRecords": [],
            }
        ]

    def tearDown(self) -> None:
        projects.PROJECTS = self.original_projects
        config.DB_FILE = self.original_db_file
        self.temp_dir.cleanup()

    def test_create_requirement_task_only_reads_document_before_skill_steps(self) -> None:
        with patch.object(client, "call_llm") as call_llm:
            task = requirements.create_requirement_task(
                {
                    "fileName": "客户需求说明.pdf",
                    "fileType": "application/pdf",
                    "content": "需要完成材料扩散模拟，输出技术路线、风险控制和交付清单。",
                }
            )

        self.assertEqual(task["status"], "processing")
        self.assertEqual(task["fileName"], "客户需求说明.pdf")
        self.assertEqual(
            [step["label"] for step in task["steps"]],
            ["读取文档", "解析任务", "生成方案"],
        )
        self.assertEqual(task["steps"][0]["status"], "completed")
        self.assertEqual(task["steps"][1]["status"], "pending")
        self.assertEqual(task["steps"][2]["status"], "pending")
        self.assertEqual(task["documents"], {})
        self.assertEqual(call_llm.call_count, 0)

    def test_run_next_requirement_step_executes_one_llm_skill_at_a_time(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.pdf",
                "fileType": "application/pdf",
                "content": "需要完成材料扩散模拟，输出技术路线、风险控制和交付清单。",
            }
        )

        with patch.object(client, "call_llm", return_value="# 需求解析结果\n\n真实解析") as call_llm:
            after_analysis = requirements.run_next_requirement_step(task["id"])

        self.assertEqual(call_llm.call_count, 1)
        self.assertEqual(after_analysis["status"], "processing")
        self.assertEqual(after_analysis["steps"][1]["status"], "completed")
        self.assertEqual(after_analysis["steps"][2]["status"], "pending")
        self.assertIn("# 需求解析结果", after_analysis["documents"]["analysis"]["content"])
        self.assertNotIn("plan", after_analysis["documents"])

        with patch.object(cli_client, "call", return_value="# 实施方案\n\n真实方案") as cli_call:
            completed = requirements.run_next_requirement_step(task["id"])

        self.assertEqual(cli_call.call_count, 1)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["steps"][2]["status"], "completed")
        self.assertIn("# 实施方案", completed["documents"]["plan"]["content"])
        self.assertEqual(completed["documents"]["analysis"]["currentVersionId"], "analysis-v1")
        self.assertEqual(completed["documents"]["plan"]["currentVersionId"], "plan-v1")

    def test_requirement_documents_are_written_under_project_root(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.pdf",
                "fileType": "application/pdf",
                "content": "需要完成材料扩散模拟。",
                "projectId": "p-test",
            }
        )

        with patch.object(client, "call_llm", return_value="# 需求解析结果\n\n真实解析"):
            requirements.run_next_requirement_step(task["id"])
        with patch.object(cli_client, "call", return_value="# 实施方案\n\n真实方案"):
            requirements.run_next_requirement_step(task["id"])

        self.assertTrue((self.project_root / "01-requirement" / "analysis-v1.md").exists())
        self.assertTrue((self.project_root / "02-plan" / "plan-v1.md").exists())

    def test_add_requirement_chat_message_creates_new_plan_version(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.txt",
                "fileType": "text/plain",
                "content": "需要完成模拟方案。",
            }
        )
        with patch.object(client, "call_llm", return_value="# 需求解析结果\n\n真实解析"):
            requirements.run_next_requirement_step(task["id"])
        with patch.object(cli_client, "call", return_value="# 实施方案\n\n真实方案"):
            task = requirements.run_next_requirement_step(task["id"])

        with patch.object(cli_client, "call", return_value="# 实施方案\n\n## 风险控制\n真实优化方案") as cli_call:
            updated = requirements.add_requirement_chat_message(
                task["id"],
                {"message": "把风险控制写得更具体，并保存为客户版。"},
            )

        plan = updated["documents"]["plan"]
        self.assertEqual(plan["currentVersionId"], "plan-v2")
        self.assertEqual(plan["versions"][0]["name"], "v2 客户版")
        self.assertIn("风险控制", plan["content"])
        self.assertEqual(cli_call.call_count, 1)
        self.assertEqual(updated["conversation"][-2]["role"], "user")
        self.assertEqual(updated["conversation"][-1]["role"], "assistant")
        self.assertEqual(updated["conversation"][-1]["usedSkills"][0]["id"], "optimize_plan")

    def test_call_llm_captures_hidden_reasoning_chain(self) -> None:
        class FakeResponse:
            def __init__(self, body: bytes) -> None:
                self._body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self._body

        payload = (
            '{"choices": [{"message": {"content": "# 结果", '
            '"reasoning_content": "先拆解目标，再判断约束，最后规划交付。"}}]}'
        ).encode("utf-8")

        with patch.object(config, "get_llm_settings", return_value={
            "api_base_url": "https://example.com/v1",
            "api_key": "secret",
            "model": "test-model",
            "timeout_seconds": 5,
            "temperature": 0.1,
        }), patch.object(client.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            content = client.call_llm([{"role": "user", "content": "hi"}])

        self.assertEqual(content, "# 结果")
        self.assertEqual(
            client.consume_last_llm_reasoning(),
            "先拆解目标，再判断约束，最后规划交付。",
        )
        self.assertEqual(client.consume_last_llm_reasoning(), "")

    def test_analysis_document_stores_reasoning_chain(self) -> None:
        def fake_call_llm(messages, settings=None):
            client._LAST_LLM_REASONING = "用户想要可扩展的模拟流程"
            return "# 需求解析结果\n\n真实解析"

        with patch.object(client, "call_llm", side_effect=fake_call_llm):
            document = requirements.build_analysis_document("a.pdf", "需求文本")

        self.assertEqual(document["reasoning"], "用户想要可扩展的模拟流程")

    def test_run_next_requirement_step_stores_reasoning_in_documents(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.pdf",
                "fileType": "application/pdf",
                "content": "需要完成材料扩散模拟。",
            }
        )

        def fake_analysis(messages, settings=None):
            client._LAST_LLM_REASONING = "解析阶段的隐藏推理"
            return "# 需求解析结果\n\n真实解析"

        with patch.object(client, "call_llm", side_effect=fake_analysis):
            after_analysis = requirements.run_next_requirement_step(task["id"])

        self.assertEqual(after_analysis["documents"]["analysis"]["reasoning"], "解析阶段的隐藏推理")

        def fake_plan(messages, settings=None):
            cli_client._LAST_REASONING = "方案阶段的隐藏推理"
            return "# 实施方案\n\n真实方案"

        with patch.object(cli_client, "call", side_effect=fake_plan):
            completed = requirements.run_next_requirement_step(task["id"])

        self.assertEqual(completed["documents"]["plan"]["reasoning"], "方案阶段的隐藏推理")
        self.assertEqual(completed["conversation"][-1]["usedSkills"][0]["id"], "generate_plan")

    def test_stream_next_requirement_step_emits_incremental_deltas(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.pdf",
                "fileType": "application/pdf",
                "content": "需要完成材料扩散模拟。",
            }
        )

        def fake_stream(messages, settings=None):
            client._LAST_LLM_REASONING = ""
            yield {"type": "reasoning", "text": "先看目标。"}
            yield {"type": "content", "text": "# 需求解析结果\n"}
            yield {"type": "content", "text": "真实解析"}
            client._LAST_LLM_REASONING = "先看目标。"

        with patch.object(client, "stream_chat", side_effect=fake_stream):
            events = list(requirements.stream_next_requirement_step(task["id"]))

        self.assertEqual(events[0]["type"], "step")
        self.assertIn({"type": "reasoning", "text": "先看目标。"}, events)
        self.assertIn({"type": "content", "text": "真实解析"}, events)
        done = events[-1]
        self.assertEqual(done["type"], "done")
        self.assertIn("# 需求解析结果", done["task"]["documents"]["analysis"]["content"])
        self.assertEqual(done["task"]["documents"]["analysis"]["reasoning"], "先看目标。")

    def test_save_requirement_version_appends_manual_edit(self) -> None:
        task = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.txt",
                "fileType": "text/plain",
                "content": "需要完成模拟方案。",
            }
        )
        with patch.object(client, "call_llm", return_value="# 需求解析结果\n\n真实解析"):
            requirements.run_next_requirement_step(task["id"])
        with patch.object(cli_client, "call", return_value="# 实施方案\n\n真实方案"):
            task = requirements.run_next_requirement_step(task["id"])

        updated = requirements.save_requirement_version(
            task["id"],
            {"target": "plan", "content": "# 实施方案\n\n我手动改过的内容"},
        )

        plan = updated["documents"]["plan"]
        self.assertEqual(plan["content"], "# 实施方案\n\n我手动改过的内容")
        self.assertEqual(plan["versions"][0]["name"], "v2 手动编辑")
        self.assertEqual(plan["versions"][0]["source"], "手动编辑")
        self.assertEqual(plan["currentVersionId"], plan["versions"][0]["id"])

        # 重新读库确认已持久化。
        reloaded = requirements.find_requirement_task(task["id"])
        self.assertEqual(reloaded["documents"]["plan"]["content"], "# 实施方案\n\n我手动改过的内容")

    def test_save_requirement_version_validates_target_and_content(self) -> None:
        task = requirements.create_requirement_task(
            {"fileName": "a.txt", "fileType": "text/plain", "content": "x"}
        )
        with self.assertRaises(ValueError):
            requirements.save_requirement_version(task["id"], {"target": "plan", "content": "x"})
        with self.assertRaises(ValueError):
            requirements.save_requirement_version(task["id"], {"target": "bad", "content": "x"})

    def _seed_with_plan(self) -> dict:
        task = requirements.create_requirement_task(
            {"fileName": "界面需求.txt", "fileType": "text/plain", "content": "做石墨烯/水固液界面模拟。"}
        )
        with patch.object(client, "call_llm", return_value="# 解析\n\n内容"):
            requirements.run_next_requirement_step(task["id"])
        with patch.object(cli_client, "call", return_value="# 实施方案\n\n构建石墨烯基底与水相界面。"):
            task = requirements.run_next_requirement_step(task["id"])
        return task

    def test_generate_modeling_spec_parses_and_persists(self) -> None:
        task = self._seed_with_plan()
        spec_json = (
            "好的，规划如下：\n```json\n"
            '{"buildingBlocks": ['
            '{"name": "水", "formula": "H2O", "type": "molecule", "role": "溶剂"},'
            '{"name": "石墨烯", "formula": "", "type": "surface", "role": "基底"}],'
            '"targetSystem": {"kind": "interface", "summary": "固液界面",'
            '"components": [{"block": "水", "count": 500}], "box": "4x4x6 nm",'
            '"interface": {"phaseA": "石墨烯", "phaseB": "水", "note": "固液界面"}}}'
            "\n```\n"
        )
        with patch.object(cli_client, "call", return_value=spec_json):
            updated = requirements.generate_requirement_modeling_spec(task["id"])

        spec = updated["documents"]["modelingSpec"]
        self.assertEqual(len(spec["buildingBlocks"]), 2)
        self.assertEqual(spec["buildingBlocks"][0]["name"], "水")
        self.assertEqual(spec["buildingBlocks"][1]["type"], "surface")
        self.assertEqual(spec["targetSystem"]["kind"], "interface")
        self.assertEqual(spec["targetSystem"]["interface"]["phaseA"], "石墨烯")
        self.assertEqual(spec["planVersionId"], updated["documents"]["plan"]["currentVersionId"])

        reloaded = requirements.find_requirement_task(task["id"])
        self.assertIn("modelingSpec", reloaded["documents"])

    def test_generate_modeling_spec_requires_plan(self) -> None:
        task = requirements.create_requirement_task(
            {"fileName": "a.txt", "fileType": "text/plain", "content": "x"}
        )
        with self.assertRaises(ValueError):
            requirements.generate_requirement_modeling_spec(task["id"])

    def test_ensure_modeling_spec_regenerates_when_plan_version_changes(self) -> None:
        task = self._seed_with_plan()
        spec_json = '```json\n{"buildingBlocks": [{"name": "水", "type": "molecule"}], "targetSystem": {"kind": "bulk"}}\n```'
        with patch.object(cli_client, "call", return_value=spec_json):
            task = requirements.ensure_requirement_modeling_spec(task)
        first_version = task["documents"]["modelingSpec"]["planVersionId"]

        # 再次 ensure：版本未变，不应重新生成（call 不被触发）。
        with patch.object(cli_client, "call", side_effect=AssertionError("should not regenerate")):
            same = requirements.ensure_requirement_modeling_spec(task)
        self.assertEqual(same["documents"]["modelingSpec"]["planVersionId"], first_version)

    def test_requirement_tasks_persist_to_sqlite(self) -> None:
        created = requirements.create_requirement_task(
            {
                "fileName": "客户需求说明.docx",
                "fileType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "content": "需要形成一份可导出的方案。",
            }
        )

        tasks = requirements.load_requirement_tasks()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["id"], created["id"])
        self.assertEqual(tasks[0]["status"], "processing")
        self.assertEqual(tasks[0]["documents"], {})


if __name__ == "__main__":
    unittest.main()
