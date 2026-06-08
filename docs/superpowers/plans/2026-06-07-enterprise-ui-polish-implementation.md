# Enterprise UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有单文件前端收敛为更稳定的企业控制台视觉和交互版本，并补齐轻量全局设置与本地偏好持久化。

**Architecture:** 继续使用 `frontend/public/index.html` 单文件承载样式、结构和前端状态逻辑，不新增前端框架和后端设置接口。本轮通过“静态结构测试先行 + 最小可用前端状态扩展”的方式，收敛全局 token、页头和工具条层级、表单与按钮反馈、以及右上角设置面板。

**Tech Stack:** Vanilla HTML/CSS/JavaScript, Python `unittest`, localStorage

---

## File Map

- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
  - 责任：全局 CSS token、页面布局节奏、设置面板结构、toast 与表单反馈、偏好持久化逻辑
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`
  - 责任：锁定本轮新增的 UI 结构、反馈函数和设置入口
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_dashboard_markup.py`
  - 责任：补首页页头和工作台结构的静态回归锚点

### Task 1: 锁定企业控制台 UI 锚点

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_dashboard_markup.py`
- Test: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`

- [ ] **Step 1: 先写失败的静态结构测试**

```python
class ProductUsabilityMarkupTests(unittest.TestCase):
    def test_feedback_and_settings_controls_exist(self) -> None:
        self.assertIn('id="settingsButton"', INDEX_HTML)
        self.assertIn('id="settingsPanel"', INDEX_HTML)
        self.assertIn('id="defaultPageSelect"', INDEX_HTML)
        self.assertIn('id="defaultSortSelect"', INDEX_HTML)
        self.assertIn('id="densitySelect"', INDEX_HTML)
        self.assertIn('id="helperTextToggle"', INDEX_HTML)
        self.assertIn('id="toastRegion"', INDEX_HTML)
        self.assertIn("function loadPreferences", INDEX_HTML)
        self.assertIn("function savePreferences", INDEX_HTML)
        self.assertIn("function showToast", INDEX_HTML)
        self.assertIn("localStorage.setItem", INDEX_HTML)


class DashboardMarkupTests(unittest.TestCase):
    def test_dashboard_contains_workbench_header_and_summary_regions(self) -> None:
        self.assertIn('class="page-header page-header--split"', INDEX_HTML)
        self.assertIn('class="page-toolbar"', INDEX_HTML)
        self.assertIn('class="dashboard-shell"', INDEX_HTML)
        self.assertIn('id="summaryList"', INDEX_HTML)
        self.assertIn('id="reminderList"', INDEX_HTML)
```

- [ ] **Step 2: 运行测试并确认先红**

Run:

```bash
python -m unittest frontend.tests.test_product_usability_markup frontend.tests.test_dashboard_markup
```

Expected:

```text
FAIL: test_feedback_and_settings_controls_exist
FAIL: test_dashboard_contains_workbench_header_and_summary_regions
```

- [ ] **Step 3: 保持测试命名与后续实现函数一致**

后续实现必须使用以下名字，不要临时改名：

```javascript
const preferencesStorageKey = "simflow.preferences";

function loadPreferences() {}
function savePreferences(nextPreferences) {}
function applyPreferences() {}
function openSettingsPanel() {}
function closeSettingsPanel() {}
function showToast(message, tone) {}
function setActionLoading(button, isLoading, loadingText) {}
```

- [ ] **Step 4: 核对锚点覆盖范围**

本任务覆盖的设计要求：

```text
- 轻量设置入口
- 本地偏好持久化
- 不再只依赖 alert
- 仪表盘页头和工作台结构
```

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/tests/test_product_usability_markup.py frontend/tests/test_dashboard_markup.py
git commit -m "test: lock enterprise ui polish markup anchors"
```

### Task 2: 收敛全局 token、字体和页面节奏

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_dashboard_markup.py`

- [ ] **Step 1: 先根据设计稿重写全局 token 区和基础字体链**

