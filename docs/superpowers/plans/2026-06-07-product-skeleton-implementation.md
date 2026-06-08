# Product Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a business-oriented multi-page frontend skeleton for the internal simulation project system by cleaning the dashboard and adding new project, project list, and project detail pages backed by minimal sample APIs.

**Architecture:** Keep the current no-build static Node.js frontend and minimal Python backend. Split frontend rendering into route-aware page sections within `frontend/public/index.html` so the sidebar navigates to real pages, and extend the backend with JSON endpoints for dashboard, project list, and project detail sample data.

**Tech Stack:** Static HTML/CSS/JavaScript, Node.js built-in `http` server, Python built-in `http.server`

---

### Task 1: Extend backend sample API surface

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\src\main.py`
- Test: manual HTTP checks against `http://localhost:8000/health`, `http://localhost:8000/api/dashboard`, `http://localhost:8000/api/projects`, `http://localhost:8000/api/projects/p-001`

- [ ] **Step 1: Write the failing test**

Create a one-off manual expectation list for the new endpoints:

```text
GET /api/projects
Expected JSON shape:
{
  "projects": [
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
      "rootDirectory": "/data/projects/p-001"
    }
  ]
}

GET /api/projects/p-001
Expected JSON shape:
{
  "project": {
    "id": "p-001",
    "name": "锂电电解液扩散模拟"
  }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run after starting the backend:

```bash
curl http://localhost:8000/api/projects
curl http://localhost:8000/api/projects/p-001
```

Expected: fallback message or missing endpoint behavior, proving the routes do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add:

```python
PROJECTS = [
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
    }
]
```

And in `do_GET()`:

```python
if self.path == "/api/projects":
    self._send_json({"projects": PROJECTS})
    return

if self.path.startswith("/api/projects/"):
    project_id = self.path.rsplit("/", 1)[-1]
    project = next((item for item in PROJECTS if item["id"] == project_id), None)
    if project is None:
        self._send_json({"error": "project not found"}, status_code=404)
        return
    self._send_json({"project": project})
    return
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
curl http://localhost:8000/api/projects
curl http://localhost:8000/api/projects/p-001
```

Expected: both endpoints return JSON with the fields from the expectation block.

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/backend/src/main.py
git commit -m "feat: add sample project api endpoints"
```

### Task 2: Clean dashboard copy and make navigation real

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: browser verification of `/`, `/?page=create`, `/?page=projects`, `/?page=detail&id=p-001`

- [ ] **Step 1: Write the failing test**

Create a manual UI checklist:

```text
Dashboard expectations:
- Page title uses business wording, not "Dashboard V2"
- Sidebar contains real entries: 项目仪表盘, 新建项目, 项目列表, 项目详情
- Homepage has KPI cards, charts, and risk reminders only
- Homepage does not show decorative prototype-only copy
```

- [ ] **Step 2: Run test to verify it fails**

Open the current homepage and confirm:

```text
- The browser title still contains "Dashboard V2"
- Sidebar entries are decorative, not real pages
- Prototype wording is still visible
```

- [ ] **Step 3: Write minimal implementation**

In `index.html`, change:

```html
<title>项目管理系统</title>
```

Add route state:

```javascript
const currentPage = new URLSearchParams(window.location.search).get("page") || "dashboard";
const currentProjectId = new URLSearchParams(window.location.search).get("id") || "p-001";
```

Replace decorative nav items with buttons carrying `data-page` and optional `data-id`, then render page sections conditionally:

```javascript
function navigateTo(page, id) {
  const url = new URL(window.location.href);
  url.searchParams.set("page", page);
  if (id) {
    url.searchParams.set("id", id);
  } else {
    url.searchParams.delete("id");
  }
  window.location.href = url.toString();
}
```

Render only the dashboard page on `/` and remove placeholder wording from the title, hero copy, and side note.

- [ ] **Step 4: Run test to verify it passes**

Open:

```text
http://localhost:5173/
```

Expected:

