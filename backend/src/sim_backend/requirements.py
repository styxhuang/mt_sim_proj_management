"""需求解析任务的领域逻辑与编排。

每个大模型动作都通过 :mod:`sim_backend.skills` 执行：
- ``run_next_requirement_step`` / ``add_requirement_chat_message``：一次性执行，返回完整任务。
- ``stream_next_requirement_step`` / ``stream_requirement_chat_message``：流式执行，逐块产出增量供 SSE 推送。
"""

import json
import re
from datetime import datetime

from . import project_files, projects
from .database import (
    deserialize_json,
    get_connection,
    initialize_database,
    serialize_json,
)
from .skills import consume_last_reasoning, run_skill, stream_skill


def current_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def next_requirement_task_id() -> str:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) FROM requirement_tasks").fetchone()
    return f"req-{int(row[0]) + 1:03d}"


def build_requirement_steps() -> list[dict]:
    return [
        {"label": "读取文档", "status": "completed", "detail": "已抽取需求文本"},
        {"label": "解析任务", "status": "pending", "detail": "等待小P解析任务"},
        {"label": "生成方案", "status": "pending", "detail": "等待小P生成 Markdown 实施方案"},
    ]


# --- 文档构造 -------------------------------------------------------------

def _analysis_document(content: str, reasoning: str) -> dict:
    return {
        "currentVersionId": "analysis-v1",
        "content": content,
        "reasoning": reasoning,
        "versions": [
            {
                "id": "analysis-v1",
                "name": "v1 解析结果",
                "content": content,
                "createdAt": current_timestamp(),
                "source": "模型首次解析",
            }
        ],
    }


def _plan_document(content: str, reasoning: str) -> dict:
    return {
        "currentVersionId": "plan-v1",
        "content": content,
        "reasoning": reasoning,
        "versions": [
            {
                "id": "plan-v1",
                "name": "v1 初版",
                "content": content,
                "createdAt": current_timestamp(),
                "source": "模型首次生成",
            }
        ],
    }


def build_analysis_document(file_name: str, source_text: str) -> dict:
    result = run_skill(
        "analyze_requirement",
        {"file_name": file_name, "source_text": source_text},
    )
    return _analysis_document(result["content"], result["reasoning"])


def build_plan_document(source_text: str) -> dict:
    result = run_skill("generate_plan", {"source_text": source_text})
    return _plan_document(result["content"], result["reasoning"])


# --- 持久化 ---------------------------------------------------------------

def save_requirement_task(task: dict) -> None:
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO requirement_tasks (
                id, file_name, file_type, status, source_text, steps,
                conversation, documents, exports, project_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task["id"],
                task["fileName"],
                task["fileType"],
                task["status"],
                task["sourceText"],
                serialize_json(task["steps"]),
                serialize_json(task["conversation"]),
                json.dumps(task["documents"], ensure_ascii=False),
                serialize_json(task.get("exports", [])),
                str(task.get("projectId", "")),
                task["createdAt"],
                task["updatedAt"],
            ),
        )


