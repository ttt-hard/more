"""Planner 规划器与适配器。

`PlannerPort` 是 runtime 依赖的抽象；`ProviderPlanner` / `LLMPlanner` 走
真正的 `ModelProvider` 调用，用 JSON 文本协议让模型输出
`{action, args, answer, citations}` 再 parse；`FunctionCallingPlanner` 走
OpenAI 原生 function calling 协议，把每个工具的 JSON Schema 直接喂给模型，
取回结构化 `tool_calls` 就是下一个动作，没 tool_call 就是 respond。
`LegacyPlannerAdapter` 兼容老 `LLMService.plan` 签名。
`_normalize_respond_action` 把模型常见的 "answer/final/done/reply" 等
action 归一到 "respond"，避免 runtime 陷入 "Unknown tool" 死循环。

**Streaming planner protocol**：`FunctionCallingPlanner.stream_plan()` 返回
`Iterator[PlanStreamEvent]`，其中：
  - `PlanContentDelta(text)` 是 LLM 边输出边给的可见 content token。
    Runtime 可以立刻转发为 `TokenEvent` 给前端，实现打字机效果。
  - `PlanReasoningDelta(text)` 是思考链 token（DeepSeek-R1 / OpenAI o1
    类模型）。默认不给前端看，可以记 trace。
  - `PlanDone(plan)` 流结束时的最终 `AgentPlan`，runtime 据此决定执行
    tool 或终止 react loop。
这个 protocol 让 runtime 既能逐 token 立即 emit，又能在流结束时拿到
完整的结构化决策。JSON-协议 planner 不实现 `stream_plan`；runtime 用
`hasattr` 检测是否支持，不支持就 fall back 到 `plan()`。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol, Union

from ..prompts import PlannerPromptInput, PromptTemplateRegistry
from ..domain import LLMSettings, MemoryContext
from ..llm import AgentPlan, LLMError, LLMService
from ..observability import RunTrace
from ..providers import CompletionRequest, ModelProvider, ProviderError, ToolCall
from ..tools.registry import ToolRegistry


@dataclass(frozen=True)
class PlanContentDelta:
    """A visible content token chunk streamed from the LLM."""

    text: str


@dataclass(frozen=True)
class PlanReasoningDelta:
    """A reasoning/chain-of-thought token chunk (model-specific; not shown to users by default)."""

    text: str


@dataclass(frozen=True)
class PlanDone:
    """End-of-stream sentinel carrying the fully assembled plan."""

    plan: AgentPlan


PlanStreamEvent = Union[PlanContentDelta, PlanReasoningDelta, PlanDone]


RESPOND_ALIASES: frozenset[str] = frozenset(
    {
        "respond",
        "answer",
        "reply",
        "final_answer",
        "finalanswer",
        "final",
        "finalize",
        "finish",
        "done",
        "complete",
        "return",
        "respond_final",
    }
)


def _normalize_respond_action(action: str) -> str:
    """Map common LLM hallucinations of a 'finalize answer' action back to 'respond'.

    Some models emit ``action: "answer"`` (or reply/final_answer/etc.) instead of the
    documented ``"respond"`` sentinel even when the prompt says otherwise. We treat any
    such known alias as ``respond`` so the runtime produces a final answer rather than
    looping on ``Unknown tool``.
    """
    normalized = action.strip().lower()
    if normalized in RESPOND_ALIASES:
        return "respond"
    return action


class PlannerPort(Protocol):
    def is_configured(self) -> bool: ...

    def plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> AgentPlan: ...


@dataclass(frozen=True)
class PlannerConfig:
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout: float = 30.0


class ProviderPlanner:
    def __init__(
        self,
        *,
        provider: ModelProvider,
        config: PlannerConfig,
        prompt_registry: PromptTemplateRegistry | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.prompt_registry = prompt_registry or PromptTemplateRegistry()
        self.run_trace: RunTrace | None = None

    def attach_trace(self, trace: RunTrace | None) -> None:
        self.run_trace = trace

    @classmethod
    def from_llm_service(cls, llm_service: LLMService) -> "ProviderPlanner":
        return cls(
            provider=llm_service.provider,
            config=PlannerConfig(
                model=llm_service.model,
                base_url=llm_service.base_url,
                api_key=llm_service.api_key,
                timeout=llm_service.timeout,
            ),
            prompt_registry=llm_service.prompt_registry,
        )

    @classmethod
    def from_settings(
        cls,
        *,
        provider: ModelProvider,
        settings: LLMSettings,
        prompt_registry: PromptTemplateRegistry | None = None,
    ) -> "ProviderPlanner":
        return cls(
            provider=provider,
            config=PlannerConfig(
                model=settings.model,
                base_url=settings.base_url,
                api_key=settings.api_key,
                timeout=settings.timeout,
            ),
            prompt_registry=prompt_registry,
        )

    def is_configured(self) -> bool:
        return bool(self.config.model)

    def plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> AgentPlan:
        if not self.is_configured():
            raise LLMError("LLM is not configured")

        trace = self.run_trace
        started = perf_counter()
        request_summary = {
            "current_note_path": current_note_path or "",
            "tool_results_count": len(tool_results),
            "thread_summary_present": bool(thread_summary.strip()),
            "token_budget_state": (token_budget or {}).get("state", "") if isinstance(token_budget, dict) else "",
        }
        prompt_input = PlannerPromptInput(
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        request = CompletionRequest(
            model=self.config.model,
            system_prompt=self.prompt_registry.planner_system_prompt(),
            user_prompt=self.prompt_registry.planner_user_prompt(prompt_input),
            temperature=0.1,
            timeout=self.config.timeout,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            metadata={"current_note_path": current_note_path or ""},
        )
        try:
            response = self.provider.complete(request)
        except ProviderError as exc:
            if trace is not None:
                trace.record_llm_call(
                    stage="planner",
                    model=self.config.model,
                    latency_ms=(perf_counter() - started) * 1000.0,
                    request_summary=request_summary,
                    error=str(exc),
                )
            raise LLMError(str(exc)) from exc
        plan = self._parse_plan(response.content)
        if trace is not None:
            trace.record_llm_call(
                stage="planner",
                model=self.config.model,
                latency_ms=(perf_counter() - started) * 1000.0,
                request_summary=request_summary,
                response_summary={
                    "action": plan.action,
                    "answer_length": len(plan.answer),
                    "citations_count": len(plan.citations),
                },
            )
        return plan

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
        return AgentPlan(
            action=_normalize_respond_action(action),
            args={str(key): value for key, value in args.items()},
            answer=answer,
            citations=[str(item) for item in citations],
        )


class LegacyPlannerAdapter:
    def __init__(self, llm_like: object) -> None:
        self.llm_like = llm_like
        self.run_trace: RunTrace | None = None

    def attach_trace(self, trace: RunTrace | None) -> None:
        self.run_trace = trace

    def is_configured(self) -> bool:
        is_configured = getattr(self.llm_like, "is_configured", None)
        if callable(is_configured):
            return bool(is_configured())
        return False

    def plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> AgentPlan:
        planner = getattr(self.llm_like, "plan", None)
        if not callable(planner):
            raise LLMError("Planner adapter target does not implement plan()")
        trace = self.run_trace
        started = perf_counter()
        request_summary = {
            "current_note_path": current_note_path or "",
            "tool_results_count": len(tool_results),
            "thread_summary_present": bool(thread_summary.strip()),
            "token_budget_state": (token_budget or {}).get("state", "") if isinstance(token_budget, dict) else "",
        }
        try:
            plan = planner(
                prompt=prompt,
                memory_context=memory_context,
                current_note_path=current_note_path,
                tool_results=tool_results,
                thread_summary=thread_summary,
                token_budget=token_budget,
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            plan = planner(
                prompt=prompt,
                memory_context=memory_context,
                current_note_path=current_note_path,
                tool_results=tool_results,
            )
        except Exception as exc:  # noqa: BLE001
            if trace is not None:
                trace.record_llm_call(
                    stage="planner",
                    model="legacy",
                    latency_ms=(perf_counter() - started) * 1000.0,
                    request_summary=request_summary,
                    error=str(exc),
                )
            raise

        if trace is not None:
            trace.record_llm_call(
                stage="planner",
                model="legacy",
                latency_ms=(perf_counter() - started) * 1000.0,
                request_summary=request_summary,
                response_summary={
                    "action": plan.action,
                    "answer_length": len(plan.answer),
                    "citations_count": len(plan.citations),
                },
            )
        return plan


class LLMPlanner(ProviderPlanner):
    def __init__(self, llm_service: LLMService) -> None:
        super().__init__(
            provider=llm_service.provider,
            config=PlannerConfig(
                model=llm_service.model,
                base_url=llm_service.base_url,
                api_key=llm_service.api_key,
                timeout=llm_service.timeout,
            ),
            prompt_registry=llm_service.prompt_registry,
        )


class FunctionCallingPlanner:
    """Planner 使用 OpenAI 原生 function calling 协议。

    与 `ProviderPlanner` 的区别：
    - 每个 tool 的 JSON Schema 通过 `tools=[...]` 直接交给模型，由 API
      服务端强制 arguments 合规；不再依赖 JSON 文本解析。
    - 模型用 `tool_calls` 声明下一步动作；无 tool_calls 视为 respond，
      content 直接作为 answer。
    - System prompt 精简到"要调工具就调，否则回答"，无需教 JSON schema。

    适用于 DeepSeek / Qwen / GPT 等兼容 OpenAI function calling 的 provider。
    不兼容的 provider 仍应使用 `ProviderPlanner`。
    """

    def __init__(
        self,
        *,
        provider: ModelProvider,
        config: PlannerConfig,
        tool_registry: ToolRegistry,
        prompt_registry: PromptTemplateRegistry | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.tool_registry = tool_registry
        self.prompt_registry = prompt_registry or PromptTemplateRegistry()
        self.run_trace: RunTrace | None = None

    def attach_trace(self, trace: RunTrace | None) -> None:
        self.run_trace = trace

    @classmethod
    def from_llm_service(
        cls,
        llm_service: LLMService,
        *,
        tool_registry: ToolRegistry,
    ) -> "FunctionCallingPlanner":
        return cls(
            provider=llm_service.provider,
            config=PlannerConfig(
                model=llm_service.model,
                base_url=llm_service.base_url,
                api_key=llm_service.api_key,
                timeout=llm_service.timeout,
            ),
            tool_registry=tool_registry,
            prompt_registry=llm_service.prompt_registry,
        )

    def is_configured(self) -> bool:
        return bool(self.config.model)

    def _system_prompt(self) -> str:
        return (
            "You are the planning layer for the more workspace agent.\n"
            "On each step, decide EITHER:\n"
            "  (a) call exactly one tool from the provided `tools` list to make progress, OR\n"
            "  (b) emit your final, user-facing answer as plain text (no tool call).\n"
            "\n"
            "Rules:\n"
            "- If the user's request requires inspecting or changing workspace state, "
            "call a tool first; otherwise answer directly.\n"
            "- Follow the procedure of any loaded skill (see <active_skills>). "
            "If a relevant skill is listed and you have not loaded it yet, call `load_skill` first.\n"
            "- Respect the project rules in <project_context>.\n"
            "- Prefer grounded actions over speculation; keep the plan minimal.\n"
            "- When you decide to answer, produce the answer as natural language content. "
            "Do NOT emit JSON schemas, tool-call wrappers, or markdown code fences wrapping an action — "
            "that's what the tool-call channel is for."
        )

    def plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> AgentPlan:
        if not self.is_configured():
            raise LLMError("LLM is not configured")

        trace = self.run_trace
        started = perf_counter()
        tools_schemas = self.tool_registry.as_function_schemas()
        prompt_input = PlannerPromptInput(
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        request = CompletionRequest(
            model=self.config.model,
            system_prompt=self._system_prompt(),
            user_prompt=self.prompt_registry.planner_user_prompt(prompt_input),
            temperature=0.1,
            timeout=self.config.timeout,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            tools=tools_schemas,
            tool_choice="auto",
            metadata={"current_note_path": current_note_path or ""},
        )
        request_summary = {
            "current_note_path": current_note_path or "",
            "tool_results_count": len(tool_results),
            "thread_summary_present": bool(thread_summary.strip()),
            "token_budget_state": (token_budget or {}).get("state", "") if isinstance(token_budget, dict) else "",
            "tools_count": len(tools_schemas),
            "mode": "function_calling",
        }
        try:
            response = self.provider.complete(request)
        except ProviderError as exc:
            if trace is not None:
                trace.record_llm_call(
                    stage="planner",
                    model=self.config.model,
                    latency_ms=(perf_counter() - started) * 1000.0,
                    request_summary=request_summary,
                    error=str(exc),
                )
            raise LLMError(str(exc)) from exc

        plan = self._plan_from_response(response.content, response.tool_calls)
        if trace is not None:
            trace.record_llm_call(
                stage="planner",
                model=self.config.model,
                latency_ms=(perf_counter() - started) * 1000.0,
                request_summary=request_summary,
                response_summary={
                    "action": plan.action,
                    "answer_length": len(plan.answer),
                    "citations_count": len(plan.citations),
                    "tool_calls_count": len(response.tool_calls),
                },
            )
        return plan

    def _plan_from_response(
        self,
        content: str,
        tool_calls: list[ToolCall],
    ) -> AgentPlan:
        if tool_calls:
            # Planner issues one step at a time; additional tool_calls (rare, some
            # models emit parallel) are ignored — next loop iteration re-plans.
            call = tool_calls[0]
            action = _normalize_respond_action(call.name)
            return AgentPlan(
                action=action,
                args={str(key): value for key, value in call.arguments.items()},
                answer="",
                citations=[],
            )
        # No tool_calls → final answer as plain text content.
        answer = (content or "").strip()
        if not answer:
            # Defensive: OpenAI occasionally returns empty content with no tool_calls
            # when the model decides nothing. Treat as an empty respond so runtime
            # terminates rather than looping on an unknown action.
            answer = ""
        # Mark the answer as final so AnswerService does not waste another LLM
        # round-trip regenerating what the function-calling LLM already authored
        # with the full tool_results context.
        return AgentPlan(
            action="respond",
            args={},
            answer=answer,
            citations=[],
            is_final_answer=True,
        )

    def stream_plan(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str = "",
        token_budget: dict[str, object] | None = None,
    ) -> Iterator[PlanStreamEvent]:
        """Streaming variant of `plan`.

        Yields `PlanContentDelta` / `PlanReasoningDelta` events for every
        token the LLM emits, then a terminal `PlanDone(plan)`. If the LLM
        chose to call tools, the intermediate content stream is typically
        empty — consumers see zero deltas and a `PlanDone` carrying a
        tool-call plan. Otherwise every content delta cumulatively forms
        the respond answer, which also lives on `plan.answer` when the
        terminal event arrives so downstream code can recover it if it
        missed any deltas.

        Falls back to a one-shot `PlanDone` if the provider does not
        implement `stream_chunks` (static-response adapters in tests).
        """
        if not self.is_configured():
            raise LLMError("LLM is not configured")

        trace = self.run_trace
        started = perf_counter()
        tools_schemas = self.tool_registry.as_function_schemas()
        prompt_input = PlannerPromptInput(
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            thread_summary=thread_summary,
            token_budget=token_budget,
        )
        request = CompletionRequest(
            model=self.config.model,
            system_prompt=self._system_prompt(),
            user_prompt=self.prompt_registry.planner_user_prompt(prompt_input),
            temperature=0.1,
            timeout=self.config.timeout,
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            tools=tools_schemas,
            tool_choice="auto",
            metadata={"current_note_path": current_note_path or ""},
        )
        request_summary = {
            "current_note_path": current_note_path or "",
            "tool_results_count": len(tool_results),
            "thread_summary_present": bool(thread_summary.strip()),
            "token_budget_state": (token_budget or {}).get("state", "") if isinstance(token_budget, dict) else "",
            "tools_count": len(tools_schemas),
            "mode": "function_calling_stream",
        }

        stream_chunks = getattr(self.provider, "stream_chunks", None)
        if not callable(stream_chunks):
            # Provider doesn't support streaming → fall back to one-shot plan().
            plan = self.plan(
                prompt=prompt,
                memory_context=memory_context,
                current_note_path=current_note_path,
                tool_results=tool_results,
                thread_summary=thread_summary,
                token_budget=token_budget,
            )
            yield PlanDone(plan=plan)
            return

        accumulated_content: list[str] = []
        accumulated_reasoning: list[str] = []
        terminal_tool_calls: list[ToolCall] = []
        try:
            for chunk in stream_chunks(request):
                if getattr(chunk, "content", ""):
                    accumulated_content.append(chunk.content)
                    yield PlanContentDelta(text=chunk.content)
                if getattr(chunk, "reasoning", ""):
                    accumulated_reasoning.append(chunk.reasoning)
                    yield PlanReasoningDelta(text=chunk.reasoning)
                if getattr(chunk, "finished", False):
                    terminal_tool_calls = list(getattr(chunk, "tool_calls", []) or [])
                    break
        except ProviderError as exc:
            if trace is not None:
                trace.record_llm_call(
                    stage="planner",
                    model=self.config.model,
                    latency_ms=(perf_counter() - started) * 1000.0,
                    request_summary=request_summary,
                    error=str(exc),
                )
            raise LLMError(str(exc)) from exc

        full_content = "".join(accumulated_content)
        plan = self._plan_from_response(full_content, terminal_tool_calls)
        if trace is not None:
            trace.record_llm_call(
                stage="planner",
                model=self.config.model,
                latency_ms=(perf_counter() - started) * 1000.0,
                request_summary=request_summary,
                response_summary={
                    "action": plan.action,
                    "answer_length": len(plan.answer),
                    "citations_count": len(plan.citations),
                    "tool_calls_count": len(terminal_tool_calls),
                    "reasoning_chars": sum(len(part) for part in accumulated_reasoning),
                    "streamed": True,
                },
            )
        yield PlanDone(plan=plan)
