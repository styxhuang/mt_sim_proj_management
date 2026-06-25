"""技能注册表与执行入口。

所有大模型用法都以 Skill 形式注册在 ``SKILLS`` 中，通过 :func:`run_skill`
（一次性）或 :func:`stream_skill`（流式）统一执行。
"""

from .. import config
from ..llm import cli_client, client
from . import base as skill_base
from .analysis import analyze_requirement
from .base import Skill
from .computation import extract_computation_spec, plan_computation, refine_computation_spec
from .modeling import build_molecule
from .modeling_plan import extract_modeling_spec
from .plan import generate_plan, optimize_plan


_ADAPTED_SKILLS: dict[str, Skill] = {
    skill.id: skill
    for skill in (
        analyze_requirement,
        generate_plan,
        optimize_plan,
        extract_modeling_spec,
        build_molecule,
        extract_computation_spec,
        refine_computation_spec,
        plan_computation,
    )
}


def discover_resource_skills(exclude: set[str] | None = None) -> dict[str, Skill]:
    """发现纯文件定义的 skill，供后续扩展无需改 Python 注册表。"""
    excluded = exclude or set()
    if not skill_base.SKILL_ROOT.exists():
        return {}
    discovered: dict[str, Skill] = {}
    for skill_dir in sorted(skill_base.SKILL_ROOT.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue
        if skill_dir.name in excluded:
            continue
        try:
            skill = skill_base.load_skill_definition(skill_dir.name)
        except ValueError:
            # Agent/script 型 skill 可以共存在 backend/skills 下，但不会注册为一次性 LLM 调用。
            continue
        discovered[skill.id] = skill
    return discovered


SKILLS: dict[str, Skill] = {
    **_ADAPTED_SKILLS,
    **discover_resource_skills(exclude=set(_ADAPTED_SKILLS)),
}

# provider 标识 → 执行模块。各模块需提供统一接口：call / stream /
# consume_last_reasoning。
PROVIDERS = {
    "http": client,
    "cursor_cli": cli_client,
}

# 前端可选模型 → (provider 标识, 具体模型名)。model 为空表示用该 provider 的
# 配置默认值（HTTP 默认即 DeepSeek）。
MODEL_CHOICES: dict[str, tuple[str, str]] = {
    "gpt-5.5-medium-fast": ("cursor_cli", "gpt-5.5-medium-fast"),
    "deepseek": ("http", ""),
}


def get_skill(skill_id: str) -> Skill:
    if skill_id not in SKILLS:
        raise KeyError(f"unknown skill: {skill_id}")
    return SKILLS[skill_id]


def _provider_settings(provider_id: str, model: str, context: dict | None = None) -> dict | None:
    if provider_id == "http":
        settings = config.get_llm_settings()
    else:
        settings = config.get_cli_settings()
        overrides = (context or {}).get("_cli_settings") or {}
        if isinstance(overrides, dict):
            settings = {**settings, **overrides}
    if model:
        settings = {**settings, "model": model}
    return settings


def _resolve_execution(skill: Skill, model_choice: str | None, context: dict | None = None):
    """根据用户所选模型解析出 (执行模块, 设置覆盖)。

    传入已知的 model_choice 时，整条流程都改用该 provider/model；否则回退到技能
    自身声明的默认 provider。
    """
    if model_choice and model_choice in MODEL_CHOICES:
        provider_id, model = MODEL_CHOICES[model_choice]
    else:
        provider_id, model = skill.provider, ""
    module = PROVIDERS.get(provider_id)
    if module is None:
        raise KeyError(f"unknown provider: {provider_id}")
    return module, _provider_settings(provider_id, model, context)


def run_skill(skill_id: str, context: dict, model_choice: str | None = None) -> dict:
    """一次性执行技能，返回 ``{"content", "reasoning"}``。"""
    skill = get_skill(skill_id)
    module, settings = _resolve_execution(skill, model_choice, context)
    messages = skill.build_messages(context)
    content = module.call(messages, settings)
    reasoning = module.consume_last_reasoning()
    return {"content": content, "reasoning": reasoning}


def stream_skill(skill_id: str, context: dict, model_choice: str | None = None):
    """流式执行技能，逐块产出 ``{"type", "text"}`` 增量。"""
    skill = get_skill(skill_id)
    module, settings = _resolve_execution(skill, model_choice, context)
    messages = skill.build_messages(context)
    yield from module.stream(messages, settings)


def consume_last_reasoning(skill_id: str, model_choice: str | None = None) -> str:
    """取出指定技能所用执行后端最近一次的推理链路。"""
    module, _ = _resolve_execution(get_skill(skill_id), model_choice)
    return module.consume_last_reasoning()


__all__ = [
    "Skill",
    "SKILLS",
    "PROVIDERS",
    "MODEL_CHOICES",
    "get_skill",
    "discover_resource_skills",
    "run_skill",
    "stream_skill",
    "consume_last_reasoning",
]
