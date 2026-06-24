"""HTTP 服务与路由。

需求解析的两个执行端点采用 SSE（text/event-stream）流式推送模型增量；
其余端点保持 JSON 响应。
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import config, dashboard, executions, projects, requirements, workspace


class AppHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status_code: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def _start_sse(self) -> None:
        # HTTP/1.0 默认在响应结束后关闭连接，客户端据此判定流结束；
        # 因此这里不发送 keep-alive，确保 done 之后连接及时关闭。
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _send_sse_event(self, event: dict) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _stream_sse(self, events) -> None:
        self._start_sse()
        try:
            for event in events:
                self._send_sse_event(event)
        except (ValueError, KeyError) as error:
            self._send_sse_event({"type": "error", "error": str(error)})

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        route_path = urlparse(self.path).path

        if route_path == "/health":
            self._send_json({"status": "ok", "service": "backend"})
            return

        if route_path == "/api/dashboard":
            self._send_json(dashboard.get_dashboard_payload())
            return

        if route_path == "/api/requirement-tasks":
            self._send_json({"tasks": requirements.load_requirement_tasks()})
            return

        if route_path.startswith("/api/requirement-tasks/"):
            task_id = route_path.rsplit("/", 1)[-1]
            sub_path = route_path[len("/api/requirement-tasks/") :]
            if sub_path.endswith("/documents"):
                task_id = sub_path[: -len("/documents")]
                part = parse_qs(urlparse(self.path).query).get("part", [""])[0].strip()
                try:
                    document = requirements.get_task_document(task_id, part)
                except ValueError as error:
                    self._send_json({"error": str(error)}, status_code=400)
                    return
                if document is None:
                    self._send_json({"error": "document not found"}, status_code=404)
                    return
                self._send_json({"document": document})
                return
            if sub_path.endswith("/specs"):
                task_id = sub_path[: -len("/specs")]
                part = parse_qs(urlparse(self.path).query).get("part", [""])[0].strip()
                try:
                    spec = requirements.get_task_spec(task_id, part)
                except ValueError as error:
                    self._send_json({"error": str(error)}, status_code=400)
                    return
                if spec is None:
                    self._send_json({"error": "spec not found"}, status_code=404)
                    return
                self._send_json({"spec": spec})
                return
            task_id = sub_path.split("/")[0]
            task = requirements.find_requirement_task(task_id)
            if task is None:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            self._send_json({"task": task})
            return

        if route_path == "/api/executions":
            task_id = parse_qs(urlparse(self.path).query).get("taskId", [""])[0].strip()
            if task_id:
                execution = executions.find_execution_by_task(task_id)
                self._send_json({"execution": executions.execution_without_content(execution) if execution else None})
                return
            self._send_json({"executions": executions.load_executions()})
            return

        if route_path.startswith("/api/executions/"):
            parts = route_path[len("/api/executions/") :].split("/")
            execution_id = parts[0]
            execution = executions.find_execution(execution_id)
            if execution is None:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            if len(parts) == 2 and parts[1] == "structures":
                self._send_json({"structures": executions.list_structure_metas(execution)})
                return
            if len(parts) == 3 and parts[1] == "structures":
                structure = executions.get_structure_content(execution, parts[2])
                if structure is None:
                    self._send_json({"error": "structure not found"}, status_code=404)
                    return
                self._send_json({"structure": structure})
                return
            if len(parts) == 4 and parts[1] == "computation" and parts[2] == "artifacts":
                artifact = executions.get_computation_artifact_content(execution, parts[3])
                if artifact is None:
                    self._send_json({"error": "artifact not found"}, status_code=404)
                    return
                self._send_json({"artifact": artifact})
                return
            if len(parts) == 2 and parts[1] == "summary":
                self._send_json({"execution": executions.execution_summary(execution)})
                return
            self._send_json({"execution": executions.execution_without_content(execution)})
            return

        if route_path == "/api/projects":
            self._send_json({"projects": projects.PROJECTS})
            return

        if route_path.startswith("/api/projects/") and route_path.endswith("/workspace/summary"):
            project_id = route_path.split("/")[-3]
            try:
                payload = workspace.get_workspace_summary(project_id)
            except KeyError:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json(payload)
            return

        if route_path.startswith("/api/projects/") and route_path.endswith("/workspace"):
            project_id = route_path.split("/")[-2]
            project = projects.find_project(project_id)
            if project is None:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            task = requirements.find_requirement_task_by_project(project_id)
            execution = (
                executions.find_execution_by_task(task["id"]) if task else None
            )
            self._send_json(
                {
                    "project": project,
                    "requirementTask": requirements.task_summary(task),
                    "execution": executions.execution_summary(execution),
                    "flags": workspace.get_workspace_summary(project_id).get("flags"),
                }
            )
            return

        if route_path.startswith("/api/projects/"):
            project_id = route_path.rsplit("/", 1)[-1]
            project = projects.find_project(project_id)
            if project is None:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project})
            return

        self._send_json({"message": "Sim delivery backend is running."})

    def do_POST(self) -> None:
        route_path = urlparse(self.path).path

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json body"}, status_code=400)
            return

        if route_path == "/api/requirement-tasks":
            try:
                task = requirements.create_requirement_task(payload)
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json({"task": task}, status_code=201)
            return

        if route_path.startswith("/api/requirement-tasks/") and route_path.endswith("/run-next-step"):
            task_id = route_path.split("/")[-2]
            model_choice = str(payload.get("model", "")).strip() or None
            try:
                events = requirements.stream_next_requirement_step(task_id, model_choice)
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            self._stream_sse(events)
            return

        if route_path.startswith("/api/requirement-tasks/") and route_path.endswith("/messages"):
            task_id = route_path.split("/")[-2]
            try:
                events = requirements.stream_requirement_chat_message(task_id, payload)
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            self._stream_sse(events)
            return

        if route_path.startswith("/api/requirement-tasks/") and route_path.endswith("/versions"):
            task_id = route_path.split("/")[-2]
            try:
                task = requirements.save_requirement_version(task_id, payload)
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json({"task": task}, status_code=201)
            return

        if route_path.startswith("/api/requirement-tasks/") and route_path.endswith("/computation-spec"):
            task_id = route_path.split("/")[-2]
            model_choice = str(payload.get("model", "")).strip() or None
            try:
                task = requirements.generate_requirement_computation_spec(task_id, model_choice)
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json({"task": task, "spec": task.get("documents", {}).get("computationSpec")}, status_code=201)
            return

        if route_path.startswith("/api/requirement-tasks/") and route_path.endswith("/modeling-spec"):
            task_id = route_path.split("/")[-2]
            model_choice = str(payload.get("model", "")).strip() or None
            try:
                task = requirements.generate_requirement_modeling_spec(task_id, model_choice)
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json({"task": task}, status_code=201)
            return

        if route_path == "/api/executions":
            try:
                execution = executions.get_or_create_execution(payload.get("requirementTaskId", ""))
            except KeyError:
                self._send_json({"error": "requirement task not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json({"execution": executions.execution_without_content(execution)}, status_code=201)
            return

        if route_path.startswith("/api/executions/") and route_path.endswith("/auto-modeling"):
            execution_id = route_path.split("/")[-2]
            try:
                events = executions.stream_auto_modeling(execution_id, payload)
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            self._stream_sse(events)
            return

        if route_path.startswith("/api/executions/") and route_path.endswith("/modeling-chat"):
            execution_id = route_path.split("/")[-2]
            try:
                events = executions.stream_modeling_chat(execution_id, payload)
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            self._stream_sse(events)
            return

        if route_path.startswith("/api/executions/") and route_path.endswith("/run-computation"):
            execution_id = route_path.split("/")[-2]
            try:
                events = executions.stream_computation(execution_id, payload)
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._stream_sse(events)
            return

        if route_path.startswith("/api/executions/") and route_path.endswith("/computation/prepare"):
            execution_id = route_path.split("/")[-3]
            try:
                result = executions.prepare_computation_from_modeling(execution_id)
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json(result)
            return

        if route_path.startswith("/api/executions/") and "/computation/steps/" in route_path and route_path.endswith("/run"):
            parts = route_path[len("/api/executions/") :].split("/")
            execution_id = parts[0]
            step_id = parts[3] if len(parts) >= 5 else ""
            try:
                result = executions.run_computation_step(
                    execution_id,
                    step_id,
                    str(payload.get("runner", "local")).strip() or "local",
                )
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json(result)
            return

        if route_path.startswith("/api/executions/") and "/computation/steps/" in route_path and route_path.endswith("/terminate"):
            parts = route_path[len("/api/executions/") :].split("/")
            execution_id = parts[0]
            step_id = parts[3] if len(parts) >= 5 else ""
            try:
                result = executions.terminate_computation_step(execution_id, step_id)
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json(result)
            return

        if route_path.startswith("/api/executions/") and route_path.endswith("/computation/run-all"):
            execution_id = route_path.split("/")[-3]
            try:
                result = executions.run_all_computation_steps(
                    execution_id,
                    default_runner=str(payload.get("defaultRunner", "local")).strip() or "local",
                    runner_overrides=payload.get("runnerOverrides") if isinstance(payload.get("runnerOverrides"), dict) else {},
                )
            except KeyError:
                self._send_json({"error": "execution not found"}, status_code=404)
                return
            except ValueError as error:
                self._send_json({"error": str(error)}, status_code=400)
                return
            self._send_json(result)
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
                project = projects.add_package_record(project_id, payload)
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

        project = projects.add_project({**payload, "amount": amount})
        self._send_json({"project": project}, status_code=201)

    def do_PATCH(self) -> None:
        route_path = urlparse(self.path).path

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
                project = projects.replace_delivery_checklist(project_id, checklist)
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
                project = projects.update_project_fields(project_id, patchable_payload)
            except KeyError:
                self._send_json({"error": "project not found"}, status_code=404)
                return
            self._send_json({"project": project})
            return

        self._send_json({"error": "route not found"}, status_code=404)

    def do_DELETE(self) -> None:
        route_path = urlparse(self.path).path

        try:
            payload = self._read_json_body()
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json body"}, status_code=400)
            return

        if route_path != "/api/projects":
            self._send_json({"error": "route not found"}, status_code=404)
            return

        ids = payload.get("ids")
        if not isinstance(ids, list):
            self._send_json({"error": "ids must be a list"}, status_code=400)
            return

        try:
            deleted_ids = projects.delete_projects(ids)
        except ValueError as error:
            self._send_json({"error": str(error)}, status_code=400)
            return
        except KeyError:
            self._send_json({"error": "project not found"}, status_code=404)
            return

        self._send_json({"deletedIds": deleted_ids, "projects": projects.PROJECTS})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((config.HOST, config.PORT), AppHandler)
    print(f"Backend running at http://localhost:{config.PORT}")
    server.serve_forever()
