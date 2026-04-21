"""Prompt 模板注册表。

`PromptTemplateRegistry` 组织 planner / answer 两阶段的 system prompt 和
user prompt 模板，支持外部（chains）注入自定义模板。`DEFAULT_PROMPT_REGISTRY`
是进程范围内的默认单例，被 `LLMService` 引用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..domain import MemoryContext


def _json_block(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _xml_block(tag: str, value: object) -> str:
    return f"<{tag}>\n{_json_block(value)}\n</{tag}>"


def _current_note_payload(memory_context: MemoryContext) -> dict[str, object] | None:
    if memory_context.current_note is None:
        return None
    return {
        "path": memory_context.current_note.relative_path,
        "title": memory_context.current_note.title,
        "summary": memory_context.current_note.summary,
        "tags": memory_context.current_note.tags,
    }


def _retrieval_payload(memory_context: MemoryContext, *, limit: int = 5) -> list[dict[str, object]]:
    packed = memory_context.thread_memory.get("retrieval_evidence")
    if isinstance(packed, list) and packed:
        return [dict(item) for item in packed[:limit] if isinstance(item, dict)]
    return [
        {
            "path": hit.path,
            "title": hit.title,
            "snippet": hit.snippet,
            "kind": hit.kind,
            "score": hit.score,
            "chunk_id": hit.chunk_id,
            "section": hit.section,
            "token_count": hit.token_count,
            "start_offset": hit.start_offset,
        }
        for hit in memory_context.related_hits[:limit]
    ]


def _thread_memory_payload(memory_context: MemoryContext, key: str) -> object:
    return memory_context.thread_memory.get(key)


@dataclass(frozen=True)
class PlannerPromptInput:
    prompt: str
    memory_context: MemoryContext
    current_note_path: str | None
    tool_results: list[dict[str, object]]
    thread_summary: str = ""
    token_budget: dict[str, object] | None = None


@dataclass(frozen=True)
class AnswerPromptInput:
    prompt: str
    memory_context: MemoryContext
    current_note_path: str | None
    tool_results: list[dict[str, object]]
    citations: list[str]
    planner_hint: str
    thread_summary: str = ""
    token_budget: dict[str, object] | None = None


@dataclass(frozen=True)
class CompressionPromptInput:
    messages: list[dict[str, object]]
    active_note_path: str | None
    current_summary: str
    token_budget: dict[str, object]


@dataclass(frozen=True)
class PromptTemplateRegistry:
    def planner_system_prompt(self) -> str:
        return (
            "You are the planning layer for the more workspace agent.\n"
            "Choose exactly one next action and return JSON only with keys action, args, answer, citations.\n"
            "\n"
            "ACTION MUST be one of:\n"
            "  - \"respond\" — finalize and return the user-facing answer (use this when no further tools are needed; put the reply in the \"answer\" field).\n"
            "  - a tool name listed in <tool_catalog> — call that tool (put inputs in \"args\").\n"
            "\n"
            "Never invent a tool name. If you are ready to answer, the action MUST be \"respond\" — not \"answer\", not \"reply\", not \"final_answer\".\n"
            "If the user's request requires reading or changing workspace state, call a tool first; otherwise respond directly.\n"
            "args must be a JSON object. citations must be a JSON array of note paths or URLs.\n"
            "Prefer grounded actions over speculation and keep the plan minimal."
        )

    def planner_user_prompt(
        self,
        prompt_input: PlannerPromptInput,
    ) -> str:
        return "\n\n".join(
            [
                _xml_block(
                    "workspace_state",
                    {
                        "current_note_path": prompt_input.current_note_path,
                        "default_note_dir": prompt_input.memory_context.preferences.default_note_dir,
                        "preferences": {
                            "language": prompt_input.memory_context.preferences.language,
                            "answer_style": prompt_input.memory_context.preferences.answer_style,
                        },
                    },
                ),
                _xml_block("project_context", _thread_memory_payload(prompt_input.memory_context, "project_context") or []),
                _xml_block("active_skills", _thread_memory_payload(prompt_input.memory_context, "active_skills") or []),
                _xml_block("tool_catalog", _thread_memory_payload(prompt_input.memory_context, "tool_catalog") or []),
                _xml_block("current_note", _current_note_payload(prompt_input.memory_context)),
                _xml_block("thread_summary", prompt_input.thread_summary.strip()),
                _xml_block("recent_turns", _thread_memory_payload(prompt_input.memory_context, "recent_turns") or []),
                _xml_block("retrieval_hits", _retrieval_payload(prompt_input.memory_context)),
                _xml_block(
                    "workspace_memory_refs",
                    _thread_memory_payload(prompt_input.memory_context, "workspace_memory_refs")
                    or [asdict_like(record) for record in prompt_input.memory_context.workspace_memory],
                ),
                _xml_block(
                    "current_note_excerpt",
                    _thread_memory_payload(prompt_input.memory_context, "current_note_excerpt") or "",
                ),
                _xml_block(
                    "context_allocation",
                    _thread_memory_payload(prompt_input.memory_context, "context_allocation") or {},
                ),
                _xml_block("tool_results", prompt_input.tool_results),
                _xml_block("token_budget", prompt_input.token_budget or {}),
                _xml_block("user_request", {"prompt": prompt_input.prompt}),
                _xml_block(
                    "output_schema",
                    {
                        "action": "string",
                        "args": "object",
                        "answer": "string",
                        "citations": ["string"],
                    },
                ),
            ]
        )

    def answer_system_prompt(self, *, language: str) -> str:
        preferred_language = language or "zh-CN"
        return (
            "You are the final response layer for the more workspace assistant.\n"
            f"Reply in {preferred_language} unless the user explicitly asks for another language.\n"
            "Ground the answer in retrieval hits and tool results.\n"
            "Only make claims that are supported by the provided evidence.\n"
            "If evidence is weak or missing, say so explicitly instead of guessing.\n"
            "Do not invent citations, file paths, note titles, or facts.\n"
            "If the request asks for a draft, output draft-ready content directly.\n"
            "Be concrete and concise."
        )

    def answer_user_prompt(
        self,
        prompt_input: AnswerPromptInput,
    ) -> str:
        return "\n\n".join(
            [
                _xml_block(
                    "workspace_state",
                    {
                        "current_note_path": prompt_input.current_note_path,
                        "default_note_dir": prompt_input.memory_context.preferences.default_note_dir,
                        "preferences": {
                            "language": prompt_input.memory_context.preferences.language,
                            "answer_style": prompt_input.memory_context.preferences.answer_style,
                        },
                    },
                ),
                _xml_block("project_context", _thread_memory_payload(prompt_input.memory_context, "project_context") or []),
                _xml_block("active_skills", _thread_memory_payload(prompt_input.memory_context, "active_skills") or []),
                _xml_block("tool_catalog", _thread_memory_payload(prompt_input.memory_context, "tool_catalog") or []),
                _xml_block("current_note", _current_note_payload(prompt_input.memory_context)),
                _xml_block("thread_summary", prompt_input.thread_summary.strip()),
                _xml_block("recent_turns", _thread_memory_payload(prompt_input.memory_context, "recent_turns") or []),
                _xml_block("retrieval_evidence", _retrieval_payload(prompt_input.memory_context)),
                _xml_block(
                    "workspace_memory_refs",
                    _thread_memory_payload(prompt_input.memory_context, "workspace_memory_refs")
                    or [asdict_like(record) for record in prompt_input.memory_context.workspace_memory],
                ),
                _xml_block(
                    "current_note_excerpt",
                    _thread_memory_payload(prompt_input.memory_context, "current_note_excerpt") or "",
                ),
                _xml_block(
                    "context_allocation",
                    _thread_memory_payload(prompt_input.memory_context, "context_allocation") or {},
                ),
                _xml_block("tool_results", prompt_input.tool_results),
                _xml_block("citations", prompt_input.citations),
                _xml_block("planner_hint", prompt_input.planner_hint.strip()),
                _xml_block("token_budget", prompt_input.token_budget or {}),
                _xml_block(
                    "output_rules",
                    {
                        "grounded": True,
                        "cite_evidence": True,
                        "do_not_invent_facts": True,
                        "say_insufficient_if_missing_evidence": True,
                        "concise": True,
                        "draft_ready_if_requested": True,
                    },
                ),
                _xml_block("user_request", {"prompt": prompt_input.prompt}),
            ]
        )

    def compression_system_prompt(self) -> str:
        return (
            "You summarize an active thread for later continuation.\n"
            "Keep only durable goals, decisions, file paths, failures, pending work, and preferences.\n"
            "Do not restate full transcripts."
        )

    def compression_user_prompt(
        self,
        prompt_input: CompressionPromptInput,
    ) -> str:
        return "\n\n".join(
            [
                _xml_block("active_note_path", prompt_input.active_note_path or ""),
                _xml_block("current_summary", prompt_input.current_summary),
                _xml_block("token_budget", prompt_input.token_budget),
                _xml_block("recent_messages", prompt_input.messages),
            ]
        )


DEFAULT_PROMPT_REGISTRY = PromptTemplateRegistry()


def asdict_like(value: object) -> dict[str, object]:
    return {
        key: item
        for key, item in getattr(value, "__dict__", {}).items()
        if not key.startswith("_")
    }


__all__ = [
    "AnswerPromptInput",
    "CompressionPromptInput",
    "DEFAULT_PROMPT_REGISTRY",
    "PlannerPromptInput",
    "PromptTemplateRegistry",
]
