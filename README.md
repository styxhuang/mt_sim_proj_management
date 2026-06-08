# sim_delivery_system

计算模拟项目管理系统项目目录。

## 目录结构

```text
sim_delivery_system/
  frontend/      Node.js 前端项目
    public/      静态资源
    src/         前端源码
  backend/       后端项目
    src/         后端源码
  docs/          设计文档、接口文档、开发记录
```

## 约定

- `frontend/` 后续可初始化为 `Vite`、`Next.js` 或其他 Node.js 前端工程
- `backend/` 后续根据你的技术选择再补框架
- `docs/` 用于放产品说明、接口设计、部署说明等

## 启动

在项目根目录执行：

```bash
bash start-dev.sh
```

脚本会分别检查前端 Node.js 启动条件和后端 Python 启动条件，校验 `5173` 和 `8000` 端口是否空闲，然后同时启动两端，并将日志写入 `logs/`。

停止服务：

```bash
bash stop-dev.sh
```

脚本会根据 `run/` 下的 PID 文件停止前端和后端进程，并自动清理失效的 PID 文件。

查看状态：

```bash
bash status-dev.sh
```

重启服务：

```bash
bash restart-dev.sh
```

如果默认端口冲突，可以临时指定端口：

```bash
FRONTEND_PORT=5175 BACKEND_PORT=8011 bash start-dev.sh
```

后端项目数据默认存放在 `backend/data/projects.json`。如需临时测试，也可以覆盖数据文件路径：

```bash
PROJECTS_DATA_FILE=/tmp/sim-projects.json PORT=8011 python backend/src/main.py
```
