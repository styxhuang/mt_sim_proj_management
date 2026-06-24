"""计算模拟项目交付管理系统后端包。

模块划分：
- config:       运行配置（端口、数据库路径、LLM 设置）
- database:     SQLite 连接与建表
- projects:     项目领域逻辑与种子数据
- dashboard:    运营看板聚合
- llm.client:   OpenAI 兼容流式客户端
- skills:       大模型技能注册表（解析 / 生成方案 / 优化方案）
- requirements: 需求解析任务编排
- server:       HTTP 服务与路由
"""

__all__ = [
    "config",
    "database",
    "projects",
    "dashboard",
    "requirements",
    "server",
]