将现有头部 token 从：

```css
:root {
  --panel: rgba(11, 18, 32, 0.82);
  --line: rgba(148, 163, 184, 0.14);
  --text: #f8fafc;
  --muted: #94a3b8;
  --brand: #38bdf8;
  --brand-soft: rgba(56, 189, 248, 0.14);
  --accent: #22c55e;
  --warn: #f59e0b;
  --radius-xl: 28px;
  --radius-lg: 22px;
  --radius-md: 18px;
  --shadow: 0 28px 64px rgba(2, 6, 23, 0.42);
}

body {
  font-family: "DM Sans", Arial, sans-serif;
}
```

收敛为：

```css
:root {
  --bg-canvas: #020617;
  --bg-shell: rgba(8, 15, 28, 0.92);
  --bg-panel: rgba(15, 23, 42, 0.78);
  --bg-panel-strong: rgba(15, 23, 42, 0.92);
  --bg-panel-soft: rgba(15, 23, 42, 0.58);
  --line-soft: rgba(148, 163, 184, 0.12);
  --line-strong: rgba(148, 163, 184, 0.22);
  --text-strong: #f8fafc;
  --text-main: #e2e8f0;
  --text-muted: #94a3b8;
  --text-faint: #64748b;
  --brand: #38bdf8;
  --brand-strong: #2563eb;
  --brand-soft: rgba(56, 189, 248, 0.12);
  --success: #22c55e;
  --warning: #f59e0b;
  --danger: #f97316;
  --radius-xl: 24px;
  --radius-lg: 18px;
  --radius-md: 14px;
  --radius-sm: 10px;
  --space-1: 8px;
  --space-2: 12px;
  --space-3: 16px;
  --space-4: 20px;
  --space-5: 24px;
  --space-6: 32px;
  --shadow-panel: 0 18px 40px rgba(2, 6, 23, 0.28);
  --shadow-raised: 0 12px 24px rgba(2, 6, 23, 0.22);
  --control-height: 44px;
  --control-height-sm: 36px;
  --page-max-width: 1440px;
}

body {
  font-family: "DM Sans", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", Arial, sans-serif;
  color: var(--text-main);
}
```

- [ ] **Step 2: 调整全局容器、页头和工具条结构**

在 `renderPageHeader()` 与通用样式中引入两层头部结构：

```javascript
function renderPageHeader(title, description, actions = "") {
  const statusClass = state.apiOnline ? "online" : "offline";
  const statusText = state.apiOnline ? `后端已连接 · ${apiBaseUrl}` : "当前显示本地示例数据";
  return `
    <section class="page-header page-header--split">
      <div class="page-header-main">
        <div class="eyebrow">运营工作台</div>
        <div class="page-title">
          <h1>${escapeHtml(title)}</h1>
          <p>${escapeHtml(description)}</p>
        </div>
      </div>
      <div class="page-header-side">
        <div class="status-group">
          <div class="status-pill ${statusClass}">${escapeHtml(statusText)}</div>
        </div>
        ${actions}
      </div>
    </section>
  `;
}
```

```css
.page-header--split {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.page-toolbar {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-4);
}
```

- [ ] **Step 3: 收敛卡片、列表和表单的间距与权重**

统一以下选择器：

```css
.sidebar,
.main,
.metric-card,
.panel-card,
.page-card,
.detail-card,
.table-row,
.summary-item,
.reminder-item,
.record-item,
.check-item,
.empty-state {
  background: var(--bg-panel);
  border: 1px solid var(--line-soft);
  box-shadow: var(--shadow-panel);
}

.field-group input,
.field-group select,
.field-group textarea,
.toolbar input,
.toolbar select {
  min-height: var(--control-height);
  border-radius: var(--radius-md);
  background: var(--bg-panel-soft);
  color: var(--text-strong);
}
```

- [ ] **Step 4: 运行静态测试确认结构已绿**

Run:

```bash
python -m unittest frontend.tests.test_dashboard_markup
```

