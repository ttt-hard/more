"""MCP 客户端子包。

`MCPService` 管理 `MCPServerDefinition` 的注册、按 transport 连接（stdio /
http / builtin）、同步 `MCPToolDefinition` 清单，并把调用桥接到
`ToolRegistry` 的 `mcp_bridge` 条目。`execute_tool` 是 planner / 回归测试的
统一入口，内部返回 `ToolResult`。
"""

from .service import MCPService

__all__ = ["MCPService"]
