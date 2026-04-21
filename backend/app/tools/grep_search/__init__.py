"""`grep_search` tool：在工作区文本文件内搜索匹配行。"""

from __future__ import annotations

from pathlib import Path

from ..base import ToolContext, ToolResult

PROMPT = (Path(__file__).parent / "prompt.md").read_text(encoding="utf-8")


def grep_search(args: dict[str, object], context: ToolContext) -> ToolResult:
    pattern = str(args.get("pattern") or "").strip()
    include_hidden = bool(args.get("include_hidden", False))
    if not pattern:
        return ToolResult(ok=False, tool="grep_search", summary="", error="grep_search requires pattern")
    hits = context.fs.grep(pattern, include_hidden=include_hidden)
    lines = [f"Grep `{pattern}` matched {len(hits)} line(s):"]
    lines.extend(f"- {hit['path']}:{hit['line_number']} {hit['line']}" for hit in hits[:20])
    return ToolResult(
        ok=True,
        tool="grep_search",
        summary="\n".join(lines),
        citations=[str(hit["path"]) for hit in hits[:5]],
        payload={"count": len(hits)},
    )


PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Literal substring to find inside text files (not a regex).",
        },
        "include_hidden": {
            "type": "boolean",
            "description": "If true, include hidden files/directories in the scan.",
        },
    },
    "required": ["pattern"],
    "additionalProperties": False,
}


def register(registry) -> None:
    registry.register(
        "grep_search",
        grep_search,
        kind="native",
        description=PROMPT,
        parameters=PARAMETERS,
    )


__all__ = ["PARAMETERS", "PROMPT", "grep_search", "register"]
