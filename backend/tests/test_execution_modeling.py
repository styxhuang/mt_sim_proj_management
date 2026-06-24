import pathlib
import os
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import config, executions, projects, requirements  # noqa: E402
from sim_backend.llm import cli_client, client  # noqa: E402


SERVER_SOURCE = (pathlib.Path(__file__).resolve().parents[1] / "src" / "sim_backend" / "server.py").read_text(encoding="utf-8")


def _seed_task_with_plan() -> dict:
    task = requirements.create_requirement_task(
        {"fileName": "扩散需求.txt", "fileType": "text/plain", "content": "需要做扩散模拟。"}
    )
    with patch.object(client, "call_llm", return_value="# 需求解析结果\n\n解析"):
        requirements.run_next_requirement_step(task["id"])
    with patch.object(cli_client, "call", return_value="# 实施方案\n\n方案"):
        task = requirements.run_next_requirement_step(task["id"])
    return task


class ExtractStructureTests(unittest.TestCase):
    def test_extracts_pdb_block(self) -> None:
        markdown = (
            "已为水分子建模。\n\n"
            "```pdb\n"
            "HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O\n"
            "END\n"
            "```\n"
        )
        structure = executions.extract_structure(markdown)
        self.assertIsNotNone(structure)
        self.assertEqual(structure["format"], "pdb")
        self.assertIn("HETATM", structure["content"])
        self.assertEqual(structure["name"], "model.pdb")

    def test_returns_none_without_block(self) -> None:
        self.assertIsNone(executions.extract_structure("没有结构代码块"))

    def test_extracts_pdb_from_untagged_block(self) -> None:
        # 模型漏写语言标签时，按内容嗅探出 PDB。
        markdown = "结构如下：\n```\nHETATM    1  O   HOH A   1   0 0 0\nEND\n```"
        result = executions.extract_structure(markdown)
        self.assertIsNotNone(result)
        self.assertEqual(result["format"], "pdb")

    def test_extracts_xyz_from_untagged_block(self) -> None:
        markdown = "```\n2\nwater\nO 0 0 0\nH 1 0 0\n```"
        result = executions.extract_structure(markdown)
        self.assertIsNotNone(result)
        self.assertEqual(result["format"], "xyz")

    def test_parses_molecule_name(self) -> None:
        self.assertEqual(executions.parse_molecule_name("名称：水\n\n说明..."), "水")
        self.assertEqual(executions.parse_molecule_name("名称: H2O"), "H2O")
        self.assertEqual(executions.parse_molecule_name("没有名称行"), "")


