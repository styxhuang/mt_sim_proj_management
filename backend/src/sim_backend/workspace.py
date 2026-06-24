"""工作台轻量聚合 API。"""

from . import executions, projects, requirements


def project_summary(project: dict) -> dict:
    return {
        "id": project["id"],
        "name": project["name"],
        "customer": project["customer"],
        "amount": project["amount"],
        "currentStage": project["currentStage"],
        "progress": project["progress"],
        "plannedDeliveryDate": project["plannedDeliveryDate"],
        "status": project["status"],
        "packageStatus": project["packageStatus"],
        "rootDirectory": project["rootDirectory"],
        "template": project.get("template", ""),
        "description": project.get("description", ""),
    }


def get_workspace_summary(project_id: str) -> dict:
    project = projects.find_project(project_id)
    if project is None:
        raise KeyError("project not found")

    task = requirements.find_requirement_task_by_project(project_id)
    execution = executions.find_execution_by_task(task["id"]) if task else None

    task_flags = requirements.task_summary(task)
    exec_summary = executions.execution_summary(execution) if execution else None

    modeling = (execution or {}).get("modules", {}).get("modeling", {}) if execution else {}
    has_system = bool((modeling.get("system") or {}).get("content"))

    computation = (execution or {}).get("modules", {}).get("computation", {}) if execution else {}
    comp_spec = (task or {}).get("documents", {}).get("computationSpec") if task else None
    steps = (comp_spec or {}).get("workflowSteps") or []
    computation_done = bool(steps) and all(str(s.get("status")) == "completed" for s in steps)

    return {
        "project": project_summary(project),
        "flags": {
            "hasAnalysis": bool(task_flags and task_flags.get("hasAnalysis")),
            "hasPlan": bool(task_flags and task_flags.get("hasPlan")),
            "hasModelingSpec": bool(task_flags and task_flags.get("hasModelingSpec")),
            "hasComputationSpec": bool(task_flags and task_flags.get("hasComputationSpec")),
            "hasSystem": has_system,
            "computationRefined": bool(computation.get("refined")),
            "computationDone": computation_done,
        },
        "requirementTask": task_flags,
        "execution": exec_summary,
    }
