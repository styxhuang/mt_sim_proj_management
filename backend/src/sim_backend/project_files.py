"""项目文件夹落盘辅助。

数据库保存结构化状态；这里负责把面向用户的方案、结构和计算产物同步到
项目 ``rootDirectory`` 下，保证一个项目的文件集中存放。
"""

from pathlib import Path

from . import config, projects


def project_root_for_task(task: dict | None) -> Path:
    project_id = str((task or {}).get("projectId", "")).strip()
    project = projects.find_project(project_id) if project_id else None
    configured = str((project or {}).get("rootDirectory", "")).strip()
    if configured:
        return Path(configured)
    fallback = project_id or str((task or {}).get("id", "unassigned")).strip() or "unassigned"
    return config.DB_FILE.parent / "project-files" / fallback


def ensure_project_dir(task: dict | None, *parts: str) -> Path:
    root = project_root_for_task(task)
    path = root.joinpath(*[str(part).strip("/") for part in parts if str(part).strip("/")])
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_project_file(task: dict | None, parts: list[str], content: str) -> Path:
    if not parts:
        raise ValueError("parts is required")
    directory = ensure_project_dir(task, *parts[:-1])
    path = directory / parts[-1]
    path.write_text(str(content or ""), encoding="utf-8")
    return path
