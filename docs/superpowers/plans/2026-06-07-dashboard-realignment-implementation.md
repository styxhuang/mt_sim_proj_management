# Dashboard Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dashboard page so it keeps the prototype's visual character and chart types while staying inside the current multi-page product shell and using the real backend API.

**Architecture:** Keep the current query-param routing, page shell, and backend API surface. Rework only the dashboard rendering layer, extend the `/api/dashboard` payload to be chart-friendly, and preserve the existing create/projects/detail pages for follow-up feature work.

**Tech Stack:** Static HTML/CSS/vanilla JavaScript frontend, Python `http.server` backend, Bash lifecycle scripts, Windows localhost proxy helper.

---

## File Map

- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
  - Rebuild dashboard-specific layout, chart rendering helpers, and dashboard section styles.
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\src\main.py`
  - Extend dashboard payload to include `summaryCards` and make chart data match the new frontend expectations.
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\data\projects.json`
  - Keep sample data aligned with stage distribution, amount ranking, and reminder generation.
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\README.md`
  - Document the updated dashboard behavior if needed.
- Test/Verify:
  - `wsl bash -lc "cd /mnt/d/0-wiki/git-repo/projects/sim_delivery_system && bash restart-dev.sh"`
  - `wsl bash -lc "curl -I http://localhost:5173/ && curl -s http://localhost:8000/api/dashboard"`
  - `powershell Invoke-WebRequest http://localhost:5173/`

### Task 1: Align Dashboard API Data

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\src\main.py`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\data\projects.json`

- [ ] **Step 1: Add the target dashboard payload shape to the backend**

```python
def get_dashboard_payload() -> dict:
    total_amount = sum(project["amount"] for project in PROJECTS)
    near_delivery = sum(project["status"] == "临近交付" for project in PROJECTS)
    ready_to_pack = sum(project["packageStatus"] == "可打包" for project in PROJECTS)

    stage_order = ["立项", "建模", "模拟计算", "结果分析", "报告交付"]
    stage_counter = {label: 0 for label in stage_order}
    for project in PROJECTS:
        stage = project["currentStage"]
        stage_counter[stage] = stage_counter.get(stage, 0) + 1

    top_projects = sorted(PROJECTS, key=lambda item: item["amount"], reverse=True)[:5]

    return {
        "projectCount": len(PROJECTS),
        "totalAmountWan": total_amount,
        "nearDelivery": near_delivery,
        "readyToPack": ready_to_pack,
        "stageDistribution": [
            {"label": label, "value": stage_counter.get(label, 0)}
            for label in stage_order
        ],
        "deliveryTrend": [
            {"month": "1月", "value": 2},
            {"month": "2月", "value": 3},
            {"month": "3月", "value": 2},
            {"month": "4月", "value": 4},
            {"month": "5月", "value": 3},
            {"month": "6月", "value": 5},
        ],
        "topAmounts": [
            {"label": project["name"], "value": project["amount"]}
            for project in top_projects
        ],
        "summaryCards": [
            {
                "title": "金额集中度较高",
                "detail": "前两大项目贡献了当前金额的大部分，建议优先跟进交付节奏。",
                "level": "normal",
            },
            {
                "title": "报告阶段仍有堆积",
                "detail": "多个项目正集中进入报告和交付收口阶段，建议提前安排复核时间。",
                "level": "warn",
            },
            {
                "title": "标准目录执行稳定",
                "detail": "新建项目目录结构已统一，后续交付包整理会更顺畅。",
                "level": "normal",
            },
        ],
        "riskReminders": [
            {
                "title": "优先推进临近交付项目",
                "detail": "高分子膜界面稳定性计算需在 2 天内完成说明文档确认。",
                "level": "high",
            },
            {
                "title": "模拟资源需提前排期",
                "detail": "锂电电解液扩散模拟仍在计算阶段，建议锁定本周算力窗口。",
                "level": "medium",
            },
            {
                "title": "新项目建模需尽快完成",
                "detail": "催化位点吸附能扫描尚未进入计算阶段，需确认输入参数。",
                "level": "low",
            },
        ],
    }
```

- [ ] **Step 2: Run a focused backend syntax check**

Run:

```bash
python -m py_compile d:\0-wiki\git-repo\projects\sim_delivery_system\backend\src\main.py
```

Expected: no output.

- [ ] **Step 3: Verify the API returns the new fields**

Run:

```bash
wsl bash -lc "curl -s http://localhost:8000/api/dashboard"
```

Expected: JSON containing `summaryCards`, `stageDistribution`, `deliveryTrend`, and `topAmounts`.

- [ ] **Step 4: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/backend/src/main.py d:/0-wiki/git-repo/projects/sim_delivery_system/backend/data/projects.json
git commit -m "feat: align dashboard api payload"
```

### Task 2: Rebuild Dashboard Layout and Styling

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`

- [ ] **Step 1: Replace the simplified dashboard section structure with the prototype-inspired layout**

