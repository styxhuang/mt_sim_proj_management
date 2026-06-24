"""建模规划抽取技能。

从已生成的实施方案中抽取一份结构化「建模规划」，描述需要构建的基本单元
（分子 / 表面·slab / 离子等）以及目标体系（体相 / 界面 / 吸附等），供「项目执行」
阶段预填建模步骤、驱动 Mol* 建模流程。

输出为单个 JSON 代码块，由 :mod:`sim_backend.requirements` 解析后持久化。
"""

from .base import load_skill_definition


def _normalize_context(context: dict) -> dict:
    plan_text = str(context.get("plan_text", "")).strip()
    return {**context, "plan_text_or_empty": plan_text or "（实施方案为空，请输出一个空的合理结构。）"}


extract_modeling_spec = load_skill_definition("extract_modeling_spec", _normalize_context)
_build_messages = extract_modeling_spec.build_messages
