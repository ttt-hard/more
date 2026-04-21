"""Agent 上下文快照。

`AgentContextSnapshot` 在一次 turn 开始时打包 prompt、当前 note 路径、默认
note 目录、内存上下文，便于后续 runtime / answer 环节复用同一份只读视图。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import MemoryContext


@dataclass(frozen=True)
class AgentContextSnapshot:
    prompt: str
    current_note_path: str | None
    default_note_dir: str
    memory_context: MemoryContext


ContextSnapshot = AgentContextSnapshot
