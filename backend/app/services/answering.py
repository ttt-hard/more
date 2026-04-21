"""回答生成服务。

`AnswerService.generate_stream` 根据 runtime outcome 选取以下几条路径
之一生成最终答案：

1. **final_answer_ready 快路径**：当 runtime 的 outcome 已经是 function
   calling planner 流出的 LLM 最终稿（`outcome.final_answer_ready=True`），
   跳过第二次 LLM 调用，直接把 `outcome.answer` 分块流到前端，加上
   `来源：` footer。这让 react loop 真正统一——LLM 决定终止的那一刻产出
   的 content 就是 user-facing answer，不再由独立 answer LLM 重写。

2. **streaming 路径**：兼容旧 JSON 协议 planner 或上游未声明 final 的场景，
   调用 `LLMService.stream_answer_chunks` / `stream_answer`。

3. **complete 路径**：provider 不支持流式时同步拿全文。

4. **fallback**：证据不足直接回"无法回答"；所有 LLM 路径都失败时回
   planner_hint 或通用提示。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from inspect import Signature, signature
from time import perf_counter
from typing import TYPE_CHECKING, Any

from ..prompts import AnswerPromptInput
from ..domain import MemoryContext
from ..llm import LLMError
from ..observability import RunTrace
from ..runtime_control import CancellationToken

if TYPE_CHECKING:
    from ..agent.events import AgentEventBase
    from ..agent.outcome import RuntimeOutcome


@dataclass(frozen=True)
class AnswerGeneration:
    final_answer: str
    citations: list[str]
    events: list[AgentEventBase | Any]


@dataclass(frozen=True)
class AnswerRequest:
    prompt: str
    memory_context: MemoryContext
    current_note_path: str | None
    outcome: RuntimeOutcome
    thread_summary: str = ""
    token_budget: dict[str, object] | None = None
    cancellation_token: CancellationToken | None = None
    run_trace: RunTrace | None = None


class AnswerService:
    def __init__(self, llm_service: object) -> None:
        self.llm_service = llm_service

    def generate(self, request: AnswerRequest) -> AnswerGeneration:
        """Backward-compatible synchronous API: drains generate_stream into an AnswerGeneration."""

        events: list[Any] = []
        final_result: AnswerGeneration | None = None
        for emitted in self.generate_stream(request):
            if isinstance(emitted, AnswerGeneration):
                final_result = emitted
            else:
                events.append(emitted)
        if final_result is None:
            return AnswerGeneration(final_answer="", citations=[], events=events)
        return AnswerGeneration(
            final_answer=final_result.final_answer,
            citations=final_result.citations,
            events=events,
        )

    def generate_stream(self, request: AnswerRequest) -> Iterator[Any]:
        """True-streaming generator: yields AgentEventBase items one at a time, then a final AnswerGeneration."""

        from ..agent.events import PhaseStatusEvent, ReasoningDeltaEvent, TokenEvent, coerce_agent_event

        final_answer = request.outcome.answer.strip()
        effective_citations = self._effective_citations(
            prompt=request.prompt,
            memory_context=request.memory_context,
            current_note_path=request.current_note_path,
            citations=request.outcome.citations,
        )
        streamed_chunks: list[str] = []
        should_generate_answer = request.outcome.task_state == "completed" and request.outcome.run_status == "completed"
        stage_started = perf_counter()
        trace = request.run_trace
        prompt_input: AnswerPromptInput | None = None
        reasoning_chars = 0

        # Fast path: function-calling planner already produced the user-facing
        # final answer with full tool_results context. Skip the second LLM
        # round-trip. Two sub-modes:
        #   1. `answer_streamed=True`: runtime already emitted the content
        #      tokens via SSE (streaming planner). Only append the citation
        #      footer as extra tokens — emitting the answer again would
        #      double-render on the frontend.
        #   2. `answer_streamed=False`: non-streaming planner produced a
        #      one-shot final answer. Chunk-emit the whole thing as tokens.
        if (
            should_generate_answer
            and request.outcome.final_answer_ready
            and final_answer
        ):
            if not request.outcome.answer_streamed:
                yield coerce_agent_event(
                    PhaseStatusEvent(
                        phase="answering",
                        label="正在生成回答",
                        detail="Planner 已输出最终答案，直接流出给用户。",
                    )
                )
            enriched_answer = final_answer
            if self._is_grounded_answer(enriched_answer) and effective_citations:
                enriched_answer = self._ensure_citation_footer(enriched_answer, effective_citations)
            tokens_to_emit = (
                enriched_answer[len(final_answer):]
                if request.outcome.answer_streamed
                else enriched_answer
            )
            for chunk in self._chunk_text(tokens_to_emit, chunk_size=48):
                if request.cancellation_token is not None:
                    request.cancellation_token.raise_if_cancelled()
                if trace is not None:
                    trace.mark_first_answer_token()
                yield coerce_agent_event(TokenEvent(text=chunk))
            if trace is not None:
                trace.set_metric(
                    "answer_source",
                    "planner_stream" if request.outcome.answer_streamed else "planner_final",
                )
                trace.set_metric("answer_grounded", self._is_grounded_answer(enriched_answer))
                trace.set_metric("answer_generated", bool(enriched_answer.strip()))
                trace.observe_metric("answer_generation_latency_ms", (perf_counter() - stage_started) * 1000.0)
                trace.observe_metric("answer_output_chars", len(enriched_answer))
                trace.observe_metric("answer_citation_count", len(effective_citations))
                trace.observe_metric("answer_with_citation", int(bool(effective_citations)))
            yield AnswerGeneration(final_answer=enriched_answer, citations=effective_citations, events=[])
            return

        if should_generate_answer:
            planner_hint = final_answer
            final_answer = ""
            prompt_input = AnswerPromptInput(
                prompt=request.prompt,
                memory_context=request.memory_context,
                current_note_path=request.current_note_path,
                tool_results=request.outcome.tool_results,
                citations=request.outcome.citations,
                planner_hint=planner_hint,
                thread_summary=request.thread_summary,
                token_budget=request.token_budget,
            )
            yield coerce_agent_event(
                PhaseStatusEvent(
                    phase="answering",
                    label="正在生成回答",
                    detail="正在结合工具结果、检索证据和线程上下文组织最终回答。",
                )
            )
            evidence_available = self._has_grounding(prompt_input)
            if not evidence_available:
                final_answer = "基于当前上下文证据不足，无法给出可靠回答。请先选择相关文档、执行检索或提供更具体的问题。"
                if trace is not None:
                    trace.set_metric("answer_source", "insufficient_evidence")
                    trace.set_metric("answer_grounded", False)
                    trace.set_metric("evidence_available", False)
            elif self._supports_streaming_chunks():
                try:
                    for chunk in self._stream_answer_chunks(prompt_input):
                        if request.cancellation_token is not None:
                            request.cancellation_token.raise_if_cancelled()
                        reasoning_text = getattr(chunk, "reasoning", "") or ""
                        content_text = getattr(chunk, "content", "") or ""
                        if reasoning_text:
                            reasoning_chars += len(reasoning_text)
                            yield coerce_agent_event(ReasoningDeltaEvent(text=reasoning_text))
                        if content_text:
                            streamed_chunks.append(content_text)
                            if trace is not None:
                                trace.mark_first_answer_token()
                            yield coerce_agent_event(TokenEvent(text=content_text))
                    if trace is not None and streamed_chunks:
                        trace.record_llm_call(
                            stage="answer",
                            model=str(getattr(self.llm_service, "model", "answer")),
                            latency_ms=(perf_counter() - stage_started) * 1000.0,
                            request_summary={"mode": "stream", "tool_results_count": len(request.outcome.tool_results)},
                            response_summary={"chunks": len(streamed_chunks), "reasoning_chars": reasoning_chars},
                        )
                except LLMError:
                    # Keep whatever tokens we already yielded; resetting here would make
                    # the downstream fallback re-emit the full answer and duplicate content
                    # on the frontend. Only zero-emission failures fall through to _complete_answer.
                    pass
            elif self._supports_streaming_answer():
                try:
                    for chunk in self._stream_answer(prompt_input):
                        if request.cancellation_token is not None:
                            request.cancellation_token.raise_if_cancelled()
                        if not chunk:
                            continue
                        streamed_chunks.append(chunk)
                        if trace is not None:
                            trace.mark_first_answer_token()
                        yield coerce_agent_event(TokenEvent(text=chunk))
                    if trace is not None and streamed_chunks:
                        trace.record_llm_call(
                            stage="answer",
                            model=str(getattr(self.llm_service, "model", "answer")),
                            latency_ms=(perf_counter() - stage_started) * 1000.0,
                            request_summary={"mode": "stream", "tool_results_count": len(request.outcome.tool_results)},
                            response_summary={"chunks": len(streamed_chunks)},
                        )
                except LLMError:
                    # Same rationale as the streaming_chunks branch: preserve already-yielded
                    # tokens so the fallback path cannot double-emit them.
                    pass

            if streamed_chunks:
                final_answer = "".join(streamed_chunks).strip()
                if trace is not None:
                    trace.set_metric("answer_source", "stream")
            elif self._supports_complete_answer():
                try:
                    if request.cancellation_token is not None:
                        request.cancellation_token.raise_if_cancelled()
                    completed_answer = self._complete_answer(prompt_input).strip()
                    if completed_answer:
                        final_answer = completed_answer
                        if trace is not None:
                            trace.set_metric("answer_source", "complete")
                            trace.record_llm_call(
                                stage="answer",
                                model=str(getattr(self.llm_service, "model", "answer")),
                                latency_ms=(perf_counter() - stage_started) * 1000.0,
                                request_summary={"mode": "complete", "tool_results_count": len(request.outcome.tool_results)},
                                response_summary={"chars": len(completed_answer)},
                            )
                except LLMError:
                    pass

            if not final_answer.strip():
                final_answer = planner_hint
                if trace is not None:
                    trace.set_metric("answer_source", "planner_hint")

        if not final_answer.strip():
            final_answer = "抱歉，当前没有生成可用回答。请换一个更具体的问题再试。"
            if trace is not None:
                trace.set_metric("answer_source", "fallback_message")

        streamed_answer = "".join(streamed_chunks).strip() if streamed_chunks else ""

        if should_generate_answer and self._is_grounded_answer(final_answer) and effective_citations:
            final_answer = self._ensure_citation_footer(final_answer, effective_citations)

        if streamed_chunks and final_answer.startswith(streamed_answer):
            suffix = final_answer[len(streamed_answer) :]
            if suffix:
                for chunk in self._chunk_text(suffix, chunk_size=48):
                    if request.cancellation_token is not None:
                        request.cancellation_token.raise_if_cancelled()
                    if trace is not None:
                        trace.mark_first_answer_token()
                    yield coerce_agent_event(TokenEvent(text=chunk))

        if not streamed_chunks:
            for chunk in self._chunk_text(final_answer, chunk_size=48):
                if request.cancellation_token is not None:
                    request.cancellation_token.raise_if_cancelled()
                if trace is not None:
                    trace.mark_first_answer_token()
                yield coerce_agent_event(TokenEvent(text=chunk))

        if trace is not None:
            trace.observe_metric("answer_generation_latency_ms", (perf_counter() - stage_started) * 1000.0)
            trace.observe_metric("answer_output_chars", len(final_answer))
            trace.observe_metric("answer_citation_count", len(effective_citations))
            trace.observe_metric("answer_with_citation", int(bool(effective_citations)))
            trace.observe_metric("reasoning_chars", reasoning_chars)
            trace.set_metric("evidence_available", self._has_grounding(prompt_input) if prompt_input is not None else False)
            trace.set_metric("answer_grounded", self._is_grounded_answer(final_answer))
            trace.set_metric("answer_generated", bool(final_answer.strip()))

        yield AnswerGeneration(final_answer=final_answer, citations=effective_citations, events=[])

    def _supports_streaming_answer(self) -> bool:
        return self._is_llm_configured() and callable(getattr(self.llm_service, "stream_answer", None))

    def _supports_streaming_chunks(self) -> bool:
        return self._is_llm_configured() and callable(getattr(self.llm_service, "stream_answer_chunks", None))

    def _supports_complete_answer(self) -> bool:
        return self._is_llm_configured() and callable(getattr(self.llm_service, "complete_answer", None))

    def _is_llm_configured(self) -> bool:
        is_configured = getattr(self.llm_service, "is_configured", None)
        return bool(callable(is_configured) and is_configured())

    def _chunk_text(self, text: str, chunk_size: int) -> list[str]:
        if not text:
            return []
        return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]

    def _stream_answer(self, prompt_input: AnswerPromptInput):
        stream_method = getattr(self.llm_service, "stream_answer")
        try:
            return stream_method(prompt_input=prompt_input)
        except TypeError as exc:
            if not self._looks_like_signature_mismatch(stream_method, exc):
                raise
            return stream_method(
                prompt=prompt_input.prompt,
                memory_context=prompt_input.memory_context,
                current_note_path=prompt_input.current_note_path,
                tool_results=prompt_input.tool_results,
                citations=prompt_input.citations,
                planner_hint=prompt_input.planner_hint,
            )

    def _stream_answer_chunks(self, prompt_input: AnswerPromptInput):
        stream_method = getattr(self.llm_service, "stream_answer_chunks")
        try:
            return stream_method(prompt_input=prompt_input)
        except TypeError as exc:
            if not self._looks_like_signature_mismatch(stream_method, exc):
                raise
            return stream_method(
                prompt=prompt_input.prompt,
                memory_context=prompt_input.memory_context,
                current_note_path=prompt_input.current_note_path,
                tool_results=prompt_input.tool_results,
                citations=prompt_input.citations,
                planner_hint=prompt_input.planner_hint,
            )

    def _complete_answer(self, prompt_input: AnswerPromptInput) -> str:
        complete_method = getattr(self.llm_service, "complete_answer")
        try:
            return complete_method(prompt_input=prompt_input)
        except TypeError as exc:
            if not self._looks_like_signature_mismatch(complete_method, exc):
                raise
            return complete_method(
                prompt=prompt_input.prompt,
                memory_context=prompt_input.memory_context,
                current_note_path=prompt_input.current_note_path,
                tool_results=prompt_input.tool_results,
                citations=prompt_input.citations,
                planner_hint=prompt_input.planner_hint,
            )

    def _has_grounding(self, prompt_input: AnswerPromptInput) -> bool:
        thread_memory = prompt_input.memory_context.thread_memory
        retrieval_evidence = thread_memory.get("retrieval_evidence") or []
        workspace_memory_refs = thread_memory.get("workspace_memory_refs") or []
        current_note_excerpt = str(thread_memory.get("current_note_excerpt") or "").strip()
        return bool(
            prompt_input.citations
            or retrieval_evidence
            or workspace_memory_refs
            or current_note_excerpt
            or prompt_input.tool_results
        )

    def _is_grounded_answer(self, final_answer: str) -> bool:
        normalized = final_answer.strip()
        if not normalized:
            return False
        return "证据不足" not in normalized and "无法给出可靠回答" not in normalized

    def _looks_like_signature_mismatch(self, func: object, exc: TypeError) -> bool:
        text = str(exc)
        if "prompt_input" in text and ("unexpected keyword argument" in text or "required positional argument" in text):
            return True
        try:
            sig: Signature = signature(func)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return "prompt_input" not in sig.parameters

    def _effective_citations(
        self,
        *,
        prompt: str,
        memory_context: MemoryContext,
        current_note_path: str | None,
        citations: list[str],
    ) -> list[str]:
        values = list(citations)
        thread_memory = memory_context.thread_memory
        for item in thread_memory.get("retrieval_evidence") or []:
            if isinstance(item, dict):
                path = str(item.get("path") or "").strip()
                if path:
                    values.append(path)
        current_note_excerpt = str(thread_memory.get("current_note_excerpt") or "").strip()
        if current_note_excerpt:
            if memory_context.current_note is not None:
                values.append(memory_context.current_note.relative_path)
            if current_note_path:
                values.append(current_note_path)
        return self._merge_citations(values)

    def _ensure_citation_footer(self, final_answer: str, citations: list[str]) -> str:
        normalized = final_answer.rstrip()
        if "来源：" in normalized or "Sources:" in normalized:
            return normalized
        cited_paths = [citation for citation in citations if citation in normalized]
        if cited_paths:
            return normalized
        footer_lines = "\n".join(f"- {citation}" for citation in citations[:3])
        return f"{normalized}\n\n来源：\n{footer_lines}"

    def _merge_citations(self, citations: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for citation in citations:
            normalized = citation.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return merged


__all__ = ["AnswerGeneration", "AnswerRequest", "AnswerService"]
