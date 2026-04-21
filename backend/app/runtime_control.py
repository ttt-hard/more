"""运行时控制原语。

`RunConfig` 定义一次 run 的参数上限（planner_model / max_steps / token_budget
等）；`CancellationToken` 供 SSE 端点和 coordinator 实现协作式取消 —— 工作流
在关键节点调 `raise_if_cancelled()` 主动抛 `RunCancelledError`。
"""

from __future__ import annotations

from dataclasses import dataclass, field


class RunCancelledError(Exception):
    """Raised when a run is cancelled through the cancellation token."""


@dataclass(frozen=True)
class RunConfig:
    planner_model: str = ""
    answer_model: str = ""
    max_steps: int = 20
    max_retries: int = 1
    token_budget: int = 4000
    compression_threshold: int = 1800
    tool_timeout_ms: int = 30_000
    metadata: dict[str, object] = field(default_factory=dict)


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = False
        self.reason = ""

    def cancel(self, reason: str = "") -> None:
        self._cancelled = True
        self.reason = reason.strip()

    def is_cancelled(self) -> bool:
        return self._cancelled

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise RunCancelledError(self.reason or "Run cancelled")


__all__ = ["CancellationToken", "RunCancelledError", "RunConfig"]