```html
<section class="dashboard-hero">
  <div class="hero-copy">
    <div class="eyebrow">Business Overview Dashboard</div>
    <h1>更轻量的项目看板，只保留最重要的判断信息</h1>
    <p>聚焦项目规模、交付节奏、金额分布和本周优先事项。</p>
  </div>
  <div class="hero-brief" id="heroBrief"></div>
</section>

<section class="metrics-grid" id="metricsGrid"></section>

<section class="dashboard-grid">
  <div class="dashboard-stack">
    <article class="chart-card">
      <div class="section-head">
        <div>
          <h3>项目阶段分布</h3>
          <div class="section-note">看当前项目主要堆积在哪个阶段</div>
        </div>
      </div>
      <div class="stage-chart" id="stageChart"></div>
    </article>

    <article class="chart-card">
      <div class="section-head">
        <div>
          <h3>金额 Top 项目</h3>
          <div class="section-note">看金额主要集中在哪几个项目</div>
        </div>
      </div>
      <div class="ranking" id="amountChart"></div>
    </article>
  </div>

  <div class="dashboard-stack">
    <article class="chart-card">
      <div class="section-head">
        <div>
          <h3>月度交付趋势</h3>
          <div class="section-note">看最近 6 个月交付压力变化</div>
        </div>
      </div>
      <div class="line-chart">
        <svg viewBox="0 0 420 190" aria-label="月度交付趋势图" role="img">
          <g class="line-grid" id="trendGrid"></g>
          <path class="line-axis" d="M24 156 H396"></path>
          <path class="area-fill" id="areaFill"></path>
          <path class="trend-line" id="trendLine"></path>
          <g id="trendPoints"></g>
        </svg>
        <div class="axis-labels" id="trendLabels"></div>
      </div>
    </article>

    <article class="summary-card">
      <div class="section-head">
        <div>
          <h3>经营摘要</h3>
          <div class="section-note">适合首页快速扫一眼</div>
        </div>
      </div>
      <div class="summary-list" id="summaryList"></div>
    </article>
  </div>
</section>

<section class="reminder-card">
  <div class="section-head">
    <div>
      <h3>风险提醒</h3>
      <div class="section-note">首页只保留需要优先处理的项目</div>
    </div>
  </div>
  <div class="reminder-list" id="reminderList"></div>
</section>
```

- [ ] **Step 2: Restore the prototype-like chart and card styles**

```css
.chart-card,
.reminder-card,
.summary-card {
  border-radius: 24px;
  padding: 20px;
  background: var(--panel);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  backdrop-filter: blur(18px);
}

.stage-chart {
  display: grid;
  gap: 12px;
}

.stage-row {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) 36px;
  align-items: center;
  gap: 12px;
}

.line-chart svg {
  width: 100%;
  height: 190px;
  display: block;
}

.ranking {
  display: grid;
  gap: 14px;
}

.summary-list,
.reminder-list {
  display: grid;
  gap: 12px;
}
```

- [ ] **Step 3: Run editor diagnostics to catch CSS/HTML mistakes**

Run: workspace diagnostics for `frontend/public/index.html`

Expected: no diagnostics.

- [ ] **Step 4: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html
git commit -m "feat: rebuild dashboard layout"
```

### Task 3: Replace Simplified Chart Rendering With Prototype-Style Renderers

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`

- [ ] **Step 1: Add dedicated render helpers for metrics, stage chart, trend chart, amount ranking, summary, and reminders**

```javascript
function renderMetrics(metrics) {
  return metrics.map((item) => `
    <article class="metric-card">
      <div class="metric-label">${escapeHtml(item.label)}</div>
      <div class="metric-value">${escapeHtml(String(item.value))}</div>
      <div class="metric-sub">${escapeHtml(item.sub)}</div>
      <div class="metric-foot">${escapeHtml(item.foot)}</div>
    </article>
  `).join("");
}

function renderStageChart(items) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return items.map((item) => `
    <div class="stage-row">
      <div class="stage-label">${escapeHtml(item.label)}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${(item.value / max) * 100}%"></div>
      </div>
      <div class="stage-value">${item.value}</div>
    </div>
  `).join("");
}

function renderAmountChart(items) {
  const max = Math.max(...items.map((item) => item.value), 1);
  return items.map((item) => `
    <div class="rank-row">
      <div class="rank-bar">
        <div class="rank-name">${escapeHtml(item.label)}</div>
        <div class="rank-track">
          <div class="rank-fill" style="width:${(item.value / max) * 100}%"></div>
        </div>
      </div>
      <div class="rank-value">${item.value}</div>
    </div>
  `).join("");
}
```

- [ ] **Step 2: Implement the SVG trend chart renderer instead of the current bar-row fallback**

```javascript
function renderTrendChart(trend) {
  const values = trend.map((item) => item.value);
  const max = Math.max(...values, 1);
  const stepX = 372 / Math.max(trend.length - 1, 1);
  const points = trend.map((item, index) => {
    const x = 24 + stepX * index;
    const y = 156 - (item.value / max) * 120;
    return { x, y, label: item.month };
  });

  const linePath = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");
  const areaPath = `M ${points[0].x} 156 ${points.map((point) => `L ${point.x} ${point.y}`).join(" ")} L ${points[points.length - 1].x} 156 Z`;

  trendLineEl.setAttribute("d", linePath);
  areaFillEl.setAttribute("d", areaPath);
  trendPointsEl.innerHTML = points
    .map((point) => `<circle class="trend-point" cx="${point.x}" cy="${point.y}" r="5"></circle>`)
    .join("");
  trendLabelsEl.innerHTML = points.map((point) => `<span>${escapeHtml(point.label)}</span>`).join("");
  trendGridEl.innerHTML = [24, 68, 112, 156]
    .map((y) => `<line x1="24" y1="${y}" x2="396" y2="${y}"></line>`)
    .join("");
}
```

