"""项目领域逻辑与种子数据。

``PROJECTS`` 为运行期内存状态，导入时从数据库加载。其它模块通过
``projects.PROJECTS`` 动态访问，测试也可直接替换该属性。
"""

import json
import sqlite3
from pathlib import Path

from . import config
from .database import (
    deserialize_json,
    get_connection,
    initialize_database,
    serialize_json,
)


STAGE_ORDER = ["立项", "需求解析", "方案确认", "建模", "模拟计算", "交付"]

STAGE_PROGRESS = {
    "立项": 5,
    "需求解析": 20,
    "方案确认": 40,
    "建模": 60,
    "模拟计算": 80,
    "交付": 95,
}

LEGACY_STAGE_MAP = {
    "建模执行": "建模",
}


def normalize_stage(stage: str) -> str:
    stage = str(stage or "").strip()
    return LEGACY_STAGE_MAP.get(stage, stage)


def normalize_root_directory(root_directory: str, project_id: str) -> str:
    raw = str(root_directory or "").strip()
    if not raw:
        return raw
    project_id = str(project_id or "").strip()
    path = Path(raw)
    name = path.name
    if name and not name.isascii() and project_id:
        return str(path.with_name(project_id))
    return raw

DEFAULT_PROJECTS = [
    {
        "id": "p-001",
        "name": "锂电电解液扩散模拟",
        "customer": "华东新能源",
        "amount": 42,
        "currentStage": "模拟计算",
        "progress": 72,
        "plannedDeliveryDate": "2026-06-14",
        "status": "进行中",
        "packageStatus": "待打包",
        "rootDirectory": "/data/projects/p-001",
        "template": "标准扩散模板",
        "description": "评估不同温度条件下电解液扩散速率和迁移趋势。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "需求解析", "status": "已完成"},
            {"name": "方案确认", "status": "已完成"},
            {"name": "建模", "status": "已完成"},
            {"name": "模拟计算", "status": "进行中"},
            {"name": "交付", "status": "未开始"},
        ],
        "deliveryChecklist": [
            {"name": "分析报告", "status": "待完成"},
            {"name": "结果图表", "status": "已完成"},
            {"name": "原始数据", "status": "待整理"},
            {"name": "说明文档", "status": "待完成"},
        ],
        "packageRecords": [
            {"version": "v0.9", "date": "2026-06-06", "type": "内部预审包"},
        ],
    },
    {
        "id": "p-002",
        "name": "高分子膜界面稳定性计算",
        "customer": "南方材料",
        "amount": 58,
        "currentStage": "交付",
        "progress": 82,
        "plannedDeliveryDate": "2026-06-09",
        "status": "临近交付",
        "packageStatus": "可打包",
        "rootDirectory": "/data/projects/p-002",
        "template": "界面分析模板",
        "description": "分析膜材料在不同电场条件下的界面稳定性表现。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "需求解析", "status": "已完成"},
            {"name": "方案确认", "status": "已完成"},
            {"name": "建模", "status": "已完成"},
            {"name": "模拟计算", "status": "已完成"},
            {"name": "交付", "status": "进行中"},
        ],
        "deliveryChecklist": [
            {"name": "分析报告", "status": "已完成"},
            {"name": "结果图表", "status": "已完成"},
            {"name": "原始数据", "status": "已完成"},
            {"name": "说明文档", "status": "待确认"},
        ],
        "packageRecords": [
            {"version": "v1.0-rc1", "date": "2026-06-07", "type": "客户交付包"},
        ],
    },
    {
        "id": "p-003",
        "name": "催化位点吸附能扫描",
        "customer": "西部催化",
        "amount": 33,
        "currentStage": "方案确认",
        "progress": 35,
        "plannedDeliveryDate": "2026-06-21",
        "status": "进行中",
        "packageStatus": "未开始",
        "rootDirectory": "/data/projects/p-003",
        "template": "吸附能扫描模板",
        "description": "比较多种位点构型下关键中间体的吸附能分布。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "需求解析", "status": "已完成"},
            {"name": "方案确认", "status": "进行中"},
            {"name": "建模", "status": "未开始"},
            {"name": "模拟计算", "status": "未开始"},
            {"name": "交付", "status": "未开始"},
        ],
        "deliveryChecklist": [
            {"name": "分析报告", "status": "未开始"},
            {"name": "结果图表", "status": "未开始"},
            {"name": "原始数据", "status": "未开始"},
            {"name": "说明文档", "status": "未开始"},
        ],
        "packageRecords": [],
    },
]


