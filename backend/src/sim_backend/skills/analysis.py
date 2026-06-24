"""需求解析技能。"""

from .base import load_skill_definition


def _normalize_context(context: dict) -> dict:
    file_name = str(context.get("file_name", ""))
    source_text = str(context.get("source_text", ""))
    return {
        **context,
        "file_name": file_name,
        "source_text_or_empty": source_text.strip()
        or "文档没有抽取到可读文本。请在“风险与待确认问题”中说明，并基于文件名给出需要向客户澄清的问题清单。",
    }


analyze_requirement = load_skill_definition("analyze_requirement", _normalize_context)
_build_messages = analyze_requirement.build_messages
