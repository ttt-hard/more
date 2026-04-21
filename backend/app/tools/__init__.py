"""Agent 工具实现集合。

`registry` 暴露 `ToolRegistry / ToolDefinition / build_default_tool_registry`；
`base` 暴露 `ToolContext / ToolResult / ToolHandler / ToolKind`。每个其他子模块
都提供一个 `register_xxx_tools(registry)` 函数供 `build_default_tool_registry`
按需调用：
- `filesystem`：读 / 写 / 编辑 / 移动 / 删除 / glob / grep
- `notes`：笔记 CRUD 与摘要 / 互链
- `ingest`：本地文件 + URL 导入为笔记
- `search`：lexical 搜索
- `memory`：用户偏好读写
- `mcp_tool`：外部 MCP 工具桥接
"""

from .base import ToolContext, ToolHandler, ToolKind, ToolResult
from .registry import ToolDefinition, ToolRegistry, build_default_tool_registry

__all__ = [
    "ToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolKind",
    "ToolRegistry",
    "ToolResult",
    "build_default_tool_registry",
]
