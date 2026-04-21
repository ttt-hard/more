"""`search_notes` + `search_workspace` tools：lexical 检索工作区内容。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def search_notes(args: dict[str, object], context: ToolContext) -> ToolResult:
    query = str(args.get("query") or context.prompt).strip()
    if not query:
        return ToolResult(ok=False, tool="search_notes", summary="", error="search_notes requires query")
    hits = context.search_service.search(query, limit=int(args.get("limit") or 5))
    top = hits[0] if hits else None
    events = [
        {"type": "tool_started", "tool": "search_notes", "query": query},
        {"type": "tool_finished", "tool": "search_notes", "query": query},
    ]
    if top:
        answer = (
            f"I found {len(hits)} relevant workspace result(s).\n"
            f"Top hit: `{top.path}`\n"
            f"Snippet: {top.snippet}"
        )
        return ToolResult(
            ok=True,
            tool="search_notes",
            summary=answer,
            citations=[hit.path for hit in hits[:3]],
            events=events,
            payload={"count": len(hits)},
        )
    return ToolResult(
        ok=True,
        tool="search_notes",
        summary="No matching notes were found.",
        events=events,
        payload={"count": 0},
    )


def search_workspace(args: dict[str, object], context: ToolContext) -> ToolResult:
    return search_notes(args, context)


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search query. If omitted, the user's current prompt is used as the query.",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of hits to return (default 5).",
            "minimum": 1,
            "maximum": 50,
        },
    },
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "search_notes",
        search_notes,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )
    registry.register(
        "search_workspace",
        search_workspace,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "register", "search_notes", "search_workspace"]
