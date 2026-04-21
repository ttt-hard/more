"""LLM provider 抽象层。

`ModelProvider` Protocol 是 `LLMService` 依赖的接口（complete / stream /
test_connection）；`CompletionRequest` / `CompletionResponse` / `StreamChunk`
是跨 provider 的 DTO。具体实现放在 `litellm_provider.py`。

`CompletionRequest.tools` / `tool_choice` 供 OpenAI 兼容的原生 function
calling 路径使用，provider 若识别就把 tools 透传到 chat completion；响应
里的 `tool_calls` 字段被解析为 `ToolCall` 列表，供 planner 直接消费而不
用 JSON 文本 parse。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


class ProviderError(Exception):
    """Raised when the model provider cannot complete a request."""


@dataclass(frozen=True)
class ToolCall:
    """A single tool invocation requested by the model via function calling."""

    id: str
    name: str
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.1
    max_tokens: int | None = None
    timeout: float = 30.0
    base_url: str = ""
    api_key: str = ""
    metadata: dict[str, object] = field(default_factory=dict)
    # OpenAI-compatible function calling:
    #   `tools`: list of {"type": "function", "function": {name, description, parameters}}
    #   `tool_choice`: "auto" | "none" | {"type":"function","function":{"name":...}}
    tools: list[dict[str, object]] | None = None
    tool_choice: str | dict[str, object] | None = None


@dataclass(frozen=True)
class CompletionResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StreamChunk:
    """A single streamed delta.

    Streaming semantics across a full response:

    - Intermediate chunks carry visible `content` and/or `reasoning` text
      deltas. `tool_calls` is empty and `finished=False`.
    - Exactly one final chunk is yielded with `finished=True`. If the LLM
      chose to call tools, the final chunk carries the fully assembled
      `tool_calls` (every delta merged by `index`). Otherwise `tool_calls=[]`.
    - `finish_reason` mirrors OpenAI's field ("stop" | "tool_calls" | "length"
      | ...) on the final chunk; `None` on intermediate chunks.

    Consumers should treat any chunk with `finished=True` as end-of-stream,
    then inspect `tool_calls` to decide whether to continue the react loop
    or treat the accumulated content as the final answer.
    """

    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finished: bool = False
    finish_reason: str | None = None


class ModelProvider(Protocol):
    def is_configured(self) -> bool: ...

    def complete(self, request: CompletionRequest) -> CompletionResponse: ...

    def stream_complete(self, request: CompletionRequest) -> Iterator[str]: ...

    def test_connection(self, request: CompletionRequest) -> dict[str, object]: ...
