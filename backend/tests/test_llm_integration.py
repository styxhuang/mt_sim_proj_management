import json
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from sim_backend.llm import client  # noqa: E402


class LlmIntegrationTests(unittest.TestCase):
    def test_call_llm_posts_openai_compatible_chat_completion_request(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {"choices": [{"message": {"content": "# 真实模型输出"}}]},
                    ensure_ascii=False,
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        settings = {
            "api_base_url": "https://example.test/v1",
            "api_key": "test-key",
            "model": "deepseek-chat",
            "timeout_seconds": 12,
            "temperature": 0.1,
        }

        with patch.object(client.urllib.request, "urlopen", fake_urlopen):
            content = client.call_llm(
                [{"role": "user", "content": "生成方案"}],
                settings=settings,
            )

        self.assertEqual(content, "# 真实模型输出")
        self.assertEqual(captured["url"], "https://example.test/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(captured["payload"]["model"], "deepseek-chat")
        self.assertEqual(captured["payload"]["messages"][0]["content"], "生成方案")
        self.assertEqual(captured["payload"]["temperature"], 0.1)
        self.assertEqual(captured["timeout"], 12)

    def test_stream_chat_parses_sse_content_and_reasoning_deltas(self) -> None:
        sse_lines = [
            'data: {"choices": [{"delta": {"reasoning_content": "先想一想。"}}]}\n'.encode("utf-8"),
            'data: {"choices": [{"delta": {"content": "# 方案"}}]}\n'.encode("utf-8"),
            'data: {"choices": [{"delta": {"content": "\\n正文"}}]}\n'.encode("utf-8"),
            b"data: [DONE]\n",
        ]

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                return iter(sse_lines)

        captured = {}

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        settings = {
            "api_base_url": "https://example.test/v1",
            "api_key": "test-key",
            "model": "deepseek-reasoner",
            "timeout_seconds": 30,
            "temperature": 0.2,
        }

        with patch.object(client.urllib.request, "urlopen", fake_urlopen):
            deltas = list(client.stream_chat([{"role": "user", "content": "生成方案"}], settings=settings))

        self.assertTrue(captured["payload"]["stream"])
        self.assertIn({"type": "reasoning", "text": "先想一想。"}, deltas)
        self.assertIn({"type": "content", "text": "# 方案"}, deltas)
        self.assertIn({"type": "content", "text": "\n正文"}, deltas)
        self.assertEqual(client.consume_last_llm_reasoning(), "先想一想。")

    def test_call_llm_requires_api_key_and_model_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "LLM_API_KEY"):
            client.call_llm(
                [{"role": "user", "content": "生成方案"}],
                settings={
                    "api_base_url": "https://example.test/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                    "timeout_seconds": 30,
                    "temperature": 0.2,
                },
            )


if __name__ == "__main__":
    unittest.main()
