"""业务服务层聚合导出。

为方便 `api/deps.py` 一次性拿到所有 service 类型，这里集中转发；注意
这里也从 `app.ingest` / `app.search` 等顶层模块 re-export 关键类，统一
`from app.services import X` 的调用体验。
"""

from ..ingest import IngestError, IngestService
from ..notes import NoteError, NoteFormatError, NoteService
from .answering import AnswerGeneration, AnswerRequest, AnswerService
from .context_packing import ContextPack, ContextPackingPolicy
from .conversations import CompressionPolicyResult, CompressionSummaryInput, ConversationCompressionService, ConversationSummaryStrategy
from ..mcp.service import MCPService
from ..skills.service import SkillService
from .memory import MemoryError, MemoryService
from .memory_extraction import MemoryExtractionInput, MemoryExtractionService
from .run_scope import RunScope, RunScopeService
from .search import FileSearchIndex, SearchError, SearchIndex, SearchService
from .turn_context import PreparedTurnContext, TurnContextService, TurnPreflight
from .turn_state import TurnState, TurnStateService
from .retrieval import (
    EmbeddingProvider,
    EmbeddingRetrievalService,
    FastEmbedProvider,
    HashEmbeddingBackend,
    HybridRetrievalService,
    LexicalRetrievalService,
    ReciprocalRankFusionRanker,
    RetrievalRanker,
    RetrievalService,
    build_embedding_provider,
    build_default_retrieval_service,
)

__all__ = [
    "AnswerGeneration",
    "AnswerRequest",
    "AnswerService",
    "CompressionPolicyResult",
    "CompressionSummaryInput",
    "ConversationCompressionService",
    "ConversationSummaryStrategy",
    "ContextPack",
    "ContextPackingPolicy",
    "FileSearchIndex",
    "IngestError",
    "IngestService",
    "MemoryError",
    "MemoryExtractionInput",
    "MemoryExtractionService",
    "MemoryService",
    "MCPService",
    "NoteError",
    "NoteFormatError",
    "NoteService",
    "EmbeddingRetrievalService",
    "EmbeddingProvider",
    "FastEmbedProvider",
    "HashEmbeddingBackend",
    "HybridRetrievalService",
    "LexicalRetrievalService",
    "ReciprocalRankFusionRanker",
    "RunScope",
    "RunScopeService",
    "SearchError",
    "SearchIndex",
    "SearchService",
    "SkillService",
    "PreparedTurnContext",
    "TurnContextService",
    "TurnPreflight",
    "TurnState",
    "TurnStateService",
    "build_embedding_provider",
    "RetrievalRanker",
    "RetrievalService",
    "build_default_retrieval_service",
]
