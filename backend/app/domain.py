"""领域模型（纯数据层）。

集中定义全系统共享的 dataclass 值对象（Workspace/Conversation/Message/
NoteMeta/SearchHit/MemoryContext 等），无任何 I/O 和业务逻辑。所有 service、
store、agent 层都围绕这些类型交换数据，是最底层的契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Workspace:
    name: str
    root_path: str
    config_path: str


@dataclass(frozen=True)
class FileEntry:
    path: str
    kind: str
    size: int
    modified_at: str


@dataclass(frozen=True)
class TreeEntry:
    path: str
    kind: str
    size: int
    modified_at: str
    children: list["TreeEntry"] = field(default_factory=list)


@dataclass(frozen=True)
class NoteMeta:
    id: str
    title: str
    relative_path: str
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    related: list[str] = field(default_factory=list)
    updated_at: str = ""
    source_type: str = "manual"


@dataclass(frozen=True)
class NoteDocument:
    meta: NoteMeta
    content: str


@dataclass(frozen=True)
class SearchHit:
    path: str
    kind: str
    title: str
    score: float
    snippet: str
    chunk_id: str = ""
    section: str = ""
    token_count: int = 0
    start_offset: int = 0


@dataclass(frozen=True)
class SearchIndexStatus:
    indexed_files: int
    indexed_chunks: int
    built_at: str
    manifest_path: str
    inverted_index_path: str
    chunks_path: str


@dataclass(frozen=True)
class UserPreference:
    language: str = "zh-CN"
    answer_style: str = "concise"
    default_note_dir: str = "Notes"
    theme: str = "system"


@dataclass(frozen=True)
class WorkspaceMemoryRecord:
    id: str
    kind: str
    value: str
    confidence: float
    source_thread_id: str
    source_message_id: str
    created_at: str
    updated_at: str
    status: str = "active"


@dataclass(frozen=True)
class MemoryCandidate:
    id: str
    kind: str
    value: str
    confidence: float
    source_thread_id: str
    source_message_id: str
    created_at: str
    status: str = "pending"


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    prompt_prefix: str
    when_to_use: str = ""
    tool_subset: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class MCPToolDefinition:
    name: str
    description: str
    input_schema: dict[str, object] = field(default_factory=dict)
    execution_mode: str = "builtin"
    builtin_action: str = "echo"
    enabled: bool = True


@dataclass(frozen=True)
class MCPServerDefinition:
    id: str
    name: str
    description: str = ""
    transport: str = "builtin"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_directory: str | None = None
    enabled: bool = True
    tools: list[MCPToolDefinition] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class MemoryContext:
    preferences: UserPreference
    current_note: NoteMeta | None
    related_hits: list[SearchHit]
    profile_memory: UserPreference | None = None
    workspace_memory: list[WorkspaceMemoryRecord] = field(default_factory=list)
    thread_memory: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str = ""
    status: str = "active"
    archived_at: str | None = None
    active_note_path: str | None = None
    summary: str = ""
    token_estimate: int = 0
    compacted_token_estimate: int = 0
    compression_state: str = "ok"
    compression_count: int = 0
    last_compacted_at: str | None = None
    labels: list[str] = field(default_factory=list)
    pinned: bool = False


@dataclass(frozen=True)
class Message:
    id: str
    role: str
    content: str
    citations: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    created_at: str = ""
    # Transcript of the reasoning/thinking stream produced while this message
    # was being generated (the `reasoning_delta` events concatenated in order,
    # including any text rolled back from the optimistic answer stream on
    # middle tool-call turns). Persisted per-message so that when a user
    # re-opens the conversation later, the UI can rehydrate each assistant
    # bubble's "thinking" panel instead of silently dropping it. Kept as a
    # plain string (not a list of deltas) because the split points are only
    # meaningful at streaming time — once persisted, only the concatenated
    # narrative matters for replay.
    reasoning: str = ""


@dataclass(frozen=True)
class ConversationCheckpoint:
    id: str
    conversation_id: str
    label: str
    summary: str
    token_estimate: int
    active_note_path: str | None
    created_at: str


@dataclass(frozen=True)
class ResumeContext:
    conversation: Conversation
    budget: dict[str, object]
    recent_messages: list[Message] = field(default_factory=list)
    active_note: NoteMeta | None = None
    workspace_memory_refs: list[WorkspaceMemoryRecord] = field(default_factory=list)
    checkpoints: list[ConversationCheckpoint] = field(default_factory=list)


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    parent_id: str | None
    state: str
    created_at: str


@dataclass(frozen=True)
class AgentRun:
    id: str
    task_id: str
    mode: str
    status: str
    created_at: str


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    action: str
    targets: list[str]
    reason: str
    status: str
    created_at: str
    payload: dict[str, object] = field(default_factory=dict)
    source: str = "api"


@dataclass(frozen=True)
class ImportJob:
    id: str
    source_type: str
    source_ref: str
    status: str
    output_path: str
    created_at: str


@dataclass(frozen=True)
class LLMSettings:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout: float = 30.0
    # 启用 OpenAI 原生 function calling 作为 planner（vs 传统 JSON 文本解析）。
    # DeepSeek / GPT / Qwen 等兼容 OpenAI 协议的模型默认都走 True；若遇
    # 不支持或格式偏差严重的 provider 可改为 False 回退到 `ProviderPlanner`。
    use_function_calling: bool = True


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
