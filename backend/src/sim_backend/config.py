"""运行期配置。

通过环境变量驱动，便于在不同部署环境覆盖。模块内的属性会被其它模块在
调用时动态读取（而非导入即拷贝），因此测试可以直接 patch 这里的属性，
例如 ``sim_backend.config.DB_FILE``。
"""

import os
from pathlib import Path


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))

# backend/ 目录（sim_backend 的上两级）
_BACKEND_DIR = Path(__file__).resolve().parents[2]

DB_FILE = Path(
    os.environ.get(
        "PROJECTS_DB_FILE",
        str(_BACKEND_DIR / "data" / "projects.db"),
    )
)
LEGACY_DATA_FILE = Path(
    os.environ.get(
        "PROJECTS_DATA_FILE",
        str(_BACKEND_DIR / "data" / "projects.json"),
    )
)

# OpenAI 兼容 chat completions 配置。请勿提交真实密钥，优先用环境变量注入。
LLM_API_BASE_URL = os.environ.get("LLM_API_BASE_URL", "").strip()
LLM_API_KEY = os.environ.get("LLM_API_KEY", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "").strip()
LLM_TIMEOUT_SECONDS = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

# Cursor CLI（cursor-agent）配置。用于把部分技能（默认：方案生成/优化）改为
# 通过本机已登录的 Cursor CLI 执行，而非直连 OpenAI 兼容接口。
# CURSOR_CLI_MODEL 默认 gpt-5.5-medium；可通过环境变量改成其它模型（cursor-agent models 查看）。
# 留空则回退到账号默认模型。
CURSOR_CLI_COMMAND = os.environ.get("CURSOR_CLI_COMMAND", "cursor-agent").strip() or "cursor-agent"
CURSOR_CLI_MODEL = os.environ.get("CURSOR_CLI_MODEL", "gpt-5.5-medium").strip()
CURSOR_CLI_TIMEOUT_SECONDS = int(os.environ.get("CURSOR_CLI_TIMEOUT_SECONDS", "360"))
CURSOR_LOCAL_RUN_TIMEOUT_SECONDS = int(os.environ.get("CURSOR_LOCAL_RUN_TIMEOUT_SECONDS", "600"))
CURSOR_CLI_MODE = os.environ.get("CURSOR_CLI_MODE", "ask").strip() or "ask"
CURSOR_CLI_WORKSPACE = os.environ.get("CURSOR_CLI_WORKSPACE", "").strip()
CURSOR_CLI_FORCE = os.environ.get("CURSOR_CLI_FORCE", "").strip().lower() in {"1", "true", "yes", "on"}


def get_llm_settings() -> dict:
    """返回当前 LLM 配置快照，调用时动态读取模块属性。"""
    return {
        "api_base_url": str(LLM_API_BASE_URL).strip(),
        "api_key": str(LLM_API_KEY).strip(),
        "model": str(LLM_MODEL).strip(),
        "timeout_seconds": int(LLM_TIMEOUT_SECONDS),
        "temperature": float(LLM_TEMPERATURE),
    }


def get_cli_settings() -> dict:
    """返回当前 Cursor CLI 配置快照。"""
    return {
        "command": str(CURSOR_CLI_COMMAND).strip() or "cursor-agent",
        "model": str(CURSOR_CLI_MODEL).strip(),
        "timeout_seconds": int(CURSOR_CLI_TIMEOUT_SECONDS),
        "mode": str(CURSOR_CLI_MODE).strip() or "ask",
        "workspace": str(CURSOR_CLI_WORKSPACE).strip(),
        "force": bool(CURSOR_CLI_FORCE),
    }


def get_local_run_cli_settings() -> dict:
    """返回允许真实运行本地模拟步骤的 Cursor CLI 配置。"""
    return {
        **get_cli_settings(),
        "timeout_seconds": max(int(CURSOR_CLI_TIMEOUT_SECONDS), int(CURSOR_LOCAL_RUN_TIMEOUT_SECONDS)),
    }
