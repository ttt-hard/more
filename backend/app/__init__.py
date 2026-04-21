"""more 后端包入口。

子包布局：
- `api/`：FastAPI 路由 + 依赖注入 + 统一异常处理
- `agent/`：单 agent 协调器、运行时、工具注册表
- `chains/`：Prompt 模板注册表与 harness
- `infrastructure/`：文件锁、MCP stdio 客户端、watcher 接口
- `providers/`：LLM provider 抽象与 LiteLLM 实现
- `services/`：业务服务（answering / memory / retrieval / turn_* / mcp 等）
- `stores/`：基于 `.more/` 侧车目录的文件型存储
- 顶层模块：`domain` / `workspace_fs` / `notes` / `ingest` / `search` /
  `llm` / `observability` / `runtime_control` / `runtime_registry` / `main`
"""
