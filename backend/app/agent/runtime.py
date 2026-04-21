"""Agent 运行时：planner → tool 循环。

`AgentRuntime.run` 的核心是"规划 → 调工具 → 复核 → 再规划"循环，最多跑
`max_steps` 轮（默认 20，E2E 实测显示典型 skill 驱动链路需要 5~10 步），
每轮 planner 返回 action=respond 则终止；遇到 LLMError 走指数退避重试，
彻底失败则切回 `RegexFallbackPlanner`。工具失败时也会触发一轮 retry /
recovered 事件，直到耗尽预算。
"""

from __future__ import annotations

from ..observability_langfuse import observe, observed_tool
from ..workspace_fs import WorkspaceFS
from .events import (
    FallbackUsedEvent,
    PhaseStatusEvent,
    ReasoningDeltaEvent,
    ReasoningStepEvent,
    RecoveredEvent,
    RetryingEvent,
    StreamRollbackEvent,
    TokenEvent,
    ToolFailedEvent,
    coerce_agent_event,
)
from time import perf_counter

from ..llm import AgentPlan, LLMError
from ..ingest import IngestService
from ..services.memory import MemoryService
from ..notes import NoteService
from ..services.search import SearchService
from ..stores import ApprovalStorePort
from ..stores.approvals import ApprovalStore
from ..tools.base import ToolContext, ToolResult
from ..tools.registry import ToolRegistry
from .fallback import RegexFallbackPlanner
from .outcome import RuntimeOutcome
from .planner import PlanContentDelta, PlanDone, PlanReasoningDelta, PlannerPort
from .requests import RuntimeRequest


