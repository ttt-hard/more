"""笔记端点。

笔记 CRUD + 元数据补丁，走 `NoteService`；每次成功的写入都会同步刷新
搜索索引，确保随后的搜索能命中最新内容。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from ...notes import NoteService
from ..deps import get_note_service
from ..schemas import CreateNoteRequest, UpdateNoteRequest

router = APIRouter(prefix="/api/notes")


@router.get("")
def list_notes(path: str = "", note_service: NoteService = Depends(get_note_service)) -> dict[str, object]:
    return {"notes": [asdict(note) for note in note_service.list_notes(path)]}


@router.get("/{path:path}")
def get_note(path: str, note_service: NoteService = Depends(get_note_service)) -> dict[str, object]:
    return {"note": asdict(note_service.get_note(path))}


@router.post("")
def create_note(request: CreateNoteRequest, note_service: NoteService = Depends(get_note_service)) -> dict[str, object]:
    note = note_service.create_note(
        relative_path=request.path,
        content=request.content,
        title=request.title,
        tags=request.tags,
        summary=request.summary,
        related=request.related,
        source_type=request.source_type,
    )
    return {"note": asdict(note)}


@router.put("/{path:path}")
def update_note(
    path: str,
    request: UpdateNoteRequest,
    note_service: NoteService = Depends(get_note_service),
) -> dict[str, object]:
    note = note_service.update_note(
        relative_path=path,
        content=request.content,
        title=request.title,
        tags=request.tags,
        summary=request.summary,
        related=request.related,
        source_type=request.source_type,
    )
    return {"note": asdict(note)}
