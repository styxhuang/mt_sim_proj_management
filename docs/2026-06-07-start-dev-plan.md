# Start Dev Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bash one-command startup script that checks the project structure and starts the Node.js frontend and Python backend in the background with separate logs.

**Architecture:** Keep the solution project-local and simple. A single `start-dev.sh` script at the project root validates runtime tools, checks startup entry files, creates `logs/` and `run/`, then launches frontend and backend independently with PID files for later stop/restart workflows.

**Tech Stack:** Bash, Node.js/npm for frontend, Python for backend

---

### Task 1: Add root startup script

**Files:**
- Create: `d:\0-wiki\git-repo\projects\sim_delivery_system\start-dev.sh`

- [ ] **Step 1: Create the script with environment and path checks**

Add checks for:

```bash
frontend/package.json
backend/src/main.py or backend/src/app.py
node
npm
python3 or python
```

- [ ] **Step 2: Add startup commands**

Use:

```bash
cd frontend && npm run dev
cd backend && python -m uvicorn src.main:app --reload
```

with fallback to `src.app:app` when `src/main.py` is absent.

- [ ] **Step 3: Add background process handling**

Create and use:

```text
logs/frontend.log
logs/backend.log
run/frontend.pid
run/backend.pid
```

- [ ] **Step 4: Add clear console messages**

Print success/failure messages that tell the user what is missing and where the logs are located.

### Task 2: Verify behavior

**Files:**
- Modify: `d:\0-wiki\git-repo\projects\sim_delivery_system\README.md`

- [ ] **Step 1: Make script executable in Git-friendly form**

Ensure the file uses a normal shebang and LF-friendly shell syntax:

```bash
#!/usr/bin/env bash
```

- [ ] **Step 2: Add README usage note**

Document:

```bash
bash start-dev.sh
```

- [ ] **Step 3: Run lightweight verification**

Verify the script at least reaches the intended validation failures in the current empty project, proving the checks work before frontend/backend are initialized.
