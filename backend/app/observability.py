"""运行追踪与可观测性。

`RunTrace` 以单次 turn 为粒度记录 phase 流转、LLM 调用延迟、各类 metric（
retrieval_hit_count / tool_latency_total_ms / compression_state 等）和事件
序列。coordinator / runtime / answering 会在关键节点 `record_phase` / `
observe_metric`，最终由 eval / benchmark 脚本汇总。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from time import perf_counter
from typing import Any

from .domain import utc_now_iso
from .runtime_control import RunConfig


@dataclass
class RunTrace:
    run_id: str = ""
    conversation_id: str = ""
    config: RunConfig = field(default_factory=RunConfig)
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    cancelled_at: str | None = None
    cancelled_reason: str = ""
    budget_snapshot: dict[str, object] = field(default_factory=dict)
    phases: list[dict[str, object]] = field(default_factory=list)
    llm_calls: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    _started_perf: float = field(default_factory=perf_counter, init=False, repr=False)
    _first_answer_token_recorded: bool = field(default=False, init=False, repr=False)

    def record_phase(
        self,
        *,
        phase: str,
        label: str,
        detail: str | None = None,
        status: str = "started",
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.phases.append(
            {
                "phase": phase,
                "label": label,
                "detail": detail,
                "status": status,
                "metadata": metadata or {},
                "at": utc_now_iso(),
            }
        )

    def record_event(self, payload: Any) -> None:
        if payload is None:
            return
        if hasattr(payload, "model_dump"):
            rendered = payload.model_dump(mode="json")
        elif is_dataclass(payload):
            rendered = asdict(payload)
        elif isinstance(payload, dict):
            rendered = dict(payload)
        else:
            rendered = {"value": str(payload)}
        self.events.append(rendered)

    def record_llm_call(
        self,
        *,
        stage: str,
        model: str,
        latency_ms: float,
        request_summary: dict[str, object] | None = None,
        response_summary: dict[str, object] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_hit: bool | None = None,
        error: str | None = None,
    ) -> None:
        self.llm_calls.append(
            {
                "stage": stage,
                "model": model,
                "latency_ms": latency_ms,
                "request_summary": request_summary or {},
                "response_summary": response_summary or {},
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_hit": cache_hit,
                "error": error,
                "at": utc_now_iso(),
            }
        )

    def set_metric(self, name: str, value: object) -> None:
        normalized = name.strip()
        if normalized:
            self.metrics[normalized] = value

    def increment_metric(self, name: str, amount: int | float = 1) -> None:
        normalized = name.strip()
        if not normalized:
            return
        current = self.metrics.get(normalized, 0)
        if not isinstance(current, (int, float)):
            current = 0
        self.metrics[normalized] = current + amount

    def observe_metric(self, name: str, value: int | float, *, mode: str = "set") -> None:
        normalized = name.strip()
        if not normalized:
            return
        current = self.metrics.get(normalized)
        if mode == "max":
            if not isinstance(current, (int, float)) or value > current:
                self.metrics[normalized] = value
            return
        if mode == "min":
            if not isinstance(current, (int, float)) or value < current:
                self.metrics[normalized] = value
            return
        self.metrics[normalized] = value

    def elapsed_ms(self) -> float:
        return (perf_counter() - self._started_perf) * 1000.0

    def mark_first_answer_token(self) -> None:
        if self._first_answer_token_recorded:
            return
        self._first_answer_token_recorded = True
        self.observe_metric("first_answer_latency_ms", self.elapsed_ms())

    def mark_cancelled(self, reason: str = "") -> None:
        self.cancelled_at = utc_now_iso()
        self.cancelled_reason = reason.strip()

    def finish(self) -> None:
        self.finished_at = utc_now_iso()

    def snapshot(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "conversation_id": self.conversation_id,
            "config": asdict(self.config),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancelled_at": self.cancelled_at,
            "cancelled_reason": self.cancelled_reason,
            "budget_snapshot": dict(self.budget_snapshot),
            "phases": list(self.phases),
            "llm_calls": list(self.llm_calls),
            "events": list(self.events),
            "metrics": dict(self.metrics),
            "notes": list(self.notes),
        }

    def note(self, message: str) -> None:
        normalized = message.strip()
        if normalized:
            self.notes.append(normalized)


__all__ = ["RunTrace"]
