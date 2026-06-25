"""需求解析技能。"""

from .base import load_skill_definition


def _normalize_context(context: dict) -> dict:
    file_name = str(context.get("file_name", ""))
    source_path = str(context.get("source_path", "")).strip()
    return {
        **context,
        "file_name": file_name,
        "source_path_or_empty": source_path or "（未保存原始文件路径）",
    }


analyze_requirement = load_skill_definition("analyze_requirement", _normalize_context)
_build_messages = analyze_requirement.build_messages