class ExecutionLifecycleTests(unittest.TestCase):
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

    def test_get_or_create_requires_plan(self) -> None:
        task = requirements.create_requirement_task(
            {"fileName": "a.txt", "fileType": "text/plain", "content": "x"}
        )
        with self.assertRaises(ValueError):
            executions.get_or_create_execution(task["id"])

    def test_get_or_create_is_idempotent_per_task(self) -> None:
        task = _seed_task_with_plan()
        first = executions.get_or_create_execution(task["id"])
        second = executions.get_or_create_execution(task["id"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["status"], "modeling")
        modeling = first["modules"]["modeling"]
        self.assertEqual(modeling["status"], "pending")
        self.assertEqual(modeling["stage"], "molecules")
        self.assertEqual(modeling["molecules"], [])
        self.assertIsNone(modeling["system"])

    def _seed_task_with_spec(self) -> dict:
        task = _seed_task_with_plan()
        task["projectId"] = "p-test"
        task["documents"]["modelingSpec"] = {
            "buildingBlocks": [
                {"name": "水", "type": "molecule", "role": "溶剂"},
                {"name": "石墨烯", "type": "surface", "role": "基底"},
            ],
            "targetSystem": {
                "kind": "interface",
                "components": [{"block": "水", "count": 50}],
                "interface": {"phaseA": "石墨烯", "phaseB": "水", "note": "固液界面"},
            },
            "planVersionId": task["documents"]["plan"]["currentVersionId"],
        }
        task["documents"]["computationSpec"] = {
            "calculationType": "MD",
            "software": ["GROMACS"],
            "workflowSteps": [
                {"id": "step-1", "name": "NVT 平衡", "phase": "equilibration", "status": "pending", "parameters": {}}
            ],
            "planVersionId": task["documents"]["plan"]["currentVersionId"],
        }
        requirements.save_requirement_task(task)
        return task

    def test_auto_modeling_builds_each_block_then_assembles(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])

        calls = {"n": 0}
        smiles = ["O", "c1ccccc1"]

        def fake_stream(messages, settings=None):
            idx = calls["n"]
            calls["n"] += 1
            yield {"type": "content", "text": f"名称：结构{calls['n']}\n```smiles\n{smiles[idx % len(smiles)]}\n```"}

        with patch.object(cli_client, "stream", side_effect=fake_stream):
            events = list(executions.stream_auto_modeling(execution["id"], {}))

        done = events[-1]
        self.assertEqual(done["type"], "done")
        full = executions.find_execution(execution["id"])
        modeling = full["modules"]["modeling"]
        self.assertEqual(len(modeling["molecules"]), 2)
        self.assertEqual(modeling["status"], "completed")
        self.assertIsNotNone(modeling["system"])
        self.assertIn("HETATM", modeling["system"]["content"])
        self.assertEqual(done["execution"]["modules"]["computation"]["status"], "pending")
        # 仅 2 次模型调用（每个分子一次）；组装是确定性摆放，不调用模型。
        self.assertEqual(calls["n"], 2)
        self.assertEqual(sum(1 for event in events if event["type"] == "progress"), 2)
        assistant_messages = [message for message in done["execution"]["conversation"] if message["role"] == "assistant"]
        self.assertEqual(assistant_messages[0]["usedSkills"][0]["id"], "build_molecule")
        self.assertEqual(assistant_messages[1]["usedSkills"][0]["id"], "build_molecule")
        self.assertTrue((self.project_root / "03-modeling" / "molecules" / "mol-1.pdb").exists())
        self.assertTrue((self.project_root / "03-modeling" / "molecules" / "mol-2.pdb").exists())
        self.assertTrue((self.project_root / "03-modeling" / "system" / "system.pdb").exists())

    def test_prepare_computation_from_modeling_requires_completed_system(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])

        with self.assertRaises(ValueError):
            executions.prepare_computation_from_modeling(execution["id"])

    def test_prepare_computation_from_modeling_records_model_input_and_advances_project(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        modeling = execution["modules"]["modeling"]
        modeling["status"] = "completed"
        modeling["molecules"] = [
            {
                "id": "mol-1",
                "name": "水",
                "format": "pdb",
                "filePath": str(self.project_root / "03-modeling" / "molecules" / "mol-1.pdb"),
            }
        ]
        modeling["system"] = {
            "format": "pdb",
            "name": "system.pdb",
            "content": "HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O\nEND\n",
            "filePath": str(self.project_root / "03-modeling" / "system" / "system.pdb"),
        }
        executions.save_execution(execution)

        payload = executions.prepare_computation_from_modeling(execution["id"])

        prepared = payload["execution"]
        computation = prepared["modules"]["computation"]
        self.assertEqual(computation["status"], "pending")
        self.assertEqual(computation["modelInput"]["structureId"], "system")
        self.assertEqual(computation["modelInput"]["filePath"], str(self.project_root / "03-modeling" / "system" / "system.pdb"))
        self.assertEqual(computation["modelInput"]["atomCount"], 1)
        self.assertEqual(computation["modelInput"]["molecules"][0]["name"], "水")
        self.assertEqual(computation["modelInput"]["manifestPath"], str(self.project_root / "04-computation" / "model-input.json"))
        self.assertTrue((self.project_root / "04-computation" / "model-input.json").exists())
        self.assertEqual(prepared["modules"]["modeling"]["status"], "completed")
        self.assertEqual(projects.find_project("p-test")["currentStage"], "模拟计算")
        self.assertIn("/computation/prepare", SERVER_SOURCE)

    def test_prepare_computation_from_modeling_preserves_refined_computation_status(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        modeling = execution["modules"]["modeling"]
        modeling["status"] = "completed"
        modeling["system"] = {
            "format": "pdb",
            "name": "system.pdb",
            "content": "HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O\nEND\n",
            "filePath": str(self.project_root / "03-modeling" / "system" / "system.pdb"),
        }
        execution["modules"]["computation"]["status"] = "completed"
        execution["modules"]["computation"]["refined"] = True
        execution["modules"]["computation"]["detail"] = "已细化 1 个计算步骤"
        executions.save_execution(execution)

        payload = executions.prepare_computation_from_modeling(execution["id"])

        computation = payload["execution"]["modules"]["computation"]
        self.assertEqual(computation["status"], "completed")
        self.assertTrue(computation["refined"])
        self.assertIn("已细化", computation["detail"])

    def test_execution_detail_api_uses_lightweight_response_without_structure_content(self) -> None:
        self.assertIn('"execution": executions.execution_without_content(execution)', SERVER_SOURCE)
        self.assertNotIn('self._send_json({"execution": execution})', SERVER_SOURCE)

    def test_lightweight_execution_marks_modeling_completed_when_system_exists(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        modeling = execution["modules"]["modeling"]
        modeling["status"] = "pending"
        modeling["detail"] = "等待建模"
        modeling["system"] = {
            "format": "pdb",
            "name": "system.pdb",
            "content": "HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O\nEND\n",
        }

        payload = executions.execution_without_content(execution)

        self.assertEqual(payload["modules"]["modeling"]["status"], "completed")
        self.assertEqual(payload["modules"]["modeling"]["system"]["atomCount"], 1)
        self.assertNotIn("content", payload["modules"]["modeling"]["system"])

    def test_modeling_chat_replaces_molecule_and_reassembles(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])

        smiles = ["O", "c1ccccc1"]
        calls = {"n": 0}

        def fake_auto(messages, settings=None):
            idx = calls["n"]
            calls["n"] += 1
            yield {"type": "content", "text": f"名称：结构{calls['n']}\n```smiles\n{smiles[idx % len(smiles)]}\n```"}

        with patch.object(cli_client, "stream", side_effect=fake_auto):
            list(executions.stream_auto_modeling(execution["id"], {}))

        before = executions.find_execution(execution["id"])
        first_name = before["modules"]["modeling"]["molecules"][0]["name"]
        mol_count = len(before["modules"]["modeling"]["molecules"])

        def fake_fix(messages, settings=None):
            yield {"type": "content", "text": f"名称：{first_name}\n```smiles\nCCO\n```"}

        with patch.object(cli_client, "stream", side_effect=fake_fix):
            events = list(
                executions.stream_modeling_chat(execution["id"], {"message": f"{first_name} 结构不对，请重建"})
            )

        modeling = executions.find_execution(execution["id"])["modules"]["modeling"]
        # 同名分子被替换而非新增，体系重新组装。
        self.assertEqual(len(modeling["molecules"]), mol_count)
        self.assertIsNotNone(modeling["system"])
        self.assertIn("HETATM", modeling["system"]["content"])
        self.assertEqual(events[-1]["execution"]["conversation"][-1]["usedSkills"][0]["id"], "build_molecule")

    def test_component_ratios_scale_to_target_atom_count(self) -> None:
        molecules = [
            {"id": "mol-1", "name": "A代表分子", "blockName": "A", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
            {"id": "mol-2", "name": "B代表分子", "blockName": "B", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
            {"id": "mol-3", "name": "C代表分子", "blockName": "C", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
        ]
        components = executions._resolve_components(
            molecules,
            {
                "targetSystem": {
                    "atomCount": 50000,
                    "components": [
                        {"block": "A", "count": "6"},
                        {"block": "B", "count": "5"},
                        {"block": "C", "count": "1"},
                    ],
                }
            },
        )

        self.assertEqual([comp["count"] for comp in components], [25000, 20833, 4167])

    def test_precomputed_component_counts_are_preserved_and_matched_by_alias(self) -> None:
        molecules = [
            {"id": "mol-1", "name": "ECO", "code": "ECO", "blockName": "环氧化蓖麻油代表甘油三酯", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
            {"id": "mol-2", "name": "MTH", "code": "MTH", "blockName": "甲基四氢邻苯二酸酐", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
            {"id": "mol-3", "name": "DMP", "code": "DMP", "blockName": "DMP-30", "content": "HETATM    1  C   LIG A   1       0.000   0.000   0.000  1.00  0.00           C"},
        ]
        components = executions._resolve_components(
            molecules,
            {
                "targetSystem": {
                    "atomCount": 50000,
                    "components": [
                        {"block": "ECO", "count": 167},
                        {"block": "MTH", "count": 949},
                        {"block": "DMP", "count": 5},
                    ],
                }
            },
        )

        self.assertEqual([comp["name"] for comp in components], ["ECO", "MTH", "DMP"])
        self.assertEqual([comp["count"] for comp in components], [167, 949, 5])

    def test_modeling_chat_system_request_reassembles_without_llm(self) -> None:
        task = self._seed_task_with_spec()
        task["documents"]["modelingSpec"]["targetSystem"]["atomCount"] = 1000
        task["documents"]["modelingSpec"]["targetSystem"]["components"] = [
            {"block": "水", "count": "6"},
            {"block": "石墨烯", "count": "1"},
        ]
        requirements.save_requirement_task(task)
        execution = executions.get_or_create_execution(task["id"])

        calls = {"n": 0}

        def fake_auto(messages, settings=None):
            smiles = ["O", "c1ccccc1"][calls["n"]]
            calls["n"] += 1
            yield {"type": "content", "text": f"名称：结构{calls['n']}\n```smiles\n{smiles}\n```"}

        with patch.object(cli_client, "stream", side_effect=fake_auto):
            list(executions.stream_auto_modeling(execution["id"], {}))

        with patch.object(cli_client, "stream") as llm_stream:
            events = list(
                executions.stream_modeling_chat(
                    execution["id"], {"message": "提高完整体系分子数量，按目标原子数和摩尔比重新组装"}
                )
            )

        self.assertEqual(llm_stream.call_count, 0)
        self.assertEqual(events[-1]["type"], "done")
        modeling = executions.find_execution(execution["id"])["modules"]["modeling"]
        self.assertIsNotNone(modeling["system"])
        self.assertIn("重新组装完整体系", modeling["detail"])
        self.assertEqual(modeling["usedSkills"][0]["id"], "build_amorphous")
        self.assertEqual(events[-1]["execution"]["conversation"][-1]["usedSkills"][0]["id"], "build_amorphous")
        self.assertIn("build_amorphous", events[-1]["execution"]["conversation"][-1]["content"])

    def test_modeling_chat_requires_message(self) -> None:
        task = _seed_task_with_plan()
        execution = executions.get_or_create_execution(task["id"])
        with self.assertRaises(ValueError):
            list(executions.stream_modeling_chat(execution["id"], {"message": "  "}))

    def test_auto_modeling_requires_spec(self) -> None:
        task = _seed_task_with_plan()
        execution = executions.get_or_create_execution(task["id"])
        with self.assertRaises(ValueError):
            list(executions.stream_auto_modeling(execution["id"], {}))

    def test_computation_requires_assembled_system(self) -> None:
        task = _seed_task_with_plan()
        execution = executions.get_or_create_execution(task["id"])
        with self.assertRaises(ValueError):
            list(executions.stream_computation(execution["id"], {}))

    def test_computation_generates_plan_after_modeling(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])

        smiles = ["O", "c1ccccc1"]
        calls = {"n": 0}

        def fake_auto(messages, settings=None):
            idx = calls["n"]
            calls["n"] += 1
            yield {"type": "content", "text": f"名称：结构{calls['n']}\n```smiles\n{smiles[idx % len(smiles)]}\n```"}

        with patch.object(cli_client, "stream", side_effect=fake_auto):
            list(executions.stream_auto_modeling(execution["id"], {}))
        executions.prepare_computation_from_modeling(execution["id"])

        def fake_compute(messages, settings=None):
            yield {
                "type": "content",
                "text": '```json\n{"calculationType":"MD","software":["GROMACS"],"workflowSteps":[{"id":"step-1","name":"NVT 平衡","phase":"equilibration","status":"completed","parameters":{"temperature":"300 K"},"executionDoc":"## 计算目标\\n\\n做动力学模拟。"}]}\n```',
            }

        with patch.object(cli_client, "stream", side_effect=fake_compute):
            events = list(executions.stream_computation(execution["id"], {}))

        done = events[-1]
        self.assertEqual(done["type"], "done")
        computation = done["execution"]["modules"]["computation"]
        self.assertEqual(computation["status"], "pending")
        self.assertTrue(computation.get("refined"))
        self.assertIn("待运行", computation["detail"])
        spec = done.get("computationSpec") or {}
        self.assertTrue(spec.get("workflowSteps"))
        self.assertEqual(spec["workflowSteps"][0]["status"], "pending")
        self.assertEqual(spec.get("modelInput", {}).get("structureId"), "system")
        self.assertTrue(spec.get("modelInput", {}).get("filePath", "").endswith("03-modeling/system/system.pdb"))
        self.assertEqual(done["execution"]["conversation"][-1]["usedSkills"][0]["id"], "refine_computation_spec")

    def test_run_computation_step_local_generates_artifacts(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        with patch.object(cli_client, "call", return_value="# NVT 平衡\n\n已生成本地执行方案和结果文件。") as cli_call:
            result = executions.run_computation_step(execution["id"], "step-1", "local")

        run = result["run"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["runner"], "local")
        self.assertTrue(run["artifacts"])
        self.assertIn("cursor-cli", "\n".join(run["logs"]))
        self.assertIn("cursor-cli", run["summary"])
        self.assertEqual(cli_call.call_count, 1)
        self.assertIn("NVT 平衡", cli_call.call_args.args[0][-1]["content"])
        self.assertIn("项目路径", cli_call.call_args.args[0][-1]["content"])
        self.assertIn("structure_build", cli_call.call_args.args[0][-1]["content"])
        self.assertIn("不要停留在只读计划", cli_call.call_args.args[0][-1]["content"])
        self.assertIn("-c gas", cli_call.call_args.args[0][-1]["content"])
        cli_settings = cli_call.call_args.args[1]
        self.assertEqual(cli_settings["workspace"], str(self.project_root))
        self.assertEqual(cli_settings["mode"], "agent")
        self.assertTrue(cli_settings["force"])
        self.assertEqual(cli_settings["timeout_seconds"], 600)
        updated = result["execution"]
        computation = updated["modules"]["computation"]
        self.assertEqual(computation["runs"]["step-1"]["status"], "completed")
        self.assertEqual(computation["runnerSelections"]["step-1"], "local")
        artifact = computation["artifacts"][0]
        self.assertEqual(artifact["stepId"], "step-1")
        content = executions.get_computation_artifact_content(updated, artifact["id"])
        self.assertIn("NVT 平衡", content["content"])
        self.assertTrue(str(pathlib.Path(artifact["storagePath"])).startswith(str(self.project_root)))
        artifact_names = [item["name"] for item in computation["artifacts"]]
        self.assertTrue(any(name.endswith("-prompt.md") for name in artifact_names))
        self.assertTrue(any(name.endswith("-result.md") for name in artifact_names))
        self.assertTrue(any(name.endswith("-run.log") for name in artifact_names))

    def test_local_computation_prompt_rewrites_legacy_bcc_to_gas(self) -> None:
        task = self._seed_task_with_spec()
        task["documents"]["computationSpec"]["workflowSteps"][0]["method"] = "使用 AM1-BCC 固定电荷"
        task["documents"]["computationSpec"]["workflowSteps"][0]["parameters"] = {
            "chargeStrategy": "推荐 AM1-BCC",
            "command": "antechamber -c bcc",
        }
        requirements.save_requirement_task(task)
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        with patch.object(cli_client, "call", return_value="# 本地执行\n\n完成。") as cli_call:
            executions.run_computation_step(execution["id"], "step-1", "local")

        prompt = cli_call.call_args.args[0][-1]["content"]
        self.assertIn("默认使用 gas 电荷", prompt)
        self.assertIn("antechamber -c gas", prompt)
        self.assertNotIn("AM1-BCC", prompt)
        self.assertNotIn("-c bcc", prompt)

    def test_completed_local_run_merges_real_execution_logs(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        run_root = self.project_root / "04-computation" / f"{execution['id']}-step-1"
        logs = run_root / "logs"
        topology = run_root / "topology"
        logs.mkdir(parents=True)
        topology.mkdir()
        (logs / "step-1-run.log").write_text("antechamber -c gas\n", encoding="utf-8")
        (logs / "grompp_check.log").write_text("There was 1 WARNING\n[exit_code] 0\n", encoding="utf-8")
        (logs / "final_validation.log").write_text("FINAL VALIDATION PASS\n", encoding="utf-8")
        (topology / "system.top").write_text("[ system ]\n", encoding="utf-8")

        with patch.object(cli_client, "call", return_value="# 本地执行\n\n完成。"):
            result = executions.run_computation_step(execution["id"], "step-1", "local")

        run = result["run"]
        logs_text = "\n".join(run["logs"])
        self.assertIn("真实执行日志", logs_text)
        self.assertIn("FINAL VALIDATION PASS", logs_text)
        self.assertTrue(any(artifact["name"] == "grompp_check.log" for artifact in run["artifacts"]))
        self.assertTrue(any(artifact["name"] == "system.top" for artifact in run["artifacts"]))

    def test_computation_artifacts_use_execution_step_directory(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])

        artifact = executions._write_computation_artifact(
            execution,
            "step-1",
            "step-1-result.md",
            "result",
            "result",
            "text/markdown",
        )

        self.assertIn(f"04-computation/{execution['id']}-step-1/artifacts/", artifact["storagePath"])
        self.assertNotIn("04-computation/step-1/", artifact["storagePath"])

    def test_migrate_computation_artifact_layout_moves_legacy_step_artifacts(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        legacy_dir = self.project_root / "04-computation" / "step-1"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "artifact-001-step-1-result.md"
        legacy_file.write_text("legacy result", encoding="utf-8")
        computation = execution["modules"]["computation"]
        computation["artifacts"] = [
            {
                "id": "artifact-001",
                "stepId": "step-1",
                "name": "step-1-result.md",
                "kind": "result",
                "mime": "text/markdown",
                "size": legacy_file.stat().st_size,
                "storagePath": str(legacy_file),
                "createdAt": "2026-06-22T00:00:00",
            }
        ]
        executions.save_execution(execution)

        migrated = executions.migrate_computation_artifact_layout(execution["id"])

        artifact = migrated["modules"]["computation"]["artifacts"][0]
        target = self.project_root / "04-computation" / f"{execution['id']}-step-1" / "artifacts" / legacy_file.name
        self.assertEqual(artifact["storagePath"], str(target))
        self.assertTrue(target.exists())
        self.assertFalse(legacy_file.exists())
        self.assertFalse(legacy_dir.exists())

    def test_run_computation_step_bohrium_requires_scripts(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        result = executions.run_computation_step(execution["id"], "step-1", "bohrium")

        run = result["run"]
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["runner"], "bohrium")
        self.assertIn("未找到可提交", "\n".join(run["logs"]))
        self.assertEqual(result["execution"]["modules"]["computation"]["status"], "failed")

    def test_run_computation_step_bohrium_auto_prepares_gromacs_package(self) -> None:
        task = self._seed_task_with_spec()
        step = task["documents"]["computationSpec"]["workflowSteps"][0]
        step["name"] = "能量最小化"
        step["dependsOn"] = ["step-2"]
        step["usedSkills"] = [{"scripts": ["skills/polymer-21step-equilibration/scripts/generate_21_mdp.py"]}]
        requirements.save_requirement_task(task)
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {
            "format": "pdb",
            "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C",
            "name": "system.pdb",
        }
        executions.save_execution(execution)
        previous_topology = self.project_root / "04-computation" / f"{execution['id']}-step-2" / "topology"
        previous_topology.mkdir(parents=True)
        (previous_topology / "system.top").write_text("[ system ]\n", encoding="utf-8")
        (previous_topology / "ECO.itp").write_text("[ moleculetype ]\n", encoding="utf-8")
        (previous_topology / "system_sanitized.gro").write_text("test\n1\n    1SYS      C    1   0.000   0.000   0.000\n   1.0   1.0   1.0\n", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "JobId: 12345"
            stderr = ""

        with patch.object(executions.shutil, "which", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", return_value=Completed()):
            result = executions.run_computation_step(execution["id"], "step-1", "bohrium")

        run = result["run"]
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["remote"]["jobId"], "12345")
        self.assertIn("自动生成 Bohrium GROMACS 提交包", "\n".join(run["logs"]))
        self.assertIn("等待 Bohrium job 完成", "\n".join(run["logs"]))
        job_json_path = self.project_root / "04-computation" / f"{execution['id']}-step-1" / "job.json"
        self.assertTrue(job_json_path.exists())
        job_config = json.loads(job_json_path.read_text(encoding="utf-8"))
        self.assertEqual(job_config["image_address"], "registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4")
        self.assertEqual(job_config["machine_type"], "c4_m15_1 * NVIDIA T4")
        input_dir = self.project_root / "04-computation" / f"{execution['id']}-step-1" / "bohrium-input"
        self.assertTrue((input_dir / "em.mdp").exists())
        self.assertTrue((input_dir / "em2.mdp").exists())
        self.assertTrue((input_dir / "1nvt.mdp").exists())
        self.assertTrue((input_dir / "21npt.mdp").exists())
        run_script = (input_dir / "run.sh").read_text(encoding="utf-8")
        self.assertIn("GMX=gmx_mpi", run_script)
        self.assertIn("OMPI_ALLOW_RUN_AS_ROOT=1", run_script)
        self.assertIn("$GMX grompp", run_script)
        self.assertIn("$GMX mdrun -v -deffnm em -gpu_id 0", run_script)
        self.assertIn("$GMX mdrun -v -deffnm em2 -gpu_id 0", run_script)
        self.assertIn('steps=("1nvt"', run_script)
        self.assertIn('"21npt")', run_script)
        self.assertIn("$GMX mdrun -v -deffnm $i -nstlist 80 -gpu_id 0", run_script)
        self.assertNotIn("-deffnm em -nstlist", run_script)
        artifact_names = [artifact["name"] for artifact in run["artifacts"]]
        self.assertIn("job.json", artifact_names)
        self.assertIn("run.sh", artifact_names)

    def test_run_computation_step_bohrium_auto_prepares_polymer_skill_without_scripts(self) -> None:
        task = self._seed_task_with_spec()
        step = task["documents"]["computationSpec"]["workflowSteps"][0]
        step["name"] = "聚合物 21 步平衡法"
        step["dependsOn"] = ["step-2"]
        step["usedSkills"] = [{"id": "polymer-21step-equilibration", "name": "聚合物 21 步平衡法"}]
        requirements.save_requirement_task(task)
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {
            "format": "pdb",
            "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C",
            "name": "system.pdb",
        }
        executions.save_execution(execution)
        previous_topology = self.project_root / "04-computation" / f"{execution['id']}-step-2" / "topology"
        previous_topology.mkdir(parents=True)
        (previous_topology / "system.top").write_text("[ system ]\n", encoding="utf-8")
        (previous_topology / "system_sanitized.gro").write_text("test\n1\n    1SYS      C    1   0.000   0.000   0.000\n   1.0   1.0   1.0\n", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = "JobId: 12345"
            stderr = ""

        with patch.object(executions.shutil, "which", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", return_value=Completed()):
            result = executions.run_computation_step(execution["id"], "step-1", "bohrium")

        run = result["run"]
        self.assertEqual(run["status"], "running")
        self.assertIn("自动生成 Bohrium GROMACS 提交包", "\n".join(run["logs"]))
        self.assertNotIn("未找到可提交", "\n".join(run["logs"]))

    def test_bohrium_env_prefers_bashrc_access_key_aliases(self) -> None:
        home = pathlib.Path(self.temp_dir.name) / "home"
        home.mkdir()
        (home / ".bashrc").write_text(
            'export ACCESS_KEY="new-access-key"\nexport PROJECT_ID="123456"\n',
            encoding="utf-8",
        )

        with patch.object(executions.Path, "home", return_value=home), patch.dict(
            os.environ,
            {"BOHRIUM_ACCESS_KEY": "old-access-key", "BOHRIUM_PROJECT_ID": "654321"},
        ):
            env = executions._bohrium_env()

        self.assertEqual(env["ACCESS_KEY"], "new-access-key")
        self.assertEqual(env["PROJECT_ID"], "123456")
        self.assertEqual(env["BOHRIUM_ACCESS_KEY"], "new-access-key")
        self.assertEqual(env["BOHRIUM_PROJECT_ID"], "123456")

    def test_find_execution_reconciles_finished_bohrium_job(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {
            "format": "pdb",
            "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C",
            "name": "system.pdb",
        }
        computation = execution["modules"]["computation"]
        computation["status"] = "in_progress"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "NVT 平衡",
            "runner": "bohrium",
            "status": "running",
            "logs": ["Bohrium job 已提交：12345"],
            "summary": "Bohrium 已提交：NVT 平衡，等待 job 完成",
            "artifacts": [],
            "remote": {"jobId": "12345", "jobGroupId": "88"},
            "startedAt": "2026-06-22T00:00:00",
            "completedAt": "",
        }
        executions.save_execution(execution)

        class Finished:
            returncode = 0
            stdout = json.dumps({"jobId": 12345, "status": 2, "statusName": "Finished"})
            stderr = ""

        with patch.object(executions, "_find_bohr", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", return_value=Finished()):
            recovered = executions.find_execution(execution["id"])

        run = recovered["modules"]["computation"]["runs"]["step-1"]
        self.assertEqual(run["status"], "completed")
        self.assertIn("Bohrium job 已完成", "\n".join(run["logs"]))
        self.assertEqual(recovered["modules"]["computation"]["status"], "completed")
        task_after = requirements.find_requirement_task(task["id"])
        self.assertIsNotNone(task_after)
        step_after = task_after["documents"]["computationSpec"]["workflowSteps"][0]
        self.assertEqual(step_after["status"], "completed")

    def test_find_execution_downloads_finished_bohrium_job_to_execution_results(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        computation = execution["modules"]["computation"]
        computation["status"] = "in_progress"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "NVT 平衡",
            "runner": "bohrium",
            "status": "running",
            "logs": ["Bohrium job 已提交：12345"],
            "summary": "Bohrium 已提交：NVT 平衡，等待 job 完成",
            "artifacts": [],
            "remote": {"jobId": "12345"},
            "startedAt": "2026-06-22T00:00:00",
            "completedAt": "",
        }
        executions.save_execution(execution)

        class Completed:
            returncode = 0
            stdout = json.dumps({"jobId": 12345, "status": 2, "statusName": "Finished"})
            stderr = ""

        def fake_run(command, **_kwargs):
            if command[:3] == ["/usr/bin/bohr", "job", "download"]:
                output_dir = pathlib.Path(command[-1])
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "job.done").write_text("done\n", encoding="utf-8")
                (output_dir / "21npt.gro").write_text("gro\n", encoding="utf-8")
            return Completed()

        with patch.object(executions, "_find_bohr", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", side_effect=fake_run):
            recovered = executions.find_execution(execution["id"])

        results_dir = self.project_root / "04-computation" / f"{execution['id']}-step-1" / "results"
        self.assertTrue((results_dir / "job.done").exists())
        self.assertTrue((results_dir / "21npt.gro").exists())
        run = recovered["modules"]["computation"]["runs"]["step-1"]
        self.assertEqual(run["remote"]["downloadDir"], str(results_dir))
        self.assertTrue(any(artifact["name"] == "21npt.gro" for artifact in run["artifacts"]))

    def test_find_execution_reconciles_failed_bohrium_job(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {
            "format": "pdb",
            "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C",
            "name": "system.pdb",
        }
        computation = execution["modules"]["computation"]
        computation["status"] = "in_progress"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "NVT 平衡",
            "runner": "bohrium",
            "status": "running",
            "logs": ["Bohrium job 已提交：12345"],
            "summary": "Bohrium 已提交：NVT 平衡，等待 job 完成",
            "artifacts": [],
            "remote": {"jobId": "12345"},
            "startedAt": "2026-06-22T00:00:00",
            "completedAt": "",
        }
        executions.save_execution(execution)

        class Failed:
            returncode = 0
            stdout = json.dumps({"jobId": 12345, "status": -1, "statusName": "Failed", "message": "mdrun failed"})
            stderr = ""

        with patch.object(executions, "_find_bohr", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", return_value=Failed()):
            recovered = executions.find_execution(execution["id"])

        run = recovered["modules"]["computation"]["runs"]["step-1"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("mdrun failed", "\n".join(run["logs"]))
        self.assertEqual(recovered["modules"]["computation"]["status"], "failed")

    def test_find_execution_syncs_completed_bohrium_run_to_workflow_step(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        computation = execution["modules"]["computation"]
        computation["status"] = "completed"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "能量最小化",
            "runner": "bohrium",
            "status": "completed",
            "logs": ["Bohrium job 已完成：12345"],
            "summary": "Bohrium job 已完成：能量最小化",
            "artifacts": [],
            "remote": {"jobId": "12345"},
            "startedAt": "2026-06-22T00:00:00",
            "completedAt": "2026-06-22T00:10:00",
        }
        requirements.save_requirement_task(task)
        executions.save_execution(execution)

        recovered = executions.find_execution(execution["id"])

        self.assertEqual(recovered["modules"]["computation"]["runs"]["step-1"]["status"], "completed")
        task_after = requirements.find_requirement_task(task["id"])
        self.assertIsNotNone(task_after)
        step_after = task_after["documents"]["computationSpec"]["workflowSteps"][0]
        self.assertEqual(step_after["status"], "completed")
        self.assertEqual(step_after["runner"], "bohrium")

    def test_terminate_bohrium_computation_step_marks_run_failed(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        computation = execution["modules"]["computation"]
        computation["status"] = "in_progress"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "能量最小化",
            "runner": "bohrium",
            "status": "running",
            "logs": ["Bohrium job 已提交：12345"],
            "summary": "Bohrium 已提交：能量最小化，等待 job 完成",
            "artifacts": [],
            "remote": {"jobId": "12345"},
            "startedAt": "2026-06-22T00:00:00",
            "completedAt": "",
        }
        executions.save_execution(execution)

        class Terminated:
            returncode = 0
            stdout = "terminated"
            stderr = ""

        with patch.object(executions, "_find_bohr", return_value="/usr/bin/bohr"), patch.object(executions.subprocess, "run", return_value=Terminated()) as run_call:
            result = executions.terminate_computation_step(execution["id"], "step-1")

        commands = [call.args[0] for call in run_call.call_args_list]
        self.assertIn(["/usr/bin/bohr", "job", "terminate", "12345"], commands)
        run = result["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("已终止", run["summary"])
        self.assertIn("Bohrium job 已终止：12345", "\n".join(run["logs"]))
        self.assertEqual(result["execution"]["modules"]["computation"]["status"], "failed")
        task_after = requirements.find_requirement_task(task["id"])
        self.assertIsNotNone(task_after)
        step_after = task_after["documents"]["computationSpec"]["workflowSteps"][0]
        self.assertEqual(step_after["status"], "failed")

    def test_run_computation_step_persists_logs_when_cursor_cli_fails(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        with patch.object(cli_client, "call", side_effect=ValueError("cursor-agent 调用失败")):
            result = executions.run_computation_step(execution["id"], "step-1", "local")

        run = result["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("cursor-agent 调用失败", "\n".join(run["logs"]))
        artifact_names = [item["name"] for item in result["execution"]["modules"]["computation"]["artifacts"]]
        self.assertTrue(any(name.endswith("-prompt.md") for name in artifact_names))
        self.assertTrue(any(name.endswith("-run.log") for name in artifact_names))
        self.assertEqual(result["execution"]["modules"]["computation"]["status"], "failed")

    def test_run_computation_step_marks_readonly_result_as_failed(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        readonly_result = "当前为 Ask mode，只读检查发现未发现真实参数产物。"
        with patch.object(cli_client, "call", return_value=readonly_result):
            result = executions.run_computation_step(execution["id"], "step-1", "local")

        run = result["run"]
        self.assertEqual(run["status"], "failed")
        self.assertIn("未实际完成", run["summary"])
        self.assertIn("未实际执行", "\n".join(run["logs"]))
        self.assertEqual(result["execution"]["modules"]["computation"]["status"], "failed")

    def test_find_execution_reconciles_finished_local_run_from_logs(self) -> None:
        task = self._seed_task_with_spec()
        execution = executions.get_or_create_execution(task["id"])
        computation = execution["modules"]["computation"]
        computation["status"] = "in_progress"
        computation["detail"] = "正在运行：NVT 平衡"
        computation["currentStepId"] = "step-1"
        computation["runnerSelections"]["step-1"] = "local"
        computation["runs"]["step-1"] = {
            "id": "run-step-1-1",
            "stepId": "step-1",
            "stepName": "NVT 平衡",
            "runner": "local",
            "status": "running",
            "logs": ["开始运行"],
            "summary": "",
            "artifacts": [],
            "startedAt": "2026-06-22T21:00:00",
            "completedAt": "",
        }
        executions.save_execution(execution)

        run_root = self.project_root / "04-computation" / f"{execution['id']}-step-1"
        logs = run_root / "logs"
        topology = run_root / "topology"
        logs.mkdir(parents=True)
        topology.mkdir()
        (logs / "step-1-run.log").write_text("step finished\n", encoding="utf-8")
        (logs / "grompp_check.log").write_text("There was 1 WARNING\n[exit_code] 0\n", encoding="utf-8")
        (topology / "system.top").write_text("[ system ]\n", encoding="utf-8")

        recovered = executions.find_execution(execution["id"])
        run = recovered["modules"]["computation"]["runs"]["step-1"]
        self.assertEqual(run["status"], "completed")
        self.assertIn("已从本地日志恢复完成状态", run["summary"])
        self.assertTrue(any(artifact["name"] == "step-1-run.log" for artifact in run["artifacts"]))
        self.assertEqual(recovered["modules"]["computation"]["status"], "completed")

    def test_run_all_computation_steps_stops_after_failure(self) -> None:
        task = self._seed_task_with_spec()
        task["documents"]["computationSpec"]["workflowSteps"].append(
            {"id": "step-2", "name": "NPT 平衡", "phase": "equilibration", "status": "pending", "parameters": {}}
        )
        requirements.save_requirement_task(task)
        execution = executions.get_or_create_execution(task["id"])
        execution["modules"]["modeling"]["system"] = {"format": "pdb", "content": "HETATM    1  C   SYS A   1       0.000   0.000   0.000  1.00  0.00           C", "name": "system.pdb"}
        execution["modules"]["computation"]["status"] = "pending"
        executions.save_execution(execution)

        with patch.object(cli_client, "call", return_value="# 本地步骤结果\n\n完成。"):
            result = executions.run_all_computation_steps(
                execution["id"],
                default_runner="local",
                runner_overrides={"step-2": "bohrium"},
            )

        self.assertEqual([run["stepId"] for run in result["runs"]], ["step-1", "step-2"])
        self.assertEqual(result["runs"][0]["status"], "completed")
        self.assertEqual(result["runs"][1]["status"], "failed")
        computation = result["execution"]["modules"]["computation"]
        self.assertEqual(computation["runs"]["step-1"]["status"], "completed")
        self.assertEqual(computation["runs"]["step-2"]["status"], "failed")
        self.assertEqual(computation["status"], "failed")

    def test_computation_run_api_routes_are_registered(self) -> None:
        self.assertIn("/computation/steps/", SERVER_SOURCE)
        self.assertIn("/computation/run-all", SERVER_SOURCE)
        self.assertIn("/terminate", SERVER_SOURCE)
        self.assertIn('"computation"', SERVER_SOURCE)
        self.assertIn('"artifacts"', SERVER_SOURCE)
        self.assertIn("get_computation_artifact_content", SERVER_SOURCE)

    def test_computation_skills_are_registered(self) -> None:
        from sim_backend import skills

        self.assertIn("extract_computation_spec", skills.SKILLS)
        self.assertIn("refine_computation_spec", skills.SKILLS)

    def test_computation_prompts_prefer_polymer_21step_as_single_step(self) -> None:
        from sim_backend import skills

        context = {
            "project_skill_catalog": "- polymer-21step-equilibration: 聚合物 21 步平衡法",
            "plan_text_or_empty": "本项目为聚合物体系，使用 GROMACS 进行分子动力学平衡。",
            "computation_spec_json": json.dumps(
                {
                    "calculationType": "MD",
                    "software": ["GROMACS"],
                    "workflowSteps": [
                        {"id": "step-1", "name": "短程 NVT 预平衡", "phase": "equilibration"},
                        {"id": "step-2", "name": "NPT 密度平衡", "phase": "equilibration"},
                    ],
                },
                ensure_ascii=False,
            ),
            "system_summary_or_empty": "聚合物主体体系，约 50000 原子。",
            "model_input_json": "{}",
        }

        extract_text = "\n".join(message["content"] for message in skills.SKILLS["extract_computation_spec"].build_messages(context))
        refine_text = "\n".join(message["content"] for message in skills.SKILLS["refine_computation_spec"].build_messages(context))

        self.assertIn("聚合物 21 步平衡法", extract_text)
        self.assertIn("不要拆成多个单独动力学步骤", extract_text)
        self.assertIn("聚合物 21 步平衡法", refine_text)
        self.assertIn("允许将多个泛化 NVT/NPT 平衡步骤合并", refine_text)

    def test_gromacs_bohrium_skill_is_available_for_standalone_runs(self) -> None:
        from sim_backend.skills.computation import _project_skill_catalog

        catalog = _project_skill_catalog()

        self.assertIn("gromacs-bohrium", catalog)
        self.assertIn("registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4", catalog)
        self.assertIn("c4_m15_1 * NVIDIA T4", catalog)

    def test_computation_spec_preserves_used_skills(self) -> None:
        from sim_backend.requirements import _normalize_computation_spec

        spec = _normalize_computation_spec(
            {
                "workflowSteps": [
                    {
                        "id": "step-1",
                        "name": "聚合物 21 步平衡",
                        "usedSkills": [
                            {
                                "id": "polymer-21step-equilibration",
                                "name": "聚合物 21 步平衡法",
                                "scripts": ["backend/skills/polymer-21step-equilibration/scripts/generate_21_mdp.py"],
                                "reason": "生成 GROMACS MDP 文件",
                            }
                        ],
                    }
                ]
            }
        )

        used = spec["workflowSteps"][0]["usedSkills"]
        self.assertEqual(used[0]["id"], "polymer-21step-equilibration")
        self.assertIn("generate_21_mdp.py", used[0]["scripts"][0])


if __name__ == "__main__":
    unittest.main()
