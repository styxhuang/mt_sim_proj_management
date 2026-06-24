"""项目执行（模拟流程）领域逻辑与编排。

每个执行（execution）关联一个已完成方案的需求任务。当前实现的模块：
- modeling：全自动建模——``stream_auto_modeling`` 读建模规划，逐个 ``build_molecule``
  确定单体（SMILES→RDKit 生成 3D 结构），再复用单体做确定性随机填充组装成完整体系。
- computation：后续计算流程，先留占位骨架。

结构解析见 :func:`extract_structure`。
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from . import chem, config, project_files, projects
from .database import (
    deserialize_json,
    get_connection,
    initialize_database,
    serialize_json,
)
from .llm import cli_client
from .requirements import find_requirement_task, generate_requirement_computation_spec, save_requirement_task
from .requirements import _normalize_computation_spec, _parse_spec_json
from .skills import consume_last_reasoning, stream_skill


# Mol* 可解析的结构格式 → 代码块语言标签。
STRUCTURE_FORMATS = ("pdb", "xyz", "mol2", "sdf", "mol", "gro", "cif", "mmcif")

_STRUCTURE_BLOCK = re.compile(
    r"```(" + "|".join(STRUCTURE_FORMATS) + r")\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def current_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


_NAME_LINE = re.compile(r"^\s*名称\s*[:：]\s*(.+?)\s*$", re.MULTILINE)


_ANY_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _sniff_format(content: str) -> str | None:
    """在没有正确语言标签时，根据内容猜测结构格式（PDB/XYZ）。"""
    lines = [line for line in content.splitlines() if line.strip()]
    if not lines:
        return None
    text = "\n".join(lines)
    if re.search(r"^\s*(ATOM|HETATM)\s", text, re.MULTILINE):
        return "pdb"
    if re.search(r"^\s*CRYST1", text, re.MULTILINE):
        return "pdb"
    # XYZ：第一行是原子数，其后每行是“元素 x y z”
    if lines[0].strip().isdigit() and len(lines) >= int(lines[0].strip()) + 2:
        sample = lines[2].split()
        if len(sample) >= 4:
            return "xyz"
    return None


def extract_structure(markdown: str) -> dict | None:
    """从模型回复中解析首个结构文件代码块。

    优先匹配带格式语言标签的代码块；若模型漏写/写错语言标签，则在任意代码块中
    依据内容嗅探 PDB/XYZ。返回 ``{"format", "content", "name"}``；未找到返回 ``None``。
    """
    match = _STRUCTURE_BLOCK.search(markdown or "")
    if match:
        fmt = match.group(1).lower()
        content = match.group(2).strip("\n")
        if content.strip():
            return {"format": fmt, "content": content, "name": f"model.{fmt}"}

    for block in _ANY_BLOCK.finditer(markdown or ""):
        content = block.group(1).strip("\n")
        if not content.strip():
            continue
        fmt = _sniff_format(content)
        if fmt:
            return {"format": fmt, "content": content, "name": f"model.{fmt}"}
    return None


def parse_molecule_name(markdown: str) -> str:
    """解析单分子回复中的"名称：xxx"行；无则返回空串。"""
    match = _NAME_LINE.search(markdown or "")
    return match.group(1).strip() if match else ""


_SMILES_BLOCK = re.compile(r"```smiles\s*\n([^\n`]+)", re.IGNORECASE)
_SMILES_LINE = re.compile(r"^\s*SMILES\s*[:：]\s*(\S+)", re.MULTILINE | re.IGNORECASE)


def parse_smiles(markdown: str) -> str:
    """从模型回复中解析 SMILES：优先 ```smiles 代码块，回退到 ``SMILES: xxx`` 行。"""
    text = str(markdown or "")
    block = _SMILES_BLOCK.search(text)
    if block:
        return block.group(1).strip()
    line = _SMILES_LINE.search(text)
    return line.group(1).strip() if line else ""


def structure_from_molecule_reply(content: str, fallback_smiles: str = "") -> dict | None:
    """把单分子回复转成结构：优先 SMILES→RDKit（几何可靠），否则回退到结构代码块。

    ``fallback_smiles`` 用于规划里已带 SMILES、而模型回复漏给的情况。
    """
    smiles = parse_smiles(content) or str(fallback_smiles or "").strip()
    if smiles:
        pdb = chem.smiles_to_pdb(smiles)
        if pdb:
            return {"format": "pdb", "content": pdb, "name": "model.pdb"}
    return extract_structure(content)


def default_modules() -> dict:
    return {
        "modeling": {
            "title": "建模",
            "status": "pending",
            "detail": "先构建单个分子，再组装为完整体系",
            "stage": "molecules",
            "molecules": [],
            "system": None,
            "usedSkills": [],
        },
        "computation": {
            "title": "模拟计算",
            "status": "locked",
            "detail": "完成建模后开放",
            "refined": False,
            "modelInput": None,
            "runnerSelections": {},
            "runs": {},
            "artifacts": [],
            "currentStepId": "",
        },
    }


def _ensure_computation_module(execution: dict) -> dict:
    modules = execution.setdefault("modules", {})
    defaults = default_modules()["computation"]
    computation = modules.setdefault("computation", {})
    for key, value in defaults.items():
        if key not in computation:
            if isinstance(value, dict):
                computation[key] = dict(value)
            elif isinstance(value, list):
                computation[key] = list(value)
            else:
                computation[key] = value
    return computation


def _structure_meta(structure: dict | None, structure_id: str, kind: str) -> dict | None:
    if not structure or not structure.get("content"):
        return None
    atoms = len(chem._parse_pdb_atoms(structure["content"])) if structure.get("format") == "pdb" else 0
    return {
        "id": structure_id,
        "name": structure.get("name", structure_id),
        "format": structure.get("format", "pdb"),
        "kind": kind,
        "atomCount": atoms or None,
    }


def list_structure_metas(execution: dict) -> list[dict]:
    modeling = execution.get("modules", {}).get("modeling", {})
    items: list[dict] = []
    for molecule in modeling.get("molecules") or []:
        meta = _structure_meta(molecule, molecule.get("id", ""), "molecule")
        if meta:
            items.append(meta)
    system = modeling.get("system")
    if system and system.get("content"):
        items.append(_structure_meta(system, "system", "system") or {"id": "system", "name": "完整体系", "format": "pdb", "kind": "system"})
    return items


def get_structure_content(execution: dict, structure_id: str) -> dict | None:
    modeling = execution.get("modules", {}).get("modeling", {})
    if structure_id == "system":
        system = modeling.get("system")
        if system and system.get("content"):
            return {"id": "system", "format": system.get("format", "pdb"), "content": system["content"], "name": system.get("name", "system.pdb")}
        return None
    for molecule in modeling.get("molecules") or []:
        if molecule.get("id") == structure_id and molecule.get("content"):
            return {
                "id": molecule["id"],
                "format": molecule.get("format", "pdb"),
                "content": molecule["content"],
                "name": molecule.get("name", molecule["id"]),
            }
    return None


def _build_model_input(modeling: dict, system: dict, manifest_path: str = "") -> dict:
    atom_count = len(chem._parse_pdb_atoms(system.get("content", ""))) if system.get("format") == "pdb" else None
    model_input = {
        "structureId": "system",
        "name": system.get("name", "system.pdb"),
        "format": system.get("format", "pdb"),
        "filePath": system.get("filePath", ""),
        "atomCount": atom_count,
        "molecules": [
            {
                "id": molecule.get("id", ""),
                "name": molecule.get("name", ""),
                "format": molecule.get("format", ""),
                "filePath": molecule.get("filePath", ""),
            }
            for molecule in modeling.get("molecules") or []
        ],
    }
    if manifest_path:
        model_input["manifestPath"] = manifest_path
    return model_input


def _write_computation_model_input(task: dict, model_input: dict) -> str:
    path = project_files.write_project_file(
        task,
        ["04-computation", "model-input.json"],
        json.dumps(model_input, ensure_ascii=False, indent=2),
    )
    return str(path)


def prepare_computation_from_modeling(execution_id: str) -> dict:
    """把已完成的完整体系登记为模拟计算输入，并推进项目到模拟计算阶段。"""
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")

    modeling = execution.get("modules", {}).get("modeling", {})
    system = modeling.get("system") or {}
    if not system.get("content"):
        raise ValueError("complete modeled system is required before computation")

    task = find_requirement_task(execution["requirementTaskId"])
    if task is None:
        raise KeyError("requirement task not found")

    modeling["status"] = "completed"
    modeling["detail"] = "已完成建模，完整体系已作为模拟计算输入"
    computation = _ensure_computation_module(execution)
    if not computation.get("refined") and computation.get("status") != "completed":
        computation["status"] = "pending"
        computation["detail"] = "已接收建模体系，可细化并运行模拟计算"
    model_input = _build_model_input(modeling, system)
    manifest_path = _write_computation_model_input(task, model_input)
    model_input["manifestPath"] = manifest_path
    _write_computation_model_input(task, model_input)
    computation["modelInput"] = model_input
    execution["status"] = "computation"
    execution["updatedAt"] = current_timestamp()
    save_execution(execution)
    project = projects.advance_project_stage(task.get("projectId", ""), "模拟计算")
    return {"execution": execution_without_content(execution), "project": project}


def execution_without_content(execution: dict) -> dict:
    """去掉 PDB 等大字段，供轻量 API / SSE 使用。"""
    if not execution:
        return execution
    copy = {
        "id": execution["id"],
        "requirementTaskId": execution["requirementTaskId"],
        "title": execution["title"],
        "status": execution["status"],
        "createdAt": execution["createdAt"],
        "updatedAt": execution["updatedAt"],
        "modules": {},
        "conversation": execution.get("conversation", []),
    }
    modules = execution.get("modules", {})
    modeling = modules.get("modeling", {})
    molecules = []
    for mol in modeling.get("molecules") or []:
        molecules.append({k: v for k, v in mol.items() if k != "content"})
    system = modeling.get("system")
    system_meta = None
    if system:
        system_meta = {k: v for k, v in system.items() if k != "content"}
        if system.get("content"):
            system_meta["atomCount"] = len(chem._parse_pdb_atoms(system["content"]))
    modeling_meta = {**modeling}
    if system_meta and (system_meta.get("atomCount") or system.get("content")):
        modeling_meta["status"] = "completed"
        modeling_meta["detail"] = modeling_meta.get("detail") or "已完成建模，完整体系已就绪"
    copy["modules"]["modeling"] = {
        **modeling_meta,
        "molecules": molecules,
        "system": system_meta,
    }
    copy["modules"]["computation"] = modules.get("computation", {})
    copy["structures"] = list_structure_metas(execution)
    return copy


def execution_summary(execution: dict | None) -> dict | None:
    if not execution:
        return None
    lite = execution_without_content(execution)
    return {
        "id": lite["id"],
        "requirementTaskId": lite["requirementTaskId"],
        "status": lite["status"],
        "modules": lite["modules"],
        "structures": lite.get("structures", []),
        "updatedAt": lite["updatedAt"],
    }


def _sse_execution(execution: dict) -> dict:
    return execution_without_content(execution)


def _plan_content(task: dict) -> str:
    return str(task.get("documents", {}).get("plan", {}).get("content", "")).strip()


# --- 持久化 ---------------------------------------------------------------

def next_execution_id() -> str:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute("SELECT COUNT(*) FROM executions").fetchone()
    return f"exec-{int(row[0]) + 1:03d}"


def save_execution(execution: dict) -> None:
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO executions (
                id, requirement_task_id, title, status, modules,
                conversation, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution["id"],
                execution["requirementTaskId"],
                execution["title"],
                execution["status"],
                serialize_json(execution["modules"]),
                serialize_json(execution["conversation"]),
                execution["createdAt"],
                execution["updatedAt"],
            ),
        )


def _row_to_execution(row) -> dict:
    execution = {
        "id": row["id"],
        "requirementTaskId": row["requirement_task_id"],
        "title": row["title"],
        "status": row["status"],
        "modules": deserialize_json(row["modules"]),
        "conversation": deserialize_json(row["conversation"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
    _ensure_computation_module(execution)
    return execution


def _local_run_root(execution: dict, step_id: str) -> Path | None:
    task = find_requirement_task(execution.get("requirementTaskId", ""))
    if not task:
        return None
    project = projects.find_project(task.get("projectId", ""))
    project_path = str((project or {}).get("rootDirectory", "")).strip()
    if not project_path:
        return None
    return Path(project_path) / "04-computation" / f"{execution.get('id')}-{step_id}"


def _next_computation_artifact_id(computation: dict) -> str:
    return f"artifact-{len(computation.get('artifacts') or []) + 1:03d}"


def _attach_existing_computation_artifact(execution: dict, step_id: str, path: Path, kind: str, mime: str) -> dict:
    computation = _ensure_computation_module(execution)
    existing = next(
        (
            artifact
            for artifact in computation.get("artifacts") or []
            if str(artifact.get("storagePath")) == str(path)
        ),
        None,
    )
    if existing:
        return existing
    artifact = {
        "id": _next_computation_artifact_id(computation),
        "stepId": step_id,
        "name": path.name,
        "kind": kind,
        "mime": mime,
        "size": path.stat().st_size if path.exists() else 0,
        "storagePath": str(path),
        "createdAt": current_timestamp(),
    }
    computation.setdefault("artifacts", []).append(artifact)
    return artifact


def _reconcile_local_running_runs(execution: dict) -> bool:
    computation = _ensure_computation_module(execution)
    changed = False
    for step_id, run in list((computation.get("runs") or {}).items()):
        if run.get("status") != "running" or run.get("runner") != "local":
            continue
        root = _local_run_root(execution, step_id)
        if not root or not root.exists():
            continue
        logs_dir = root / "logs"
        grompp_log = logs_dir / "grompp_check.log"
        step_log = logs_dir / f"{step_id}-run.log"
        if not step_log.exists():
            matches = sorted(logs_dir.glob("*-run.log")) if logs_dir.exists() else []
            step_log = matches[0] if matches else step_log
        grompp_text = grompp_log.read_text(encoding="utf-8", errors="replace") if grompp_log.exists() else ""
        step_text = step_log.read_text(encoding="utf-8", errors="replace") if step_log.exists() else ""
        if "[exit_code] 0" in grompp_text:
            status = "completed"
            summary = f"本地运行完成：{run.get('stepName') or step_id}（已从本地日志恢复完成状态）"
        elif "[exit_code]" in grompp_text or "failed" in step_text.lower() or "fatal" in grompp_text.lower():
            status = "failed"
            summary = f"本地运行失败：{run.get('stepName') or step_id}（已从本地日志恢复失败状态）"
        else:
            continue

        artifacts: list[dict] = []
        if step_log.exists():
            artifacts.append(_attach_existing_computation_artifact(execution, step_id, step_log, "log", "text/plain"))
        if grompp_log.exists():
            artifacts.append(_attach_existing_computation_artifact(execution, step_id, grompp_log, "log", "text/plain"))
        for pattern, kind, mime in [
            ("topology/*.top", "topology", "text/plain"),
            ("topology/*.itp", "topology", "text/plain"),
            ("topology/*.gro", "structure", "text/plain"),
            ("topology/*.tpr", "binary", "application/octet-stream"),
            ("params/*/*.mol2", "parameter", "text/plain"),
            ("params/*/*.frcmod", "parameter", "text/plain"),
        ]:
            for path in sorted(root.glob(pattern)):
                artifacts.append(_attach_existing_computation_artifact(execution, step_id, path, kind, mime))

        completed_at = current_timestamp()
        run.update(
            {
                "status": status,
                "summary": summary,
                "logs": [
                    *(run.get("logs") or []),
                    f"{completed_at} {summary}",
                    "grompp_check.log: " + ("exit_code 0" if status == "completed" else "存在失败标记"),
                ],
                "artifacts": artifacts,
                "completedAt": completed_at,
            }
        )
        computation["runs"][step_id] = run
        computation["status"] = status
        computation["detail"] = summary
        computation["currentStepId"] = step_id
        execution["updatedAt"] = completed_at
        task = find_requirement_task(execution.get("requirementTaskId", ""))
        if task:
            _set_step_status(task, step_id, status, run)
        changed = True
    if changed:
        save_execution(execution)
    return changed


def _merge_local_run_outputs(execution: dict, step_id: str, run: dict) -> dict:
    root = _local_run_root(execution, step_id)
    if not root or not root.exists():
        return run
    logs_dir = root / "logs"
    if not logs_dir.exists():
        return run

    artifacts: list[dict] = list(run.get("artifacts") or [])
    existing_paths = {str(artifact.get("storagePath")) for artifact in artifacts}
    for path, kind, mime in [
        *[(path, "log", "text/plain") for path in sorted(logs_dir.glob("*.log"))],
        *[(path, "topology", "text/plain") for path in sorted((root / "topology").glob("*.top"))],
        *[(path, "topology", "text/plain") for path in sorted((root / "topology").glob("*.itp"))],
        *[(path, "structure", "text/plain") for path in sorted((root / "topology").glob("*.gro"))],
        *[(path, "binary", "application/octet-stream") for path in sorted((root / "topology").glob("*.tpr"))],
        *[(path, "result", "text/markdown") for path in sorted(root.glob("*summary.md"))],
    ]:
        artifact = _attach_existing_computation_artifact(execution, step_id, path, kind, mime)
        if str(path) not in existing_paths:
            artifacts.append(artifact)
            existing_paths.add(str(path))

    merged_logs = list(run.get("logs") or [])
    summary_lines: list[str] = []
    for log_name in ("final_validation.log", "grompp_check.log", f"{step_id}-run.log", "step-2-run.log"):
        path = logs_dir / log_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if log_name == "final_validation.log":
            summary_lines.extend(line for line in text.splitlines() if line.strip()[-4:] == "PASS" or "PASS" in line)
        elif log_name == "grompp_check.log":
            if "[exit_code] 0" in text:
                summary_lines.append("grompp_check.log: exit_code 0")
            warning_match = re.search(r"There (?:was|were) .*WARNING", text)
            if warning_match:
                summary_lines.append(f"grompp_check.log: {warning_match.group(0)}")
        elif "antechamber" in text or "parmchk2" in text or "grompp" in text:
            command_lines = [
                line
                for line in text.splitlines()
                if any(key in line for key in ("antechamber", "parmchk2", "tleap", "grompp"))
            ]
            summary_lines.extend(command_lines[:5])
    if summary_lines:
        marker = "真实执行日志："
        merged_logs = [line for line in merged_logs if line != marker and line not in summary_lines]
        merged_logs.append(marker)
        merged_logs.extend(summary_lines[:12])
    run["logs"] = merged_logs
    run["artifacts"] = artifacts
    return run


def _refresh_local_run_outputs(execution: dict) -> bool:
    computation = _ensure_computation_module(execution)
    changed = False
    for step_id, run in list((computation.get("runs") or {}).items()):
        if run.get("runner") != "local" or run.get("status") == "running":
            continue
        before = json.dumps(run, ensure_ascii=False, sort_keys=True)
        merged = _merge_local_run_outputs(execution, step_id, run)
        after = json.dumps(merged, ensure_ascii=False, sort_keys=True)
        if after != before:
            computation.setdefault("runs", {})[step_id] = merged
            changed = True
    if changed:
        execution["updatedAt"] = current_timestamp()
        save_execution(execution)
    return changed


def find_execution(execution_id: str) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM executions WHERE id = ?",
            (execution_id,),
        ).fetchone()
    execution = _row_to_execution(row) if row else None
    if execution:
        _reconcile_local_running_runs(execution)
        _reconcile_bohrium_running_runs(execution)
        _refresh_local_run_outputs(execution)
    return execution


def find_execution_by_task(task_id: str) -> dict | None:
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM executions WHERE requirement_task_id = ? ORDER BY created_at DESC, id DESC",
            (task_id,),
        ).fetchone()
    execution = _row_to_execution(row) if row else None
    if execution:
        _reconcile_local_running_runs(execution)
        _reconcile_bohrium_running_runs(execution)
        _refresh_local_run_outputs(execution)
    return execution


def get_or_create_execution(requirement_task_id: str) -> dict:
    """按需求任务获取执行；不存在则创建（要求该任务已生成方案）。"""
    requirement_task_id = str(requirement_task_id or "").strip()
    if not requirement_task_id:
        raise ValueError("requirementTaskId is required")

    existing = find_execution_by_task(requirement_task_id)
    if existing:
        return existing

    task = find_requirement_task(requirement_task_id)
    if task is None:
        raise KeyError("requirement task not found")
    if "plan" not in task.get("documents", {}):
        raise ValueError("requirement task has no plan yet")

    now = current_timestamp()
    execution = {
        "id": next_execution_id(),
        "requirementTaskId": requirement_task_id,
        "title": str(task.get("fileName", "")).strip() or "未命名项目",
        "status": "modeling",
        "modules": default_modules(),
        "conversation": [
            {
                "role": "assistant",
                "content": "已进入项目执行。建模分两步：先在「单分子构建」里逐个描述体系中的分子，我会分别生成单体结构；再切到「体系组装」，按数量/配比组装成完整体系。结构会在右侧用 Mol* 展示。",
                "createdAt": now,
            }
        ],
        "createdAt": now,
        "updatedAt": now,
    }
    save_execution(execution)
    return execution


def load_executions() -> list[dict]:
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM executions ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [_row_to_execution(row) for row in rows]


# --- 自动建模编排（读规划 → 逐个建分子 → 组装体系） ----------------------

_TYPE_LABELS = {
    "molecule": "分子",
    "ion": "离子",
    "surface": "表面",
    "slab": "slab",
    "polymer": "聚合物",
    "cluster": "团簇",
}

def _three_char_code(value: object, index: int = 0) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(value or "").upper())
    if cleaned and cleaned[0].isalpha():
        return cleaned[:3].ljust(3, "X")
    return f"M{(index + 1) % 100:02d}"


def _block_to_note(block: dict) -> str:
    code = _three_char_code(block.get("code") or block.get("name"), 0)
    meta = "，".join(
        part
        for part in [
            f"代码 {code}",
            str(block.get("formula", "")).strip(),
            _TYPE_LABELS.get(str(block.get("type", "")).strip(), str(block.get("type", "")).strip()),
            str(block.get("role", "")).strip(),
        ]
        if part
    )
    note = f"构建{code}"
    if meta:
        note += f"（{meta}）"
    extra = str(block.get("note", "")).strip()
    if extra:
        note += f"。{extra}"
    return note


_RATIO_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# 解析目标原子数：优先 atomCount 字段，其次 box 文本里的"X万原子 / 50000 原子"。
_WAN_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~–]\s*(\d+(?:\.\d+)?)\s*万")
_WAN_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*万")
_ATOM_PLAIN = re.compile(r"(\d{3,7})")

# 体系规模：常规约 5 万原子，硬上限 10 万（用户要求）。
_DEFAULT_ATOMS = 50000
_MAX_ATOMS = 100000
# 绝对整数配比（明确个数）认定阈值：不超过此值则按原样使用、不按原子数放大。
_ABSOLUTE_COUNT_LIMIT = 2000
# 若模型已给出上百个整数分子，通常是按目标原子数整数化后的实际组成。
_PRECOMPUTED_COUNT_THRESHOLD = 100


def _parse_ratio(value) -> float | None:
    """从 "6.08份" / "50" / 2 这类值里取出数值；取不到返回 None。"""
    if isinstance(value, (int, float)):
        return float(value)
    match = _RATIO_NUM.search(str(value or ""))
    return float(match.group()) if match else None


def _target_atom_count(spec: dict | None) -> int:
    """解析期望总原子数：atomCount 字段优先，其次 box 文本，默认 5 万，封顶 10 万。"""
    target = (spec or {}).get("targetSystem") or {}
    raw = str(target.get("atomCount", "")).strip()
    box = str(target.get("box", ""))
    value: float | None = None
    if raw:
        m = _ATOM_PLAIN.search(raw.replace(",", ""))
        if "万" in raw:
            wm = _WAN_SINGLE.search(raw)
            if wm:
                value = float(wm.group(1)) * 10000
        elif m:
            value = float(m.group(1))
    if value is None:
        rng = _WAN_RANGE.search(box)
        single = _WAN_SINGLE.search(box)
        plain = _ATOM_PLAIN.search(box.replace(",", ""))
        if rng:
            value = (float(rng.group(1)) + float(rng.group(2))) / 2 * 10000
        elif single:
            value = float(single.group(1)) * 10000
        elif plain:
            value = float(plain.group(1))
    if value is None or value <= 0:
        value = _DEFAULT_ATOMS
    return int(max(1000, min(value, _MAX_ATOMS)))


def _has_explicit_target_atom_count(spec: dict | None) -> bool:
    target = (spec or {}).get("targetSystem") or {}
    raw = str(target.get("atomCount", "")).strip()
    box = str(target.get("box", "")).strip()
    return bool(raw or "原子" in box or "万" in box)


def _allocate_counts(
    ratios: list[float | None],
    atoms: list[int],
    target_atoms: int,
    scale_to_target: bool = False,
) -> list[int]:
    """把配比/份数换算成整数分子个数，使总原子数接近 ``target_atoms``。

    若配比全是较小的绝对整数（明确个数），按原样使用；否则按"配比×单体原子数"
    缩放到目标原子数，并保证不超过硬上限、每种至少 1 个。
    """
    cleaned = [r if (r is not None and r > 0) else 1.0 for r in ratios]
    looks_like_integer_counts = all(abs(r - round(r)) < 1e-6 for r in cleaned)
    if looks_like_integer_counts and (
        not scale_to_target
        or sum(cleaned) >= _PRECOMPUTED_COUNT_THRESHOLD
        or sum(r * a for r, a in zip(cleaned, atoms)) >= target_atoms * 0.75
    ):
        return [max(1, int(round(r))) for r in cleaned]
    denom = sum(r * a for r, a in zip(cleaned, atoms)) or 1.0
    scale = target_atoms / denom
    counts = [max(1, int(round(scale * r))) for r in cleaned]
    while sum(c * a for c, a in zip(counts, atoms)) > _MAX_ATOMS:
        idx = max(range(len(counts)), key=lambda j: counts[j] * atoms[j])
        if counts[idx] <= 1:
            break
        counts[idx] -= 1
    return counts


def _name_key(value: str) -> str:
    return re.sub(r"[\s_\-·（）()]+", "", str(value or "")).lower()


def _name_aliases(value: str) -> set[str]:
    raw = str(value or "")
    pieces = [raw]
    pieces.extend(re.split(r"[/／,，;；|｜]+", raw))
    aliases: set[str] = set()
    for piece in pieces:
        key = _name_key(piece)
        if key:
            aliases.add(key)
    return aliases


def _names_match(left: str, right: str) -> bool:
    left_aliases = _name_aliases(left)
    right_aliases = _name_aliases(right)
    if not left_aliases or not right_aliases:
        return False
    if left_aliases & right_aliases:
        return True
    return any(a in b or b in a for a in left_aliases for b in right_aliases)


def _resolve_components(molecules: list[dict], spec: dict | None) -> list[dict]:
    """把建好的单体与规划里的配比对应起来，得到 ``pack_pdbs`` 的输入（含整数个数）。"""
    by_name: dict[str, dict] = {}
    named_molecules: list[tuple[str, dict]] = []
    for mol in molecules:
        for key in (mol.get("code"), mol.get("name"), mol.get("blockName")):
            normalized = _name_key(str(key or ""))
            if normalized:
                by_name[normalized] = mol
                named_molecules.append((str(key), mol))
    target = (spec or {}).get("targetSystem") or {}
    pairs: list[tuple[dict, object]] = []
    used: set[str] = set()
    for comp in target.get("components") or []:
        block_name = str(comp.get("block", "")).strip()
        block_key = _name_key(block_name)
        mol = by_name.get(block_key)
        if mol is None and block_key:
            match = next(
                (
                    candidate
                    for candidate_name, candidate in named_molecules
                    if _names_match(block_name, candidate_name)
                ),
                None,
            )
            mol = match
        if mol and mol["id"] not in used:
            pairs.append((mol, comp.get("count")))
            used.add(mol["id"])
    for mol in molecules:
        if mol["id"] not in used:
            pairs.append((mol, 1))
    if not pairs:
        return []
    atoms = [len(chem._parse_pdb_atoms(mol["content"])) or 1 for mol, _ in pairs]
    counts = _allocate_counts(
        [_parse_ratio(raw) for _, raw in pairs],
        atoms,
        _target_atom_count(spec),
        scale_to_target=_has_explicit_target_atom_count(spec),
    )
    components: list[dict] = []
    for index, ((mol, _), count) in enumerate(zip(pairs, counts)):
        code = mol.get("code") or _three_char_code(mol.get("name"), index)
        components.append({"content": mol["content"], "count": count, "name": code})
    return components


def _assemble_execution_system(execution: dict, spec: dict | None) -> tuple[dict | None, str]:
    """复用已建好的单体，确定性地把体系组装成一个 PDB。返回 (structure, 摘要文本)。"""
    molecules = execution["modules"]["modeling"].get("molecules", [])
    if not molecules:
        return None, "没有可组装的分子。"
    components = _resolve_components(molecules, spec)
    pdb = chem.pack_pdbs(components)
    if not pdb:
        return None, "组装失败：无法解析单体结构。"
    structure = {"format": "pdb", "content": pdb, "name": "system.pdb"}
    summary = "已调用 build_amorphous 按建模规划组装完整体系：" + "、".join(
        f"{comp['name']}×{comp['count']}" for comp in components
    )
    return structure, summary


def _record_modeling_skill(modeling: dict, skill_id: str, name: str, reason: str) -> None:
    used = modeling.setdefault("usedSkills", [])
    if any(item.get("id") == skill_id for item in used if isinstance(item, dict)):
        return
    used.append({"id": skill_id, "name": name, "reason": reason})


def _modeling_skill(skill_id: str, name: str, reason: str) -> dict:
    return {"id": skill_id, "name": name, "reason": reason}


def _is_system_assembly_request(message: str) -> bool:
    text = str(message or "").lower()
    system_terms = ("完整体系", "体系", "组装", "分子数量", "原子数量", "原子数", "摩尔比", "配比")
    molecule_terms = ("单分子", "smiles", "重建分子", "修正分子")
    return any(term in text for term in system_terms) and not any(term in text for term in molecule_terms)


def stream_auto_modeling(execution_id: str, payload: dict):
    """自动编排建模：依据建模规划逐个构建分子，再组装为完整体系。

    产出类型：``step``（阶段说明）、``content``/``reasoning``（模型增量）、
    ``progress``（一个分子完成并入库，附 execution）、``done``（全部完成）。
    """
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    model_choice = str(payload.get("model", "")).strip() or None

    task = find_requirement_task(execution["requirementTaskId"])
    if task is None:
        raise KeyError("requirement task not found")
    plan_text = _plan_content(task)
    spec = (task.get("documents", {}) or {}).get("modelingSpec") or {}
    blocks = [block for block in (spec.get("buildingBlocks") or []) if str(block.get("name", "")).strip()]
    if not blocks:
        raise ValueError("modeling spec has no building blocks")

    modeling = execution["modules"]["modeling"]
    modeling["molecules"] = []
    modeling["system"] = None
    modeling["stage"] = "molecules"
    modeling["status"] = "in_progress"
    now = current_timestamp()
    # 每次自动建模都从干净的对话开始，避免历次结果堆叠。
    execution["conversation"] = [
        {"role": "user", "content": "自动建模：按建模规划逐个构建分子并组装为完整体系。", "createdAt": now}
    ]
    execution["updatedAt"] = now
    save_execution(execution)
    yield {"type": "step", "stage": "molecules", "label": "开始自动建模", "execution": _sse_execution(execution)}

    total = len(blocks)
    for index, block in enumerate(blocks, start=1):
        code = _three_char_code(block.get("code") or block.get("name"), index - 1)
        name = str(block.get("name", code)).strip() or code
        yield {"type": "step", "stage": "molecules", "label": f"构建分子 {index}/{total}：{name}", "execution": _sse_execution(execution)}

        parts: list[str] = []
        for delta in stream_skill("build_molecule", {"plan_text": plan_text, "note": _block_to_note(block)}, model_choice):
            if delta.get("type") == "content":
                parts.append(delta["text"])
            yield delta
        content = "".join(parts).strip()
        structure = structure_from_molecule_reply(content, fallback_smiles=str(block.get("smiles", "")))
        now = current_timestamp()
        if structure:
            molecules = modeling["molecules"]
            mol_name = _three_char_code(parse_molecule_name(content) or code, index - 1)
            mol_id = f"mol-{len(molecules) + 1}"
            file_path = _write_modeling_structure(
                execution,
                structure,
                ["03-modeling", "molecules", f"{mol_id}.{structure['format']}"],
            )
            molecules.append(
                {
                    "id": mol_id,
                    "name": mol_name,
                    "code": mol_name,
                    "blockName": name,
                    "format": structure["format"],
                    "content": structure["content"],
                    "filePath": file_path,
                }
            )
            modeling["detail"] = f"已构建 {len(molecules)} 个分子"
        execution["conversation"].append(
            {
                "role": "assistant",
                "content": content or f"（{name}：未解析到结构）",
                "createdAt": now,
                "usedSkills": [_modeling_skill("build_molecule", "Build Molecule", "按建模规划生成单分子结构表示")],
            }
        )
        execution["updatedAt"] = now
        save_execution(execution)
        yield {"type": "progress", "stage": "molecules", "execution": _sse_execution(execution)}

    if not modeling["molecules"]:
        modeling["status"] = "in_progress"
        modeling["detail"] = "未解析到任何分子结构"
        save_execution(execution)
        yield {"type": "done", "execution": _sse_execution(execution)}
        return

    modeling["stage"] = "system"
    yield {"type": "step", "stage": "system", "label": "组装完整体系", "execution": _sse_execution(execution)}

    # 组装用确定性网格摆放：复用上一步建好的单体（几何已可靠），仅平移拼装，避免飘原子。
    structure, summary = _assemble_execution_system(execution, spec)
    now = current_timestamp()
    if structure:
        _record_modeling_skill(modeling, "build_amorphous", "Build Amorphous System", "按单体结构、配比和目标原子数组装完整体系")
        structure["filePath"] = _write_modeling_structure(
            execution,
            structure,
            ["03-modeling", "system", structure.get("name", "system.pdb")],
        )
        modeling["system"] = structure
        modeling["status"] = "completed"
        modeling["detail"] = "已组装完整体系"
        execution["modules"]["computation"]["status"] = "pending"
        execution["modules"]["computation"]["detail"] = "结构就绪，可开始模拟计算"
        projects.advance_project_stage(task.get("projectId", ""), "建模")
    else:
        modeling["status"] = "in_progress"
        modeling["detail"] = "未解析到体系结构"
    content = summary
    message_skills = []
    if structure:
        message_skills = [
            _modeling_skill("build_amorphous", "Build Amorphous System", "按单体结构、配比和目标原子数组装完整体系")
        ]
    execution["conversation"].append(
        {
            "role": "assistant",
            "content": content or "（未解析到体系结构）",
            "createdAt": now,
            "usedSkills": message_skills,
        }
    )
    execution["updatedAt"] = now
    save_execution(execution)
    yield {"type": "done", "execution": _sse_execution(execution)}


# --- 优化对话（自动建模后继续修正某个分子并重新组装） --------------------

def stream_modeling_chat(execution_id: str, payload: dict):
    """继续优化建模结果：按用户描述（重）建某个分子，同名则替换，并重新组装体系。

    适用于自动建模后发现某个分子结构/SMILES 不对，用自然语言要求修正。
    产出类型：``step``、``content``/``reasoning``、``done``（附完整 execution）。
    """
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    message = str(payload.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    model_choice = str(payload.get("model", "")).strip() or None

    task = find_requirement_task(execution["requirementTaskId"])
    plan_text = _plan_content(task) if task else ""
    spec = (task.get("documents", {}) or {}).get("modelingSpec") if task else None
    modeling = execution["modules"]["modeling"]
    modeling.setdefault("molecules", [])

    now = current_timestamp()
    execution["conversation"].append({"role": "user", "content": message, "createdAt": now})
    modeling["status"] = "in_progress"
    save_execution(execution)

    if _is_system_assembly_request(message):
        yield {"type": "step", "stage": "system", "label": "按建模规划重新组装完整体系", "execution": _sse_execution(execution)}
        system, summary = _assemble_execution_system(execution, spec)
        now = current_timestamp()
        if system:
            _record_modeling_skill(modeling, "build_amorphous", "Build Amorphous System", "按单体结构、配比和目标原子数重新组装完整体系")
            system["filePath"] = _write_modeling_structure(
                execution,
                system,
                ["03-modeling", "system", system.get("name", "system.pdb")],
            )
            modeling["system"] = system
            modeling["status"] = "completed"
            modeling["detail"] = "已重新组装完整体系"
            execution["modules"]["computation"]["status"] = "pending"
            execution["modules"]["computation"]["detail"] = "结构就绪，可开始模拟计算"
            content = summary
        else:
            modeling["status"] = "in_progress"
            modeling["detail"] = "重新组装失败"
            content = summary or "重新组装失败。"
        message_skills = []
        if system:
            message_skills = [
                _modeling_skill("build_amorphous", "Build Amorphous System", "按单体结构、配比和目标原子数重新组装完整体系")
            ]
        execution["conversation"].append(
            {"role": "assistant", "content": content, "createdAt": now, "usedSkills": message_skills}
        )
        execution["updatedAt"] = now
        save_execution(execution)
        yield {"type": "done", "execution": _sse_execution(execution)}
        return

    yield {"type": "step", "stage": "molecules", "label": "根据反馈优化结构", "execution": _sse_execution(execution)}

    parts: list[str] = []
    for delta in stream_skill("build_molecule", {"plan_text": plan_text, "note": message}, model_choice):
        if delta.get("type") == "content":
            parts.append(delta["text"])
        yield delta
    content = "".join(parts).strip()
    structure = structure_from_molecule_reply(content)
    now = current_timestamp()

    molecules = modeling["molecules"]
    if structure:
        name = _three_char_code(parse_molecule_name(content), len(molecules))
        existing = next((mol for mol in molecules if mol["name"] == name), None)
        if existing:
            existing["format"] = structure["format"]
            existing["content"] = structure["content"]
            existing["filePath"] = _write_modeling_structure(
                execution,
                structure,
                ["03-modeling", "molecules", f"{existing['id']}.{structure['format']}"],
            )
            modeling["detail"] = f"已更新分子：{name}"
        else:
            mol_id = f"mol-{len(molecules) + 1}"
            file_path = _write_modeling_structure(
                execution,
                structure,
                ["03-modeling", "molecules", f"{mol_id}.{structure['format']}"],
            )
            molecules.append(
                {
                    "id": mol_id,
                    "name": name,
                    "code": name,
                    "blockName": name,
                    "format": structure["format"],
                    "content": structure["content"],
                    "filePath": file_path,
                }
            )
            modeling["detail"] = f"已新增分子：{name}"
        # 已有体系或存在多个分子时，重新确定性组装。
        if modeling.get("system") or len(molecules) > 1:
            system, _summary = _assemble_execution_system(execution, spec)
            if system:
                _record_modeling_skill(modeling, "build_amorphous", "Build Amorphous System", "单体更新后重新组装完整体系")
                system["filePath"] = _write_modeling_structure(
                    execution,
                    system,
                    ["03-modeling", "system", system.get("name", "system.pdb")],
                )
                modeling["system"] = system
                modeling["status"] = "completed"
                execution["modules"]["computation"]["status"] = "pending"
                execution["modules"]["computation"]["detail"] = "结构就绪，可开始模拟计算"

    execution["conversation"].append(
        {
            "role": "assistant",
            "content": content or "（无内容）",
            "createdAt": now,
            "usedSkills": [_modeling_skill("build_molecule", "Build Molecule", "根据反馈生成或修正单分子结构表示")],
        }
    )
    execution["updatedAt"] = now
    save_execution(execution)
    yield {"type": "done", "execution": _sse_execution(execution)}


# --- 模拟计算编排（体系组装完成后细化计算流程） ---------------------------

def _system_summary(execution: dict, spec: dict | None) -> str:
    """汇总已组装体系的组成与规模，供计算方案技能参考。"""
    modeling = execution["modules"]["modeling"]
    molecules = modeling.get("molecules", [])
    system = modeling.get("system") or {}
    lines: list[str] = []
    components = _resolve_components(molecules, spec) if molecules else []
    if components:
        lines.append(
            "组分与数量：" + "、".join(f"{comp['name']}×{comp['count']}" for comp in components)
        )
    elif molecules:
        lines.append("分子库：" + "、".join(str(mol.get("name", "")) for mol in molecules))
    if system.get("content"):
        atoms = len(chem._parse_pdb_atoms(system["content"]))
        if atoms:
            lines.append(f"体系总原子数：约 {atoms} 个")
    target = (spec or {}).get("targetSystem") or {}
    if str(target.get("box", "")).strip():
        lines.append(f"目标盒子：{str(target.get('box')).strip()}")
    return "\n".join(lines) if lines else "（无可用体系摘要）"


def _safe_path_part(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return safe.strip("-") or "item"


def _task_for_execution(execution: dict) -> dict | None:
    return find_requirement_task(execution.get("requirementTaskId", ""))


def _computation_artifact_root(execution: dict, step_id: str) -> Path:
    root = _local_run_root(execution, step_id)
    if root is not None:
        return root / "artifacts"
    task = _task_for_execution(execution)
    return project_files.ensure_project_dir(task, "04-computation", _safe_path_part(step_id))


def _write_modeling_structure(execution: dict, structure: dict, parts: list[str]) -> str:
    task = _task_for_execution(execution)
    path = project_files.write_project_file(task, parts, structure.get("content", ""))
    return str(path)


def _find_workflow_step(spec: dict, step_id: str) -> dict | None:
    return next((step for step in spec.get("workflowSteps") or [] if str(step.get("id")) == step_id), None)


def _computation_spec_for_execution(execution: dict) -> tuple[dict, dict]:
    task = find_requirement_task(execution["requirementTaskId"])
    if task is None:
        raise KeyError("requirement task not found")
    spec = (task.get("documents") or {}).get("computationSpec") or {}
    if not (spec.get("workflowSteps") or []):
        raise ValueError("computation spec has no workflow steps")
    return task, spec


def _next_artifact_id(computation: dict) -> str:
    return f"artifact-{len(computation.get('artifacts') or []) + 1:03d}"


def _write_computation_artifact(
    execution: dict,
    step_id: str,
    name: str,
    content: str,
    kind: str = "result",
    mime: str = "text/plain",
) -> dict:
    computation = _ensure_computation_module(execution)
    artifact_id = _next_artifact_id(computation)
    root = _computation_artifact_root(execution, step_id)
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{artifact_id}-{_safe_path_part(name)}"
    path = root / filename
    text = str(content or "")
    path.write_text(text, encoding="utf-8")
    artifact = {
        "id": artifact_id,
        "stepId": step_id,
        "name": name,
        "kind": kind,
        "mime": mime,
        "size": path.stat().st_size,
        "storagePath": str(path),
        "createdAt": current_timestamp(),
    }
    computation.setdefault("artifacts", []).append(artifact)
    return artifact


def get_computation_artifact_content(execution: dict, artifact_id: str) -> dict | None:
    computation = _ensure_computation_module(execution)
    artifact = next(
        (item for item in computation.get("artifacts") or [] if str(item.get("id")) == str(artifact_id)),
        None,
    )
    if not artifact:
        return None
    path = Path(str(artifact.get("storagePath", "")))
    if not path.exists() or not path.is_file():
        return None
    return {**artifact, "content": path.read_text(encoding="utf-8")}


def migrate_computation_artifact_layout(execution_id: str) -> dict:
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    computation = _ensure_computation_module(execution)
    legacy_dirs: set[Path] = set()
    for artifact in computation.get("artifacts") or []:
        step_id = str(artifact.get("stepId") or "").strip()
        if not step_id:
            continue
        source = Path(str(artifact.get("storagePath") or ""))
        if not source.exists() or not source.is_file():
            continue
        target_dir = _computation_artifact_root(execution, step_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        try:
            same_path = source.resolve() == target.resolve()
        except FileNotFoundError:
            same_path = False
        if same_path:
            artifact["size"] = source.stat().st_size
            continue
        legacy_dirs.add(source.parent)
        if target.exists():
            source.unlink()
        else:
            shutil.move(str(source), str(target))
        artifact["storagePath"] = str(target)
        artifact["size"] = target.stat().st_size
    for directory in sorted(legacy_dirs, key=lambda path: len(path.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    execution["updatedAt"] = current_timestamp()
    save_execution(execution)
    return execution


def _step_scripts(step: dict) -> list[str]:
    scripts: list[str] = []
    for skill in step.get("usedSkills") or []:
        if isinstance(skill, dict):
            scripts.extend(str(script) for script in (skill.get("scripts") or []) if str(script).strip())
    return scripts


def _step_skill_ids(step: dict) -> set[str]:
    skill_ids: set[str] = set()
    for skill in step.get("usedSkills") or []:
        if isinstance(skill, str):
            skill_id = skill.strip()
        elif isinstance(skill, dict):
            skill_id = str(skill.get("id") or skill.get("skill") or skill.get("name") or "").strip()
        else:
            skill_id = ""
        if skill_id:
            skill_ids.add(skill_id)
    return skill_ids


def _can_auto_prepare_bohrium_gromacs_package(step: dict) -> bool:
    skill_ids = _step_skill_ids(step)
    return bool(skill_ids.intersection({"polymer-21step-equilibration", "gromacs-bohrium"}))


def _step_skill_catalog(step: dict) -> str:
    skills = step.get("usedSkills") or []
    if not skills:
        return "（无）"
    lines: list[str] = []
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        scripts = ", ".join(str(script) for script in (skill.get("scripts") or [])) or "无脚本"
        lines.append(f"- {skill.get('id') or skill.get('name')}: {skill.get('reason', '')}；scripts: {scripts}")
    return "\n".join(lines) if lines else "（无）"


def _project_context_for_execution(execution: dict) -> tuple[dict | None, dict | None, str]:
    task = find_requirement_task(execution["requirementTaskId"])
    project = projects.find_project(task.get("projectId", "")) if task else None
    project_path = str((project or {}).get("rootDirectory", "")).strip() or "（未配置）"
    return task, project, project_path


def _prefer_gas_charges(value):
    if isinstance(value, dict):
        return {key: _prefer_gas_charges(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_prefer_gas_charges(item) for item in value]
    if isinstance(value, str):
        return (
            value.replace("AM1-BCC", "gas")
            .replace("am1-bcc", "gas")
            .replace("-c bcc", "-c gas")
            .replace(" c bcc", " c gas")
        )
    return value


def _local_step_for_prompt(step: dict) -> dict:
    """本地执行默认使用 gas 电荷，避免旧 spec 中 AM1-BCC 触发长时间 sqm。"""
    normalized = _prefer_gas_charges(json.loads(json.dumps(step, ensure_ascii=False)))
    parameters = normalized.setdefault("parameters", {})
    if isinstance(parameters, dict):
        parameters["chargeStrategy"] = "默认使用 gas 电荷；AmberTools antechamber 必须使用 -c gas，除非用户明确指定其它电荷模型。"
    return normalized


def _build_local_run_prompt(execution: dict, step: dict, spec: dict) -> str:
    modeling_spec = None
    task, _project, project_path = _project_context_for_execution(execution)
    if task:
        modeling_spec = (task.get("documents") or {}).get("modelingSpec")
    prompt_step = _local_step_for_prompt(step)
    return (
        "你是模拟计算执行助手。请根据下面的 workflow step，生成本地可执行/可交付的运行结果。\n"
        "要求：\n"
        "1. 可以先生成简短 plan，但不要停留在只读计划；随后必须实际运行本步骤所需命令并记录结果。\n"
        "2. 所有模拟工具命令必须在 `structure_build` conda 环境中执行；优先使用 `source /opt/mamba/etc/profile.d/conda.sh && conda activate structure_build && ...` 激活环境。\n"
        "3. 默认电荷模型为 gas；AmberTools `antechamber` 必须使用 `-c gas`，不要使用 bcc 电荷模型，除非用户明确指定。\n"
        "4. 在项目路径下创建/复用本步骤输出目录，保存脚本、输入文件、日志和生成文件；不要只把命令写在 Markdown 里。\n"
        "5. 如果工具、输入或参数缺失导致无法真实运行，请先运行最小检查命令证明缺失项，再明确停止原因和下一步。\n"
        "6. 输出 Markdown，包含：运行摘要、输入文件、已执行命令、日志要点、生成文件、下一步。\n\n"
        f"Execution ID: {execution.get('id')}\n"
        f"项目路径: {project_path}\n"
        f"体系摘要:\n{_system_summary(execution, modeling_spec)}\n\n"
        f"计算类型: {spec.get('calculationType', '')}\n"
        f"软件: {', '.join(str(item) for item in (spec.get('software') or []))}\n\n"
        f"当前步骤 JSON:\n```json\n{json.dumps(prompt_step, ensure_ascii=False, indent=2)}\n```\n\n"
        f"可用 Skills:\n{_step_skill_catalog(step)}\n"
    )


def _run_local_step(execution: dict, step: dict, spec: dict) -> tuple[str, str, list[str], list[dict]]:
    step_id = str(step.get("id", "step"))
    step_name = str(step.get("name") or step_id)
    _task, _project, project_path = _project_context_for_execution(execution)
    prompt = _build_local_run_prompt(execution, step, spec)
    logs = [
        f"准备本地 cursor-cli 运行步骤：{step_name}",
        "已生成发送给 cursor-cli 的 prompt。",
    ]
    prompt_artifact = _write_computation_artifact(
        execution, step_id, f"{step_id}-prompt.md", prompt, "prompt", "text/markdown"
    )
    result = ""
    status = "completed"
    summary = f"cursor-cli 本地运行完成：{step_name}"
    try:
        cli_settings = {
            **config.get_local_run_cli_settings(),
            "workspace": project_path if project_path != "（未配置）" else "",
            "mode": "agent",
            "force": True,
        }
        result = cli_client.call(
            [
                {"role": "system", "content": "你是严谨的模拟计算执行助手，只输出可执行结果和必要日志，不输出寒暄。"},
                {"role": "user", "content": prompt},
            ],
            cli_settings,
        )
        logs.append("cursor-cli 返回结果。")
        if _local_result_indicates_no_execution(result):
            status = "failed"
            summary = f"cursor-cli 本地运行未实际完成：{step_name}"
            logs.append("cursor-cli 返回内容表明未实际执行或未生成真实产物，已标记为失败。")
    except Exception as error:
        status = "failed"
        summary = f"cursor-cli 本地运行失败：{step_name}"
        logs.append(f"cursor-cli 调用失败：{error}")
    artifacts = [
        prompt_artifact,
        _write_computation_artifact(execution, step_id, f"{step_id}-run.log", "\n".join(logs), "log", "text/plain"),
    ]
    if result:
        artifacts.insert(
            1,
            _write_computation_artifact(
                execution,
                step_id,
                f"{step_id}-result.md",
                result,
                "result",
                "text/markdown",
            ),
        )
    return status, summary, logs, artifacts


def _local_result_indicates_no_execution(result: str) -> bool:
    text = str(result or "")
    markers = [
        "Ask mode",
        "只读检查",
        "不能写入文件",
        "未实际生成",
        "当前实际未发现",
        "未发现真实参数产物",
        "不能判定真实",
    ]
    return any(marker in text for marker in markers)


def _find_bohr() -> str | None:
    found = shutil.which("bohr")
    if found:
        return found
    candidate = Path.home() / ".bohrium" / "bohr"
    return str(candidate) if candidate.exists() else None


def _bohrium_env() -> dict:
    env = os.environ.copy()
    bohrium_bin = str(Path.home() / ".bohrium")
    env["PATH"] = f"{bohrium_bin}:{env.get('PATH', '')}"
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        text = bashrc.read_text(encoding="utf-8", errors="replace")
        for key in ("BOHRIUM_PROJECT_ID", "BOHRIUM_ACCESS_KEY", "PROJECT_ID", "ACCESS_KEY"):
            match = re.search(rf"^\s*(?:export\s+)?{key}\s*=\s*['\"]?([^'\"\n#]+)", text, re.MULTILINE)
            if match:
                env[key] = match.group(1).strip()
    access_key = env.get("ACCESS_KEY") or env.get("BOHRIUM_ACCESS_KEY")
    project_id = env.get("PROJECT_ID") or env.get("BOHRIUM_PROJECT_ID")
    if access_key:
        env["ACCESS_KEY"] = access_key
        env["BOHRIUM_ACCESS_KEY"] = access_key
    if project_id:
        env["PROJECT_ID"] = project_id
        env["BOHRIUM_PROJECT_ID"] = project_id
    return env


def _parse_bohrium_submit(stdout: str, stderr: str = "") -> dict:
    text = f"{stdout or ''}\n{stderr or ''}"
    remote: dict[str, str] = {}
    job_match = re.search(r"\bJobId\s*:\s*(\d+)", text, re.IGNORECASE)
    group_match = re.search(r"\bJobGroupId\s*:\s*(\d+)", text, re.IGNORECASE)
    if job_match:
        remote["jobId"] = job_match.group(1)
    if group_match:
        remote["jobGroupId"] = group_match.group(1)
    return remote


def _load_bohrium_status(job_id: str) -> dict | None:
    bohr = _find_bohr()
    if not bohr or not job_id:
        return None
    command = [bohr, "job", "describe", "-j", str(job_id), "--json"]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False, env=_bohrium_env())
    if completed.returncode != 0:
        return {
            "state": "unknown",
            "message": (completed.stderr or completed.stdout or "").strip(),
        }
    text = (completed.stdout or "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"raw": text}
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        payload = {"raw": str(payload)}
    status_value = next((payload[key] for key in ("status", "jobStatus", "state", "webStatus") if key in payload), None)
    status_text = str(
        next(
            (payload[key] for key in ("statusStr", "statusName", "status_name", "jobStatusName") if payload.get(key)),
            status_value if status_value is not None else "",
        )
    )
    message = str(
        next(
            (payload[key] for key in ("message", "reason", "errorInfo", "error", "raw") if payload.get(key)),
            "",
        )
    ).strip()
    normalized = status_text.lower()
    if status_value == 2 or normalized in {"2", "finished", "finish", "completed", "success", "succeeded"}:
        state = "completed"
    elif status_value == -1 or normalized in {"-1", "failed", "fail", "error", "terminated", "killed"}:
        state = "failed"
    else:
        state = "running"
    return {"state": state, "status": status_value, "statusName": status_text, "message": message}


def _load_bohrium_log_excerpt(job_id: str, limit: int = 12) -> list[str]:
    bohr = _find_bohr()
    if not bohr or not job_id:
        return []
    with tempfile.TemporaryDirectory() as tmp_dir:
        completed = subprocess.run(
            [bohr, "job", "log", "-j", str(job_id)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=_bohrium_env(),
            cwd=tmp_dir,
        )
        if completed.returncode != 0:
            text = (completed.stderr or completed.stdout or "").strip()
            return [f"Bohrium 日志下载失败：{text}"] if text else []
        log_files = sorted(Path(tmp_dir).glob(f"{job_id}_log/*"))
        lines: list[str] = []
        for path in log_files:
            if path.is_file():
                lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return [line for line in lines if line.strip()][-limit:]


def _bohrium_download_dir(execution: dict, step_id: str) -> Path | None:
    root = _local_run_root(execution, step_id)
    return root / "results" if root else None


def _result_artifact_kind(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if path.name == "job.done":
        return "result", "text/plain"
    if suffix in {".log", ".stdout"}:
        return "log", "text/plain"
    if suffix in {".gro", ".pdb"}:
        return "structure", "text/plain"
    if suffix in {".mdp", ".xvg"}:
        return "result", "text/plain"
    if suffix in {".edr", ".cpt", ".tpr", ".xtc", ".trr"}:
        return "binary", "application/octet-stream"
    return "result", "application/octet-stream"


def _collect_result_artifacts(execution: dict, step_id: str, output_dir: Path) -> list[dict]:
    if not output_dir.exists():
        return []
    artifacts: list[dict] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        kind, mime = _result_artifact_kind(path)
        artifacts.append(_attach_existing_computation_artifact(execution, step_id, path, kind, mime))
    return artifacts


def _download_bohrium_results(execution: dict, step_id: str, job_id: str) -> tuple[Path | None, list[dict], str]:
    bohr = _find_bohr()
    output_dir = _bohrium_download_dir(execution, step_id)
    if not bohr or not output_dir or not job_id:
        return output_dir, [], "缺少 bohr CLI 或下载目录，未下载结果"
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [bohr, "job", "download", "-j", str(job_id), "-o", str(output_dir)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=_bohrium_env(),
    )
    if completed.returncode != 0:
        return output_dir, [], (completed.stderr or completed.stdout or "Bohrium 结果下载失败").strip()
    artifacts = _collect_result_artifacts(execution, step_id, output_dir)
    return output_dir, artifacts, "Bohrium 结果已下载"


def _reconcile_bohrium_running_runs(execution: dict) -> bool:
    computation = _ensure_computation_module(execution)
    changed = False
    for step_id, run in list((computation.get("runs") or {}).items()):
        submitted_only = run.get("status") == "completed" and "Bohrium 已提交" in str(run.get("summary") or "")
        if run.get("runner") != "bohrium" or (run.get("status") != "running" and not submitted_only):
            continue
        remote = run.get("remote") or {}
        if not remote.get("jobId"):
            parsed = _parse_bohrium_submit("\n".join(str(line) for line in (run.get("logs") or [])))
            remote.update(parsed)
            if parsed:
                run["remote"] = remote
        job_id = str(remote.get("jobId") or "").strip()
        if not job_id:
            continue
        status = _load_bohrium_status(job_id)
        if not status or status.get("state") == "unknown":
            continue
        logs = list(run.get("logs") or [])
        if status["state"] == "completed":
            output_dir, downloaded_artifacts, download_message = _download_bohrium_results(execution, step_id, job_id)
            if output_dir:
                remote["downloadDir"] = str(output_dir)
            if downloaded_artifacts:
                existing_paths = {str(artifact.get("storagePath")) for artifact in (run.get("artifacts") or [])}
                run["artifacts"] = [
                    *(run.get("artifacts") or []),
                    *[artifact for artifact in downloaded_artifacts if str(artifact.get("storagePath")) not in existing_paths],
                ]
            logs.append(download_message)
            run["status"] = "completed"
            run["completedAt"] = current_timestamp()
            run["summary"] = f"Bohrium job 已完成：{run.get('stepName') or step_id}"
            logs.append(f"Bohrium job 已完成：{job_id}")
        elif status["state"] == "failed":
            run["status"] = "failed"
            run["completedAt"] = current_timestamp()
            reason = status.get("message") or status.get("statusName") or "远端任务失败"
            run["summary"] = f"Bohrium job 失败：{run.get('stepName') or step_id}"
            logs.append(f"Bohrium job 失败：{job_id} {reason}".strip())
            excerpt = _load_bohrium_log_excerpt(job_id)
            if excerpt:
                logs.append("Bohrium 失败日志片段：")
                logs.extend(excerpt)
        else:
            run["status"] = "running"
            run["completedAt"] = ""
            run["summary"] = f"Bohrium 已提交：{run.get('stepName') or step_id}，等待 job 完成"
            label = status.get("statusName") or status.get("status") or "running"
            latest = f"Bohrium job 状态：{job_id} {label}"
            if latest not in logs:
                logs.append(latest)
        run["logs"] = logs
        remote.update({k: v for k, v in status.items() if k != "state"})
        run["remote"] = remote
        computation.setdefault("runs", {})[step_id] = run
        changed = True
    if changed:
        run_statuses = [run.get("status") for run in (computation.get("runs") or {}).values()]
        if any(status == "failed" for status in run_statuses):
            computation["status"] = "failed"
            computation["detail"] = "Bohrium 远端任务失败"
        elif any(status == "running" for status in run_statuses):
            computation["status"] = "in_progress"
            computation["detail"] = "Bohrium 远端任务运行中"
        elif run_statuses and all(status == "completed" for status in run_statuses):
            computation["status"] = "completed"
            computation["detail"] = "模拟计算步骤已完成"
        execution["updatedAt"] = current_timestamp()
        save_execution(execution)
    if _sync_bohrium_run_statuses_to_steps(execution):
        changed = True
    return changed


def _sync_bohrium_run_statuses_to_steps(execution: dict) -> bool:
    task = find_requirement_task(execution.get("requirementTaskId", ""))
    if not task:
        return False
    spec = (task.get("documents") or {}).get("computationSpec") or {}
    changed = False
    for step_id, run in ((_ensure_computation_module(execution).get("runs") or {}).items()):
        if run.get("runner") != "bohrium":
            continue
        status = str(run.get("status") or "")
        if not status:
            continue
        step = _find_workflow_step(spec, step_id)
        if not step:
            continue
        before = {
            "status": step.get("status"),
            "runner": step.get("runner"),
            "lastRunId": step.get("lastRunId"),
            "completedAt": step.get("completedAt"),
            "runSummary": step.get("runSummary"),
        }
        _set_step_status(task, step_id, status, run)
        after = {
            "status": step.get("status"),
            "runner": step.get("runner"),
            "lastRunId": step.get("lastRunId"),
            "completedAt": step.get("completedAt"),
            "runSummary": step.get("runSummary"),
        }
        changed = changed or before != after
    return changed


def _write_bohrium_em_mdp(path: Path, step: dict) -> None:
    params = step.get("parameters") or {}
    nsteps_match = re.search(r"\d+", str(params.get("maxSteps") or "100000"))
    emtol_match = re.search(r"\d+(?:\.\d+)?", str(params.get("emtol") or "5000"))
    emstep_match = re.search(r"\d+(?:\.\d+)?", str(params.get("emstep") or "0.005"))
    nsteps = nsteps_match.group(0) if nsteps_match else "100000"
    emtol = emtol_match.group(0) if emtol_match else "5000"
    emstep = emstep_match.group(0) if emstep_match else "0.005"
    path.write_text(
        "\n".join(
            [
                "integrator               = steep",
                f"nsteps                   = {nsteps}",
                f"emtol                    = {emtol}",
                f"emstep                   = {emstep}",
                "nstlog                   = 1000",
                "nstenergy                = 100",
                "cutoff-scheme            = Verlet",
                "rlist                    = 1.0",
                "coulombtype              = PME",
                "rcoulomb                 = 1.0",
                "rvdw                     = 1.0",
                "DispCorr                 = EnerPres",
                "pbc                      = xyz",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_bohrium_md_mdp(
    path: Path,
    nsteps: int,
    dt: float,
    temp: int,
    pcoupl: str,
    press: int | None,
    *,
    tau_p: float = 2.0,
    gen_vel: bool = False,
) -> None:
    lines = [
        "integrator               = md",
        f"nsteps                   = {nsteps}",
        f"dt                       = {dt}",
        "",
        "nstxout                  = 0",
        "nstvout                  = 0",
        "nstfout                  = 0",
        "nstlog                   = 1000",
        "nstenergy                = 1000",
        "nstcalcenergy            = 100",
        "",
        "cutoff-scheme            = Verlet",
        "rlist                    = 1.0",
        "coulombtype              = PME",
        "rcoulomb                 = 1.0",
        "rvdw                     = 1.0",
        "DispCorr                 = EnerPres",
        "",
        "tcoupl                   = v-rescale",
        "tc-grps                  = system",
        "tau_t                    = 0.1",
        f"ref_t                    = {temp}",
        "",
        "gen_vel                  = yes" if gen_vel else "gen_vel                  = no",
        f"gen_temp                 = {temp}" if gen_vel else "continuation             = yes",
        "gen_seed                 = -1" if gen_vel else "",
        "continuation             = no" if gen_vel else "",
    ]
    if pcoupl == "no":
        lines.extend(["", "pcoupl                   = no"])
    else:
        pcoupl_type = "Parrinello-Rahman" if "parrinello" in pcoupl.lower() else "Berendsen"
        lines.extend(
            [
                "",
                f"pcoupl                   = {pcoupl_type}",
                "pcoupltype               = isotropic",
                f"tau_p                    = {tau_p}",
                f"ref_p                    = {press}",
                "compressibility          = 4.5e-5",
            ]
        )
    lines.extend(
        [
            "",
            "constraint_algorithm     = lincs",
            "constraints              = h-bonds",
            "lincs_iter               = 1",
            "lincs_order              = 4",
            "",
            "pbc                      = xyz",
            "",
        ]
    )
    path.write_text("\n".join(line for line in lines if line != ""), encoding="utf-8")


def _write_bohrium_polymer_21step_mdps(input_dir: Path, step: dict) -> list[str]:
    _write_bohrium_em_mdp(input_dir / "em.mdp", step)
    _write_bohrium_em_mdp(input_dir / "em2.mdp", step)
    protocol = [
        (1, "NVT", 600, None, 50, 0.001),
        (2, "NVT", 300, None, 100, 0.001),
        (3, "NPT", 300, 1000, 50, 0.001),
        (4, "NVT", 600, None, 50, 0.001),
        (5, "NVT", 300, None, 100, 0.001),
        (6, "NPT", 300, 30000, 50, 0.001),
        (7, "NVT", 600, None, 50, 0.001),
        (8, "NVT", 300, None, 100, 0.001),
        (9, "NPT", 300, 50000, 50, 0.001),
        (10, "NVT", 600, None, 50, 0.001),
        (11, "NVT", 300, None, 100, 0.001),
        (12, "NPT", 300, 25000, 50, 0.001),
        (13, "NVT", 600, None, 50, 0.001),
        (14, "NVT", 300, None, 100, 0.001),
        (15, "NPT", 300, 5000, 50, 0.001),
        (16, "NVT", 600, None, 50, 0.001),
        (17, "NVT", 300, None, 100, 0.001),
        (18, "NPT", 300, 500, 50, 0.001),
        (19, "NVT", 600, None, 50, 0.001),
        (20, "NVT", 300, None, 100, 0.001),
        (21, "NPT", 298, 1, 800, 0.001),
    ]
    step_names: list[str] = []
    for index, ensemble, temp, press, duration_ps, dt in protocol:
        name = f"{index}{ensemble.lower()}"
        step_names.append(name)
        _write_bohrium_md_mdp(
            input_dir / f"{name}.mdp",
            int(duration_ps / dt),
            dt,
            temp,
            "no" if ensemble == "NVT" else ("parrinello-rahman" if index == 21 else "berendsen"),
            press,
            tau_p=5.0 if index == 21 else 2.0,
            gen_vel=index == 1,
        )
    return step_names


def _find_dependency_topology_dir(execution: dict, step: dict) -> Path | None:
    for dep_id in reversed([str(item) for item in (step.get("dependsOn") or []) if str(item).strip()]):
        root = _local_run_root(execution, dep_id)
        topology = root / "topology" if root else None
        if topology and (topology / "system.top").exists():
            return topology
    for artifact in reversed((_ensure_computation_module(execution).get("artifacts") or [])):
        if artifact.get("kind") != "topology":
            continue
        path = Path(str(artifact.get("storagePath") or ""))
        if path.name == "system.top" and path.exists():
            return path.parent
    return None


def _prepare_bohrium_gromacs_package(execution: dict, step: dict) -> tuple[Path, Path, list[dict]]:
    step_id = str(step.get("id", "step"))
    root = _local_run_root(execution, step_id)
    if root is None:
        raise ValueError("项目路径未配置，无法生成 Bohrium 输入目录")
    topology = _find_dependency_topology_dir(execution, step)
    if topology is None:
        raise ValueError("未找到依赖步骤生成的 system.top 拓扑目录")
    structure = topology / "system_sanitized.gro"
    if not structure.exists():
        structure = topology / "system.gro"
    if not structure.exists():
        raise ValueError("未找到可提交的 GROMACS 坐标文件 system_sanitized.gro/system.gro")

    input_dir = root / "bohrium-input"
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(topology / "system.top", input_dir / "system.top")
    shutil.copy2(topology / "system.top", input_dir / "topol.top")
    shutil.copy2(structure, input_dir / "system_sanitized.gro")
    for itp in sorted(topology.glob("*.itp")):
        shutil.copy2(itp, input_dir / itp.name)
    md_steps = _write_bohrium_polymer_21step_mdps(input_dir, step)
    steps_literal = " ".join(f'"{name}"' for name in md_steps)
    run_sh = input_dir / "run.sh"
    run_sh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "mkdir -p results\n"
        "collect_results() {\n"
        "  cp *.log *.stdout *.tpr *.gro *.edr *.cpt *.mdp results/ 2>/dev/null || true\n"
        "}\n"
        "trap collect_results EXIT\n"
        "export OMPI_ALLOW_RUN_AS_ROOT=1\n"
        "export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1\n"
        "export PATH=.:$PATH\n"
        "if command -v gmx_mpi >/dev/null 2>&1; then\n"
        "  GMX=gmx_mpi\n"
        "elif command -v gmx >/dev/null 2>&1; then\n"
        "  GMX=gmx\n"
        "else\n"
        "  echo 'GROMACS executable not found: expected gmx_mpi or gmx in PATH' >&2\n"
        "  exit 127\n"
        "fi\n"
        "$GMX grompp -f em.mdp -o em.tpr -p topol.top -c system_sanitized.gro -maxwarn 10\n"
        "$GMX mdrun -v -deffnm em -gpu_id 0\n"
        "$GMX grompp -f em2.mdp -o em2.tpr -p topol.top -c em.gro -maxwarn 10\n"
        "$GMX mdrun -v -deffnm em2 -gpu_id 0\n"
        "oldgroname=em2\n"
        f"steps=({steps_literal})\n"
        "for i in \"${steps[@]}\"; do\n"
        "  $GMX grompp -f $i.mdp -o $i.tpr -p topol.top -c $oldgroname.gro -maxwarn 10\n"
        "  $GMX mdrun -v -deffnm $i -nstlist 80 -gpu_id 0\n"
        "  oldgroname=$i\n"
        "done\n"
        "echo done > results/job.done\n",
        encoding="utf-8",
    )
    run_sh.chmod(0o755)

    env = _bohrium_env()
    project_id = str(env.get("BOHRIUM_PROJECT_ID") or "").strip()
    job = {
        "job_name": f"{execution.get('id')}-{step_id}-{step.get('name') or 'gromacs'}",
        "job_type": "container",
        "image_address": "registry.dp.tech/dptech/dp/native/prod-405785/gromacs:25.4",
        "machine_type": "c4_m15_1 * NVIDIA T4",
        "command": "bash run.sh",
        "result_path": "results",
        "max_reschedule_times": 1,
    }
    if project_id:
        job["project_id"] = int(project_id) if project_id.isdigit() else project_id
    job_json = root / "job.json"
    job_json.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts = [
        _attach_existing_computation_artifact(execution, step_id, job_json, "job", "application/json"),
        _attach_existing_computation_artifact(execution, step_id, run_sh, "script", "text/x-shellscript"),
        _attach_existing_computation_artifact(execution, step_id, input_dir / "em.mdp", "input", "text/plain"),
    ]
    return job_json, input_dir, artifacts


def _run_bohrium_step(execution: dict, step: dict, spec: dict) -> tuple[str, str, list[str], list[dict], dict]:
    step_id = str(step.get("id", "step"))
    step_name = str(step.get("name") or step_id)
    scripts = _step_scripts(step)
    logs = [f"准备 Bohrium 运行步骤：{step_name}"]
    can_auto_prepare = _can_auto_prepare_bohrium_gromacs_package(step)
    if not scripts and not can_auto_prepare:
        logs.append("未找到可提交到 Bohrium 的脚本；请在该步骤 usedSkills.scripts 中提供脚本路径。")
        return "failed", "Bohrium 运行失败：未找到可提交脚本", logs, [], {}
    manifest = {
        "stepId": step_id,
        "stepName": step_name,
        "scripts": scripts,
        "projectIdEnv": "BOHRIUM_PROJECT_ID",
        "accessKeyEnv": "BOHRIUM_ACCESS_KEY",
    }
    artifacts = [
        _write_computation_artifact(
            execution,
            step_id,
            f"{step_id}-bohrium-submit.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
            "job",
            "application/json",
        )
    ]
    params = step.get("parameters") or {}
    job_json = str(params.get("jobJson") or params.get("job_json") or "").strip()
    input_dir = str(params.get("inputDir") or params.get("input_dir") or "").strip()
    if not job_json or not input_dir:
        try:
            prepared_job_json, prepared_input_dir, prepared_artifacts = _prepare_bohrium_gromacs_package(execution, step)
            job_json = str(prepared_job_json)
            input_dir = str(prepared_input_dir)
            artifacts.extend(prepared_artifacts)
            logs.append(f"自动生成 Bohrium GROMACS 提交包：{input_dir}")
        except Exception as error:
            logs.append(f"缺少 Bohrium 提交所需的 jobJson/inputDir，且自动生成提交包失败：{error}")
            return "failed", "Bohrium 运行失败：缺少 jobJson/inputDir", logs, artifacts, {}
    bohr = _find_bohr()
    if not bohr:
        logs.append("未检测到 bohr CLI，已生成提交清单但未提交任务。")
        return "failed", "Bohrium 运行失败：未检测到 bohr CLI", logs, artifacts, {}
    command = [bohr, "job", "submit", "-i", job_json, "-p", input_dir]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False, env=_bohrium_env())
    logs.append("$ " + " ".join(command))
    if completed.stdout.strip():
        logs.append(completed.stdout.strip())
    if completed.stderr.strip():
        logs.append(completed.stderr.strip())
    if completed.returncode != 0:
        return "failed", f"Bohrium 提交失败：{step_name}", logs, artifacts, {}
    remote = _parse_bohrium_submit(completed.stdout, completed.stderr)
    if remote.get("jobId"):
        logs.append(f"Bohrium job 已提交：{remote['jobId']}，等待 Bohrium job 完成。")
    else:
        logs.append("Bohrium 提交成功，但未解析到 JobId；等待后续人工确认。")
    return "running", f"Bohrium 已提交：{step_name}，等待 job 完成", logs, artifacts, remote


def _set_step_status(task: dict, step_id: str, status: str, run: dict) -> None:
    spec = (task.get("documents") or {}).get("computationSpec") or {}
    step = _find_workflow_step(spec, step_id)
    if not step:
        return
    step["status"] = status
    step["runner"] = run.get("runner", "")
    step["lastRunId"] = run.get("id", "")
    step["startedAt"] = run.get("startedAt", "")
    step["completedAt"] = run.get("completedAt", "")
    step["runSummary"] = run.get("summary", "")
    step["actualOutputs"] = [
        {"artifactId": artifact.get("id"), "name": artifact.get("name"), "kind": artifact.get("kind")}
        for artifact in run.get("artifacts") or []
    ]
    save_requirement_task(task)


def terminate_computation_step(execution_id: str, step_id: str) -> dict:
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    task, spec = _computation_spec_for_execution(execution)
    step_id = str(step_id or "").strip()
    if not _find_workflow_step(spec, step_id):
        raise ValueError("computation step not found")

    computation = _ensure_computation_module(execution)
    run = (computation.get("runs") or {}).get(step_id)
    if not run:
        raise ValueError("computation step has no running job")
    if run.get("runner") != "bohrium":
        raise ValueError("only Bohrium computation steps can be terminated")
    if run.get("status") != "running":
        raise ValueError("Bohrium job is not running")
    job_id = str((run.get("remote") or {}).get("jobId") or "").strip()
    if not job_id:
        raise ValueError("Bohrium job id is missing")
    bohr = _find_bohr()
    if not bohr:
        raise ValueError("未检测到 bohr CLI，无法终止 Bohrium job")

    completed = subprocess.run(
        [bohr, "job", "terminate", job_id],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_bohrium_env(),
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "Bohrium job 终止失败").strip()
        raise ValueError(message)

    completed_at = current_timestamp()
    logs = list(run.get("logs") or [])
    logs.append(f"Bohrium job 已终止：{job_id}")
    if completed.stdout.strip():
        logs.append(completed.stdout.strip())
    run.update(
        {
            "status": "failed",
            "completedAt": completed_at,
            "summary": f"Bohrium job 已终止：{run.get('stepName') or step_id}",
            "logs": logs,
        }
    )
    computation.setdefault("runs", {})[step_id] = run
    computation["status"] = "failed"
    computation["detail"] = run["summary"]
    computation["currentStepId"] = step_id
    execution["updatedAt"] = completed_at
    _set_step_status(task, step_id, "failed", run)
    save_execution(execution)
    return {"execution": execution, "run": run, "computationSpec": task.get("documents", {}).get("computationSpec")}


def run_computation_step(execution_id: str, step_id: str, runner: str = "local") -> dict:
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    if not (execution.get("modules", {}).get("modeling", {}).get("system") or {}).get("content"):
        raise ValueError("system is not assembled yet")
    task, spec = _computation_spec_for_execution(execution)
    step_id = str(step_id or "").strip()
    step = _find_workflow_step(spec, step_id)
    if not step:
        raise ValueError("computation step not found")
    runner = str(runner or "local").strip() or "local"
    if runner not in {"local", "bohrium"}:
        raise ValueError("unknown computation runner")

    computation = _ensure_computation_module(execution)
    computation.setdefault("runnerSelections", {})[step_id] = runner
    computation["currentStepId"] = step_id
    computation["status"] = "in_progress"
    computation["detail"] = f"正在运行：{step.get('name') or step_id}"
    now = current_timestamp()
    run = {
        "id": f"run-{step_id}-{len(computation.get('runs') or {}) + 1}",
        "stepId": step_id,
        "stepName": step.get("name", step_id),
        "runner": runner,
        "status": "running",
        "logs": [f"{now} 开始运行"],
        "summary": "",
        "artifacts": [],
        "startedAt": now,
        "completedAt": "",
    }
    computation.setdefault("runs", {})[step_id] = run
    execution["updatedAt"] = now
    save_execution(execution)

    remote: dict = {}
    if runner == "bohrium":
        status, summary, logs, artifacts, remote = _run_bohrium_step(execution, step, spec)
    else:
        status, summary, logs, artifacts = _run_local_step(execution, step, spec)
    completed_at = current_timestamp()
    run_update = {
        "status": status,
        "logs": [*run["logs"], *logs],
        "summary": summary,
        "artifacts": artifacts,
        "completedAt": "" if status == "running" else completed_at,
    }
    if remote:
        run_update["remote"] = remote
    run.update(run_update)
    if runner == "local":
        run = _merge_local_run_outputs(execution, step_id, run)
    computation["runs"][step_id] = run
    computation["status"] = "failed" if status == "failed" else ("in_progress" if status == "running" else "completed")
    computation["detail"] = summary
    execution["updatedAt"] = completed_at
    _set_step_status(task, step_id, status, run)
    save_execution(execution)
    return {"execution": execution, "run": run, "computationSpec": task.get("documents", {}).get("computationSpec")}


def run_all_computation_steps(
    execution_id: str,
    default_runner: str = "local",
    runner_overrides: dict | None = None,
) -> dict:
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    _task, spec = _computation_spec_for_execution(execution)
    runs: list[dict] = []
    overrides = runner_overrides or {}
    for step in spec.get("workflowSteps") or []:
        step_id = str(step.get("id", "")).strip()
        runner = str(overrides.get(step_id) or default_runner or "local")
        result = run_computation_step(execution_id, step_id, runner)
        runs.append(result["run"])
        execution = result["execution"]
        if result["run"].get("status") == "failed":
            break
    task = find_requirement_task(execution["requirementTaskId"])
    return {
        "execution": execution,
        "runs": runs,
        "computationSpec": (task.get("documents", {}) or {}).get("computationSpec") if task else None,
    }


def materialize_execution_files(execution_id: str) -> dict:
    """把已有 execution 中的结构/计算产物同步到项目 rootDirectory。"""
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    modeling = execution.get("modules", {}).get("modeling", {})
    for mol in modeling.get("molecules") or []:
        if mol.get("content") and mol.get("id"):
            mol["filePath"] = _write_modeling_structure(
                execution,
                mol,
                ["03-modeling", "molecules", f"{mol['id']}.{mol.get('format', 'pdb')}"],
            )
    system = modeling.get("system")
    if system and system.get("content"):
        system["filePath"] = _write_modeling_structure(
            execution,
            system,
            ["03-modeling", "system", system.get("name", "system.pdb")],
        )
    execution["updatedAt"] = current_timestamp()
    save_execution(execution)
    return migrate_computation_artifact_layout(execution_id)


def stream_computation(execution_id: str, payload: dict):
    """细化模拟计算流程：要求体系已组装，基于 computationSpec 结合真实体系微调参数。

    产出类型：``step``、``content``/``reasoning``（模型增量）、``done``（附轻量 execution）。
    """
    execution = find_execution(execution_id)
    if execution is None:
        raise KeyError("execution not found")
    model_choice = str(payload.get("model", "")).strip() or None

    modeling = execution["modules"]["modeling"]
    if not (modeling.get("system") or {}).get("content"):
        raise ValueError("system is not assembled yet")

    task = find_requirement_task(execution["requirementTaskId"])
    if task is None:
        raise KeyError("requirement task not found")
    plan_text = _plan_content(task)
    spec_doc = (task.get("documents") or {}).get("computationSpec")
    if not spec_doc or not (spec_doc.get("workflowSteps") or []):
        task = generate_requirement_computation_spec(task["id"], model_choice)
        spec_doc = task.get("documents", {}).get("computationSpec") or {}
    modeling_spec = (task.get("documents", {}) or {}).get("modelingSpec")

    computation = execution["modules"]["computation"]
    if not computation.get("modelInput"):
        model_input = _build_model_input(modeling, modeling.get("system") or {})
        manifest_path = _write_computation_model_input(task, model_input)
        model_input["manifestPath"] = manifest_path
        _write_computation_model_input(task, model_input)
        computation["modelInput"] = model_input
    computation["status"] = "in_progress"
    computation["detail"] = "正在细化模拟计算流程"
    now = current_timestamp()
    execution["conversation"].append(
        {"role": "user", "content": "开始模拟计算：依据体系与方案细化计算流程参数。", "createdAt": now}
    )
    execution["updatedAt"] = now
    save_execution(execution)
    yield {"type": "step", "stage": "computation", "label": "细化模拟计算流程", "execution": _sse_execution(execution)}

    parts: list[str] = []
    context = {
        "plan_text": plan_text,
        "system_summary": _system_summary(execution, modeling_spec),
        "model_input": computation.get("modelInput") or {},
        "computation_spec": {k: v for k, v in spec_doc.items() if k not in ("planVersionId", "generatedAt", "refinedAt")},
    }
    for delta in stream_skill("refine_computation_spec", context, model_choice):
        if delta.get("type") == "content":
            parts.append(delta["text"])
        yield delta
    content = "".join(parts).strip()
    now = current_timestamp()
    if content:
        parsed = _parse_spec_json(content) or {}
        refined = _normalize_computation_spec(parsed if parsed.get("workflowSteps") else spec_doc)
        for step in refined.get("workflowSteps", []):
            step["status"] = "pending"
        plan_doc = task.get("documents", {}).get("plan", {})
        task.setdefault("documents", {})["computationSpec"] = {
            **refined,
            "modelInput": computation.get("modelInput") or {},
            "planVersionId": plan_doc.get("currentVersionId", spec_doc.get("planVersionId", "")),
            "generatedAt": spec_doc.get("generatedAt", now),
            "refinedAt": now,
        }
        save_requirement_task(task)
        computation["refined"] = True
        computation["status"] = "pending"
        computation["detail"] = f"已细化 {len(refined.get('workflowSteps', []))} 个计算步骤，待运行计算步骤"
        projects.advance_project_stage(task.get("projectId", ""), "模拟计算")
    else:
        computation["status"] = "pending"
        computation["detail"] = "未生成计算流程，请重试"
    execution["conversation"].append(
        {
            "role": "assistant",
            "content": content or "（未生成计算流程）",
            "createdAt": now,
            "usedSkills": [_modeling_skill("refine_computation_spec", "Refine Computation Spec", "基于已组装体系细化模拟计算流程")],
        }
    )
    execution["updatedAt"] = now
    save_execution(execution)
    yield {"type": "done", "execution": _sse_execution(execution), "computationSpec": task.get("documents", {}).get("computationSpec")}
