"""LLM 不可用时的正则回退规划器。

`RegexFallbackPlanner` 用关键字 / 正则扫描 prompt（如 "delete path: x.md"、
"read note:"、"search"），直接映射到本地工具调用，产出一份静态的
`RuntimeOutcome`。当 LLM provider 未配置、或 LLM 调用失败无法恢复时由
`AgentRuntime` 自动切换到这里，保证基本功能仍可用。
"""

from __future__ import annotations

import re

from ..domain import SearchHit
from .events import coerce_agent_event
from .outcome import RuntimeOutcome
from ..tools.base import ToolContext
from ..tools.registry import ToolRegistry


class RegexFallbackPlanner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(
        self,
        *,
        prompt: str,
        current_note_path: str | None,
        retrieval_hits: list[SearchHit],
        default_note_dir: str,
        context: ToolContext,
    ) -> RuntimeOutcome:
        del default_note_dir
        normalized = prompt.casefold()

        tool_matchers = [
            ("read_file", re.search(r"(?:read|open)\s+file[:\s]+(.+)", prompt, flags=re.IGNORECASE)),
            ("list_directory", re.search(r"(?:list|show)\s+(?:directory|dir)[:\s]*(.*)", prompt, flags=re.IGNORECASE)),
            ("import_file", re.search(r"(?:import|ingest)\s+file[:\s]+(.+)", prompt, flags=re.IGNORECASE)),
            ("import_url", re.search(r"(?:import|ingest)\s+url[:\s]+(.+)", prompt, flags=re.IGNORECASE)),
            ("delete_path", re.search(r"(?:delete|remove)\s+path[:\s]+(.+)", prompt, flags=re.IGNORECASE)),
            ("create_note", re.search(r"(?:create|new)\s+note[:\s]+(.+)", prompt, flags=re.IGNORECASE)),
        ]

        for tool_name, match in tool_matchers:
            if not match:
                continue
            args = self._match_to_args(tool_name, match)
            return self._tool_result_to_outcome(self.registry.execute(tool_name, args, context), tool_name)

        write_file_match = re.search(
            r"(?:write|create)\s+file[:\s]+([^\n]+)\n(.+)",
            prompt,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if write_file_match:
            result = self.registry.execute(
                "write_file",
                {
                    "path": write_file_match.group(1).strip().strip('"'),
                    "content": write_file_match.group(2).strip(),
                },
                context,
            )
            return self._tool_result_to_outcome(result, "write_file")

        edit_file_match = re.search(
            r"edit\s+file[:\s]+([^\n]+)\nsearch:\s*(.+?)\nreplace:\s*(.+)",
            prompt,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if edit_file_match:
            result = self.registry.execute(
                "edit_file",
                {
                    "path": edit_file_match.group(1).strip().strip('"'),
                    "search_text": edit_file_match.group(2).strip(),
                    "replace_text": edit_file_match.group(3).strip(),
                },
                context,
            )
            return self._tool_result_to_outcome(result, "edit_file")

        if "read current note" in normalized or ("current note" in normalized and current_note_path):
            result = self.registry.execute("read_note", {"path": current_note_path or ""}, context)
            return self._tool_result_to_outcome(result, "read_note")

        if retrieval_hits:
            result = self.registry.execute("search_notes", {"query": prompt}, context)
            return self._tool_result_to_outcome(result, "search_notes")

        if current_note_path:
            result = self.registry.execute("read_note", {"path": current_note_path}, context)
            return self._tool_result_to_outcome(result, "read_note")

        return RuntimeOutcome(
            answer="当前工作区里没有找到匹配的笔记或文件。请换一个更具体的问题，或先创建一篇笔记。",
        )

    def _match_to_args(self, tool_name: str, match: re.Match[str]) -> dict[str, object]:
        if tool_name == "list_directory":
            path = match.group(1).strip().strip('"') or "."
            return {"path": path}
        if tool_name == "create_note":
            title = match.group(1).strip()
            return {"title": title}
        if tool_name == "import_url":
            return {"url": match.group(1).strip()}
        if tool_name in {"read_file", "import_file", "delete_path"}:
            key = "source_path" if tool_name == "import_file" else "path"
            return {key: match.group(1).strip().strip('"')}
        return {}

    def _tool_result_to_outcome(self, result, tool_name: str) -> RuntimeOutcome:
        return RuntimeOutcome(
            answer=result.summary,
            citations=result.citations,
            tool_calls=[tool_name],
            tool_results=[
                {
                    "action": tool_name,
                    "ok": result.ok,
                    "summary": result.summary,
                    "citations": result.citations,
                    "payload": result.payload,
                    "error": result.error,
                }
            ],
            events=[coerce_agent_event(event) for event in result.events],
            task_state=result.task_state,
            run_status=result.run_status,
        )