```text
- Header reads as a business dashboard
- No "Dashboard V2" remains
- Sidebar entries behave like page navigation
```

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html
git commit -m "feat: clean dashboard and add page navigation"
```

### Task 3: Build the new project page

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: browser verification of `/?page=create`

- [ ] **Step 1: Write the failing test**

Manual expectation:

```text
The new project page must show:
- 项目名称
- 客户名称
- 项目金额
- 计划交付日期
- 项目模板
- 根目录路径
- 项目简介
```

- [ ] **Step 2: Run test to verify it fails**

Open:

```text
http://localhost:5173/?page=create
```

Expected: the page does not exist yet or does not contain the required fields.

- [ ] **Step 3: Write minimal implementation**

Add a route-specific section in `index.html` for the create page using a structured form and a non-persistent submit action:

```javascript
function renderCreatePage() {
  mainContentEl.innerHTML = `
    <section class="page-card">
      <h1>新建项目</h1>
      <form class="project-form">
        <label>项目名称<input name="name" /></label>
        <label>客户名称<input name="customer" /></label>
        <label>项目金额<input name="amount" type="number" /></label>
        <label>计划交付日期<input name="plannedDeliveryDate" type="date" /></label>
        <label>项目模板<select name="template"><option>标准计算项目</option></select></label>
        <label>根目录路径<input name="rootDirectory" /></label>
        <label>项目简介<textarea name="description"></textarea></label>
      </form>
    </section>
  `;
}
```

- [ ] **Step 4: Run test to verify it passes**

Open:

```text
http://localhost:5173/?page=create
```

Expected: all required fields are visible with clean layout and no placeholder filler text.

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html
git commit -m "feat: add new project page"
```

### Task 4: Build the project list page

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: browser verification of `/?page=projects`

- [ ] **Step 1: Write the failing test**

Manual expectation:

```text
The project list page must show:
- search input
- stage filter
- status filter
- columns for project name, customer, stage, progress, amount, delivery date, package status
```

- [ ] **Step 2: Run test to verify it fails**

Open:

```text
http://localhost:5173/?page=projects
```

Expected: no dedicated project list page exists yet.

- [ ] **Step 3: Write minimal implementation**

Fetch `/api/projects` and render:

```javascript
async function loadProjects() {
  const response = await fetch(`${apiBaseUrl}/api/projects`);
  const data = await response.json();
  return data.projects;
}
```

Then render a table with filters and click-through rows:

```javascript
function openProjectDetail(projectId) {
  navigateTo("detail", projectId);
}
```

- [ ] **Step 4: Run test to verify it passes**

Open:

```text
http://localhost:5173/?page=projects
```

Expected: the page shows a readable searchable table and clicking a row opens the detail page.

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html d:/0-wiki/git-repo/projects/sim_delivery_system/backend/src/main.py
git commit -m "feat: add project list page"
```

### Task 5: Build the project detail page

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: browser verification of `/?page=detail&id=p-001`

- [ ] **Step 1: Write the failing test**

Manual expectation:

```text
The project detail page must show:
- basic project information
- stage progress
- root directory path
- delivery checklist
- package records
```

- [ ] **Step 2: Run test to verify it fails**

Open:

```text
http://localhost:5173/?page=detail&id=p-001
```

Expected: no dedicated project detail page exists yet.

- [ ] **Step 3: Write minimal implementation**

Fetch `/api/projects/p-001` and render a detail layout:

```javascript
async function loadProjectDetail(projectId) {
  const response = await fetch(`${apiBaseUrl}/api/projects/${projectId}`);
  const data = await response.json();
  return data.project;
}
```

Render sections for:

```text
- 基础信息
- 阶段进度
- 目录路径
- 交付清单
- 打包记录
```

- [ ] **Step 4: Run test to verify it passes**

Open:

```text
http://localhost:5173/?page=detail&id=p-001
```

Expected: the detail page shows structured project information and does not depend on the homepage layout.

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html d:/0-wiki/git-repo/projects/sim_delivery_system/backend/src/main.py
git commit -m "feat: add project detail page"
```

### Self-Review

- Spec coverage:
  - Homepage cleanup: covered in Task 2
  - Real page navigation: covered in Task 2
  - New project page: covered in Task 3
  - Project list page: covered in Task 4
  - Project detail page: covered in Task 5
  - Backend sample data expansion: covered in Task 1 and reused by Tasks 4-5
- Placeholder scan:
  - No `TBD`, `TODO`, or vague "handle later" language remains
- Type consistency:
  - Project object fields are consistent across backend and frontend: `id`, `name`, `customer`, `amount`, `currentStage`, `progress`, `plannedDeliveryDate`, `status`, `packageStatus`, `rootDirectory`
