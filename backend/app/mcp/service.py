"""MCP server 业务服务。

`MCPService` 管理 `MCPServerStore` 里配置的外部服务器：启动 stdio 客户端
同步工具清单、列出 `tool_catalog`、把 agent 的 `execute_tool` 调用转发到
对应 MCP server，并把结果包成 `ToolResult`。
"""

from __future__ import annotations

from dataclasses import asdict, replace

from ..domain import MCPServerDefinition, MCPToolDefinition, utc_now_iso
from ..infrastructure.mcp_stdio import MCPStdioClient, MCPTransportError
from ..stores import MCPServerStore, MCPServerStorePort
from ..workspace_fs import WorkspaceFS


class MCPService:
    def __init__(self, fs: WorkspaceFS, *, server_store: MCPServerStorePort | None = None) -> None:
        self.fs = fs
        self.server_store = server_store or MCPServerStore(fs)

    def list_servers(self, *, include_disabled: bool = False) -> list[MCPServerDefinition]:
        return self.server_store.list_servers(include_disabled=include_disabled)

    def upsert_server(
        self,
        server_id: str,
        *,
        name: str,
        description: str = "",
        transport: str = "builtin",
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        working_directory: str | None = None,
        enabled: bool = True,
        tools: list[dict[str, object]] | None = None,
    ) -> MCPServerDefinition:
        existing = {server.id: server for server in self.server_store.list_servers(include_disabled=True)}
        current = existing.get(server_id)
        now = utc_now_iso()
        definitions = [
            MCPToolDefinition(
                name=str(tool.get("name") or "").strip(),
                description=str(tool.get("description") or "").strip(),
                input_schema=dict(tool.get("input_schema") or {}),
                execution_mode=str(tool.get("execution_mode") or "builtin"),
                builtin_action=str(tool.get("builtin_action") or "echo"),
                enabled=bool(tool.get("enabled", True)),
            )
            for tool in (tools or [])
            if str(tool.get("name") or "").strip()
        ]
        server = MCPServerDefinition(
            id=server_id,
            name=name.strip() or server_id,
            description=description.strip(),
            transport=transport.strip() or "builtin",
            command=(command.strip() if command.strip() else (current.command if current is not None else "")),
            args=[item.strip() for item in (args or (list(current.args) if current is not None else [])) if item.strip()],
            env={key.strip(): value for key, value in (env or (dict(current.env) if current is not None else {})).items() if key.strip()},
            working_directory=(working_directory.strip() if isinstance(working_directory, str) and working_directory.strip() else (current.working_directory if current is not None else None)),
            enabled=enabled,
            tools=definitions,
            created_at=current.created_at if current is not None else now,
            updated_at=now,
        )
        return self.server_store.upsert_server(server)

    def sync_server(self, server_id: str) -> MCPServerDefinition:
        server = self.get_server(server_id)
        if server.transport == "builtin":
            return server
        if server.transport != "stdio":
            raise ValueError(f"Unsupported MCP transport: {server.transport}")
        # MCPStdioClient.list_tools() wraps start/list/close in its own try/finally,
        # so no external close is needed here.
        discovered_tools = MCPStdioClient(server).list_tools()
        updated = replace(
            server,
            tools=discovered_tools,
            updated_at=utc_now_iso(),
        )
        return self.server_store.upsert_server(updated)

    def delete_server(self, server_id: str) -> None:
        self.server_store.delete_server(server_id)

    def get_server(self, server_id: str) -> MCPServerDefinition:
        for server in self.server_store.list_servers(include_disabled=True):
            if server.id == server_id:
                return server
        raise FileNotFoundError(f"MCP server not found: {server_id}")

    def list_tool_catalog(self) -> list[dict[str, object]]:
        catalog: list[dict[str, object]] = []
        for server in self.list_servers():
            for tool in server.tools:
                if not tool.enabled:
                    continue
                catalog.append(
                    {
                        "name": self.tool_action_name(server.id, tool.name),
                        "server_id": server.id,
                        "tool_name": tool.name,
                        "description": tool.description,
                        "kind": "external",
                        "approval_gated": False,
                        "input_schema": tool.input_schema,
                        "transport": server.transport,
                        "execution_mode": tool.execution_mode,
                    }
                )
        catalog.sort(key=lambda item: (str(item["server_id"]), str(item["tool_name"])))
        return catalog

    def list_server_tools(self, server_id: str) -> list[dict[str, object]]:
        server = self.get_server(server_id)
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "enabled": tool.enabled,
                "input_schema": tool.input_schema,
                "execution_mode": tool.execution_mode,
                "builtin_action": tool.builtin_action,
                "action_name": self.tool_action_name(server.id, tool.name),
            }
            for tool in server.tools
        ]

    def execute_tool(self, server_id: str, tool_name: str, args: dict[str, object], context) -> object:
        from ..tools.base import ToolResult

        server = self.get_server(server_id)
        tool = next((candidate for candidate in server.tools if candidate.name == tool_name and candidate.enabled), None)
        if tool is None:
            raise KeyError(f"MCP tool not found: {server_id}/{tool_name}")
        if server.transport == "builtin":
            return self._execute_builtin(tool, args, context, server_id=server_id)
        if server.transport == "stdio":
            try:
                result = MCPStdioClient(server).call_tool(tool_name, args)
            except MCPTransportError as error:
                return ToolResult(
                    ok=False,
                    tool=self.tool_action_name(server_id, tool_name),
                    summary="",
                    error=str(error),
                    payload={"server_id": server_id, "tool_name": tool_name, "transport": server.transport},
                )
            return ToolResult(
                ok=result.ok,
                tool=self.tool_action_name(server_id, tool_name),
                summary=result.summary,
                citations=result.citations,
                payload={"server_id": server_id, "tool_name": tool_name, "transport": server.transport, **result.payload},
                error=result.error,
            )
        return ToolResult(
            ok=False,
            tool=self.tool_action_name(server_id, tool_name),
            summary="",
            error=f"MCP transport `{server.transport}` is not implemented yet.",
            payload={"server_id": server_id, "tool_name": tool_name, "transport": server.transport},
        )

    def _execute_builtin(self, tool: MCPToolDefinition, args: dict[str, object], context, *, server_id: str):
        from ..tools.base import ToolResult

        action_name = self.tool_action_name(server_id, tool.name)
        if tool.builtin_action == "echo":
            text = str(args.get("text") or "").strip()
            return ToolResult(
                ok=True,
                tool=action_name,
                summary=text or "Echo completed.",
                payload={"text": text, "server_id": server_id, "tool_name": tool.name},
            )
        if tool.builtin_action == "workspace_search":
            query = str(args.get("query") or context.prompt).strip()
            limit = int(args.get("limit") or 5)
            hits = context.search_service.search(query, limit=limit) if query else []
            lines = [f"MCP workspace search matched {len(hits)} result(s)."]
            lines.extend(f"- {hit.path}: {hit.snippet}" for hit in hits[:limit])
            return ToolResult(
                ok=True,
                tool=action_name,
                summary="\n".join(lines),
                citations=[hit.path for hit in hits[:limit]],
                payload={"count": len(hits), "query": query},
            )
        if tool.builtin_action == "workspace_memory_search":
            query = str(args.get("query") or context.prompt).strip()
            limit = int(args.get("limit") or 5)
            memory_context = context.memory_service.build_context(query=query, current_note_path=context.current_note_path, limit=limit)
            refs = memory_context.workspace_memory[:limit]
            lines = [f"MCP workspace memory matched {len(refs)} record(s)."]
            lines.extend(f"- {record.kind}: {record.value}" for record in refs)
            return ToolResult(
                ok=True,
                tool=action_name,
                summary="\n".join(lines),
                payload={"count": len(refs), "query": query, "records": [asdict(record) for record in refs]},
            )
        if tool.builtin_action == "read_active_note":
            path = context.current_note_path
            if not path:
                return ToolResult(ok=False, tool=action_name, summary="", error="No active note is bound to the current thread.")
            note = context.note_service.get_note(path)
            return ToolResult(
                ok=True,
                tool=action_name,
                summary=f"Active note `{note.meta.title}`:\n\n{note.content[:600].strip()}",
                citations=[note.meta.relative_path],
                payload={"note": asdict(note.meta)},
            )
        return ToolResult(
            ok=False,
            tool=action_name,
            summary="",
            error=f"Builtin MCP action `{tool.builtin_action}` is not supported.",
            payload={"server_id": server_id, "tool_name": tool.name, "builtin_action": tool.builtin_action},
        )

    @staticmethod
    def tool_action_name(server_id: str, tool_name: str) -> str:
        normalized_server = "".join(char if char.isalnum() else "_" for char in server_id.strip())
        normalized_tool = "".join(char if char.isalnum() else "_" for char in tool_name.strip())
        return f"mcp__{normalized_server}__{normalized_tool}"


__all__ = ["MCPService"]
