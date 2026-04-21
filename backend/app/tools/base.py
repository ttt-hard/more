"""工具类型定义。

`ToolContext` 传给 handler 的依赖束（fs / note / search / ingest / memory
/ approval_store + prompt 等上下文）；`ToolResult` 是 handler 的返回
（ok / summary / citations / events / payload / requires_approval / ...）；
`ToolHandler` = `(args, context) -> ToolResult`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

from ..workspace_fs import WorkspaceFS
from ..ingest import IngestService
from ..services.memory import MemoryService
from ..notes import NoteService
from ..services.search import SearchService
from ..stores import ApprovalStorePort

if TYPE_CHECKING:
    # 只在类型检查阶段需要；运行时导入 `..agent.events` 会触发
    # agent 包的完整加载（agent/__init__.py → coordinator → runtime →
    # tools.base 回头），在自顶向下首次 import 工具子包时会构成循环。
    from ..agent.events import AgentEventBase


@dataclass
class ToolContext:
    fs: WorkspaceFS
    note_service: NoteService
    search_service: SearchService
    ingest_service: IngestService
    memory_service: MemoryService
    approval_store: ApprovalStorePort
    prompt: str
    current_note_path: str | None
    default_note_dir: str


@dataclass
class ToolResult:
    ok: bool
    tool: str
    summary: str
    citations: list[str] = field(default_factory=list)
    events: list[AgentEventBase | dict[str, Any]] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    task_state: str = "completed"
    run_status: str = "completed"
    error: str | None = None


ToolHandler = Callable[[dict[str, object], ToolContext], ToolResult]
ToolKind = Literal["native", "external", "approval-gated"]
