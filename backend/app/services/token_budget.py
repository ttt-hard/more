"""Token 预算管理。

`TokenBudgetManager.snapshot` 把 `conversation.token_estimate` 减去已压缩
`compacted_token_estimate` 得到 pending_tokens，映射为 ok / warning /
compact / force 四档 state；`apply_policy` 在该 state 下决定是否立即
触发摘要压缩。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..domain import Conversation


@dataclass(frozen=True)
class TokenBudgetSnapshot:
    total_tokens: int
    compacted_tokens: int
    pending_tokens: int
    warning_threshold: int
    compact_threshold: int
    force_threshold: int
    state: str
    utilization: float
    should_compact: bool


class TokenBudgetManager:
    def __init__(
        self,
        *,
        warning_threshold: int = 1200,
        compact_threshold: int = 1800,
        force_threshold: int = 2400,
    ) -> None:
        self.warning_threshold = warning_threshold
        self.compact_threshold = compact_threshold
        self.force_threshold = force_threshold

    def snapshot(self, conversation: Conversation) -> TokenBudgetSnapshot:
        pending_tokens = max(0, conversation.token_estimate - conversation.compacted_token_estimate)
        state = self.state_for_pending_tokens(pending_tokens)
        utilization = min(1.0, pending_tokens / self.force_threshold) if self.force_threshold else 0.0
        return TokenBudgetSnapshot(
            total_tokens=conversation.token_estimate,
            compacted_tokens=conversation.compacted_token_estimate,
            pending_tokens=pending_tokens,
            warning_threshold=self.warning_threshold,
            compact_threshold=self.compact_threshold,
            force_threshold=self.force_threshold,
            state=state,
            utilization=utilization,
            should_compact=state in {"compact", "force"},
        )

    def state_for_pending_tokens(self, pending_tokens: int) -> str:
        if pending_tokens >= self.force_threshold:
            return "force"
        if pending_tokens >= self.compact_threshold:
            return "compact"
        if pending_tokens >= self.warning_threshold:
            return "warning"
        return "ok"

    def dump_snapshot(self, conversation: Conversation) -> dict[str, object]:
        return asdict(self.snapshot(conversation))


__all__ = ["TokenBudgetManager", "TokenBudgetSnapshot"]
