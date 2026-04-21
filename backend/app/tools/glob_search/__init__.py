"""`glob_search` tool：按 glob 模式查找工作区文件。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def glob_search(args: dict[str, object], context: ToolContext) -> ToolResult:
    pattern = str(args.get("pattern") or "").strip()
    include_hidden = bool(args.get("include_hidden", False))
    if not pattern:
        return ToolResult(ok=False, tool="glob_search", summary="", error="glob_search requires pattern")
    entries = context.fs.glob(pattern, include_hidden=include_hidden)
    lines = [f"Glob `{pattern}` matched {len(entries)} item(s):"]
    lines.extend(f"- {entry.kind}: {entry.path}" for entry in entries[:20])
    return ToolResult(
        ok=True,
        tool="glob_search",
        summary="\n".join(lines),
        citations=[entry.path for entry in entries[:5]],
        payload={"count": len(entries)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Glob pattern, e.g. 'Notes/**/*.md'.",
        },
        "include_hidden": {
            "type": "boolean",
            "description": "If true, include entries whose name starts with a dot (e.g. .more/).",
        },
    },
    "required": ["pattern"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "glob_search",
        glob_search,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "glob_search", "register"]