def project_to_database_values(project: dict) -> tuple:
    return (
        str(project["id"]),
        str(project["name"]),
        str(project["customer"]),
        int(project["amount"]),
        str(project["currentStage"]),
        int(project["progress"]),
        str(project["plannedDeliveryDate"]),
        str(project["status"]),
        str(project["packageStatus"]),
        str(project["rootDirectory"]),
        str(project["template"]),
        str(project["description"]),
        serialize_json(project.get("stageTimeline", [])),
        serialize_json(project.get("deliveryChecklist", [])),
        serialize_json(project.get("packageRecords", [])),
    )


def database_row_to_project(row: sqlite3.Row) -> dict:
    stage = normalize_stage(row["current_stage"])
    return {
        "id": row["id"],
        "name": row["name"],
        "customer": row["customer"],
        "amount": row["amount"],
        "currentStage": stage,
        "progress": row["progress"],
        "plannedDeliveryDate": row["planned_delivery_date"],
        "status": row["status"],
        "packageStatus": row["package_status"],
        "rootDirectory": row["root_directory"],
        "template": row["template"],
        "description": row["description"],
        "stageTimeline": _normalize_timeline(deserialize_json(row["stage_timeline"])),
        "deliveryChecklist": deserialize_json(row["delivery_checklist"]),
        "packageRecords": deserialize_json(row["package_records"]),
    }


def load_seed_projects() -> list[dict]:
    if config.LEGACY_DATA_FILE.exists():
        return json.loads(config.LEGACY_DATA_FILE.read_text(encoding="utf-8"))
    return DEFAULT_PROJECTS


def load_projects() -> list[dict]:
    initialize_database()
    with get_connection() as connection:
        project_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]

    if project_count == 0:
        save_projects(load_seed_projects())

    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM projects ORDER BY id").fetchall()
    return [database_row_to_project(row) for row in rows]


