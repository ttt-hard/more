"""搜索端点。

`GET /api/search?q=...` 走 lexical，`POST /api/search/rebuild` 触发索引
重建。索引重建是 IO 密集，但用 `locked_path` 保护并发一致性。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from ...services.search import FileSearchIndex, SearchService
from ..deps import get_search_index, get_search_service
from ..schemas import RebuildSearchRequest

router = APIRouter(prefix="/api/search")


@router.get("")
def search(
    query: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    search_service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    return {"hits": [asdict(hit) for hit in search_service.search(query, limit=limit)]}


@router.post("/rebuild")
def rebuild_search_index(
    _: RebuildSearchRequest | None = None,
    search_index: FileSearchIndex = Depends(get_search_index),
) -> dict[str, object]:
    status = search_index.rebuild()
    return {"status": asdict(status)}
