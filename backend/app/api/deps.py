"""FastAPI 依赖注入中心。

单例 `AppState` 保存当前激活的 `WorkspaceFS`（由 `/api/workspace/activate`
端点设置）；`get_*` 系列函数构造所有 service / store，组装 coordinator。
所有路由都通过 `Depends(get_xxx)` 拿依赖，保证请求范围内的实例化一致。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from ..agent import SingleAgentCoordinator, build_default_tool_registry
from ..infrastructure.watcher import NoopWorkspaceWatcher, WorkspaceWatcher
from ..ingest import IngestService
from ..llm import LLMService
from ..notes import NoteService
from ..providers import LiteLLMProvider, ModelProvider
from ..services.context_packing import ContextPackingPolicy
from ..services.conversations import ConversationCompressionService
from ..mcp.service import MCPService
from ..services.memory import MemoryService
from ..services.memory_extraction import MemoryExtractionService
from ..services.search import FileSearchIndex, SearchService
from ..skills.service import SkillService
from ..stores.approvals import ApprovalStore
from ..stores.checkpoints import ConversationCheckpointStore
from ..stores.conversations import ConversationStore
from ..stores.mcp_servers import MCPServerStore
from ..stores.memory_candidates import MemoryCandidateStore
from ..stores.preferences import LLMSettingsStore
from ..stores.skills import SkillStore
from ..stores.tasks import TaskStore
from ..stores.workspace_memory import WorkspaceMemoryStore
from ..workspace_fs import WorkspaceFS


class AppState:
    def __init__(self) -> None:
        self.workspace_fs: WorkspaceFS | None = None

    def require_workspace(self) -> WorkspaceFS:
        if self.workspace_fs is None:
            raise HTTPException(status_code=400, detail="No active workspace")
        return self.workspace_fs


state = AppState()


def get_workspace_fs() -> WorkspaceFS:
    return state.require_workspace()


def get_note_service(fs: WorkspaceFS = Depends(get_workspace_fs)) -> NoteService:
    return NoteService(fs)


def get_search_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
) -> SearchService:
    return SearchService(fs)


def get_search_index(search_service: SearchService = Depends(get_search_service)) -> FileSearchIndex:
    return FileSearchIndex(search_service)


def get_workspace_memory_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> WorkspaceMemoryStore:
    return WorkspaceMemoryStore(fs)


def get_memory_candidate_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> MemoryCandidateStore:
    return MemoryCandidateStore(fs)


def get_checkpoint_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> ConversationCheckpointStore:
    return ConversationCheckpointStore(fs)


def get_memory_extraction_service() -> MemoryExtractionService:
    return MemoryExtractionService()


def get_context_packing_policy() -> ContextPackingPolicy:
    return ContextPackingPolicy()


def get_skill_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> SkillStore:
    return SkillStore(fs)


def get_skill_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
    skill_store: SkillStore = Depends(get_skill_store),
) -> SkillService:
    return SkillService(fs, skill_store=skill_store)


def get_mcp_server_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> MCPServerStore:
    return MCPServerStore(fs)


def get_mcp_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
    server_store: MCPServerStore = Depends(get_mcp_server_store),
) -> MCPService:
    return MCPService(fs, server_store=server_store)


def get_memory_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
    note_service: NoteService = Depends(get_note_service),
    workspace_memory_store: WorkspaceMemoryStore = Depends(get_workspace_memory_store),
) -> MemoryService:
    return MemoryService(fs, note_service=note_service, workspace_memory_store=workspace_memory_store)


def get_ingest_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
) -> IngestService:
    return IngestService(fs)


def get_provider() -> ModelProvider:
    return LiteLLMProvider()


def get_workspace_watcher() -> WorkspaceWatcher:
    return NoopWorkspaceWatcher()


def get_llm_service(
    fs: WorkspaceFS = Depends(get_workspace_fs),
    provider: ModelProvider = Depends(get_provider),
) -> LLMService:
    return LLMService(settings=LLMSettingsStore(fs).load(), provider=provider)


def get_approval_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> ApprovalStore:
    return ApprovalStore(fs)


def get_conversation_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> ConversationStore:
    return ConversationStore(fs)


def get_conversation_compression_service(
    conversation_store: ConversationStore = Depends(get_conversation_store),
    note_service: NoteService = Depends(get_note_service),
    workspace_memory_store: WorkspaceMemoryStore = Depends(get_workspace_memory_store),
    checkpoint_store: ConversationCheckpointStore = Depends(get_checkpoint_store),
) -> ConversationCompressionService:
    return ConversationCompressionService(
        conversation_store,
        note_service=note_service,
        workspace_memory_store=workspace_memory_store,
        checkpoint_store=checkpoint_store,
    )


def get_task_store(fs: WorkspaceFS = Depends(get_workspace_fs)) -> TaskStore:
    return TaskStore(fs)


def get_tool_registry(
    mcp_service: MCPService = Depends(get_mcp_service),
):
    return build_default_tool_registry(mcp_service=mcp_service)


def get_agent_coordinator(
    fs: WorkspaceFS = Depends(get_workspace_fs),
    note_service: NoteService = Depends(get_note_service),
    search_service: SearchService = Depends(get_search_service),
    ingest_service: IngestService = Depends(get_ingest_service),
    memory_service: MemoryService = Depends(get_memory_service),
    llm_service: LLMService = Depends(get_llm_service),
    conversation_store: ConversationStore = Depends(get_conversation_store),
    compression_service: ConversationCompressionService = Depends(get_conversation_compression_service),
    workspace_memory_store: WorkspaceMemoryStore = Depends(get_workspace_memory_store),
    memory_candidate_store: MemoryCandidateStore = Depends(get_memory_candidate_store),
    memory_extraction_service: MemoryExtractionService = Depends(get_memory_extraction_service),
    context_packing_policy: ContextPackingPolicy = Depends(get_context_packing_policy),
    skill_service: SkillService = Depends(get_skill_service),
    mcp_service: MCPService = Depends(get_mcp_service),
    checkpoint_store: ConversationCheckpointStore = Depends(get_checkpoint_store),
    task_store: TaskStore = Depends(get_task_store),
    tool_registry=Depends(get_tool_registry),
):
    return SingleAgentCoordinator(
        fs,
        note_service=note_service,
        search_service=search_service,
        ingest_service=ingest_service,
        memory_service=memory_service,
        llm_service=llm_service,
        conversation_store=conversation_store,
        task_store=task_store,
        tool_registry=tool_registry,
        compression_service=compression_service,
        workspace_memory_store=workspace_memory_store,
        memory_candidate_store=memory_candidate_store,
        memory_extraction_service=memory_extraction_service,
        context_packing_policy=context_packing_policy,
        skill_service=skill_service,
        mcp_service=mcp_service,
        checkpoint_store=checkpoint_store,
    )
