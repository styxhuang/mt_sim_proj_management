# Product Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove transitional placeholder copy and complete the next usable product features for detail editing, delivery/package maintenance, and project-list efficiency.

**Architecture:** Keep the current single-file frontend shell and Python JSON backend, but extend the backend with focused project update endpoints and persist the edited project records back to `projects.json`. The frontend continues to use query-param routing and adds edit forms/actions inside the existing create, projects, and detail pages without changing the startup stack.

**Tech Stack:** Static HTML/CSS/vanilla JavaScript frontend, Python `http.server` backend, local JSON persistence, Python `unittest`.

---

### Task 1: Add Project Update APIs

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\src\main.py`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\tests\test_dashboard_payload.py`
- Create: `d:\0-wiki\git-repo\projects\sim_delivery_system\backend\tests\test_project_updates.py`

- [ ] Add failing backend tests for project summary updates, checklist updates, and package record creation.
- [ ] Add backend helpers to find/update/save a project in `PROJECTS`.
- [ ] Add `PATCH /api/projects/:id`, `PATCH /api/projects/:id/checklist`, and `POST /api/projects/:id/package-records`.
- [ ] Run focused backend tests until they pass.

### Task 2: Remove Placeholder Copy And Add Detail Editing

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Create: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] Add a failing frontend markup test that checks placeholder transitional copy is removed and detail edit controls are present.
- [ ] Replace dashboard/create/detail transitional copy with production-facing copy.
- [ ] Add project detail edit form for stage, progress, status, package status, amount, delivery date, and root directory.
- [ ] Submit detail edits to the new backend endpoint and refresh state/detail view.
- [ ] Run focused frontend markup tests until they pass.

### Task 3: Add Checklist And Package Record Editing

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] Extend the failing markup test to require checklist action buttons and package record form controls.
- [ ] Add delivery checklist status buttons in the detail page and wire them to the checklist update API.
- [ ] Add package record creation form in the detail page and wire it to the package record API.
- [ ] Refresh the detail/project state after each action and keep fallback behavior intact.
- [ ] Run focused frontend markup tests until they pass.

### Task 4: Improve Project List Filters And Sorting

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\public\index.html`
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\frontend\tests\test_product_usability_markup.py`

- [ ] Extend the failing markup test to require sort controls and package-status filtering.
- [ ] Add project-list sort selector and package-status filter.
- [ ] Apply sorting for delivery date, amount, and progress while preserving current search/stage/status filters.
- [ ] Run focused frontend markup tests until they pass.

### Task 5: Verify End-To-End Behavior

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\README.md` (only if startup/usage note needs refresh)

- [ ] Run backend unit tests and frontend markup tests together.
- [ ] Restart the app with `bash restart-dev.sh`.
- [ ] Verify `http://localhost:5173/`, `?page=projects`, and `?page=detail&id=p-001` still return `200`.
- [ ] Verify the new backend endpoints respond correctly through local running services.
