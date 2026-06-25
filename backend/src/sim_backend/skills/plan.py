"""实施方案生成与优化技能。"""

from .base import load_skill_definition


def _normalize_generate_context(context: dict) -> dict:
    analysis_result = str(context.get("analysis_result", ""))
    source_path = str(context.get("source_path", "")).strip()
    note = str(context.get("note", "")).strip()
    return {
        **context,
        "user_instruction": note or "请基于以下需求解析结果生成一份可直接用于客户沟通与执行的初版实施方案。",
        "source_path_or_empty": source_path or "（未保存原始文件路径）",
        "analysis_result_or_empty": analysis_result.strip()
        or "需求解析结果为空。请在“需要补充确认的信息”中列出关键缺口，并给出一个基于常见假设的方案框架。",
    }


def _normalize_optimize_context(context: dict) -> dict:
    current_plan = str(context.get("current_plan", "")).strip()
    source_text = str(context.get("source_text", "")).strip()
    source_path = str(context.get("source_path", "")).strip()
    note = str(context.get("note", "")).strip() or "请进一步完善方案。"
    return {
        **context,
        "note": note,
        "current_plan_or_empty": current_plan or "（暂无现有方案，请基于需求生成初版。）",
        "source_path_or_empty": source_path or "（无）",
        "source_text_or_empty": source_text or "（无）",
    }


generate_plan = load_skill_definition("generate_plan", _normalize_generate_context)
optimize_plan = load_skill_definition("optimize_plan", _normalize_optimize_context)
_build_messages = generate_plan.build_messages
_build_optimize_messages = optimize_plan.build_messages