class AgentRuntime:
    def __init__(
        self,
        *,
        fs: WorkspaceFS,
        registry: ToolRegistry,
        planner: PlannerPort,
        fallback: RegexFallbackPlanner | None = None,
        note_service: NoteService,
        search_service: SearchService,
        ingest_service: IngestService,
        memory_service: MemoryService,
        approval_store: ApprovalStorePort | None = None,
        max_steps: int = 20,
        max_retries: int = 1,
    ) -> None:
        self.fs = fs
        self.registry = registry
        self.planner = planner
        self.fallback = fallback or RegexFallbackPlanner(registry)
        self.note_service = note_service
        self.search_service = search_service
        self.ingest_service = ingest_service
        self.memory_service = memory_service
        self.approval_store = approval_store or ApprovalStore(fs)
        self.max_steps = max_steps
        self.max_retries = max_retries

    @observe(name="agent.run", capture_output=False)
    def run(self, request: RuntimeRequest) -> RuntimeOutcome:
        run_trace = request.run_trace
        run_config = request.run_config
        default_note_dir = request.memory_context.preferences.default_note_dir
        retrieval_hits = request.memory_context.related_hits
        if run_trace is not None and run_config is not None:
            run_trace.config = run_config
        if request.cancellation_token is not None:
            request.cancellation_token.raise_if_cancelled()

        # Replay the (already finalised) event list of a fallback RuntimeOutcome
        # through the caller's live listener. `_run_llm_loop` emits via `emit`
        # which notifies on_event per-event in real time; the fallback paths
        # below build their RuntimeOutcome in one shot and then mutate the
        # list (inserting ReasoningStep / FallbackUsed), so we must pump the
        # final list through on_event ourselves or the coordinator's streaming
        # bridge would never see note_created / approval_required / etc.
        def _replay_events_to_listener(outcome: RuntimeOutcome) -> None:
            listener = request.on_event
            if listener is None:
                return
            for event in outcome.events:
                try:
                    listener(event)
                except Exception:  # noqa: BLE001
                    pass

        if self.planner.is_configured():
            try:
                return self._run_llm_loop(request)
            except LLMError as exc:
                fallback_reason = self._classify_fallback_reason(str(exc))
                if run_trace is not None:
                    run_trace.increment_metric("fallback_used_count")
                    run_trace.set_metric("fallback_used", True)
                    run_trace.set_metric("fallback_reason", fallback_reason)
                outcome = self.fallback.run(
                    prompt=request.prompt,
                    current_note_path=request.current_note_path,
                    retrieval_hits=retrieval_hits,
                    default_note_dir=default_note_dir,
                    context=self._build_tool_context(
                        prompt=request.prompt,
                        current_note_path=request.current_note_path,
                        default_note_dir=default_note_dir,
                    ),
                )
                outcome.events.insert(
                    0,
                    coerce_agent_event(
                        ReasoningStepEvent(
                            kind="fallback",
                            status="done",
                            title="已切换到回退规划",
                            detail=str(exc) or "LLM planner failed",
                        )
                    ),
                )
                outcome.events.insert(
                    1,
                    coerce_agent_event(
                        FallbackUsedEvent(
                            planner="regex",
                            reason=fallback_reason,
                        )
                    )
                )
                if run_trace is not None:
                    for event in outcome.events:
                        run_trace.record_event(event)
                _replay_events_to_listener(outcome)
                return outcome
        outcome = self.fallback.run(
            prompt=request.prompt,
            current_note_path=request.current_note_path,
            retrieval_hits=retrieval_hits,
            default_note_dir=default_note_dir,
            context=self._build_tool_context(
                prompt=request.prompt,
                current_note_path=request.current_note_path,
                default_note_dir=default_note_dir,
            ),
        )
        outcome.events.insert(
            0,
            coerce_agent_event(
                ReasoningStepEvent(
                    kind="fallback",
                    status="done",
                    title="使用回退规划",
                    detail="LLM provider is not configured.",
                )
            ),
        )
        outcome.events.insert(
            1,
            coerce_agent_event(
                FallbackUsedEvent(
                    planner="regex",
                    reason="provider_unconfigured",
                )
            )
        )
        if run_trace is not None:
            run_trace.increment_metric("fallback_used_count")
            run_trace.set_metric("fallback_used", True)
            run_trace.set_metric("fallback_reason", "provider_unconfigured")
            for event in outcome.events:
                run_trace.record_event(event)
        _replay_events_to_listener(outcome)
        return outcome

    @observe(name="agent.react_loop", capture_output=False)
    def _run_llm_loop(self, request: RuntimeRequest) -> RuntimeOutcome:
        prompt = request.prompt
        memory_context = request.memory_context
        current_note_path = request.current_note_path
        default_note_dir = request.memory_context.preferences.default_note_dir
        thread_summary = request.thread_summary
        token_budget = request.token_budget
        run_trace = request.run_trace
        cancellation_token = request.cancellation_token
        run_config = request.run_config
        effective_max_steps = run_config.max_steps if run_config is not None else self.max_steps
        effective_max_retries = run_config.max_retries if run_config is not None else self.max_retries
        tool_results: list[dict[str, object]] = []
        citations: list[str] = []
        tool_calls: list[str] = []
        events = []
        answer_hint = ""
        context = self._build_tool_context(
            prompt=prompt,
            current_note_path=current_note_path,
            default_note_dir=default_note_dir,
        )
        tool_recovery_pending = False

        if run_trace is not None and token_budget is not None:
            run_trace.budget_snapshot = dict(token_budget)

        # Per-run UI state shared across planner turns. Reserved for future
        # cross-turn signals; `_invoke_planner_step` no longer consults it
        # after content deltas were re-routed to the reasoning stream.
        run_state: dict[str, object] = {}

        on_event = request.on_event

        def emit(payload):
            event = coerce_agent_event(payload)
            events.append(event)
            if run_trace is not None:
                run_trace.record_event(event)
            # Pipe the event to any live listener (coordinator's SSE worker)
            # as soon as it is produced. This is what turns TokenEvents from
            # "buffered until the whole react loop finishes" into a true
            # per-delta stream. The callback is best-effort: if the listener
            # raises (e.g. the client disconnected), we swallow so the agent
            # loop can still complete and persist state cleanly; any fatal
            # condition propagates through `cancellation_token` instead.
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001
                    pass
            return event

        if run_trace is not None:
            run_trace.record_phase(
                phase="planning",
                label="正在规划",
                detail="分析当前请求并选择下一步动作。",
                metadata={"max_steps": effective_max_steps, "max_retries": effective_max_retries},
            )
            run_trace.observe_metric("retrieval_hit_count", len(memory_context.related_hits))
            run_trace.set_metric("fallback_used", False)

        for step in range(effective_max_steps):
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            emit(
                PhaseStatusEvent(
                    phase="planning",
                    label="正在规划",
                    detail="分析当前请求并选择下一步动作。",
                )
            )
            emit(
                ReasoningStepEvent(
                    kind="phase",
                    status="active",
                    title="规划下一步动作",
                    detail="分析当前请求并选择工具或直接回答。",
                )
            )
            plan: AgentPlan | None = None
            last_error: str | None = None
            streamed_content_this_turn = ""
            for attempt in range(effective_max_retries + 1):
                try:
                    plan, streamed_content_this_turn = self._invoke_planner_step(
                        prompt=prompt,
                        memory_context=memory_context,
                        current_note_path=current_note_path,
                        tool_results=tool_results,
                        thread_summary=thread_summary,
                        token_budget=token_budget,
                        emit=emit,
                        cancellation_token=cancellation_token,
                        run_state=run_state,
                    )
                    if attempt:
                        emit(
                            ReasoningStepEvent(
                                kind="recovered",
                                status="done",
                                title="规划器已恢复",
                                detail=f"第 {attempt + 1} 次尝试恢复成功。",
                            )
                        )
                        emit(RecoveredEvent(stage="planner", attempt=attempt + 1))
                    break
                except LLMError as exc:
                    last_error = str(exc)
                    if run_trace is not None:
                        run_trace.increment_metric("planner_error_count")
                    if attempt < effective_max_retries:
                        if run_trace is not None:
                            run_trace.increment_metric("planner_retry_count")
                        emit(
                            ReasoningStepEvent(
                                kind="retry",
                                status="active",
                                title="重试规划器",
                                detail=last_error,
                            )
                        )
                        emit(
                            RetryingEvent(
                                stage="planner",
                                attempt=attempt + 1,
                                detail=last_error,
                            )
                        )
                        continue
                    raise

            if plan is None:
                raise LLMError(last_error or "Planner did not produce a plan")

            if plan.action == "respond":
                emit(
                    ReasoningStepEvent(
                        kind="phase",
                        status="done",
                        title="已决定直接回答",
                        detail="当前上下文已足够生成最终答案。",
                    )
                )
                final_answer = plan.answer or answer_hint
                # If the streaming planner already flushed content tokens on
                # this final turn, signal AnswerService not to re-emit them.
                streamed_through_runtime = bool(streamed_content_this_turn.strip())
                return RuntimeOutcome(
                    answer=final_answer,
                    citations=self._merge_citations(citations + plan.citations),
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    events=events,
                    # Function-calling planner signals that its content IS the
                    # user-facing final answer; bypass the legacy answer-regen pass.
                    # Only honor the flag if the plan actually produced answer text
                    # (defensive against malformed empty final_answer responses).
                    final_answer_ready=plan.is_final_answer and bool(plan.answer.strip()),
                    answer_streamed=streamed_through_runtime,
                )

            if not self.registry.has(plan.action):
                if run_trace is not None:
                    run_trace.increment_metric("planner_unknown_action_count")
                emit(
                    ReasoningStepEvent(
                        kind="phase",
                        status="done",
                        title="使用现有结果收尾",
                        detail=f"规划器给出的动作 {plan.action} 不在工具清单中，直接返回当前答案草稿。",
                    )
                )
                return RuntimeOutcome(
                    answer=plan.answer or answer_hint,
                    citations=self._merge_citations(citations + plan.citations),
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    events=events,
                )

            tool_calls.append(plan.action)
            if run_trace is not None:
                run_trace.increment_metric("planner_step_count")
                run_trace.increment_metric("tool_call_count")
            emit(
                PhaseStatusEvent(
                    phase="tool",
                    label=f"正在调用工具：{plan.action}",
                    detail=None,
                )
            )
            emit(
                ReasoningStepEvent(
                    kind="tool",
                    status="active",
                    title=f"执行工具 · {plan.action}",
                    detail=str(plan.args) if plan.args else None,
                )
            )
            tool_started = perf_counter()
            tool_result = self._execute_tool(plan.action, plan.args, context)
            if run_trace is not None:
                run_trace.increment_metric("tool_latency_total_ms", (perf_counter() - tool_started) * 1000.0)
            for event in tool_result.events:
                emit(event)
            citations = self._merge_citations(citations + tool_result.citations + plan.citations)
            answer_hint = tool_result.summary or plan.answer or answer_hint
            tool_results.append(
                {
                    "action": plan.action,
                    "args": plan.args,
                    "ok": tool_result.ok,
                    "summary": tool_result.summary,
                    "citations": tool_result.citations,
                    "payload": tool_result.payload,
                    "error": tool_result.error,
                }
            )

            if not tool_result.ok:
                if run_trace is not None:
                    run_trace.increment_metric("tool_error_count")
                emit(
                    ReasoningStepEvent(
                        kind="error",
                        status="error",
                        title=f"工具失败 · {plan.action}",
                        detail=tool_result.error or "Tool execution failed",
                    )
                )
                emit(
                    ToolFailedEvent(
                        tool=plan.action,
                        detail=tool_result.error or "Tool execution failed",
                        step=step + 1,
                        attempt=1,
                    )
                )
                answer_hint = tool_result.error or answer_hint
                if step >= effective_max_steps - 1:
                    # No more retry budget; surface the failure immediately instead of
                    # emitting retry events / rebuilding context that would be discarded.
                    return RuntimeOutcome(
                        answer=answer_hint or tool_result.error or "抱歉，当前未能完成请求的工作区操作。",
                        citations=citations,
                        tool_calls=tool_calls,
                        tool_results=tool_results,
                        events=events,
                        task_state="failed",
                        run_status="failed",
                    )
                emit(
                    ReasoningStepEvent(
                        kind="retry",
                        status="active",
                        title=f"重试工具 · {plan.action}",
                        detail=tool_result.error or "Tool execution failed",
                    )
                )
                emit(
                    RetryingEvent(
                        stage="tool",
                        attempt=1,
                        detail=tool_result.error or "Tool execution failed",
                    )
                )
                tool_recovery_pending = True
                memory_context = self.memory_service.build_context(
                    current_note_path=current_note_path,
                    query=prompt,
                )
                continue

            if tool_recovery_pending:
                emit(
                    ReasoningStepEvent(
                        kind="recovered",
                        status="done",
                        title=f"工具已恢复 · {plan.action}",
                        detail="失败后的下一步已恢复正常执行。",
                    )
                )
                emit(RecoveredEvent(stage="tool", attempt=1))
                tool_recovery_pending = False

            emit(
                ReasoningStepEvent(
                    kind="tool",
                    status="done",
                    title=f"完成工具 · {plan.action}",
                    detail=tool_result.summary or None,
                )
            )

            if tool_result.requires_approval or tool_result.task_state != "completed" or tool_result.run_status != "completed":
                return RuntimeOutcome(
                    answer=tool_result.summary or answer_hint,
                    citations=citations,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    events=events,
                    task_state=tool_result.task_state,
                    run_status=tool_result.run_status,
                )

        return RuntimeOutcome(
            answer=answer_hint,
            citations=citations,
            tool_calls=tool_calls,
            tool_results=tool_results,
            events=events,
        )

    def _invoke_planner_step(
        self,
        *,
        prompt: str,
        memory_context,
        current_note_path: str | None,
        tool_results: list[dict[str, object]],
        thread_summary: str,
        token_budget: dict[str, object] | None,
        emit,
        cancellation_token,
        run_state: dict[str, object] | None = None,
    ) -> tuple[AgentPlan, str]:
        """Run a single planner step, preferring streaming when available.

        Returns `(plan, streamed_content)`:
          - `plan` is the final `AgentPlan` (same shape regardless of mode).
          - `streamed_content` is the concatenated content text already
            committed to the SSE stream via `TokenEvent` for THIS turn.
            Only non-empty when the turn turned out to be the final respond
            (so the answer bubble is now populated). Empty for tool-call
            middle turns because any tokens that briefly streamed have been
            rolled back via `StreamRollbackEvent`.

        Routing policy (optimistic-stream + rollback):
          - `PlanContentDelta` → emitted LIVE as `TokenEvent` the moment the
            provider yields it, so the user sees the real-time LLM token
            cadence in the answer bubble (this is the "typewriter" UX).
          - After `PlanDone` we know whether this was a real respond turn:
            * Final respond (`is_final_answer=True`): tokens stay on the
              wire; runtime sets `answer_streamed=True` so AnswerService
              will not re-emit them.
            * Middle (tool-call) turn: emit a single `StreamRollbackEvent`
              carrying the full buffered text so the frontend trims the
              last N characters off the in-progress bubble, then re-emit
              the same deltas as `ReasoningDeltaEvent`s (preserving the
              original chunking) so they land in the thinking panel.
          - `PlanReasoningDelta` (native reasoning tokens, e.g. DeepSeek-R1
            / OpenAI o1) → emitted live as `ReasoningDeltaEvent`, regardless
            of turn type. These are meta-level "thoughts", never answer text.

        `run_state` is a caller-owned dict reserved for future cross-turn
        signals (e.g. phase dedup). It is no longer consulted by this
        method, but is still accepted for backward compatibility with
        existing callers and tests.
        """
        stream_plan = getattr(self.planner, "stream_plan", None)
        if not callable(stream_plan):
            # Non-streaming planner (JSON protocol, regex fallback) → one-shot.
            plan = self.planner.plan(
                prompt=prompt,
                memory_context=memory_context,
                current_note_path=current_note_path,
                tool_results=tool_results,
                thread_summary=thread_summary,
                token_budget=token_budget,
            )
            return plan, ""

        final_plan: AgentPlan | None = None
        # Keep the original per-delta chunking so, on rollback, the thinking
        # panel can replay the narrative with the same typewriter cadence.
        streamed_deltas: list[str] = []
        for event in stream_plan(
            prompt=prompt,
            memory_context=memory_context,
            current_note_path=current_note_path,
            tool_results=tool_results,
            thread_summary=thread_summary,
            token_budget=token_budget,
        ):
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
            if isinstance(event, PlanContentDelta):
                if event.text:
                    # Optimistic real-time emission: send to the answer
                    # bubble immediately so the user sees LLM tokens as they
                    # arrive. We'll roll this back if the plan turns out to
                    # be a tool_call (middle turn) and redirect the text
                    # into the thinking panel below.
                    streamed_deltas.append(event.text)
                    emit(TokenEvent(text=event.text))
            elif isinstance(event, PlanReasoningDelta):
                # Native reasoning tokens stream to the thought panel live;
                # they are never user-facing answer content.
                if event.text:
                    emit(ReasoningDeltaEvent(text=event.text))
            elif isinstance(event, PlanDone):
                final_plan = event.plan

        if final_plan is None:
            # Defensive: planner iterator ended without PlanDone → treat as an
            # LLMError so the retry/recovery machinery up the stack can kick in.
            raise LLMError("Streaming planner did not emit a PlanDone event")

        is_final_respond = (
            final_plan.action == "respond" and bool(final_plan.is_final_answer)
        )
        if streamed_deltas and not is_final_respond:
            # Middle turn → undo the optimistic tokens, then redirect the
            # narrative into the thinking panel preserving original deltas.
            rollback_text = "".join(streamed_deltas)
            emit(StreamRollbackEvent(text=rollback_text))
            for text in streamed_deltas:
                emit(ReasoningDeltaEvent(text=text))
            return final_plan, ""
        return final_plan, "".join(streamed_deltas)

    def _build_tool_context(
        self,
        *,
        prompt: str,
        current_note_path: str | None,
        default_note_dir: str,
    ) -> ToolContext:
        return ToolContext(
            fs=self.fs,
            note_service=self.note_service,
            search_service=self.search_service,
            ingest_service=self.ingest_service,
            memory_service=self.memory_service,
            approval_store=self.approval_store,
            prompt=prompt,
            current_note_path=current_note_path,
            default_note_dir=default_note_dir,
        )

    @observed_tool(name="agent.tool")
    def _execute_tool(self, action: str, args: dict[str, object], context: ToolContext) -> ToolResult:
        try:
            return self.registry.execute(action, args, context)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                tool=action,
                summary="",
                error=str(exc),
            )

    def _merge_citations(self, citations: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for citation in citations:
            normalized = citation.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    def _classify_fallback_reason(self, detail: str) -> str:
        normalized = detail.casefold().strip()
        if not normalized:
            return "planner_error"
        if "not configured" in normalized or "provider is not configured" in normalized:
            return "provider_unconfigured"
        if "json" in normalized or "parse" in normalized:
            return "planner_parse_error"
        if "timeout" in normalized:
            return "planner_timeout"
        return "planner_error"
