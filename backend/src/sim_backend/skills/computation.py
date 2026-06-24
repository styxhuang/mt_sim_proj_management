"""模拟计算技能。

- ``extract_computation_spec``：从实施方案抽取项目专属计算流程 JSON（方案完成后后台调用）。
- ``refine_computation_spec``：体系组装完成后，在已有 spec 基础上结合真实体系规模微调参数。
"""

import json

from . import base as skill_base
from .base import load_skill_definition


def _project_skill_catalog() -> str:
    """列出可供模拟计算阶段引用的 Agent/脚本型项目 skill。"""
    root = skill_base.SKILL_ROOT
    if not root.exists():
        return "（暂无可用项目 Skill。）"
    entries: list[str] = []
    for skill_dir in sorted(root.iterdir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_dir.is_dir() or not skill_file.exists():
            continue
        text = skill_file.read_text(encoding="utf-8")
        if "## User Prompt" in text:
            continue
        metadata, _body = skill_base._parse_frontmatter(text)
        name = metadata.get("name", skill_dir.name)
        description = metadata.get("description", "").strip() or "无描述"
        scripts = sorted((skill_dir / "scripts").glob("*")) if (skill_dir / "scripts").exists() else []
        script_lines = [
            f"  - 脚本：{script.relative_to(root.parent)}"
            for script in scripts
            if script.is_file()
        ]
        reference = skill_dir / "reference.md"
        reference_line = (
            f"  - 参考：{reference.relative_to(root.parent)}"
            if reference.exists()
            else ""
        )
        detail_lines = [line for line in [reference_line, *script_lines] if line]
        detail = "\n" + "\n".join(detail_lines) if detail_lines else ""
        entries.append(f"- {name}: {description}{detail}")
    return "\n".join(entries) if entries else "（暂无可用项目 Skill。）"


def _normalize_extract_context(context: dict) -> dict:
    plan_text = str(context.get("plan_text", "")).strip()
    return {
        **context,
        "plan_text_or_empty": plan_text or "（实施方案为空。）",
        "project_skill_catalog": _project_skill_catalog(),
    }


def _normalize_refine_context(context: dict) -> dict:
    plan_text = str(context.get("plan_text", "")).strip()
    system_summary = str(context.get("system_summary", "")).strip() or "（未提供体系摘要）"
    model_input = context.get("model_input") or {}
    spec_json = json.dumps(context.get("computation_spec") or {}, ensure_ascii=False, indent=2)
    return {
        **context,
        "plan_text_or_empty": plan_text or "（无）",
        "system_summary_or_empty": system_summary,
        "model_input_json": json.dumps(model_input, ensure_ascii=False, indent=2),
        "computation_spec_json": spec_json,
        "project_skill_catalog": _project_skill_catalog(),
    }


extract_computation_spec = load_skill_definition(
    "extract_computation_spec", _normalize_extract_context
)

refine_computation_spec = load_skill_definition(
    "refine_computation_spec", _normalize_refine_context
)

# 兼容旧测试/引用
plan_computation = refine_computation_spec
_extract_messages = extract_computation_spec.build_messages
_refine_messages = refine_computation_spec.build_messages
