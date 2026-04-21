"""LLM 门面与 AgentPlan 解析。

`LLMService` 包一个 `ModelProvider`（默认 `LiteLLMProvider`），面向 Agent
层暴露 `plan` / `stream_answer` / `stream_answer_chunks` / `complete_answer`
四种调用方式；同时在内部做 JSON 解析（planner 的响应）、action 归一化
（`_normalize_respond_action`）和错误封装（`LLMError`）。
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
from dataclasses import dataclass, field

import httpx

from .prompts import AnswerPromptInput, DEFAULT_PROMPT_REGISTRY, PlannerPromptInput, PromptTemplateRegistry
from .domain import LLMSettings, MemoryContext
from .providers import CompletionRequest, LiteLLMProvider, ModelProvider, ProviderError, StreamChunk


class LLMError(Exception):
    """Base error for LLM planning operations."""


@dataclass(frozen=True)
class AgentPlan:
    action: str
    args: dict[str, object] = field(default_factory=dict)
    answer: str = ""
    citations: list[str] = field(default_factory=list)
    # True 仅当 planner 返回的 `answer` 已经是 LLM 面向用户的最终稿
    # （function calling 协议下 LLM 决定不调工具 + 直接发 content 的情形）。
    # 下游 AnswerService 见此标记会跳过二次 LLM 调用，把 answer 原样流出。
    # JSON-协议 planner 保持 False —— 它们的 answer 字段只是 hint。
    is_final_answer: bool = False


class LLMService:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
        settings: LLMSettings | None = None,
        provider: ModelProvider | None = None,
        prompt_registry: PromptTemplateRegistry | None = None,
    ) -> None:
        if settings is not None:
            self.base_url = settings.base_url
            self.api_key = settings.api_key
            self.model = settings.model
            self.timeout = settings.timeout
            self.use_function_calling = settings.use_function_calling
        else:
            self.base_url = (base_url or os.getenv("MORE_LLM_BASE_URL") or "").rstrip("/")
            self.api_key = api_key if api_key is not None else os.getenv("MORE_LLM_API_KEY", "")
            self.model = model or os.getenv("MORE_LLM_MODEL") or ""
            self.timeout = timeout
            self.use_function_calling = True
        self.provider = provider or LiteLLMProvider(client=client)
        self.prompt_registry = prompt_registry or DEFAULT_PROMPT_REGISTRY

    def is_configured(self) -> bool:
        return bool(self.model)

    def test_connection(self) -> dict[str, object]:
        if not self.is_configured():
            return {"ok": False, "error": "LLM is not configured: model is required"}
        request = CompletionRequest(
            model=self.model,
            system_prompt="You are a connectivity probe.",
            user_prompt="hi",
            temperature=0,
            max_tokens=4,
            timeout=min(self.timeout, 15.0),
            base_url=self.base_url,
            api_key=self.api_key,
        )
        return self.provider.test_connection(request)

    def build_answer_request(
        self,
        prompt_input: AnswerPromptInput | None = None,
        *,
        prompt: str | None = None,
        memory_context: MemoryContext | None = None,
        current_note_path: str | None = None,
        tool_results: list[dict[str, object]] | None = None,
        citations: list[str] | None = None,
        planner_hint: str = "",
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> CompletionRequest:
        if not self.is_configured():
            raise LLMError("LLM is not configured")
        active_prompt_input = prompt_input or AnswerPromptInput(
            prompt=prompt or "",
            memory_context=memory_context or MemoryContext(),
            current_note_path=current_note_path,
            tool_results=tool_results or [],
            citations=citations or [],
            planner_hint=planner_hint,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        return CompletionRequest(
            model=self.model,
            system_prompt=self.prompt_registry.answer_system_prompt(
                language=active_prompt_input.memory_context.preferences.language
            ),
            user_prompt=self.prompt_registry.answer_user_prompt(active_prompt_input),
            temperature=0.2,
            timeout=self.timeout,
            base_url=self.base_url,
            api_key=self.api_key,
            metadata={"current_note_path": active_prompt_input.current_note_path or ""},
        )

    def complete_answer(
        self,
        *,
        prompt_input: AnswerPromptInput | None = None,
        prompt: str | None = None,
        memory_context: MemoryContext | None = None,
        current_note_path: str | None = None,
        tool_results: list[dict[str, object]] | None = None,
        citations: list[str] | None = None,
        planner_hint: str = "",
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> str:
        request = self.build_answer_request(
            prompt_input,
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            citations=citations,
            planner_hint=planner_hint,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        try:
            response = self.provider.complete(request)
        except ProviderError as exc:
            raise LLMError(str(exc)) from exc
        return response.content.strip()

    def stream_answer(
        self,
        *,
        prompt_input: AnswerPromptInput | None = None,
        prompt: str | None = None,
        memory_context: MemoryContext | None = None,
        current_note_path: str | None = None,
        tool_results: list[dict[str, object]] | None = None,
        citations: list[str] | None = None,
        planner_hint: str = "",
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> Iterator[str]:
        request = self.build_answer_request(
            prompt_input,
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            citations=citations,
            planner_hint=planner_hint,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        stream_complete = getattr(self.provider, "stream_complete", None)
        if not callable(stream_complete):
            raise LLMError("Provider does not support streaming completions")
        try:
            yield from stream_complete(request)
        except ProviderError as exc:
            raise LLMError(str(exc)) from exc

    def stream_answer_chunks(
        self,
        *,
        prompt_input: AnswerPromptInput | None = None,
        prompt: str | None = None,
        memory_context: MemoryContext | None = None,
        current_note_path: str | None = None,
        tool_results: list[dict[str, object]] | None = None,
        citations: list[str] | None = None,
        planner_hint: str = "",
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> Iterator[StreamChunk]:
        request = self.build_answer_request(
            prompt_input,
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            citations=citations,
            planner_hint=planner_hint,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        stream_chunks = getattr(self.provider, "stream_chunks", None)
        if callable(stream_chunks):
            try:
                yield from stream_chunks(request)
            except ProviderError as exc:
                raise LLMError(str(exc)) from exc
            return
        stream_complete = getattr(self.provider, "stream_complete", None)
        if not callable(stream_complete):
            raise LLMError("Provider does not support streaming completions")
        try:
            for text in stream_complete(request):
                if text:
                    yield StreamChunk(content=text)
        except ProviderError as exc:
            raise LLMError(str(exc)) from exc

    def plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]] | None = None,
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> AgentPlan:
        if not self.is_configured():
            raise LLMError("LLM is not configured")

        prompt_input = PlannerPromptInput(
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results or [],
            thread_summary=thread_summary,
            token_budget=token_budget,
        )

        request = CompletionRequest(
            model=self.model,
            system_prompt=self.prompt_registry.planner_system_prompt(),
            user_prompt=self.prompt_registry.planner_user_prompt(prompt_input),
            temperature=0.1,
            timeout=self.timeout,
            base_url=self.base_url,
            api_key=self.api_key,
            metadata={"current_note_path": current_note_path or ""},
        )
        try:
            response = self.provider.complete(request)
        except ProviderError as exc:
            raise LLMError(str(exc)) from exc
        return self._parse_plan(response.content)

    def _build_system_prompt(self) -> str:
        return (
            "You are the planning layer for the more agent. "
            "Choose exactly one action for the workspace. "
            "Return JSON only with keys action, args, answer, citations. "
            "Valid actions: respond, search_notes, search_workspace, read_note, create_note, "
            "update_note_metadata, summarize_note, link_notes, import_file, import_url, "
            "read_file, list_directory, write_file, edit_file, move_path, delete_path, "
            "glob_search, grep_search, save_preference, read_preference. "
            "Prefer using an existing tool action over a plain respond action when a tool is needed. "
            "Args must be a JSON object. Citations must be a JSON array of paths or URLs."
        )

    def _build_answer_system_prompt(self, language: str) -> str:
        preferred_language = language or "zh-CN"
        return (
            "You are the final response layer for the more workspace assistant. "
            "Return the user-facing answer only, not JSON. "
            f"Prefer replying in {preferred_language}. "
            "Use tool results as the source of truth. "
            "If the request asks for a draft, output the draft content directly. "
            "If files or notes were created or updated, clearly summarize what changed. "
            "Be concrete and concise."
        )

    def _build_user_prompt(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
    ) -> str:
        hits = [
            {
                "path": hit.path,
                "title": hit.title,
                "snippet": hit.snippet,
                "kind": hit.kind,
            }
            for hit in memory_context.related_hits[:5]
        ]
        context = {
            "prompt": prompt,
            "current_note_path": current_note_path,
            "preferences": {
                "language": memory_context.preferences.language,
                "answer_style": memory_context.preferences.answer_style,
                "default_note_dir": memory_context.preferences.default_note_dir,
            },
            "current_note": (
                {
                    "path": memory_context.current_note.relative_path,
                    "title": memory_context.current_note.title,
                    "summary": memory_context.current_note.summary,
                    "tags": memory_context.current_note.tags,
                }
                if memory_context.current_note
                else None
            ),
            "retrieval_hits": hits,
            "tool_results": tool_results,
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    def _build_answer_user_prompt(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        citations: list[str],
        planner_hint: str,
    ) -> str:
        hits = [
            {
                "path": hit.path,
                "title": hit.title,
                "snippet": hit.snippet,
                "kind": hit.kind,
            }
            for hit in memory_context.related_hits[:5]
        ]
        context = {
            "user_request": prompt,
            "current_note_path": current_note_path,
            "planner_hint": planner_hint,
            "preferences": {
                "language": memory_context.preferences.language,
                "answer_style": memory_context.preferences.answer_style,
                "default_note_dir": memory_context.preferences.default_note_dir,
            },
            "current_note": (
                {
                    "path": memory_context.current_note.relative_path,
                    "title": memory_context.current_note.title,
                    "summary": memory_context.current_note.summary,
                    "tags": memory_context.current_note.tags,
                }
                if memory_context.current_note
                else None
            ),
            "retrieval_hits": hits,
            "tool_results": tool_results,
            "citations": citations,
        }
        return json.dumps(context, ensure_ascii=False, indent=2)

    def _parse_plan(self, content: str) -> AgentPlan:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise LLMError("LLM output was not valid JSON")
            try:
                payload = json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                raise LLMError("LLM output was not parseable as JSON") from exc

        if not isinstance(payload, dict):
            raise LLMError("LLM output must be a JSON object")

        action = str(payload.get("action") or "").strip()
        if not action:
            raise LLMError("LLM output must include an action")
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            raise LLMError("LLM args must be a JSON object")
        answer = str(payload.get("answer") or "").strip()
        citations = payload.get("citations") or []
        if not isinstance(citations, list):
            raise LLMError("LLM citations must be an array")
        from .agent.planner import _normalize_respond_action  # local import avoids cycle

        return AgentPlan(
            action=_normalize_respond_action(action),
            args={str(key): value for key, value in args.items()},
            answer=answer,
            citations=[str(item) for item in citations],
        )
