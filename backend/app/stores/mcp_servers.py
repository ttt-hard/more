"""MCP 服务器配置存储。

`MCPServerStore` 把所有已注册的 MCP server 定义（id / name / transport /
command / args / env / tools）集中存在 `.more/mcp/servers.json` 这一个
JSON 数组里。`MCPService` 启动时会 `list_servers` 并分别 connect 以
同步工具清单。
"""

from __future__ import annotations

import json
from dataclasses import asdict

from ..domain import MCPServerDefinition, MCPToolDefinition, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS


DEFAULT_MCP_SERVERS = [
    {
        "id": "workspace-hub",
        "name": "Workspace Hub",
        "description": "Builtin MCP-style workspace utilities.",
        "transport": "builtin",
        "command": "",
        "args": [],
        "env": {},
        "working_directory": None,
        "enabled": True,
        "tools": [
            {
                "name": "echo",
                "description": "Echo the provided input for connectivity checks.",
                "input_schema": {"text": "string"},
                "execution_mode": "builtin",
                "builtin_action": "echo",
                "enabled": True,
            },
            {
                "name": "workspace_search",
                "description": "Search the workspace using the hybrid retrieval service.",
                "input_schema": {"query": "string", "limit": "integer"},
                "execution_mode": "builtin",
                "builtin_action": "workspace_search",
                "enabled": True,
            },
            {
                "name": "workspace_memory_search",
                "description": "Search accepted workspace memory records.",
                "input_schema": {"query": "string", "limit": "integer"},
                "execution_mode": "builtin",
                "builtin_action": "workspace_memory_search",
                "enabled": True,
            },
            {
                "name": "read_active_note",
                "description": "Read the current active note bound to the thread.",
                "input_schema": {},
                "execution_mode": "builtin",
                "builtin_action": "read_active_note",
                "enabled": True,
            },
        ],
    }
]


class MCPServerStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.mcp_root = self.fs.sidecar_root / "mcp"
        self.mcp_root.mkdir(parents=True, exist_ok=True)
        self.servers_path = self.mcp_root / "servers.json"

    def list_servers(self, *, include_disabled: bool = False) -> list[MCPServerDefinition]:
        servers = [self._coerce_server(payload) for payload in self._read_servers()]
        if not include_disabled:
            servers = [server for server in servers if server.enabled]
        servers.sort(key=lambda item: item.name.casefold())
        return servers

    def upsert_server(self, server: MCPServerDefinition) -> MCPServerDefinition:
        # RLock-based locked_path lets us wrap the full RMW so concurrent upserts
        # cannot overwrite each other's changes.
        with locked_path(self.servers_path):
            payloads = self._read_servers()
            updated = False
            for index, payload in enumerate(payloads):
                if str(payload.get("id") or "") != server.id:
                    continue
                payloads[index] = asdict(server)
                updated = True
                break
            if not updated:
                payloads.append(asdict(server))
            self._write_servers(payloads)
        return server

    def delete_server(self, server_id: str) -> None:
        with locked_path(self.servers_path):
            payloads = [payload for payload in self._read_servers() if str(payload.get("id") or "") != server_id]
            self._write_servers(payloads)

    def _read_servers(self) -> list[dict[str, object]]:
        if not self.servers_path.exists():
            now = utc_now_iso()
            payloads: list[dict[str, object]] = []
            for item in DEFAULT_MCP_SERVERS:
                payload = dict(item)
                payload["created_at"] = now
                payload["updated_at"] = now
                payloads.append(payload)
            self._write_servers(payloads)
            return payloads
        with locked_path(self.servers_path):
            raw = json.loads(self.servers_path.read_text(encoding="utf-8") or "[]")
        if not isinstance(raw, list):
            raise ValueError("servers.json must contain a list")
        return [payload for payload in raw if isinstance(payload, dict)]

    def _write_servers(self, payloads: list[dict[str, object]]) -> None:
        with locked_path(self.servers_path):
            self.servers_path.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")

    def _coerce_server(self, payload: dict[str, object]) -> MCPServerDefinition:
        tools_payload = payload.get("tools") or []
        tools = []
        for item in tools_payload:
            if not isinstance(item, dict):
                continue
            tools.append(
                MCPToolDefinition(
                    name=str(item.get("name") or ""),
                    description=str(item.get("description") or ""),
                    input_schema=dict(item.get("input_schema") or {}),
                    execution_mode=str(item.get("execution_mode") or "builtin"),
                    builtin_action=str(item.get("builtin_action") or "echo"),
                    enabled=bool(item.get("enabled", True)),
                )
            )
        return MCPServerDefinition(
            id=str(payload.get("id") or ""),
            name=str(payload.get("name") or payload.get("id") or "Unnamed MCP Server"),
            description=str(payload.get("description") or ""),
            transport=str(payload.get("transport") or "builtin"),
            command=str(payload.get("command") or ""),
            args=[str(item) for item in payload.get("args") or []],
            env={str(key): str(value) for key, value in dict(payload.get("env") or {}).items()},
            working_directory=str(payload.get("working_directory")) if payload.get("working_directory") else None,
            enabled=bool(payload.get("enabled", True)),
            tools=tools,
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or ""),
        )


__all__ = ["MCPServerStore"]
