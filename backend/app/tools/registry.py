"""工具注册表。

`ToolRegistry` 维护 `ToolDefinition`（name / handler / kind / approval_gated
/ description / parameters），提供 `register / execute / has / names /
get_definition / as_function_schemas`。`build_default_tool_registry` 组装
所有原生工具 + MCP 桥接，作为 runtime 的默认工具集。

`parameters` 用 JSON Schema 描述工具接受的 args，供 OpenAI / DeepSeek 等
providers 的原生 function calling 使用。工具不显式传时默认为
`{"type": "object"}`（参数自由），LLM 仍能从 description 推测 args；
精确 schema 能大幅减少 planner 出错概率。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import ToolContext, ToolHandler, ToolKind, ToolResult
from . import (
    create_note as _create_note,
    delete_path as _delete_path,
    edit_file as _edit_file,
    glob_search as _glob_search,
    grep_search as _grep_search,
    import_file as _import_file,
    import_url as _import_url,
    link_notes as _link_notes,
    list_directory as _list_directory,
    load_skill as _load_skill,
    move_path as _move_path,
    read_file as _read_file,
    read_note as _read_note,
    read_preference as _read_preference,
    save_preference as _save_preference,
    search_notes as _search_notes,
    summarize_note as _summarize_note,
    update_note_metadata as _update_note_metadata,
    write_file as _write_file,
)
from .mcp_tool import register_mcp_tools


_DEFAULT_PARAMETERS: dict[str, object] = {"type": "object", "properties": {}}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler
    kind: ToolKind = "native"
    approval_gated: bool = False
    description: str = ""
    parameters: dict[str, object] = field(default_factory=lambda: dict(_DEFAULT_PARAMETERS))

    def function_schema(self) -> dict[str, object]:
        """OpenAI-compatible function calling tool schema.

        Shape: ``{"type": "function", "function": {"name", "description", "parameters"}}``.
        `description` ends up in the model prompt; `parameters` constrains the
        JSON arguments the model is allowed to emit.
        """
        params = self.parameters if self.parameters else dict(_DEFAULT_PARAMETERS)
        # Ensure the schema is a JSON object at the top level (OpenAI requirement).
        if not isinstance(params, dict) or params.get("type") != "object":
            params = dict(_DEFAULT_PARAMETERS)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description or "",
                "parameters": params,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        handler: ToolHandler,
        *,
        kind: ToolKind = "native",
        approval_gated: bool = False,
        description: str = "",
        parameters: dict[str, object] | None = None,
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            handler=handler,
            kind=kind,
            approval_gated=approval_gated,
            description=description,
            parameters=parameters if parameters is not None else dict(_DEFAULT_PARAMETERS),
        )

    def execute(self, name: str, args: dict[str, object], context: ToolContext) -> ToolResult:
        definition = self._tools.get(name)
        if definition is None:
            raise KeyError(f"Unknown tool: {name}")
        result = definition.handler(args, context)
        result.payload.setdefault(
            "tool_definition",
            {
                "name": definition.name,
                "kind": definition.kind,
                "approval_gated": definition.approval_gated,
                "description": definition.description,
            },
        )
        return result

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get_definition(self, name: str) -> ToolDefinition:
        definition = self._tools.get(name)
        if definition is None:
            raise KeyError(f"Unknown tool: {name}")
        return definition

    def as_function_schemas(self) -> list[dict[str, object]]:
        """Return every registered tool as an OpenAI-compatible tool schema."""
        return [self._tools[name].function_schema() for name in self.names()]


def build_default_tool_registry(*, mcp_service=None) -> ToolRegistry:
    registry = ToolRegistry()
    # Filesystem tools.
    _read_file.register(registry)
    _write_file.register(registry)
    _edit_file.register(registry)
    _list_directory.register(registry)
    _move_path.register(registry)
    _delete_path.register(registry)
    _glob_search.register(registry)
    _grep_search.register(registry)
    # Note tools.
    _read_note.register(registry)
    _create_note.register(registry)
    _update_note_metadata.register(registry)
    _summarize_note.register(registry)
    _link_notes.register(registry)
    # Ingest tools.
    _import_file.register(registry)
    _import_url.register(registry)
    # Search tools (registers both `search_notes` and `search_workspace`).
    _search_notes.register(registry)
    # Memory / preference tools.
    _save_preference.register(registry)
    _read_preference.register(registry)
    # Skills (lazy-load full SKILL.md body).
    _load_skill.register(registry)
    # MCP bridge tools (dynamic — one per registered MCP server tool).
    register_mcp_tools(registry, mcp_service=mcp_service)
    return registry
