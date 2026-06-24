"""通过 Cursor CLI（``cursor-agent``）执行大模型调用。

把 messages 拼成单条 prompt，调用
``cursor-agent -p --output-format stream-json --stream-partial-output`` 并解析逐
token 的 JSON 事件，产出与 :mod:`sim_backend.llm.client` 完全一致的
``{"type": "content"|"reasoning", "text": ...}`` 增量，从而无缝接入既有的流式
编排（``stream_skill`` → SSE → 前端），下游无需改动。

默认安全策略：在独立临时目录中以 ``--mode ask``（只读问答）运行，并通过
``--trust`` 跳过工作区信任提示，避免普通技能读写真实仓库或执行命令。
需要真实执行的调用可显式传入 ``mode="agent"``、``workspace`` 和 ``force``。
"""

import json
import os
import signal
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from .. import config


# 与 client._LAST_LLM_REASONING 对应，记录最近一次的隐藏推理链路。
_LAST_REASONING = ""


def consume_last_reasoning() -> str:
    """取出并清空最近一次调用产生的推理链路。"""
    global _LAST_REASONING
    reasoning = _LAST_REASONING
    _LAST_REASONING = ""
    return reasoning


def _messages_to_prompt(messages: list[dict]) -> str:
    """把 chat messages 合并为单条 prompt（system 在前，作为指令）。"""
    parts: list[str] = []
    for message in messages:
        content = str(message.get("content", "")).strip()
        if content:
            parts.append(content)
    return "\n\n".join(parts).strip()


def parse_cli_stream(lines):
    """解析 cursor-agent ``stream-json`` 输出行，逐块产出 ``{"type", "text"}``。

    规则：
    - 只有带 ``timestamp_ms`` 的 ``assistant`` 事件才是增量；最终汇总（无
      ``timestamp_ms``）与 ``result`` 事件会重复完整文本，需忽略以免重复。
    - content 文本 → ``content``；thinking 文本 → ``reasoning``。
    """
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "assistant" or "timestamp_ms" not in event:
            continue
        message = event.get("message") or {}
        for part in message.get("content") or []:
            text = part.get("text")
            if not text:
                continue
            if part.get("type") == "thinking":
                yield {"type": "reasoning", "text": text}
            else:
                yield {"type": "content", "text": text}


def _resolve_settings(settings: dict | None) -> dict:
    active = settings or config.get_cli_settings()
    command = str(active.get("command", "cursor-agent")).strip() or "cursor-agent"
    mode = str(active.get("mode", "ask")).strip() or "ask"
    workspace = str(active.get("workspace", "")).strip()
    return {
        "command": command,
        "model": str(active.get("model", "")).strip(),
        "timeout_seconds": int(active.get("timeout_seconds", 180)),
        "mode": mode,
        "workspace": workspace,
        "force": bool(active.get("force", False)),
    }


def _build_command(resolved: dict, workspace: str) -> list[str]:
    command = [
        resolved["command"],
        "-p",
        "--output-format", "stream-json",
        "--stream-partial-output",
        "--trust",
        "--workspace", workspace,
    ]
    mode = str(resolved.get("mode", "ask")).strip()
    if mode in {"ask", "plan"}:
        command += ["--mode", mode]
    if resolved.get("force"):
        command.append("--force")
    if resolved["model"]:
        command += ["--model", resolved["model"]]
    return command


def stream(messages: list[dict], settings: dict | None = None):
    """流式调用 CLI，逐块产出增量；结束时把推理链路写入 ``_LAST_REASONING``。"""
    resolved = _resolve_settings(settings)
    prompt = _messages_to_prompt(messages)
    temp_workspace = ""
    workspace = resolved.get("workspace") or ""
    if workspace:
        workspace = str(Path(workspace).expanduser())
    else:
        temp_workspace = tempfile.mkdtemp(prefix="sim_cli_")
        workspace = temp_workspace
    command = _build_command(resolved, workspace) + [prompt]

    reasoning_parts: list[str] = []
    timed_out = {"value": False}
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    def kill_process_group() -> None:
        timed_out["value"] = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    killer = threading.Timer(resolved["timeout_seconds"], kill_process_group)
    killer.start()
    try:
        for delta in parse_cli_stream(proc.stdout):
            if delta["type"] == "reasoning":
                reasoning_parts.append(delta["text"])
            yield delta
        proc.wait()
        if proc.returncode:
            detail = (proc.stderr.read() or "").strip() if proc.stderr else ""
            timeout_note = "；调用超时，已终止 cursor-agent 进程组" if timed_out["value"] else ""
            raise ValueError(
                f"cursor-agent 调用失败（exit {proc.returncode}）：{detail or '无错误输出'}{timeout_note}"
            )
    finally:
        killer.cancel()
        for pipe in (proc.stdout, proc.stderr):
            try:
                if pipe:
                    pipe.close()
            except Exception:
                pass
        if temp_workspace:
            shutil.rmtree(temp_workspace, ignore_errors=True)

    global _LAST_REASONING
    _LAST_REASONING = "".join(reasoning_parts).strip()


def call(messages: list[dict], settings: dict | None = None) -> str:
    """一次性调用，返回完整文本（内部复用流式实现）。"""
    content_parts = [
        delta["text"]
        for delta in stream(messages, settings)
        if delta["type"] == "content"
    ]
    return "".join(content_parts).strip()
