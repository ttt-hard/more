"""Agent 协调器 —— 对话 turn 的中央控制。

`SingleAgentCoordinator` 是后端 agent 的入口：组装所有下游服务（memory /
turn_context / runtime / answer / compression / memory extraction / skill /
mcp / stores），提供 `create_conversation / list_messages / run_stream / ...`
等对外方法。`run_stream` 是单轮 turn 的完整流水线（开启 turn → 构上下文
→ runtime 循环 → answer 生成 → 归档 memory candidate → 完成 turn → 发送
SSE 事件）。
"""

from __future__ import annotations

import contextvars
import queue
import threading
from dataclasses import asdict, replace

from ..observability_langfuse import observe, set_turn_session
from ..workspace_fs import WorkspaceFS
from ..domain import WorkspaceMemoryRecord, utc_now_iso
from .events import (
    DoneEvent,
    ErrorEvent,
    MessageDoneEvent,
    MessageStartEvent,
    RetrievalHitsEvent,
    TaskStatusEvent,
    coerce_agent_event,
)
from ..llm import LLMService
from ..services.answering import AnswerGeneration, AnswerRequest, AnswerService
from ..services.context_packing import ContextPackingPolicy
from ..ingest import IngestService
from ..services.conversations import ConversationCompressionService
from ..services.memory import MemoryService
from ..services.memory_extraction import MemoryExtractionInput, MemoryExtractionService
from ..mcp.service import MCPService
from ..notes import NoteService
from ..services.run_scope import RunScopeService
from ..services.search import SearchService
from ..skills.service import SkillService
from ..services.turn_context import TurnContextService
from ..services.turn_state import TurnStateService
from ..runtime_control import RunCancelledError, RunConfig
from ..stores import (
    ApprovalStorePort,
    ConversationCheckpointStorePort,
    ConversationStorePort,
    MemoryCandidateStorePort,
    TaskStorePort,
    WorkspaceMemoryStorePort,
)
from ..stores.conversations import ConversationStore
from ..stores.checkpoints import ConversationCheckpointStore
from ..stores.memory_candidates import MemoryCandidateStore
from ..stores.tasks import TaskStore
from ..stores.workspace_memory import WorkspaceMemoryStore
from .context import AgentContextSnapshot
from .errors import AgentError
from .planner import FunctionCallingPlanner, LLMPlanner, LegacyPlannerAdapter, PlannerPort
from .requests import RuntimeRequest, TurnRequest
from .runtime import AgentRuntime
from ..tools.registry import ToolRegistry, build_default_tool_registry


