"""SQLite 连接、建表与 JSON 序列化辅助。"""

import json
import sqlite3

from . import config


def get_connection() -> sqlite3.Connection:
    config.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                customer TEXT NOT NULL,
                amount INTEGER NOT NULL,
                current_stage TEXT NOT NULL,
                progress INTEGER NOT NULL,
                planned_delivery_date TEXT NOT NULL,
                status TEXT NOT NULL,
                package_status TEXT NOT NULL,
                root_directory TEXT NOT NULL,
                template TEXT NOT NULL,
                description TEXT NOT NULL,
                stage_timeline TEXT NOT NULL,
                delivery_checklist TEXT NOT NULL,
                package_records TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS requirement_tasks (
                id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                status TEXT NOT NULL,
                source_text TEXT NOT NULL,
                steps TEXT NOT NULL,
                conversation TEXT NOT NULL,
                documents TEXT NOT NULL,
                exports TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                requirement_task_id TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                modules TEXT NOT NULL,
                conversation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_requirement_tasks(connection)


def _migrate_requirement_tasks(connection: sqlite3.Connection) -> None:
    """为已存在的旧库补齐新增列，保证平滑升级。"""
    columns = {row[1] for row in connection.execute("PRAGMA table_info(requirement_tasks)")}
    if "project_id" not in columns:
        connection.execute(
            "ALTER TABLE requirement_tasks ADD COLUMN project_id TEXT NOT NULL DEFAULT ''"
        )


def serialize_json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def deserialize_json(value: str):
    return json.loads(value or "[]")
