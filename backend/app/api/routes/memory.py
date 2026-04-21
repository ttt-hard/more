"""记忆 / 偏好端点。

暴露 `UserPreference` 的读写和 `WorkspaceMemoryRecord` 的列 / 搜，
底层是 `MemoryService` + `PreferenceStore` + `WorkspaceMemoryStore`。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ...services.memory import MemoryService
from ..deps import get_memory_service
from ..schemas import UpdatePreferencesRequest

router = APIRouter(prefix="/api")


@router.get("/preferences")
def get_preferences(memory_service: MemoryService = Depends(get_memory_service)) -> dict[str, object]:
    return {"preferences": asdict(memory_service.get_preferences())}


@router.put("/preferences")
def update_preferences(
    request: UpdatePreferencesRequest,
    memory_service: MemoryService = Depends(get_memory_service),
) -> dict[str, object]:
    preferences = memory_service.update_preferences(
        language=request.language,
        answer_style=request.answer_style,
        default_note_dir=request.default_note_dir,
        theme=request.theme,
    )
    return {"preferences": asdict(preferences)}


@router.get("/memory/context")
def get_memory_context(
    current_note_path: str | None = None,
    query: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    memory_service: MemoryService = Depends(get_memory_service),
) -> dict[str, object]:
    context = memory_service.build_context(
        current_note_path=current_note_path,
        query=query,
        limit=limit,
    )
    return {
        "context": {
            "preferences": asdict(context.preferences),
            "profile_memory": asdict(context.profile_memory) if context.profile_memory else None,
            "current_note": asdict(context.current_note) if context.current_note else None,
            "related_hits": [asdict(hit) for hit in context.related_hits],
            "workspace_memory": [asdict(record) for record in context.workspace_memory],
            "thread_memory": context.thread_memory,
        }
    }
