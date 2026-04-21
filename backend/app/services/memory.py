"""记忆上下文组装。

`MemoryService.build_context` 根据当前 note + query 组合出一份
`MemoryContext`（偏好、active note meta、相关检索命中、工作区记忆
记录、线程 memory slots）；`get_preferences / update_preferences`
透传偏好读写。
"""

from __future__ import annotations

from dataclasses import asdict

from ..domain import MemoryContext, UserPreference
from ..notes import NoteError, NoteService
from ..observability_langfuse import observe
from ..prompts.project_context import load_project_context
from ..stores import PreferenceStorePort, WorkspaceMemoryStorePort
from ..stores.preferences import PreferenceStore
from ..stores.workspace_memory import WorkspaceMemoryStore
from ..workspace_fs import WorkspaceError, WorkspaceFS, WorkspaceTextError
from .retrieval import RetrievalService, build_default_retrieval_service


class MemoryError(Exception):
    """Base error for memory operations."""


class MemoryService:
    def __init__(
        self,
        fs: WorkspaceFS,
        note_service: NoteService | None = None,
        search_service: RetrievalService | None = None,
        preference_store: PreferenceStorePort | None = None,
        workspace_memory_store: WorkspaceMemoryStorePort | None = None,
    ) -> None:
        self.fs = fs
        self.note_service = note_service or NoteService(fs)
        self.retrieval_service = search_service or build_default_retrieval_service(fs, note_service=self.note_service)
        self.preference_store = preference_store or PreferenceStore(fs)
        self.workspace_memory_store = workspace_memory_store or WorkspaceMemoryStore(fs)

    def get_preferences(self) -> UserPreference:
        return self.preference_store.load()

    def update_preferences(
        self,
        *,
        language: str | None = None,
        answer_style: str | None = None,
        default_note_dir: str | None = None,
        theme: str | None = None,
    ) -> UserPreference:
        try:
            return self.preference_store.save(
                {
                    "language": language,
                    "answer_style": answer_style,
                    "default_note_dir": default_note_dir,
                    "theme": theme,
                }
            )
        except ValueError as exc:
            raise MemoryError(str(exc)) from exc

    @observe(name="memory.build_context")
    def build_context(
        self,
        *,
        current_note_path: str | None = None,
        query: str | None = None,
        limit: int = 5,
    ) -> MemoryContext:
        current_note = None
        if current_note_path:
            try:
                current_note = self.note_service.get_note(current_note_path).meta
            except (FileNotFoundError, NoteError, WorkspaceError, WorkspaceTextError, UnicodeDecodeError):
                current_note = None

        related_hits = []
        normalized_query = (query or "").strip()
        if normalized_query:
            related_hits = self.retrieval_service.retrieve(normalized_query, limit=limit)

        workspace_memory = self.workspace_memory_store.search_records(normalized_query, limit=limit) if normalized_query else []
        thread_memory: dict[str, object] = {}
        if current_note is not None:
            thread_memory["active_note_path"] = current_note.relative_path
            thread_memory["active_note_tags"] = list(current_note.tags)

        project_context_entries = load_project_context(self.fs, current_note_path=current_note_path)
        if project_context_entries:
            thread_memory["project_context"] = [asdict(entry) for entry in project_context_entries]

        preferences = self.get_preferences()
        return MemoryContext(
            preferences=preferences,
            current_note=current_note,
            related_hits=related_hits,
            profile_memory=preferences,
            workspace_memory=workspace_memory,
            thread_memory=thread_memory,
        )


__all__ = ["MemoryError", "MemoryService"]
