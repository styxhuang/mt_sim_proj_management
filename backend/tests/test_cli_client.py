import json
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend.llm import cli_client, client  # noqa: E402
from sim_backend import skills  # noqa: E402
from sim_backend.skills import generate_plan, optimize_plan, analyze_requirement  # noqa: E402


def _line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


class FakeProc:
    def __init__(self, stdout_lines, returncode=0, stderr=""):
        self.stdout = iter(stdout_lines)
        self._stderr_text = stderr
        self.stderr = self
        self.returncode = returncode

    # stderr.read()
    def read(self):
        return self._stderr_text

    def close(self):
        pass

    def wait(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class ParseCliStreamTests(unittest.TestCase):
    def test_only_timestamped_assistant_deltas_become_increments(self) -> None:
        lines = [
            _line({"type": "system", "subtype": "init"}),
            _line({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "x"}]}}),
            _line({"type": "assistant", "timestamp_ms": 1, "message": {"content": [{"type": "thinking", "text": "先想想"}]}}),
            _line({"type": "assistant", "timestamp_ms": 2, "message": {"content": [{"type": "text", "text": "# 方案"}]}}),
            _line({"type": "assistant", "timestamp_ms": 3, "message": {"content": [{"type": "text", "text": "正文"}]}}),
            # 最终汇总：无 timestamp_ms，应忽略，避免重复完整文本
            _line({"type": "assistant", "message": {"content": [{"type": "text", "text": "# 方案正文"}]}}),
            _line({"type": "result", "subtype": "success", "result": "# 方案正文"}),
        ]
        deltas = list(cli_client.parse_cli_stream(lines))
        self.assertEqual(
            deltas,
            [
                {"type": "reasoning", "text": "先想想"},
                {"type": "content", "text": "# 方案"},
                {"type": "content", "text": "正文"},
            ],
        )

    def test_messages_to_prompt_joins_system_then_user(self) -> None:
        prompt = cli_client._messages_to_prompt(
            [
                {"role": "system", "content": "你是专家"},
                {"role": "user", "content": "生成方案"},
            ]
        )
        self.assertIn("你是专家", prompt)
        self.assertIn("生成方案", prompt)
        self.assertLess(prompt.index("你是专家"), prompt.index("生成方案"))


class CliStreamSubprocessTests(unittest.TestCase):
    def test_stream_yields_deltas_and_records_reasoning(self) -> None:
        lines = [
            _line({"type": "assistant", "timestamp_ms": 1, "message": {"content": [{"type": "thinking", "text": "推理"}]}}),
            _line({"type": "assistant", "timestamp_ms": 2, "message": {"content": [{"type": "text", "text": "方案"}]}}),
            _line({"type": "result", "subtype": "success", "result": "方案"}),
        ]
        with patch.object(cli_client.subprocess, "Popen", return_value=FakeProc(lines)):
            deltas = list(cli_client.stream([{"role": "user", "content": "hi"}]))

        self.assertIn({"type": "reasoning", "text": "推理"}, deltas)
        self.assertIn({"type": "content", "text": "方案"}, deltas)
        self.assertEqual(cli_client.consume_last_reasoning(), "推理")
        self.assertEqual(cli_client.consume_last_reasoning(), "")

    def test_call_joins_content_only(self) -> None:
        lines = [
            _line({"type": "assistant", "timestamp_ms": 1, "message": {"content": [{"type": "thinking", "text": "推理"}]}}),
            _line({"type": "assistant", "timestamp_ms": 2, "message": {"content": [{"type": "text", "text": "# 方案\n"}]}}),
            _line({"type": "assistant", "timestamp_ms": 3, "message": {"content": [{"type": "text", "text": "正文"}]}}),
            _line({"type": "result", "subtype": "success", "result": "# 方案\n正文"}),
        ]
        with patch.object(cli_client.subprocess, "Popen", return_value=FakeProc(lines)):
            text = cli_client.call([{"role": "user", "content": "hi"}])
        self.assertEqual(text, "# 方案\n正文")

    def test_nonzero_exit_raises(self) -> None:
        with patch.object(cli_client.subprocess, "Popen", return_value=FakeProc([], returncode=1, stderr="boom")):
            with self.assertRaises(ValueError):
                list(cli_client.stream([{"role": "user", "content": "hi"}]))


class ProviderRoutingTests(unittest.TestCase):
    def test_plan_skills_use_cursor_cli_provider(self) -> None:
        self.assertEqual(generate_plan.provider, "cursor_cli")
        self.assertEqual(optimize_plan.provider, "cursor_cli")
        self.assertEqual(analyze_requirement.provider, "http")

    def test_run_skill_routes_plan_to_cli_and_analysis_to_http(self) -> None:
        with patch.object(cli_client, "call", return_value="方案内容") as cli_call, \
                patch.object(cli_client, "consume_last_reasoning", return_value=""), \
                patch.object(client, "call_llm") as http_call:
            result = skills.run_skill("generate_plan", {"source_text": "做扩散"})
        self.assertEqual(result["content"], "方案内容")
        self.assertEqual(cli_call.call_count, 1)
        self.assertEqual(http_call.call_count, 0)

        with patch.object(client, "call", return_value="解析内容") as http_call, \
                patch.object(client, "consume_last_reasoning", return_value=""), \
                patch.object(cli_client, "call") as cli_call:
            result = skills.run_skill("analyze_requirement", {"file_name": "a.pdf", "source_text": "x"})
        self.assertEqual(result["content"], "解析内容")
        self.assertEqual(http_call.call_count, 1)
        self.assertEqual(cli_call.call_count, 0)

    def test_model_choice_overrides_provider_and_model(self) -> None:
        # 选 deepseek：方案技能改走 HTTP。
        with patch.object(client, "call", return_value="HTTP方案") as http_call, \
                patch.object(client, "consume_last_reasoning", return_value=""), \
                patch.object(cli_client, "call") as cli_call:
            result = skills.run_skill("generate_plan", {"source_text": "x"}, "deepseek")
        self.assertEqual(result["content"], "HTTP方案")
        self.assertEqual(http_call.call_count, 1)
        self.assertEqual(cli_call.call_count, 0)

        # 选 gpt-5.5-medium-fast：解析技能改走 CLI，且把模型名透传到 settings。
        with patch.object(cli_client, "call", return_value="CLI解析") as cli_call, \
                patch.object(cli_client, "consume_last_reasoning", return_value=""), \
                patch.object(client, "call") as http_call:
            result = skills.run_skill(
                "analyze_requirement", {"file_name": "a.pdf", "source_text": "x"}, "gpt-5.5-medium-fast"
            )
        self.assertEqual(result["content"], "CLI解析")
        self.assertEqual(cli_call.call_count, 1)
        self.assertEqual(http_call.call_count, 0)
        settings = cli_call.call_args[0][1]
        self.assertEqual(settings["model"], "gpt-5.5-medium-fast")


if __name__ == "__main__":
    unittest.main()
