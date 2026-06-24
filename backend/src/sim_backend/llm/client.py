"""OpenAI 兼容 chat completions 客户端，支持一次性与流式两种调用。

流式接口 :func:`stream_chat` 逐块产出增量，用于把模型输出实时推送到前端；
:func:`call_llm` 为一次性便捷封装，返回完整文本，供领域逻辑与单元测试使用。

模型的隐藏推理链路（reasoning_content / reasoning）会被记录到模块级的
``_LAST_LLM_REASONING``，可通过 :func:`consume_last_llm_reasoning` 取出并清空。
"""

import json
import urllib.error
import urllib.request

from .. import config


_LAST_LLM_REASONING = ""


def consume_last_llm_reasoning() -> str:
    global _LAST_LLM_REASONING
    reasoning = _LAST_LLM_REASONING
    _LAST_LLM_REASONING = ""
    return reasoning


def _resolve_settings(settings: dict | None) -> dict:
    active_settings = settings or config.get_llm_settings()
    api_base_url = str(active_settings.get("api_base_url", "")).rstrip("/")
    api_key = str(active_settings.get("api_key", "")).strip()
    model = str(active_settings.get("model", "")).strip()

    if not api_base_url:
        raise ValueError("LLM_API_BASE_URL is required in sim_backend/config.py or environment")
    if not api_key:
        raise ValueError("LLM_API_KEY is required in sim_backend/config.py or environment")
    if not model:
        raise ValueError("LLM_MODEL is required in sim_backend/config.py or environment")

    return {
        "api_base_url": api_base_url,
        "api_key": api_key,
        "model": model,
        "timeout_seconds": int(active_settings.get("timeout_seconds", 60)),
        "temperature": float(active_settings.get("temperature", 0.2)),
    }


def _build_request(resolved: dict, stream: bool) -> urllib.request.Request:
    body = {
        "model": resolved["model"],
        "messages": resolved["messages"],
        "temperature": resolved["temperature"],
    }
    if stream:
        body["stream"] = True
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(
        f"{resolved['api_base_url']}/chat/completions",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {resolved['api_key']}",
            "Content-Type": "application/json",
        },
    )


def call_llm(messages: list[dict], settings: dict | None = None) -> str:
    """一次性调用，返回完整文本。同时记录隐藏推理链路。"""
    resolved = {**_resolve_settings(settings), "messages": messages}
    request = _build_request(resolved, stream=False)

    try:
        with urllib.request.urlopen(request, timeout=resolved["timeout_seconds"]) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ValueError(f"LLM request failed: HTTP {error.code} {detail}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"LLM request failed: {error.reason}") from error

    global _LAST_LLM_REASONING
    try:
        message = payload["choices"][0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("LLM response missing choices[0].message.content") from error

    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    _LAST_LLM_REASONING = str(reasoning).strip()

    return str(content).strip()


def _iter_sse_lines(response):
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        yield line[len("data:"):].strip()


def stream_chat(messages: list[dict], settings: dict | None = None):
    """流式调用，逐块产出增量。

    产出形如 ``{"type": "reasoning"|"content", "text": "..."}`` 的增量字典。
    结束时把完整推理链路写入 ``_LAST_LLM_REASONING``。
    """
    resolved = {**_resolve_settings(settings), "messages": messages}
    request = _build_request(resolved, stream=True)

    reasoning_parts: list[str] = []
    try:
        with urllib.request.urlopen(request, timeout=resolved["timeout_seconds"]) as response:
            for data in _iter_sse_lines(response):
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                reasoning_delta = delta.get("reasoning_content") or delta.get("reasoning")
                if reasoning_delta:
                    reasoning_parts.append(reasoning_delta)
                    yield {"type": "reasoning", "text": reasoning_delta}
                content_delta = delta.get("content")
                if content_delta:
                    yield {"type": "content", "text": content_delta}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise ValueError(f"LLM request failed: HTTP {error.code} {detail}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"LLM request failed: {error.reason}") from error

    global _LAST_LLM_REASONING
    _LAST_LLM_REASONING = "".join(reasoning_parts).strip()


# --- 与 cli_client 对齐的统一接口（供 skills 分发层调用） ----------------------

def consume_last_reasoning() -> str:
    return consume_last_llm_reasoning()


def call(messages: list[dict], settings: dict | None = None) -> str:
    return call_llm(messages, settings)


def stream(messages: list[dict], settings: dict | None = None):
    return stream_chat(messages, settings)