def save_projects(projects: list[dict]) -> None:
    initialize_database()
    with get_connection() as connection:
        connection.execute("DELETE FROM projects")
        connection.executemany(
            """
            INSERT INTO projects (
                id, name, customer, amount, current_stage, progress,
                planned_delivery_date, status, package_status, root_directory,
                template, description, stage_timeline, delivery_checklist,
                package_records
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [project_to_database_values(project) for project in projects],
        )


def build_new_project(payload: dict, project_id: str) -> dict:
    name = str(payload.get("name", "")).strip()
    customer = str(payload.get("customer", "")).strip()
    description = str(payload.get("description", "")).strip()
    template = str(payload.get("template", "")).strip() or "标准计算项目"
    planned_delivery_date = str(payload.get("plannedDeliveryDate", "")).strip()
    root_directory = normalize_root_directory(payload.get("rootDirectory", ""), project_id)

    return {
        "id": project_id,
        "name": name,
        "customer": customer,
        "amount": int(payload["amount"]),
        "currentStage": "立项",
        "progress": 5,
        "plannedDeliveryDate": planned_delivery_date,
        "status": "进行中",
        "packageStatus": "未开始",
        "rootDirectory": root_directory,
        "template": template,
        "description": description or "新建项目，等待补充详细计算说明。",
        "stageTimeline": build_stage_timeline("立项"),
        "deliveryChecklist": [
            {"name": "分析报告", "status": "未开始"},
            {"name": "结果图表", "status": "未开始"},
            {"name": "原始数据", "status": "未开始"},
            {"name": "说明文档", "status": "未开始"},
        ],
        "packageRecords": [],
    }


def next_project_id(projects: list[dict]) -> str:
    numeric_ids = []
    for project in projects:
        suffix = str(project.get("id", "")).replace("p-", "")
        if suffix.isdigit():
            numeric_ids.append(int(suffix))
    next_value = max(numeric_ids, default=0) + 1
    return f"p-{next_value:03d}"


def find_project(project_id: str) -> dict | None:
    return next((item for item in PROJECTS if item["id"] == project_id), None)


def _normalize_timeline(timeline: list) -> list[dict]:
    result = []
    for item in timeline or []:
        if not isinstance(item, dict):
            continue
        name = normalize_stage(str(item.get("name", "")))
        result.append({**item, "name": name})
    return result


def build_stage_timeline(current_stage: str) -> list[dict]:
    timeline = []
    current_stage = normalize_stage(current_stage)
    current_index = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else -1
    for index, stage in enumerate(STAGE_ORDER):
        if current_index == -1:
            status = "未开始"
        elif index < current_index:
            status = "已完成"
        elif index == current_index:
            status = "进行中"
        else:
            status = "未开始"
        timeline.append({"name": stage, "status": status})
    return timeline


def save_project_updates() -> None:
    save_projects(PROJECTS)


def advance_project_stage(project_id: str, stage: str) -> dict | None:
    """把项目阶段向前推进到 ``stage``（只前进不回退）。

    用于在需求解析产出方案、执行组装体系等里程碑达成时自动同步项目进度，
    让仪表盘/项目列表无需手填即可反映真实进展。
    """
    stage = normalize_stage(stage)
    if not project_id or stage not in STAGE_ORDER:
        return None
    project = find_project(project_id)
    if project is None:
        return None

    current_stage = normalize_stage(str(project.get("currentStage", "")))
    project["currentStage"] = current_stage
    current_index = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else -1
    target_index = STAGE_ORDER.index(stage)
    if target_index <= current_index:
        return project

    project["currentStage"] = stage
    project["progress"] = max(
        int(project.get("progress", 0)),
        STAGE_PROGRESS.get(stage, int(project.get("progress", 0))),
    )
    project["stageTimeline"] = build_stage_timeline(stage)
    save_project_updates()
    return project


def update_project_fields(project_id: str, payload: dict) -> dict:
    project = find_project(project_id)
    if project is None:
        raise KeyError("project not found")

    editable_fields = {
        "amount",
        "currentStage",
        "progress",
        "plannedDeliveryDate",
        "status",
        "packageStatus",
        "rootDirectory",
        "description",
        "customer",
    }
    for field in editable_fields:
        if field not in payload:
            continue
        if field == "rootDirectory":
            project[field] = normalize_root_directory(payload[field], project_id)
        else:
            project[field] = payload[field]

    if "currentStage" in payload:
        project["currentStage"] = normalize_stage(str(project["currentStage"]))
        project["stageTimeline"] = build_stage_timeline(str(project["currentStage"]))

    save_project_updates()
    return project


def replace_delivery_checklist(project_id: str, checklist: list[dict]) -> dict:
    project = find_project(project_id)
    if project is None:
        raise KeyError("project not found")

    project["deliveryChecklist"] = [
        {"name": str(item["name"]), "status": str(item["status"])}
        for item in checklist
    ]
    save_project_updates()
    return project


def add_package_record(project_id: str, record: dict) -> dict:
    project = find_project(project_id)
    if project is None:
        raise KeyError("project not found")

    package_record = {
        "version": str(record["version"]).strip(),
        "date": str(record["date"]).strip(),
        "type": str(record["type"]).strip(),
    }
    project.setdefault("packageRecords", []).append(package_record)
    save_project_updates()
    return project


def delete_projects(project_ids: list[str]) -> list[str]:
    """删除指定项目并持久化剩余项目。"""
    requested_ids = {
        str(project_id).strip()
        for project_id in project_ids
        if str(project_id).strip()
    }
    if not requested_ids:
        raise ValueError("ids must contain at least one project id")

    existing_ids = {project["id"] for project in PROJECTS}
    missing_ids = sorted(requested_ids - existing_ids)
    if missing_ids:
        raise KeyError(",".join(missing_ids))

    deleted_ids = sorted(requested_ids)
    PROJECTS[:] = [
        project for project in PROJECTS if project["id"] not in requested_ids
    ]
    save_projects(PROJECTS)
    return deleted_ids


def add_project(payload: dict) -> dict:
    """新增项目并追加到运行期状态。"""
    project = build_new_project(payload, next_project_id(PROJECTS))
    PROJECTS.append(project)
    save_projects(PROJECTS)
    return project


PROJECTS = load_projects()