Expected:

```text
OK
```

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/public/index.html frontend/tests/test_dashboard_markup.py
git commit -m "feat: tighten enterprise layout and visual tokens"
```

### Task 3: 补齐保存反馈、toast 和按钮 loading

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] **Step 1: 在主内容区加入统一反馈容器**

在 `body` 结构或 `main` 附近增加：

```html
<div class="toast-region" id="toastRegion" aria-live="polite" aria-atomic="true"></div>
```

并加入样式：

```css
.toast-region {
  position: fixed;
  top: 24px;
  right: 24px;
  display: grid;
  gap: 12px;
  z-index: 20;
}

.toast {
  min-width: 260px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-panel-strong);
  border: 1px solid var(--line-strong);
  color: var(--text-strong);
  box-shadow: var(--shadow-raised);
}

.toast.success { border-color: rgba(34, 197, 94, 0.26); }
.toast.warning { border-color: rgba(245, 158, 11, 0.28); }
.toast.error { border-color: rgba(249, 115, 22, 0.28); }
```

- [ ] **Step 2: 新增反馈辅助函数，替换仅有的 alert 模式**

```javascript
function showToast(message, tone = "success") {
  const region = document.getElementById("toastRegion");
  if (!region) return;

  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => toast.remove(), 2400);
}

function setActionLoading(button, isLoading, loadingText) {
  if (!button) return;
  if (!button.dataset.originalLabel) {
    button.dataset.originalLabel = button.textContent;
  }
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : button.dataset.originalLabel;
}
```

将现有保存流程从：

```javascript
window.alert(`项目更新失败：${error.message}`);
```

改成：

```javascript
showToast(`项目更新失败：${error.message}`, "error");
```

并在成功后补：

```javascript
showToast("项目更新已保存", "success");
```

- [ ] **Step 3: 给三个写操作都接入 loading 态**

```javascript
async function saveProjectDetail(event) {
  event.preventDefault();
  const submitButton = event.currentTarget.querySelector('button[type="submit"]');
  setActionLoading(submitButton, true, "保存中...");
  try {
    // existing patch logic
    showToast("项目更新已保存", "success");
  } catch (error) {
    showToast(`项目更新失败：${error.message}`, "error");
  } finally {
    setActionLoading(submitButton, false, "保存中...");
  }
}
```

同样模式应用到：

```javascript
async function savePackageRecord(event) {}
async function updateChecklistStatus(itemName, nextStatus) {}
```

- [ ] **Step 4: 运行产品静态测试**

Run:

```bash
python -m unittest frontend.tests.test_product_usability_markup
```

Expected:

```text
OK
```

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/public/index.html frontend/tests/test_product_usability_markup.py
git commit -m "feat: add enterprise feedback and loading states"
```

### Task 4: 增加轻量设置入口和本地偏好

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Test: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] **Step 1: 新增默认偏好对象和存储函数**

```javascript
const preferencesStorageKey = "simflow.preferences";
const defaultPreferences = {
  defaultPage: "dashboard",
  projectsSort: "deliveryAsc",
  density: "comfortable",
  showHelperText: true
};

function loadPreferences() {
  try {
    const raw = window.localStorage.getItem(preferencesStorageKey);
    return raw ? { ...defaultPreferences, ...JSON.parse(raw) } : { ...defaultPreferences };
  } catch (error) {
    return { ...defaultPreferences };
  }
}

function savePreferences(nextPreferences) {
  state.preferences = { ...state.preferences, ...nextPreferences };
  window.localStorage.setItem(preferencesStorageKey, JSON.stringify(state.preferences));
}
```

- [ ] **Step 2: 将默认页和默认排序接入现有路由与列表逻辑**

把当前读取方式：

```javascript
const currentPage = urlParams.get("page") || "dashboard";
```

改成：

```javascript
const initialPreferences = loadPreferences();
const currentPage = urlParams.get("page") || initialPreferences.defaultPage;
```

把列表排序默认值从硬编码接到偏好：

