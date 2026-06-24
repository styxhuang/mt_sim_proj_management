from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable


@dataclass(frozen=True)
class Skill:
    id: str
    title: str
    build_messages: Callable[[dict], list[dict]]
    # 执行后端：``http`` 直连 OpenAI 兼容接口；``cursor_cli`` 走本机 Cursor CLI。
    provider: str = "http"
    description: str = ""
    source_path: Path | None = None


SKILL_ROOT = Path(__file__).resolve().parents[3] / "skills"
_TEMPLATE_TOKEN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw_header = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    metadata: dict[str, str] = {}
    for line in raw_header.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, body


def _section(body: str, title: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(title)}\s*$", re.MULTILINE)
    match = pattern.search(body)
    if not match:
        return ""
    next_heading = re.search(r"^##\s+", body[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(body)
    return body[match.end() : end].strip()


def _render_template(template: str, context: dict) -> str:
    def replace(match: re.Match) -> str:
        return str(context.get(match.group(1), ""))

    return _TEMPLATE_TOKEN.sub(replace, template).strip()


def load_skill_definition(
    skill_id: str,
    context_adapter: Callable[[dict], dict] | None = None,
) -> Skill:
    """从 ``backend/skills/<skill_id>/SKILL.md`` 加载项目 LLM skill。"""
    source_path = SKILL_ROOT / skill_id / "SKILL.md"
    text = source_path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(text)
    system_template = _section(body, "System Prompt")
    user_template = _section(body, "User Prompt")
    if not user_template:
        raise ValueError(f"skill {skill_id} missing '## User Prompt' section")

    def build_messages(context: dict) -> list[dict]:
        normalized = context_adapter(context) if context_adapter else dict(context)
        messages: list[dict] = []
        system_content = _render_template(system_template, normalized)
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": _render_template(user_template, normalized)})
        return messages

    return Skill(
        id=metadata.get("name", skill_id),
        title=metadata.get("title", skill_id),
        build_messages=build_messages,
        provider=metadata.get("provider", "http"),
        description=metadata.get("description", ""),
        source_path=source_path,
    )
