from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import date, datetime
import json
import os
from pathlib import Path
from urllib.parse import urlparse


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
DATA_FILE = Path(
    os.environ.get(
        "PROJECTS_DATA_FILE",
        str(Path(__file__).resolve().parent.parent / "data" / "projects.json"),
    )
)

DEFAULT_PROJECTS = [
    {
        "id": "p-001",
        "name": "锂电电解液扩散模拟",
        "customer": "华东新能源",
        "amount": 42,
        "currentStage": "模拟计算",
        "progress": 64,
        "plannedDeliveryDate": "2026-06-14",
        "status": "进行中",
        "packageStatus": "待打包",
        "rootDirectory": "/data/projects/p-001",
        "template": "标准扩散模板",
        "description": "评估不同温度条件下电解液扩散速率和迁移趋势。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "建模", "status": "已完成"},
            {"name": "模拟计算", "status": "进行中"},
            {"name": "结果分析", "status": "未开始"},
            {"name": "报告交付", "status": "未开始"},
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
        "currentStage": "结果分析",
        "progress": 82,
        "plannedDeliveryDate": "2026-06-09",
        "status": "临近交付",
        "packageStatus": "可打包",
        "rootDirectory": "/data/projects/p-002",
        "template": "界面分析模板",
        "description": "分析膜材料在不同电场条件下的界面稳定性表现。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "建模", "status": "已完成"},
            {"name": "模拟计算", "status": "已完成"},
            {"name": "结果分析", "status": "进行中"},
            {"name": "报告交付", "status": "未开始"},
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
        "currentStage": "建模",
        "progress": 35,
        "plannedDeliveryDate": "2026-06-21",
        "status": "进行中",
        "packageStatus": "未开始",
        "rootDirectory": "/data/projects/p-003",
        "template": "吸附能扫描模板",
        "description": "比较多种位点构型下关键中间体的吸附能分布。",
        "stageTimeline": [
            {"name": "立项", "status": "已完成"},
            {"name": "建模", "status": "进行中"},
            {"name": "模拟计算", "status": "未开始"},
            {"name": "结果分析", "status": "未开始"},
            {"name": "报告交付", "status": "未开始"},
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


def ensure_data_file() -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(
            json.dumps(DEFAULT_PROJECTS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_projects() -> list[dict]:
    ensure_data_file()
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_projects(projects: list[dict]) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(projects, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_new_project(payload: dict, project_id: str) -> dict:
    name = str(payload.get("name", "")).strip()
    customer = str(payload.get("customer", "")).strip()
    description = str(payload.get("description", "")).strip()
    template = str(payload.get("template", "")).strip() or "标准计算项目"
    planned_delivery_date = str(payload.get("plannedDeliveryDate", "")).strip()
    root_directory = str(payload.get("rootDirectory", "")).strip()

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
        "stageTimeline": [
            {"name": "立项", "status": "进行中"},
            {"name": "建模", "status": "未开始"},
            {"name": "模拟计算", "status": "未开始"},
            {"name": "结果分析", "status": "未开始"},
            {"name": "报告交付", "status": "未开始"},
        ],
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


def build_stage_timeline(current_stage: str) -> list[dict]:
    timeline = []
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
        project[field] = payload[field]

    if "currentStage" in payload:
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


PROJECTS = load_projects()


STAGE_ORDER = ["立项", "建模", "模拟计算", "结果分析", "报告交付"]


def parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def build_delivery_trend(projects: list[dict], today: date) -> list[dict]:
    points = []
    month_index = today.year * 12 + today.month - 1
    for offset in range(5, -1, -1):
        current_index = month_index - offset
        year = current_index // 12
        month = current_index % 12 + 1
        points.append(
            {
                "year": year,
                "monthNumber": month,
                "month": f"{month}月",
                "value": 0,
            }
        )

    point_lookup = {(point["year"], point["monthNumber"]): point for point in points}
    for project in projects:
        planned_date = parse_iso_date(project.get("plannedDeliveryDate", ""))
        if not planned_date:
            continue
        point = point_lookup.get((planned_date.year, planned_date.month))
        if point:
            point["value"] += 1

    return [{"month": point["month"], "value": point["value"]} for point in points]


def build_summary_cards(
    projects: list[dict], total_amount: int, stage_counter: dict[str, int], ready_to_pack: int
) -> list[dict]:
    top_projects = sorted(projects, key=lambda item: item["amount"], reverse=True)
    top_two_amount = sum(project["amount"] for project in top_projects[:2])
    concentration = round((top_two_amount / total_amount) * 100) if total_amount else 0
    busiest_stage = max(STAGE_ORDER, key=lambda stage: stage_counter.get(stage, 0))
    busiest_count = stage_counter.get(busiest_stage, 0)
    configured_roots = sum(bool(str(project.get("rootDirectory", "")).strip()) for project in projects)

    return [
        {
            "title": "金额集中度较高" if concentration >= 60 else "金额分布相对均衡",
            "detail": (
                f"前两大项目占当前总金额约 {concentration}%，"
                "建议优先跟进高价值项目的交付节奏。"
                if projects
                else "当前还没有项目数据，金额集中度会在项目录入后自动生成。"
            ),
            "level": "warn" if concentration >= 60 else "normal",
        },
        {
            "title": f"{busiest_stage}阶段项目较集中" if busiest_count else "当前阶段分布较均衡",
            "detail": (
                f"目前有 {busiest_count} 个项目处于{busiest_stage}阶段，"
                "建议提前安排相关资源和复核时间。"
                if busiest_count
                else "项目阶段数据还不足，后续会随项目推进自动更新。"
            ),
            "level": "warn" if busiest_count >= 2 else "normal",
        },
        {
            "title": "目录配置完整度稳定" if configured_roots == len(projects) and len(projects) > 0 else "仍有项目待补目录配置",
            "detail": (
                f"{ready_to_pack} 个项目已具备打包条件，"
                "标准目录和交付整理流程可以继续复用。"
                if configured_roots == len(projects) and len(projects) > 0
                else "部分项目还缺少根目录配置，建议补齐后再进入交付打包流程。"
            ),
            "level": "normal" if configured_roots == len(projects) and len(projects) > 0 else "warn",
        },
    ]


def build_risk_reminders(projects: list[dict], today: date) -> list[dict]:
    reminders = []
    by_delivery = sorted(
        projects,
        key=lambda item: parse_iso_date(item.get("plannedDeliveryDate", "")) or date.max,
    )

    for project in by_delivery:
        planned_date = parse_iso_date(project.get("plannedDeliveryDate", ""))
        days_left = (planned_date - today).days if planned_date else None

        if project.get("status") == "临近交付" or (days_left is not None and days_left <= 3):
            reminders.append(
                {
                    "title": f"优先推进 {project['name']}",
                    "detail": (
                        f"距离计划交付还有 {max(days_left, 0)} 天，建议优先完成报告复核和说明文档确认。"
                        if days_left is not None
                        else "该项目已接近交付窗口，建议尽快确认最终交付材料。"
                    ),
                    "level": "high",
                }
            )
            continue

        if project.get("currentStage") == "模拟计算":
            reminders.append(
                {
                    "title": f"{project['name']} 需提前锁定算力",
                    "detail": "项目仍在模拟计算阶段，建议提前排定算力窗口，避免影响后续分析与交付。",
                    "level": "medium",
                }
            )
            continue

        if project.get("currentStage") == "建模":
            reminders.append(
                {
                    "title": f"{project['name']} 建模需尽快收口",
                    "detail": "当前仍在前置建模阶段，建议尽快确认输入参数，避免挤压后续计算周期。",
                    "level": "low",
                }
            )

    if len(reminders) < 3:
        reminders.append(
            {
                "title": "持续关注交付材料完整性",
                "detail": "建议在进入报告交付阶段前统一核对分析报告、图表、原始数据和说明文档。",
                "level": "low",
            }
        )

    return reminders[:3]


def get_dashboard_payload() -> dict:
    today = date.today()
    total_amount = sum(project["amount"] for project in PROJECTS)
    near_delivery = sum(project["status"] == "临近交付" for project in PROJECTS)
    ready_to_pack = sum(project["packageStatus"] == "可打包" for project in PROJECTS)
    stage_counter = {label: 0 for label in STAGE_ORDER}
    for project in PROJECTS:
        stage = project.get("currentStage", "")
        stage_counter[stage] = stage_counter.get(stage, 0) + 1

    top_projects = sorted(PROJECTS, key=lambda item: item["amount"], reverse=True)[:5]

    return {
        "projectCount": len(PROJECTS),
        "totalAmountWan": total_amount,
        "nearDelivery": near_delivery,
        "readyToPack": ready_to_pack,
        "stageDistribution": [
            {"label": label, "value": stage_counter.get(label, 0)}
            for label in STAGE_ORDER
        ],
        "deliveryTrend": build_delivery_trend(PROJECTS, today),
        "topAmounts": [
            {"label": project["name"], "value": project["amount"]}
            for project in top_projects
        ],
        "summaryCards": build_summary_cards(PROJECTS, total_amount, stage_counter, ready_to_pack),
        "riskReminders": build_risk_reminders(PROJECTS, today),
    }


class AppHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status_code: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        route_path = parsed_url.path

        if route_path == "/health":
            self._send_json({"status": "ok", "service": "backend"})
            return

        if route_path == "/api/dashboard":
            self._send_json(get_dashboard_payload())
            return

        if route_path == "/api/projects":
            self._send_json({"projects": PROJECTS})
            return

        if route_path.startswith("/api/projects/"):
            project_id = route_path.rsplit("/", 1)[-1]
            project = find_project(project_id)
            if project is None:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project})
            return

        self._send_json({"message": "Sim delivery backend is running."})

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        route_path = parsed_url.path

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json body"}, status_code=400)
            return

        if route_path.startswith("/api/projects/") and route_path.endswith("/package-records"):
            project_id = route_path.split("/")[-2]
            required_fields = ["version", "date", "type"]
            missing_fields = [field for field in required_fields if not str(payload.get(field, "")).strip()]
            if missing_fields:
                self._send_json(
                    {"error": "missing required fields", "fields": missing_fields},
                    status_code=400,
                )
                return
            try:
                project = add_package_record(project_id, payload)
            except KeyError:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project}, status_code=201)
            return

        if route_path != "/api/projects":
            self._send_json({"error": "route not found"}, status_code=404)
            return

        required_fields = ["name", "customer", "amount", "plannedDeliveryDate", "rootDirectory"]
        missing_fields = [field for field in required_fields if not str(payload.get(field, "")).strip()]
        if missing_fields:
            self._send_json(
                {"error": "missing required fields", "fields": missing_fields},
                status_code=400,
            )
            return

        try:
            amount = int(payload.get("amount", 0))
        except (TypeError, ValueError):
            self._send_json({"error": "amount must be an integer"}, status_code=400)
            return

        if amount < 0:
            self._send_json({"error": "amount must be non-negative"}, status_code=400)
            return

        global PROJECTS
        project = build_new_project({**payload, "amount": amount}, next_project_id(PROJECTS))
        PROJECTS.append(project)
        save_projects(PROJECTS)
        self._send_json({"project": project}, status_code=201)

    def do_PATCH(self) -> None:
        parsed_url = urlparse(self.path)
        route_path = parsed_url.path

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json body"}, status_code=400)
            return

        if route_path.startswith("/api/projects/") and route_path.endswith("/checklist"):
            project_id = route_path.split("/")[-2]
            checklist = payload.get("deliveryChecklist")
            if not isinstance(checklist, list):
                self._send_json({"error": "deliveryChecklist must be a list"}, status_code=400)
                return
            try:
                project = replace_delivery_checklist(project_id, checklist)
            except KeyError:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project})
            return

        if route_path.startswith("/api/projects/"):
            project_id = route_path.rsplit("/", 1)[-1]
            patchable_payload = {}
            if "amount" in payload:
                try:
                    patchable_payload["amount"] = int(payload.get("amount", 0))
                except (TypeError, ValueError):
                    self._send_json({"error": "amount must be an integer"}, status_code=400)
                    return
                if patchable_payload["amount"] < 0:
                    self._send_json({"error": "amount must be non-negative"}, status_code=400)
                    return
            for field in [
                "currentStage",
                "progress",
                "plannedDeliveryDate",
                "status",
                "packageStatus",
                "rootDirectory",
                "description",
                "customer",
            ]:
                if field in payload:
                    patchable_payload[field] = payload[field]
            if "progress" in patchable_payload:
                try:
                    patchable_payload["progress"] = int(patchable_payload["progress"])
                except (TypeError, ValueError):
                    self._send_json({"error": "progress must be an integer"}, status_code=400)
                    return
                if patchable_payload["progress"] < 0 or patchable_payload["progress"] > 100:
                    self._send_json({"error": "progress must be between 0 and 100"}, status_code=400)
                    return
            try:
                project = update_project_fields(project_id, patchable_payload)
            except KeyError:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project})
            return

        self._send_json({"error": "route not found"}, status_code=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Backend running at http://localhost:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