```javascript
const sortValue = document.getElementById("sortFilter")?.value || state.preferences.projectsSort;
```

- [ ] **Step 3: 新增右上角设置按钮和弹出轻面板**

```html
<button class="button-secondary" id="settingsButton" type="button">全局设置</button>

<aside class="settings-panel hidden" id="settingsPanel" aria-labelledby="settingsTitle">
  <div class="detail-card-head">
    <h3 id="settingsTitle">全局设置</h3>
    <button class="button-link" id="closeSettingsButton" type="button">关闭</button>
  </div>
  <form class="detail-edit-form" id="settingsForm">
    <div class="field-group">
      <label for="defaultPageSelect">默认首页</label>
      <select id="defaultPageSelect" name="defaultPage"></select>
    </div>
    <div class="field-group">
      <label for="defaultSortSelect">项目列表默认排序</label>
      <select id="defaultSortSelect" name="projectsSort"></select>
    </div>
    <div class="field-group">
      <label for="densitySelect">页面密度</label>
      <select id="densitySelect" name="density"></select>
    </div>
    <label class="toggle-field">
      <input id="helperTextToggle" name="showHelperText" type="checkbox">
      <span>显示辅助说明</span>
    </label>
    <div class="actions">
      <button class="button-primary" type="submit">保存设置</button>
    </div>
  </form>
</aside>
```

- [ ] **Step 4: 应用偏好到页面密度和辅助文案显示**

```javascript
function applyPreferences() {
  document.body.dataset.density = state.preferences.density;
  document.body.classList.toggle("helpers-hidden", !state.preferences.showHelperText);
}

function openSettingsPanel() {
  document.getElementById("settingsPanel")?.classList.remove("hidden");
}

function closeSettingsPanel() {
  document.getElementById("settingsPanel")?.classList.add("hidden");
}
```

```css
body[data-density="compact"] .page-card,
body[data-density="compact"] .detail-card,
body[data-density="compact"] .table-row {
  padding: 14px;
}

body.helpers-hidden .helper-text {
  display: none;
}
```

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/public/index.html frontend/tests/test_product_usability_markup.py
git commit -m "feat: add lightweight global ui preferences"
```

### Task 5: 端到端验证和诊断收口

**Files:**
- Verify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Verify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_dashboard_markup.py`
- Verify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] **Step 1: 运行前端静态回归测试**

Run:

```bash
python -m unittest frontend.tests.test_dashboard_markup frontend.tests.test_product_usability_markup
```

Expected:

```text
...
OK
```

- [ ] **Step 2: 跑完整项目回归，确认前后端行为不回退**

Run:

```bash
python -m unittest backend.tests.test_dashboard_payload backend.tests.test_project_updates frontend.tests.test_dashboard_markup frontend.tests.test_product_usability_markup
```

Expected:

```text
Ran 7 tests in 0.xxxs
OK
```

- [ ] **Step 3: 启动服务并验证关键页面**

Run:

```bash
bash restart-dev.sh
python -c "from urllib.request import urlopen; urls=['http://127.0.0.1:5173/','http://127.0.0.1:5173/?page=projects','http://127.0.0.1:5173/?page=detail&id=p-001']; [print(url, urlopen(url).status) for url in urls]"
```

Expected:

```text
http://127.0.0.1:5173/ 200
http://127.0.0.1:5173/?page=projects 200
http://127.0.0.1:5173/?page=detail&id=p-001 200
```

- [ ] **Step 4: 运行诊断检查最近修改文件**

需要检查：

```text
- frontend/public/index.html
- frontend/tests/test_dashboard_markup.py
- frontend/tests/test_product_usability_markup.py
```

Expected:

```text
No diagnostics
```

- [ ] **Step 5: 提交本任务**

```bash
git add frontend/public/index.html frontend/tests/test_dashboard_markup.py frontend/tests/test_product_usability_markup.py
git commit -m "chore: verify enterprise ui polish rollout"
```
