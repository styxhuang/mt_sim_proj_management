import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend import skills  # noqa: E402
from sim_backend.skills import analysis, base, build_molecule, computation, modeling_plan, plan  # noqa: E402


class SkillPromptTests(unittest.TestCase):
    def test_plan_skill_is_loaded_from_backend_skill_file(self) -> None:
        skill_path = pathlib.Path(__file__).resolve().parents[1] / "skills" / "generate_plan" / "SKILL.md"
        self.assertTrue(skill_path.exists())
        self.assertEqual(plan.generate_plan.source_path, skill_path)

    def test_file_only_skills_can_be_discovered_for_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = pathlib.Path(temp_dir) / "echo_skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: echo_skill",
                        "title: Echo Skill",
                        "provider: http",
                        "---",
                        "",
                        "## System Prompt",
                        "你是回声测试助手。",
                        "",
                        "## User Prompt",
                        "{{message}}",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(base, "SKILL_ROOT", pathlib.Path(temp_dir)):
                discovered = skills.discover_resource_skills(exclude=set())

        self.assertIn("echo_skill", discovered)
        self.assertEqual(discovered["echo_skill"].build_messages({"message": "hi"})[-1]["content"], "hi")

    def test_plan_prompt_requires_all_sections_and_guidance(self) -> None:
        messages = plan._build_messages({"analysis_result": "# 需求解析结果\n做扩散模拟"})
        user_content = messages[-1]["content"]
        for section in [
            "# 需求理解",
            "# 项目目标拆解",
            "# 计算意图",
            "# 需要补充确认的信息",
            "# 计算架构设计",
            "# 具体方案",
            "# 验证与质量控制",
            "# 结果输出设计",
            "# 需求计算风险以及风险控制",
            "# 项目边界条件",
            "# 交付清单",
            "# 工作量评估",
            "# 算力资源评估",
            "# 报价和周期",
            "# 总结",
        ]:
            self.assertIn(section, user_content)
        # 富化提示：方案应支持售前、评审、报价和合同附件，而不是只列参数。
        self.assertIn("售前交流", messages[0]["content"])
        self.assertIn("技术评审", messages[0]["content"])
        self.assertIn("合同附件", messages[0]["content"])
        self.assertIn("先讲项目目标与价值，再讲技术实现", messages[0]["content"])
        self.assertIn("不要编造", messages[0]["content"])
        # 计算类型、模拟尺度、软件体系和资源评估必须明确。
        self.assertIn("分子动力学", user_content)
        self.assertIn("二者都要", user_content)
        self.assertIn("全原子", user_content)
        self.assertIn("粗粒化", user_content)
        self.assertIn("软件选择", user_content)
        self.assertIn("GROMACS / LAMMPS", user_content)
        self.assertIn("CPU核时", user_content)
        self.assertIn("GPU时长", user_content)
        self.assertIn("预计数据规模", user_content)
        # 允许指定章节使用表格，但叙述章节禁止表格。
        self.assertIn("需求理解", user_content)
        self.assertIn("禁止使用表格", user_content)
        self.assertIn("| 输出结果 | 方法来源 | 物理意义 | 支撑结论 |", user_content)
        self.assertIn("| 模块 | 工作内容 | 人工工时 | CPU核时 | GPU时长 |", user_content)
        # 整体定位为可直接交付客户的正式实施方案文档。
        self.assertIn("可直接提交客户", messages[0]["content"])
        # 客户交付稿不应出现内部分析口吻。
        self.assertIn("禁止出现“客户已明确”", messages[0]["content"])
        self.assertIn("禁止出现“客户后续”", messages[0]["content"])
        self.assertIn("禁止出现“我的推断”", messages[0]["content"])
        self.assertIn("禁止出现“我认为”", messages[0]["content"])

    def test_plan_empty_requirement_still_asks_for_missing_info(self) -> None:
        messages = plan._build_messages({"analysis_result": ""})
        self.assertIn("需要补充确认的信息", messages[-1]["content"])

    def test_requirement_prompts_use_source_path_then_analysis_result(self) -> None:
        analysis_messages = analysis._build_messages({
            "file_name": "需求截图.png",
            "source_text": "不应该传给 cursor_cli 的抽取正文",
            "source_path": "/data/projects/p-001/01-requirement/uploads/需求截图.png",
        })
        plan_messages = plan._build_messages({
            "source_text": "不应该作为方案生成依据的原始正文",
            "analysis_result": "# 需求解析结果\n客户希望做图片中的拉伸模拟。",
            "source_path": "/data/projects/p-001/01-requirement/uploads/需求截图.png",
        })

        self.assertIn("原始文件路径", analysis_messages[-1]["content"])
        self.assertIn("/data/projects/p-001/01-requirement/uploads/需求截图.png", analysis_messages[-1]["content"])
        self.assertIn("读取原始文件", analysis_messages[-1]["content"])
        self.assertIn("图片", analysis_messages[-1]["content"])
        self.assertNotIn("不应该传给 cursor_cli 的抽取正文", analysis_messages[-1]["content"])
        self.assertIn("需求解析结果", plan_messages[-1]["content"])
        self.assertIn("客户希望做图片中的拉伸模拟", plan_messages[-1]["content"])
        self.assertNotIn("不应该作为方案生成依据的原始正文", plan_messages[-1]["content"])

    def test_optimize_prompt_revises_existing_plan_not_regenerate(self) -> None:
        messages = plan._build_optimize_messages(
            {
                "source_text": "原始需求文本",
                "current_plan": "# 需求理解\n现有方案正文",
                "note": "客户不想做量化，只做动力学",
            }
        )
        user_content = messages[-1]["content"]
        # 现有方案与客户意见都要进入上下文。
        self.assertIn("现有方案正文", user_content)
        self.assertIn("客户不想做量化，只做动力学", user_content)
        # 明确是“修订”而非“从零重写”，且不要把意见原样抄进正文。
        self.assertIn("在现有方案的基础上做针对性修订", user_content)
        self.assertIn("不要从零重写", user_content)
        self.assertIn("不要把客户意见原样抄进正文", user_content)
        # 仍输出完整文档并遵守硬性排版规则。
        self.assertIn("完整", user_content)
        self.assertIn("硬性排版规则", user_content)
        # 禁止把修订过程/对话性措辞写进正文。
        self.assertIn("不能暴露它是被修改过的", user_content)
        self.assertIn("严禁出现任何过程性", user_content)

    def test_modeling_spec_prompt_demands_structured_json(self) -> None:
        messages = modeling_plan._build_messages({"plan_text": "# 实施方案\n做固液界面模拟"})
        system_content = messages[0]["content"]
        user_content = messages[-1]["content"]
        # 系统提示要求只输出 JSON，并定义 buildingBlocks / targetSystem / interface 字段。
        self.assertIn("只输出一个 JSON 代码块", system_content)
        self.assertIn("buildingBlocks", system_content)
        self.assertIn("targetSystem", system_content)
        self.assertIn("interface", system_content)
        self.assertIn("surface", system_content)
        # JSON 模板里的字段名应是合法可解析的英文键。
        self.assertIn("实施方案", user_content)
        # 确认提示中给出的结构关键字齐全。
        for key in ("name", "code", "formula", "type", "role", "kind", "components", "box"):
            self.assertIn(key, system_content)
        self.assertIn("三字符英文缩写", system_content)
        self.assertIn("禁止使用中文作为残基名", system_content)

    def test_build_molecule_prompt_requires_three_letter_ascii_code(self) -> None:
        messages = build_molecule.build_messages({"plan_text": "环氧树脂", "note": "环氧化蓖麻油"})
        combined = "\n".join(message["content"] for message in messages)
        self.assertIn("名称：<三字符英文缩写>", combined)
        self.assertIn("禁止输出中文名称", combined)
        self.assertIn("PDB 残基名", combined)

    def test_analysis_prompt_requires_all_sections(self) -> None:
        messages = analysis._build_messages({"file_name": "a.pdf", "source_path": "/tmp/a.pdf"})
        user_content = messages[-1]["content"]
        for section in [
            "# 需求解析结果",
            "# 目标与背景",
            "# 关键约束",
            "# 交付物识别",
            "# 风险与待确认问题",
        ]:
            self.assertIn(section, user_content)

    def test_computation_refine_prompt_includes_agent_skill_catalog(self) -> None:
        messages = computation._refine_messages(
            {
                "plan_text": "聚合物体系需要 GROMACS 平衡",
                "system_summary": "聚合物体系，约 5 万原子",
                "computation_spec": {
                    "workflowSteps": [
                        {"id": "step-1", "name": "聚合物平衡", "phase": "equilibration"}
                    ]
                },
            }
        )
        user_content = messages[-1]["content"]
        self.assertIn("可用项目 Skills", user_content)
        self.assertIn("polymer-21step-equilibration", user_content)
        self.assertIn("build_amorphous", user_content)
        self.assertIn("generate_21_mdp.py", user_content)
        self.assertIn("usedSkills", messages[0]["content"])

    def test_computation_prompts_default_to_gas_charges(self) -> None:
        extract_messages = computation._extract_messages({"plan_text": "GAFF 参数化"})
        refine_messages = computation._refine_messages(
            {
                "plan_text": "GAFF 参数化",
                "system_summary": "三种小分子",
                "computation_spec": {"workflowSteps": [{"id": "step-1", "name": "参数化"}]},
            }
        )
        combined = "\n".join(message["content"] for message in extract_messages + refine_messages)
        self.assertIn("gas 电荷", combined)
        self.assertIn("antechamber -c gas", combined)
        self.assertIn("不要默认写 AM1-BCC", combined)


if __name__ == "__main__":
    unittest.main()
