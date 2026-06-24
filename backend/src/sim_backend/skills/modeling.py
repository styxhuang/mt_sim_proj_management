"""分子建模技能。

``build_molecule``：逐个确定体系中每种组分的化学结构（优先 SMILES，由 RDKit 生成
3D 坐标），形成"分子库"。体系组装不再依赖大模型生成坐标，而是由
:mod:`sim_backend.executions` 复用单体做确定性随机填充，避免几何错误。

通过 Cursor CLI（ask 模式）执行。
"""

from .base import load_skill_definition


def _normalize_context(context: dict) -> dict:
    plan_text = str(context.get("plan_text", "")).strip()
    note = str(context.get("note", "")).strip() or "请构建体系中的一个关键分子。"
    return {
        **context,
        "note_or_default": note,
        "plan_text_or_empty": plan_text or "（暂无实施方案文本，请基于分子描述做合理假设。）",
    }


build_molecule = load_skill_definition("build_molecule", _normalize_context)
_molecule_messages = build_molecule.build_messages
