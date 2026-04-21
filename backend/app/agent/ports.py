"""Agent 层协议接口。

`CoordinatorPort` / `SubTaskRequest` / `ToolLease` 定义 coordinator 对外
的扩展点，供未来多 agent 编排或外部任务租用使用，当前只有
`SingleAgentCoordinator` 一份具体实现。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .context import AgentContextSnapshot
from .requests import TurnRequest


@dataclass(frozen=True)
class ToolLease:
    tool_names: list[str] = field(default_factory=list)
    lease_kind: str = "exclusive"
    owner_id: str = ""


@dataclass(frozen=True)
class SubTaskRequest:
    id: str
    prompt: str
    parent_task_id: str
    context_snapshot: AgentContextSnapshot
    allowed_tools: list[str] = field(default_factory=list)
    tool_lease: ToolLease | None = None


class CoordinatorPort(Protocol):
    def create_conversation(self, title: str | None = None): ...

    def list_messages(self, conversation_id: str): ...

    def run_stream(self, request: TurnRequest): ...
