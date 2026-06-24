"""运营看板数据聚合。"""

from datetime import date, datetime

from . import projects as projects_module
from .projects import STAGE_ORDER


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
            "title": "目录配置完整度稳定" if configured_roots == len(projects) else "仍有项目待补目录配置",
            "detail": (
                f"{ready_to_pack} 个项目已具备打包条件，"
                "标准目录和交付整理流程可以继续复用。"
                if configured_roots == len(projects)
                else "部分项目还缺少根目录配置，建议补齐后再进入交付打包流程。"
            ),
            "level": "normal" if configured_roots == len(projects) else "warn",
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

        if project.get("currentStage") == "建模执行":
            reminders.append(
                {
                    "title": f"{project['name']} 需提前锁定算力",
                    "detail": "项目仍在建模执行阶段，建议提前排定算力窗口，避免影响后续分析与交付。",
                    "level": "medium",
                }
            )
            continue

        if project.get("currentStage") == "方案确认":
            reminders.append(
                {
                    "title": f"{project['name']} 方案需尽快确认",
                    "detail": "当前仍在方案确认阶段，建议尽快确认实施方案，避免挤压后续建模与计算周期。",
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
    projects = projects_module.PROJECTS
    today = date.today()
    total_amount = sum(project["amount"] for project in projects)
    near_delivery = sum(project["status"] == "临近交付" for project in projects)
    ready_to_pack = sum(project["packageStatus"] == "可打包" for project in projects)
    stage_counter = {label: 0 for label in STAGE_ORDER}
    for project in projects:
        stage = project.get("currentStage", "")
        stage_counter[stage] = stage_counter.get(stage, 0) + 1

    top_projects = sorted(projects, key=lambda item: item["amount"], reverse=True)[:5]

    return {
        "projectCount": len(projects),
        "totalAmountWan": total_amount,
        "nearDelivery": near_delivery,
        "readyToPack": ready_to_pack,
        "stageDistribution": [
            {"label": label, "value": stage_counter.get(label, 0)}
            for label in STAGE_ORDER
        ],
        "deliveryTrend": build_delivery_trend(projects, today),
        "topAmounts": [
            {"label": project["name"], "value": project["amount"]}
            for project in top_projects
        ],
        "summaryCards": build_summary_cards(projects, total_amount, stage_counter, ready_to_pack),
        "riskReminders": build_risk_reminders(projects, today),
    }
