"""Store 协议契约。

集中声明所有持久化存储的 `Protocol`（ConversationStorePort /
TaskStorePort / WorkspaceMemoryStorePort / ... ），service 层只依赖这些
接口，方便单测用 fake 替换。具体实现在同目录其它文件中。
"""

from __future__ import annotations

from typing import Protocol

from ..domain import (
    AgentRun,
    ApprovalRequest,
    Conversation,
    ConversationCheckpoint,
    LLMSettings,
    MCPServerDefinition,
    MemoryCandidate,
    Message,
    SkillDefinition,
    Task,
    UserPreference,
    WorkspaceMemoryRecord,
)


class ConversationStorePort(Protocol):
    def create_conversation(self, title: str | None = None) -> Conversation: ...

    def get_conversation(self, conversation_id: str) -> Conversation: ...

    def list_conversations(self, *, include_archived: bool = False) -> list[Conversation]: ...

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation: ...

    def archive_conversation(self, conversation_id: str) -> Conversation: ...

    def resume_conversation(self, conversation_id: str) -> Conversation: ...

    def update_context(
        self,
        conversation_id: str,
        *,
        active_note_path: str | None = None,
        summary: str | None = None,
        compacted_token_estimate: int | None = None,
        compression_state: str | None = None,
        compression_count: int | None = None,
        last_compacted_at: str | None = None,
        labels: list[str] | None = None,
        pinned: bool | None = None,
    ) -> Conversation: ...

    def append_message(self, conversation_id: str, message: Message) -> None: ...

    def list_messages(self, conversation_id: str) -> list[Message]: ...


class TaskStorePort(Protocol):
    def create_task(self, kind: str, parent_id: str | None = None) -> Task: ...

    def update_task_state(self, task_id: str, state: str) -> Task: ...

    def list_tasks(self) -> list[Task]: ...

    def create_run(self, task_id: str, mode: str) -> AgentRun: ...

    def update_run_status(self, run_id: str, status: str) -> AgentRun: ...

    def list_runs(self) -> list[AgentRun]: ...


class ApprovalStorePort(Protocol):
    def create_request(
        self,
        *,
        action: str,
        targets: list[str],
        reason: str,
        payload: dict[str, object],
        source: str = "api",
    ) -> ApprovalRequest: ...

    def get_request(self, approval_id: str) -> ApprovalRequest: ...

    def list_requests(self) -> list[ApprovalRequest]: ...

    def approve(self, approval_id: str) -> tuple[ApprovalRequest, dict[str, object]]: ...

    def reject(self, approval_id: str) -> ApprovalRequest: ...

    def requires_move_approval(self, source_path: str, target_path: str, overwrite: bool) -> bool: ...

    def requires_delete_approval(self, path: str, recursive: bool) -> bool: ...


class PreferenceStorePort(Protocol):
    def load(self) -> UserPreference: ...

    def save(self, updates: dict[str, str | None]) -> UserPreference: ...


class LLMSettingsStorePort(Protocol):
    def load(self) -> LLMSettings: ...

    def save(self, updates: dict[str, str | float | None]) -> LLMSettings: ...


class WorkspaceMemoryStorePort(Protocol):
    def list_records(self, *, include_inactive: bool = False) -> list[WorkspaceMemoryRecord]: ...

    def upsert_record(self, record: WorkspaceMemoryRecord) -> WorkspaceMemoryRecord: ...

    def search_records(self, query: str, *, limit: int = 5) -> list[WorkspaceMemoryRecord]: ...


class MemoryCandidateStorePort(Protocol):
    def list_candidates(self, conversation_id: str, *, include_resolved: bool = False) -> list[MemoryCandidate]: ...

    def create_candidates(self, conversation_id: str, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]: ...

    def update_candidate_status(
        self,
        conversation_id: str,
        candidate_id: str,
        *,
        status: str,
    ) -> MemoryCandidate: ...


class ConversationCheckpointStorePort(Protocol):
    def create_checkpoint(
        self,
        *,
        conversation_id: str,
        label: str,
        summary: str,
        token_estimate: int,
        active_note_path: str | None,
    ) -> ConversationCheckpoint: ...

    def list_checkpoints(self, conversation_id: str) -> list[ConversationCheckpoint]: ...


class SkillStorePort(Protocol):
    def list_skills(
        self,
        *,
        include_disabled: bool = False,
        include_content: bool = False,
    ) -> list[SkillDefinition]: ...

    def get_skill(self, skill_id: str) -> SkillDefinition | None: ...

    def upsert_skill(self, skill: SkillDefinition) -> SkillDefinition: ...

    def delete_skill(self, skill_id: str) -> None: ...


class MCPServerStorePort(Protocol):
    def list_servers(self, *, include_disabled: bool = False) -> list[MCPServerDefinition]: ...

    def upsert_server(self, server: MCPServerDefinition) -> MCPServerDefinition: ...

    def delete_server(self, server_id: str) -> None: ...
