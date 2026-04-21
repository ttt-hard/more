"""Runtime 执行结果数据类型。

`RuntimeOutcome` 聚合 runtime 一次循环后的产物：answer 草稿、引用、
tool 调用列表、各工具的 result payload、累计的事件，以及 task_state /
run_status 供 coordinator 推进到下一步。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .events import AgentEventBase


@dataclass
class RuntimeOutcome:
    answer: str
    citations: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    tool_results: list[dict[str, object]] = field(default_factory=list)
    events: list[AgentEventBase] = field(default_factory=list)
    task_state: str = "completed"
    run_status: str = "completed"
    # True 当 `answer` 已经是 planner 流出的最终用户回复（function calling
    # planner 的 respond 分支）。下游 AnswerService 见此直接流出，不再
    # 重新调用 LLM。
    final_answer_ready: bool = False
    # True 当 runtime 的 streaming planner 已经把 content tokens 通过
    # `TokenEvent` 送到 SSE stream。下游 AnswerService 看到此标记就不
    # 会重发 tokens（避免前端重复渲染），只负责收尾工作（如追加 citation
    # footer 作为额外 tokens）。
    answer_streamed: bool = False