def database_row_to_requirement_task(row) -> dict:
    documents = json.loads(row["documents"] or "{}")
    return {
        "id": row["id"],
        "fileName": row["file_name"],
        "fileType": row["file_type"],
        "status": row["status"],
        "sourceText": row["source_text"],
        "steps": deserialize_json(row["steps"]),
        "conversation": deserialize_json(row["conversation"]),
        "documents": documents,
        "exports": deserialize_json(row["exports"]),
        "projectId": (row["project_id"] if "project_id" in row.keys() else ""),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def load_requirement_tasks() -> list[dict]:
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM requirement_tasks ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [database_row_to_requirement_task(row) for row in rows]


def find_requirement_task(task_id: str) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM requirement_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    return database_row_to_requirement_task(row) if row else None


def find_requirement_task_by_project(project_id: str) -> dict | None:
    """返回该项目最近创建的需求任务（1:1 关联）。"""
    project_id = str(project_id or "").strip()
    if not project_id:
        return None
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM requirement_tasks WHERE project_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return database_row_to_requirement_task(row) if row else None


def create_requirement_task(payload: dict) -> dict:
    file_name = str(payload.get("fileName", "")).strip()
    if not file_name:
        raise ValueError("fileName is required")
    source_text = str(payload.get("content", "")).strip()
    now = current_timestamp()
    task = {
        "id": next_requirement_task_id(),
        "fileName": file_name,
        "fileType": str(payload.get("fileType", "")).strip() or "application/octet-stream",
        "status": "processing",
        "sourceText": source_text,
        "projectId": str(payload.get("projectId", "")).strip(),
        "steps": build_requirement_steps(),
        "conversation": [
            {"role": "user", "content": f"已上传：{file_name}", "createdAt": now},
            {
                "role": "assistant",
                "content": "已完成读取文档，等待解析任务。",
                "createdAt": now,
            },
        ],
        "documents": {},
        "exports": [],
        "createdAt": now,
        "updatedAt": now,
    }
    save_requirement_task(task)
    return task


# --- 分步执行（解析 / 生成方案） ------------------------------------------

def _plan_next_step(task: dict) -> dict | None:
    documents = task.get("documents", {})
    if "analysis" not in documents:
        return {
            "skill_id": "analyze_requirement",
            "step_index": 1,
            "context": {
                "file_name": task["fileName"],
                "source_text": task["sourceText"],
            },
            "running_detail": "小P 正在识别目标、约束、交付物和风险",
        }
    if "plan" not in documents:
        return {
            "skill_id": "generate_plan",
            "step_index": 2,
            "context": {"source_text": task["sourceText"]},
            "running_detail": "小P 正在生成 Markdown 实施方案",
        }
    return None


def _mark_step_running(task: dict, plan: dict) -> None:
    step = task["steps"][plan["step_index"]]
    step["status"] = "in_progress"
    step["detail"] = plan["running_detail"]
    task["updatedAt"] = current_timestamp()


def _apply_step_result(task: dict, skill_id: str, content: str, reasoning: str) -> None:
    documents = task.setdefault("documents", {})
    steps = task["steps"]
    if skill_id == "analyze_requirement":
        documents["analysis"] = _analysis_document(content, reasoning)
        _write_requirement_documents(task)
        steps[1]["status"] = "completed"
        steps[1]["detail"] = "已识别目标、约束、交付物和风险"
        task["status"] = "processing"
        projects.advance_project_stage(task.get("projectId", ""), "需求解析")
    elif skill_id == "generate_plan":
        documents["plan"] = _plan_document(content, reasoning)
        _write_requirement_documents(task)
        steps[2]["status"] = "completed"
        steps[2]["detail"] = "已生成实施方案"
        task["status"] = "completed"
        projects.advance_project_stage(task.get("projectId", ""), "方案确认")
        _try_extract_specs_after_plan(task)
        task["conversation"].append(
            {
                "role": "assistant",
                "content": "已完成读取文档、解析任务和生成方案。",
                "createdAt": current_timestamp(),
                "usedSkills": [_message_skill(skill_id)],
            }
        )
    task["updatedAt"] = current_timestamp()


def _message_skill(skill_id: str, reason: str = "") -> dict:
    return {"id": skill_id, "name": skill_id, "reason": reason}


def _write_requirement_documents(task: dict) -> None:
    documents = task.get("documents") or {}
    analysis = documents.get("analysis")
    if analysis and analysis.get("content"):
        project_files.write_project_file(
            task,
            ["01-requirement", f"{analysis.get('currentVersionId', 'analysis')}.md"],
            analysis.get("content", ""),
        )
    plan = documents.get("plan")
    if plan and plan.get("content"):
        project_files.write_project_file(
            task,
            ["02-plan", f"{plan.get('currentVersionId', 'plan')}.md"],
            plan.get("content", ""),
        )
    modeling_spec = documents.get("modelingSpec")
    if modeling_spec:
        project_files.write_project_file(
            task,
            ["02-plan", "modeling-spec.json"],
            json.dumps(modeling_spec, ensure_ascii=False, indent=2),
        )
    computation_spec = documents.get("computationSpec")
    if computation_spec:
        project_files.write_project_file(
            task,
            ["02-plan", "computation-spec.json"],
            json.dumps(computation_spec, ensure_ascii=False, indent=2),
        )


def materialize_requirement_files(task_id: str) -> dict:
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    _write_requirement_documents(task)
    return task


def run_next_requirement_step(task_id: str) -> dict:
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    if task["status"] == "completed":
        return task

    plan = _plan_next_step(task)
    if plan is None:
        task["status"] = "completed"
        task["updatedAt"] = current_timestamp()
        save_requirement_task(task)
        return task

    _mark_step_running(task, plan)
    save_requirement_task(task)

    result = run_skill(plan["skill_id"], plan["context"])
    _apply_step_result(task, plan["skill_id"], result["content"], result["reasoning"])
    save_requirement_task(task)
    return task


def stream_next_requirement_step(task_id: str, model_choice: str | None = None):
    """流式执行下一步技能，逐块产出增量字典。

    产出类型：``step``（步骤进入执行中）、``reasoning``/``content``（模型增量）、
    ``done``（完成，附完整 task）。``model_choice`` 指定本次使用的模型。
    """
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    if task["status"] == "completed":
        yield {"type": "done", "task": task}
        return

    plan = _plan_next_step(task)
    if plan is None:
        task["status"] = "completed"
        task["updatedAt"] = current_timestamp()
        save_requirement_task(task)
        yield {"type": "done", "task": task}
        return

    _mark_step_running(task, plan)
    save_requirement_task(task)
    yield {"type": "step", "skill": plan["skill_id"], "task": task}

    content_parts: list[str] = []
    for delta in stream_skill(plan["skill_id"], plan["context"], model_choice):
        if delta.get("type") == "content":
            content_parts.append(delta["text"])
        yield delta

    reasoning = consume_last_reasoning(plan["skill_id"], model_choice)
    content = "".join(content_parts).strip()
    _apply_step_result(task, plan["skill_id"], content, reasoning)
    save_requirement_task(task)
    yield {"type": "done", "task": task}


# --- 二次优化对话 ---------------------------------------------------------

def _current_plan_content(task: dict) -> str:
    """取当前方案文档的最新正文，作为优化的修订基线。"""
    plan = task.get("documents", {}).get("plan", {})
    return str(plan.get("content", "")).strip()


# --- 建模规划抽取 ---------------------------------------------------------

def _parse_spec_json(content: str) -> dict | None:
    """从模型回复中解析建模规划 JSON：优先 ```json 代码块，回退到首个 {...}。"""
    text = str(content or "")
    block = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    candidate = block.group(1) if block else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if not candidate:
        return None
    try:
        spec = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return spec if isinstance(spec, dict) else None


def _normalize_modeling_spec(spec: dict) -> dict:
    """规整建模规划结构，保证前端可安全渲染。"""
    blocks = []
    for item in spec.get("buildingBlocks") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        blocks.append(
            {
                "name": name,
                "smiles": str(item.get("smiles", "")).strip(),
                "formula": str(item.get("formula", "")).strip(),
                "type": str(item.get("type", "molecule")).strip() or "molecule",
                "role": str(item.get("role", "")).strip(),
                "note": str(item.get("note", "")).strip(),
            }
        )
    target = spec.get("targetSystem") if isinstance(spec.get("targetSystem"), dict) else {}
    components = []
    for comp in target.get("components") or []:
        if isinstance(comp, dict) and str(comp.get("block", "")).strip():
            components.append(
                {"block": str(comp.get("block")).strip(), "count": comp.get("count", "")}
            )
    interface = target.get("interface") if isinstance(target.get("interface"), dict) else None
    normalized_interface = None
    if interface:
        normalized_interface = {
            "phaseA": str(interface.get("phaseA", "")).strip(),
            "phaseB": str(interface.get("phaseB", "")).strip(),
            "note": str(interface.get("note", "")).strip(),
        }
    return {
        "buildingBlocks": blocks,
        "targetSystem": {
            "kind": str(target.get("kind", "bulk")).strip() or "bulk",
            "summary": str(target.get("summary", "")).strip(),
            "components": components,
            "box": str(target.get("box", "")).strip(),
            "atomCount": str(target.get("atomCount", "")).strip(),
            "interface": normalized_interface,
        },
    }


def generate_requirement_modeling_spec(task_id: str, model_choice: str | None = None) -> dict:
    """依据当前实施方案抽取建模规划，持久化到 ``documents.modelingSpec`` 并返回任务。"""
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    plan_text = _current_plan_content(task)
    if not plan_text:
        raise ValueError("plan is required before extracting modeling spec")

    result = run_skill("extract_modeling_spec", {"plan_text": plan_text}, model_choice)
    parsed = _parse_spec_json(result["content"]) or {}
    spec = _normalize_modeling_spec(parsed)

    plan_doc = task.get("documents", {}).get("plan", {})
    task.setdefault("documents", {})["modelingSpec"] = {
        **spec,
        "planVersionId": plan_doc.get("currentVersionId", ""),
        "generatedAt": current_timestamp(),
    }
    _write_requirement_documents(task)
    task["updatedAt"] = current_timestamp()
    save_requirement_task(task)
    return task


def ensure_requirement_modeling_spec(task: dict, model_choice: str | None = None) -> dict:
    """若任务缺少与当前方案版本匹配的建模规划，则生成；否则原样返回。"""
    documents = task.get("documents", {})
    plan_doc = documents.get("plan")
    if not plan_doc:
        return task
    spec = documents.get("modelingSpec")
    if spec and spec.get("planVersionId") == plan_doc.get("currentVersionId"):
        return task
    try:
        return generate_requirement_modeling_spec(task["id"], model_choice)
    except (ValueError, KeyError):
        return task


def _normalize_computation_spec(spec: dict) -> dict:
    def normalize_used_skills(raw) -> list[dict]:
        normalized = []
        for item in raw or []:
            if isinstance(item, str):
                skill_id = item.strip()
                if skill_id:
                    normalized.append({"id": skill_id, "name": skill_id, "scripts": [], "reason": ""})
                continue
            if not isinstance(item, dict):
                continue
            skill_id = str(item.get("id", item.get("skill", ""))).strip()
            if not skill_id:
                continue
            scripts = [
                str(script).strip()
                for script in (item.get("scripts") or item.get("scriptPaths") or [])
                if str(script).strip()
            ]
            normalized.append(
                {
                    "id": skill_id,
                    "name": str(item.get("name", skill_id)).strip() or skill_id,
                    "scripts": scripts,
                    "reason": str(item.get("reason", item.get("usage", ""))).strip(),
                }
            )
        return normalized

    steps = []
    for index, item in enumerate(spec.get("workflowSteps") or [], start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        step_id = str(item.get("id", "")).strip() or f"step-{index}"
        steps.append(
            {
                "id": step_id,
                "name": name,
                "phase": str(item.get("phase", "other")).strip() or "other",
                "purpose": str(item.get("purpose", "")).strip(),
                "software": str(item.get("software", "")).strip(),
                "method": str(item.get("method", "")).strip(),
                "parameters": item.get("parameters") if isinstance(item.get("parameters"), dict) else {},
                "expectedInputs": [str(x).strip() for x in (item.get("expectedInputs") or []) if str(x).strip()],
                "expectedOutputs": [str(x).strip() for x in (item.get("expectedOutputs") or []) if str(x).strip()],
                "dependsOn": [str(x).strip() for x in (item.get("dependsOn") or []) if str(x).strip()],
                "status": str(item.get("status", "pending")).strip() or "pending",
                "executionDoc": str(item.get("executionDoc", "")).strip(),
                "usedSkills": normalize_used_skills(item.get("usedSkills")),
            }
        )
    software = [str(x).strip() for x in (spec.get("software") or []) if str(x).strip()]
    analysis_items = [str(x).strip() for x in (spec.get("analysisItems") or []) if str(x).strip()]
    return {
        "calculationType": str(spec.get("calculationType", "")).strip() or "MD",
        "software": software,
        "workflowSteps": steps,
        "analysisItems": analysis_items,
        "note": str(spec.get("note", "")).strip(),
    }


def generate_requirement_computation_spec(task_id: str, model_choice: str | None = None) -> dict:
    """从实施方案抽取计算流程规划，存入 ``documents.computationSpec``。"""
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    plan_text = _current_plan_content(task)
    if not plan_text:
        raise ValueError("plan is required before extracting computation spec")

    result = run_skill("extract_computation_spec", {"plan_text": plan_text}, model_choice)
    parsed = _parse_spec_json(result["content"]) or {}
    spec = _normalize_computation_spec(parsed)
    plan_doc = task.get("documents", {}).get("plan", {})
    task.setdefault("documents", {})["computationSpec"] = {
        **spec,
        "planVersionId": plan_doc.get("currentVersionId", ""),
        "generatedAt": current_timestamp(),
        "refinedAt": "",
    }
    _write_requirement_documents(task)
    task["updatedAt"] = current_timestamp()
    save_requirement_task(task)
    return task


def _try_extract_specs_after_plan(task: dict) -> None:
    """方案完成后静默抽取 modeling / computation 规划（失败不阻塞）。"""
    try:
        generate_requirement_modeling_spec(task["id"])
        task = find_requirement_task(task["id"]) or task
    except (ValueError, KeyError):
        pass
    try:
        generate_requirement_computation_spec(task["id"])
    except (ValueError, KeyError):
        pass


def get_task_document(task_id: str, part: str) -> dict | None:
    task = find_requirement_task(task_id)
    if task is None:
        return None
    part = str(part or "").strip()
    if part not in ("analysis", "plan"):
        raise ValueError("part must be 'analysis' or 'plan'")
    document = (task.get("documents") or {}).get(part)
    if not document:
        return None
    return {
        "part": part,
        "currentVersionId": document.get("currentVersionId", ""),
        "content": document.get("content", ""),
        "versions": document.get("versions", []),
    }


def get_task_spec(task_id: str, part: str) -> dict | None:
    task = find_requirement_task(task_id)
    if task is None:
        return None
    part = str(part or "").strip()
    if part not in ("modeling", "computation"):
        raise ValueError("part must be 'modeling' or 'computation'")
    key = "modelingSpec" if part == "modeling" else "computationSpec"
    return (task.get("documents") or {}).get(key)


def task_summary(task: dict | None) -> dict | None:
    if not task:
        return None
    documents = task.get("documents") or {}
    return {
        "id": task["id"],
        "fileName": task.get("fileName", ""),
        "status": task.get("status", ""),
        "projectId": task.get("projectId", ""),
        "hasAnalysis": "analysis" in documents,
        "hasPlan": "plan" in documents,
        "hasModelingSpec": "modelingSpec" in documents,
        "hasComputationSpec": "computationSpec" in documents,
        "updatedAt": task.get("updatedAt", ""),
    }


def save_requirement_version(task_id: str, payload: dict) -> dict:
    """把用户手动编辑的 Markdown 作为新版本保存到指定文档。

    ``target`` 取 ``analysis`` 或 ``plan``；新版本插入到版本列表首位并设为当前版本。
    """
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    target = str(payload.get("target", "")).strip()
    if target not in ("analysis", "plan"):
        raise ValueError("target must be 'analysis' or 'plan'")
    content = str(payload.get("content", "")).strip()
    if not content:
        raise ValueError("content is required")

    document = task.get("documents", {}).get(target)
    if not document:
        raise ValueError(f"document not found: {target}")

    now = current_timestamp()
    next_number = len(document.get("versions", [])) + 1
    version = {
        "id": f"{target}-v{next_number}",
        "name": f"v{next_number} 手动编辑",
        "content": content,
        "createdAt": now,
        "source": "手动编辑",
    }
    document.setdefault("versions", []).insert(0, version)
    document["currentVersionId"] = version["id"]
    document["content"] = content
    _write_requirement_documents(task)
    task["updatedAt"] = now
    save_requirement_task(task)
    return task


def _plan_version_name(plan: dict, message: str) -> tuple[str, int]:
    next_number = len(plan["versions"]) + 1
    if "客户" in message or "风险" in message:
        return f"v{next_number} 客户版", next_number
    return f"v{next_number} 优化版", next_number


def _apply_chat_result(task: dict, message: str, content: str, reasoning: str) -> dict:
    now = current_timestamp()
    plan = task["documents"]["plan"]
    version_name, next_number = _plan_version_name(plan, message)
    version = {
        "id": f"plan-v{next_number}",
        "name": version_name,
        "content": content,
        "createdAt": now,
        "source": message,
    }
    plan["versions"].insert(0, version)
    plan["currentVersionId"] = version["id"]
    plan["content"] = content
    plan["reasoning"] = reasoning
    _write_requirement_documents(task)
    task["conversation"].extend(
        [
            {"role": "user", "content": message, "createdAt": now},
            {
                "role": "assistant",
                "content": f"已根据要求更新方案，并保存为 {version_name}。",
                "createdAt": now,
                "usedSkills": [_message_skill("optimize_plan")],
            },
        ]
    )
    task["updatedAt"] = now
    return task


def add_requirement_chat_message(task_id: str, payload: dict) -> dict:
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")

    result = run_skill(
        "optimize_plan",
        {
            "source_text": task["sourceText"],
            "current_plan": _current_plan_content(task),
            "note": message,
        },
    )
    _apply_chat_result(task, message, result["content"], result["reasoning"])
    save_requirement_task(task)
    return task


def stream_requirement_chat_message(task_id: str, payload: dict):
    task = find_requirement_task(task_id)
    if task is None:
        raise KeyError("requirement task not found")
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    model_choice = str(payload.get("model", "")).strip() or None

    yield {"type": "step", "skill": "optimize_plan", "task": task}

    content_parts: list[str] = []
    for delta in stream_skill(
        "optimize_plan",
        {
            "source_text": task["sourceText"],
            "current_plan": _current_plan_content(task),
            "note": message,
        },
        model_choice,
    ):
        if delta.get("type") == "content":
            content_parts.append(delta["text"])
        yield delta

    reasoning = consume_last_reasoning("optimize_plan", model_choice)
    content = "".join(content_parts).strip()
    _apply_chat_result(task, message, content, reasoning)
    save_requirement_task(task)
    yield {"type": "done", "task": task}
