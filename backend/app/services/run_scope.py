"""Run 生命周期作用域。

`RunScopeService.open` 将 `RunTrace` 挂到 planner / llm_service 上（这些
对象可能各自需要写 trace），`close` / `mark_cancelled` 在 finally 块里
统一解绑，防止跨 run 的 trace 串写。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..observability import RunTrace


@dataclass(frozen=True)
class RunScope:
    trace: RunTrace | None
    targets: tuple[object, ...]


class RunScopeService:
    def open(self, *, trace: RunTrace | None, targets: tuple[object, ...] | list[object]) -> RunScope:
        scope = RunScope(trace=trace, targets=tuple(targets))
        for target in scope.targets:
            self._attach_trace(target, trace)
        return scope

    def mark_cancelled(self, scope: RunScope, reason: str = "") -> None:
        if scope.trace is not None:
            scope.trace.mark_cancelled(reason)

    def close(self, scope: RunScope) -> None:
        if scope.trace is not None:
            scope.trace.finish()
        for target in scope.targets:
            self._attach_trace(target, None)

    def _attach_trace(self, target: object, trace: RunTrace | None) -> None:
        attach = getattr(target, "attach_trace", None)
        if callable(attach):
            attach(trace)


__all__ = ["RunScope", "RunScopeService"]
