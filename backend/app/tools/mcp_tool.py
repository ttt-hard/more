"""MCP 桥接工具。

若 `mcp_service` 存在，把每个已注册的 MCP server 工具展开成独立 registry
条目（通过 `_build_bound_handler` 绑定 server_id / tool_name），同时保留
一个通用 `mcp_bridge` 供 planner 根据 server/tool 参数显式转发；若未配置
则只注册一个立即失败的占位符。
"""

from __future__ import annotations

from .base import ToolContext, ToolResult


def register_mcp_tools(registry, *, mcp_service=None) -> None:
    if mcp_service is None:
        registry.register(
            "mcp_bridge",
            _unconfigured_mcp_bridge,
            kind="external",
            description="Dispatch a request to a configured MCP server tool.",
        )
        return

    registry.register(
        "mcp_bridge",
        lambda args, context: _dispatch_generic(args, context, mcp_service),
        kind="external",
        description="Dispatch a request to a configured MCP server tool.",
    )
    for tool_spec in mcp_service.list_tool_catalog():
        registry.register(
            str(tool_spec["name"]),
            _build_bound_handler(
                mcp_service,
                server_id=str(tool_spec["server_id"]),
                tool_name=str(tool_spec["tool_name"]),
            ),
            kind="external",
            description=str(tool_spec.get("description") or ""),
        )


def _build_bound_handler(mcp_service, *, server_id: str, tool_name: str):
    def _handler(args: dict[str, object], context: ToolContext) -> ToolResult:
        return mcp_service.execute_tool(server_id, tool_name, args, context)

    return _handler


def _dispatch_generic(args: dict[str, object], context: ToolContext, mcp_service) -> ToolResult:
    server_id = str(args.get("server") or args.get("server_id") or "").strip()
    tool_name = str(args.get("tool") or args.get("tool_name") or "").strip()
    if not server_id or not tool_name:
        return ToolResult(
            ok=False,
            tool="mcp_bridge",
            summary="",
            error="mcp_bridge requires server/tool identifiers",
            payload={"server": server_id, "tool": tool_name},
        )
    forwarded_args = {
        key: value
        for key, value in args.items()
        if key not in {"server", "server_id", "tool", "tool_name"}
    }
    return mcp_service.execute_tool(server_id, tool_name, forwarded_args, context)


def _unconfigured_mcp_bridge(args: dict[str, object], context: ToolContext) -> ToolResult:
    del context
    server = str(args.get("server") or "").strip()
    tool_name = str(args.get("tool") or "").strip()
    return ToolResult(
        ok=False,
        tool="mcp_bridge",
        summary="",
        error=(
            "MCP bridge is not configured yet. "
            f"Requested server=`{server or 'unknown'}` tool=`{tool_name or 'unknown'}`."
        ),
        payload={
            "server": server,
            "tool": tool_name,
            "available": False,
            "integration": "reserved",
        },
    )


__all__ = ["register_mcp_tools"]