- [ ] **Step 3: Rebuild `renderDashboard()` around the new payload structure**

```javascript
function renderDashboard() {
  const dashboard = state.dashboard;
  const metrics = [
    { label: "项目总数", value: dashboard.projectCount, sub: "覆盖当前在管项目", foot: "聚焦整体项目盘子" },
    { label: "总项目金额", value: `￥${dashboard.totalAmountWan} 万`, sub: "用于观察业务规模", foot: "聚焦高价值项目" },
    { label: "临近交付", value: dashboard.nearDelivery, sub: "需要本周重点跟进", foot: "优先处理延期风险" },
    { label: "可打包项目", value: dashboard.readyToPack, sub: "具备交付整理条件", foot: "适合进入交付流程" }
  ];

  mainContentEl.innerHTML = `
    ${renderPageHeader("项目仪表盘", "聚焦项目进度、交付风险和金额分布，优先处理本周最影响交付的事项。")}
    <section class="dashboard-shell">
      ... prototype-inspired dashboard markup ...
    </section>
  `;

  metricsGridEl.innerHTML = renderMetrics(metrics);
  stageChartEl.innerHTML = renderStageChart(dashboard.stageDistribution);
  amountChartEl.innerHTML = renderAmountChart(dashboard.topAmounts);
  summaryListEl.innerHTML = renderSummaryCards(dashboard.summaryCards);
  reminderListEl.innerHTML = renderReminderCards(dashboard.riskReminders);
  renderTrendChart(dashboard.deliveryTrend);
}
```

- [ ] **Step 4: Restart the app and verify the dashboard visually**

Run:

```bash
wsl bash -lc "cd /mnt/d/0-wiki/git-repo/projects/sim_delivery_system && bash restart-dev.sh"
```

Expected:
- `http://localhost:5173/` loads
- dashboard shows horizontal stage bars
- dashboard shows SVG line/area trend chart
- dashboard shows ranking bars and summary/reminder cards

- [ ] **Step 5: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html
git commit -m "feat: restore prototype-style dashboard charts"
```

### Task 4: Harden Dashboard Data Loading and Follow-Up Page Integrity

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\README.md`

- [ ] **Step 1: Keep the other pages intact while dashboard changes land**

```javascript
const navItems = [
  { page: "dashboard", label: "综合仪表盘" },
  { page: "create", label: "新建项目" },
  { page: "projects", label: "项目列表" }
];

async function bootstrap() {
  try {
    const [dashboard, projects] = await Promise.all([
      fetchJson("/api/dashboard"),
      fetchJson("/api/projects")
    ]);
    state.dashboard = dashboard;
    state.projects = projects.projects;
    state.apiOnline = true;
  } catch (error) {
    state.apiOnline = false;
  }
  renderCurrentPage();
}
```

- [ ] **Step 2: Add a short README note about dashboard/proxy startup expectations**

```markdown
首页仪表盘现使用正式接口数据，并在 Windows 本机通过本地代理提供：

- `http://localhost:5173/` 前端页面
- `http://localhost:8000/health` 后端健康检查

如果仪表盘样式更新后未生效，请执行：

```bash
bash restart-dev.sh
```
```

- [ ] **Step 3: Run final verification commands**

Run:

```bash
wsl bash -lc "cd /mnt/d/0-wiki/git-repo/projects/sim_delivery_system && bash status-dev.sh"
```

Expected: frontend/backend and Windows localhost proxy all show listening/running.

Run:

```bash
powershell -Command "Invoke-WebRequest -UseBasicParsing http://localhost:5173/ | Select-Object -ExpandProperty StatusCode"
```

Expected: `200`

Run:

```bash
wsl bash -lc "curl -s http://localhost:8000/api/dashboard"
```

Expected: JSON payload with dashboard fields.

- [ ] **Step 4: Commit**

```bash
git add d:/0-wiki/git-repo/projects/sim_delivery_system/frontend/public/index.html d:/0-wiki/git-repo/projects/sim_delivery_system/README.md
git commit -m "docs: document dashboard startup behavior"
```

## Self-Review

- Spec coverage:
  - 首页视觉对齐：Task 2
  - 图表类型对齐：Task 3
  - 数据结构对齐：Task 1
  - 不回退多页面骨架：Task 4
- Placeholder scan:
  - No `TODO`, `TBD`, or "similar to above" placeholders remain.
- Type consistency:
  - Dashboard payload names are consistent across backend and frontend: `stageDistribution`, `deliveryTrend`, `topAmounts`, `summaryCards`, `riskReminders`.