class SingleAgentCoordinator:
    def __init__(
        self,
        fs: WorkspaceFS,
        note_service: NoteService | None = None,
        search_service: SearchService | None = None,
        ingest_service: IngestService | None = None,
        memory_service: MemoryService | None = None,
        llm_service: LLMService | None = None,
        conversation_store: ConversationStorePort | None = None,
        task_store: TaskStorePort | None = None,
        approval_store: ApprovalStorePort | None = None,
        tool_registry: ToolRegistry | None = None,
        planner: PlannerPort | None = None,
        compression_service: ConversationCompressionService | None = None,
        workspace_memory_store: WorkspaceMemoryStorePort | None = None,
        memory_candidate_store: MemoryCandidateStorePort | None = None,
        memory_extraction_service: MemoryExtractionService | None = None,
        checkpoint_store: ConversationCheckpointStorePort | None = None,
        context_packing_policy: ContextPackingPolicy | None = None,
        skill_service: SkillService | None = None,
        mcp_service: MCPService | None = None,
        run_config: RunConfig | None = None,
    ) -> None:
        self.fs = fs
        note_service = note_service or NoteService(fs)
        search_service = search_service or SearchService(fs, note_service=note_service)
        ingest_service = ingest_service or IngestService(fs, note_service=note_service)
        memory_service = memory_service or MemoryService(fs, note_service=note_service)
        self.llm_service = llm_service or LLMService()
        self.conversation_store = conversation_store or ConversationStore(fs)
        self.task_store = task_store or TaskStore(fs)
        self.checkpoint_store = checkpoint_store or ConversationCheckpointStore(fs)
        self.note_service = note_service
        self.memory_service = memory_service
        self.skill_service = skill_service or SkillService(fs)
        self.mcp_service = mcp_service or MCPService(fs)
        self.workspace_memory_store = workspace_memory_store or WorkspaceMemoryStore(fs)
        self.memory_candidate_store = memory_candidate_store or MemoryCandidateStore(fs)
        self.memory_extraction_service = memory_extraction_service or MemoryExtractionService()
        self.compression_service = compression_service or ConversationCompressionService(
            self.conversation_store,
            note_service=self.note_service,
            workspace_memory_store=self.workspace_memory_store,
            checkpoint_store=self.checkpoint_store,
        )
        self.turn_context_service = TurnContextService(
            self.compression_service,
            memory_service,
            context_packing_policy=context_packing_policy,
        )
        self.run_scope_service = RunScopeService()
        self.turn_state_service = TurnStateService(self.conversation_store, self.task_store)
        self.answer_service = AnswerService(self.llm_service)
        tool_registry = tool_registry or build_default_tool_registry(mcp_service=self.mcp_service)
        self.tool_registry = tool_registry
        self.planner = planner or self._build_planner(self.llm_service, tool_registry=tool_registry)
        model_name = getattr(self.llm_service, "model", "")
        self.run_config = run_config or RunConfig(planner_model=model_name, answer_model=model_name)
        self.runtime = AgentRuntime(
            fs=fs,
            registry=tool_registry,
            planner=self.planner,
            note_service=note_service,
            search_service=search_service,
            ingest_service=ingest_service,
            memory_service=memory_service,
            approval_store=approval_store,
        )

    def create_conversation(self, title: str | None = None):
        return self.conversation_store.create_conversation(title=title)

    def list_messages(self, conversation_id: str):
        return self.conversation_store.list_messages(conversation_id)

    def list_conversations(self, *, include_archived: bool = False):
        return self.conversation_store.list_conversations(include_archived=include_archived)

    def rename_conversation(self, conversation_id: str, title: str):
        return self.conversation_store.rename_conversation(conversation_id, title)

    def archive_conversation(self, conversation_id: str):
        return self.conversation_store.archive_conversation(conversation_id)

    def resume_conversation(self, conversation_id: str):
        return self.conversation_store.resume_conversation(conversation_id)

    def get_conversation_summary(self, conversation_id: str) -> dict[str, object]:
        return self.compression_service.conversation_status(conversation_id)

    def compact_conversation(self, conversation_id: str):
        return self.compression_service.summarize(conversation_id)

    def create_checkpoint(self, conversation_id: str, *, label: str | None = None):
        return self.compression_service.create_checkpoint(conversation_id, label=label)

    def set_conversation_pin(self, conversation_id: str, *, pinned: bool = True):
        return self.conversation_store.update_context(conversation_id, pinned=pinned)

    def update_conversation_labels(self, conversation_id: str, labels: list[str]):
        return self.conversation_store.update_context(conversation_id, labels=labels)

    def build_resume_context(self, conversation_id: str):
        return self.compression_service.build_resume_context(conversation_id)

    def list_memory_candidates(self, conversation_id: str, *, include_resolved: bool = False):
        return self.memory_candidate_store.list_candidates(conversation_id, include_resolved=include_resolved)

    def accept_memory_candidate(self, conversation_id: str, candidate_id: str):
        candidate = self.memory_candidate_store.update_candidate_status(conversation_id, candidate_id, status="accepted")
        record = self.workspace_memory_store.upsert_record(
            WorkspaceMemoryRecord(
                id=candidate.id,
                kind=candidate.kind,
                value=candidate.value,
                confidence=candidate.confidence,
                source_thread_id=candidate.source_thread_id,
                source_message_id=candidate.source_message_id,
                created_at=candidate.created_at,
                updated_at=utc_now_iso(),
            )
        )
        return candidate, record

    def reject_memory_candidate(self, conversation_id: str, candidate_id: str):
        return self.memory_candidate_store.update_candidate_status(conversation_id, candidate_id, status="rejected")

    def build_context_snapshot(
        self,
        *,
        prompt: str,
        current_note_path: str | None,
        default_note_dir: str,
    ) -> AgentContextSnapshot:
        memory_context = self.turn_context_service.build_memory_context(
            current_note_path=current_note_path,
            limit=5,
            prompt=prompt,
        )
        return AgentContextSnapshot(
            prompt=prompt,
            current_note_path=current_note_path,
            default_note_dir=default_note_dir,
            memory_context=memory_context,
        )

    # IMPORTANT: must NOT pass `capture_output=False` here. This is a
    # generator function, and Langfuse v4's `@observe` special-cases
    # generators so that `capture_output=True` (the default) triggers
    # the context-preserving wrapper that keeps the span open for the
    # lifetime of iteration. Passing `capture_output=False` would cause
    # `_sync_observe` to skip `_wrap_sync_generator_result` entirely
    # and hit `finally: langfuse_span.end()` immediately after
    # `run_stream(...)` returns the (un-iterated) generator object —
    # span closed before the body ever runs, so every nested
    # `@observe` inside becomes its own root trace and
    # `update_current_trace(session_id=...)` finds no active span.
    # See https://github.com/langfuse/langfuse-python/blob/main/langfuse/_client/observe.py
    # (`_sync_observe` → `capture_output is True` check).
    @observe(name="conversation.turn")
    def run_stream(self, request: TurnRequest):
        prompt_text = request.prompt.strip()
        if not prompt_text:
            raise AgentError("Prompt must not be empty")

        # Tag the Langfuse trace so the UI groups multi-turn conversations
        # under one session view. Silent no-op when Langfuse is disabled.
        # The `mode` / note attributes land on the trace as metadata for
        # post-hoc filtering (e.g. "show me all turns that ran with a
        # current_note attached"). Added BEFORE any yield so the session
        # id is attached even if the turn crashes immediately.
        set_turn_session(
            request.conversation_id,
            metadata={
                "mode": request.mode,
                "prompt_length": len(prompt_text),
                "has_current_note": request.current_note_path is not None,
            },
            tags=["react-loop"],
        )

        thread_summary = request.thread_summary
        token_budget = request.token_budget
        effective_run_config = request.run_config or self.run_config
        turn_state = self.turn_state_service.begin_turn(
            conversation_id=request.conversation_id,
            prompt=prompt_text,
            current_note_path=request.current_note_path,
            mode=request.mode,
            run_config=effective_run_config,
            run_trace=request.run_trace,
            token_budget=token_budget,
        )
        task = turn_state.task
        run = turn_state.run
        active_trace = turn_state.trace
        preflight = self.turn_context_service.prepare_preflight(
            conversation_id=request.conversation_id,
            thread_summary=thread_summary,
            token_budget=token_budget,
            run_trace=active_trace,
        )
        run_scope = self.run_scope_service.open(trace=active_trace, targets=(self.planner, self.llm_service))

        yield coerce_agent_event(TaskStatusEvent(task=asdict(task), run=asdict(run)))

        try:
            if request.cancellation_token is not None:
                request.cancellation_token.raise_if_cancelled()

            turn_context = self.turn_context_service.build_turn_context(
                current_note_path=request.current_note_path,
                prompt=prompt_text,
                preflight=preflight,
                run_trace=active_trace,
            )
            turn_context = self._augment_turn_context(
                turn_context,
                prompt=prompt_text,
                current_note_path=request.current_note_path,
            )
            yield coerce_agent_event(RetrievalHitsEvent(hits=[asdict(hit) for hit in turn_context.memory_context.related_hits]))
            yield coerce_agent_event(MessageStartEvent(conversation_id=request.conversation_id))

            # Per-turn transcript of the thinking panel: every reasoning_delta
            # observed in this turn's event stream (from the runtime worker
            # AND any reasoning the answer service surfaces) is concatenated
            # here in arrival order, so we can persist it on the assistant
            # Message and the frontend can rehydrate the thought bubble when
            # the user re-opens this conversation later. Without this the
            # thinking panel shows only for the currently streaming turn and
            # disappears forever once the turn finishes.
            collected_reasoning: list[str] = []

            def _record_reasoning(event):
                # Runtime emits StreamRollback followed by a replay of the same
                # text as reasoning_delta chunks, so tracking reasoning_delta
                # alone is sufficient; nothing else routes thinking-panel text.
                if getattr(event, "type", None) == "reasoning_delta":
                    text = getattr(event, "text", "") or ""
                    if text:
                        collected_reasoning.append(text)
                return event

            # Runtime is a blocking, synchronous react loop (LLM streaming is
            # consumed inside it via httpx). If we just called it here and
            # then iterated `outcome.events`, every "live" TokenEvent that
            # runtime claims to emit in real time would actually sit in
            # `outcome.events` until the whole loop finished — the browser
            # would see tokens only AFTER the LLM was done generating.
            #
            # Bridge via a thread-safe queue: the worker thread runs the
            # runtime and feeds each event into the queue the instant it is
            # emitted; this generator drains the queue and yields into the
            # SSE response, so tokens hit the wire at the actual LLM cadence.
            event_q: queue.Queue = queue.Queue()
            run_sentinel = object()
            holder: dict[str, object] = {}

            def _runtime_worker() -> None:
                try:
                    result = self.runtime.run(
                        RuntimeRequest(
                            prompt=prompt_text,
                            memory_context=turn_context.memory_context,
                            current_note_path=request.current_note_path,
                            thread_summary=turn_context.thread_summary,
                            token_budget=turn_context.token_budget,
                            run_trace=active_trace,
                            cancellation_token=request.cancellation_token,
                            run_config=effective_run_config,
                            on_event=event_q.put,
                        )
                    )
                    holder["outcome"] = result
                except BaseException as worker_exc:  # noqa: BLE001
                    holder["error"] = worker_exc
                finally:
                    event_q.put(run_sentinel)

            # Snapshot the current contextvars (including the Langfuse
            # observation context) so the worker thread inherits our span
            # parentage. Without this `ctx.run`, any `@observe` inside the
            # runtime or its tool calls would start a fresh root trace and
            # the Langfuse UI would show agent-loop spans orphaned from
            # the parent `conversation.turn`.
            worker_ctx = contextvars.copy_context()
            worker_thread = threading.Thread(
                target=lambda: worker_ctx.run(_runtime_worker),
                name="agent-runtime",
                daemon=True,
            )
            worker_thread.start()
            try:
                while True:
                    event = event_q.get()
                    if event is run_sentinel:
                        break
                    yield _record_reasoning(event)
            finally:
                worker_thread.join()

            if "error" in holder:
                raise holder["error"]  # re-raise inside the outer try/except
            outcome = holder["outcome"]

            answer_generation: AnswerGeneration | None = None
            for emitted in self.answer_service.generate_stream(
                AnswerRequest(
                    prompt=prompt_text,
                    memory_context=turn_context.memory_context,
                    current_note_path=request.current_note_path,
                    outcome=outcome,
                    thread_summary=turn_context.thread_summary,
                    token_budget=turn_context.token_budget,
                    cancellation_token=request.cancellation_token,
                    run_trace=active_trace,
                )
            ):
                if isinstance(emitted, AnswerGeneration):
                    answer_generation = emitted
                else:
                    yield _record_reasoning(emitted)
            if answer_generation is None:
                answer_generation = AnswerGeneration(final_answer="", citations=[], events=[])
            final_answer = answer_generation.final_answer

            completed_turn = self.turn_state_service.complete_turn(
                conversation_id=request.conversation_id,
                task_id=task.id,
                run_id=run.id,
                answer=final_answer,
                citations=answer_generation.citations,
                tool_calls=outcome.tool_calls,
                task_state=outcome.task_state,
                run_status=outcome.run_status,
                reasoning="".join(collected_reasoning),
            )
            current_note = turn_context.memory_context.current_note
            extracted_candidates = self.memory_extraction_service.extract_candidates(
                MemoryExtractionInput(
                    conversation_id=request.conversation_id,
                    message=completed_turn.message,
                    current_note=current_note,
                    related_hits=turn_context.memory_context.related_hits,
                ),
                run_trace=active_trace,
            )
            if extracted_candidates:
                self.memory_candidate_store.create_candidates(request.conversation_id, extracted_candidates)
            if active_trace is not None:
                active_trace.observe_metric("memory_candidate_persisted_count", len(extracted_candidates))
            self.turn_context_service.refresh_post_turn(
                conversation_id=request.conversation_id,
                run_trace=active_trace,
            )

            yield coerce_agent_event(MessageDoneEvent(message=asdict(completed_turn.message)))
            yield coerce_agent_event(TaskStatusEvent(task=asdict(completed_turn.task), run=asdict(completed_turn.run)))
            yield coerce_agent_event(DoneEvent(conversation_id=request.conversation_id))
        except RunCancelledError as exc:
            self.run_scope_service.mark_cancelled(run_scope, str(exc))
            cancelled_turn = self.turn_state_service.cancel_turn(task_id=task.id, run_id=run.id)
            yield coerce_agent_event(ErrorEvent(detail=str(exc) or "Run cancelled"))
            yield coerce_agent_event(TaskStatusEvent(task=asdict(cancelled_turn.task), run=asdict(cancelled_turn.run)))
            yield coerce_agent_event(DoneEvent(conversation_id=request.conversation_id))
        except Exception as exc:  # noqa: BLE001
            if active_trace is not None:
                active_trace.note(f"Run failed: {exc}")
                active_trace.set_metric("failed", True)
                active_trace.set_metric("failure_reason", str(exc))
            failed_turn = self.turn_state_service.fail_turn(task_id=task.id, run_id=run.id)
            yield coerce_agent_event(ErrorEvent(detail=str(exc) or "Run failed"))
            yield coerce_agent_event(TaskStatusEvent(task=asdict(failed_turn.task), run=asdict(failed_turn.run)))
            yield coerce_agent_event(DoneEvent(conversation_id=request.conversation_id))
        finally:
            self.run_scope_service.close(run_scope)

    def _build_planner(
        self,
        llm_like: object,
        *,
        tool_registry: ToolRegistry | None = None,
    ) -> PlannerPort:
        if isinstance(llm_like, LLMService):
            # LLMService with function calling enabled + a tool registry gets the
            # native function calling planner; otherwise fall back to the JSON
            # text protocol planner.
            if tool_registry is not None and getattr(llm_like, "use_function_calling", False):
                return FunctionCallingPlanner.from_llm_service(
                    llm_like,
                    tool_registry=tool_registry,
                )
            return LLMPlanner(llm_like)
        return LegacyPlannerAdapter(llm_like)

    def _augment_turn_context(self, turn_context, *, prompt: str, current_note_path: str | None):
        current_note = turn_context.memory_context.current_note
        active_tags = list(current_note.tags) if current_note is not None else []
        active_skills = [
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "when_to_use": skill.when_to_use,
                "tool_subset": skill.tool_subset,
                "examples": skill.examples,
                "load_with": f"load_skill(skill_id='{skill.id}')",
            }
            for skill in self.skill_service.resolve_skills(
                prompt=prompt,
                current_note_path=current_note_path,
                active_tags=active_tags,
            )
        ]
        tool_catalog = []
        for name in self.runtime.registry.names():
            definition = self.runtime.registry.get_definition(name)
            tool_catalog.append(
                {
                    "name": definition.name,
                    "kind": definition.kind,
                    "approval_gated": definition.approval_gated,
                    "description": definition.description,
                }
            )
        thread_memory = dict(turn_context.memory_context.thread_memory)
        thread_memory["active_skills"] = active_skills
        thread_memory["tool_catalog"] = tool_catalog
        return replace(
            turn_context,
            memory_context=replace(turn_context.memory_context, thread_memory=thread_memory),
        )
