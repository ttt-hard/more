"""搜索索引适配器。

`SearchIndex` Protocol 要求 rebuild / refresh / search / retrieve 四个
方法；`FileSearchIndex` 是一层轻适配，让 `SearchService` 满足
`SearchIndex` / `RetrievalService` 双接口，供 DI 组合给 memory 服务使用。
"""

from __future__ import annotations

from typing import Protocol

from ..domain import SearchHit, SearchIndexStatus
from ..search import SearchError, SearchService
from .retrieval import RetrievalService


class SearchIndex(RetrievalService, Protocol):
    def rebuild(self) -> SearchIndexStatus: ...
    def refresh(self, paths: list[str] | None = None) -> SearchIndexStatus: ...

    def search(self, query: str, limit: int = 10) -> list[SearchHit]: ...


class FileSearchIndex(SearchIndex):
    def __init__(self, service: SearchService) -> None:
        self.service = service

    def rebuild(self) -> SearchIndexStatus:
        return self.service.rebuild()

    def refresh(self, paths: list[str] | None = None) -> SearchIndexStatus:
        return self.service.refresh(paths)

    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]:
        return self.service.retrieve(query, limit=limit)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        return self.service.search(query, limit=limit)


__all__ = ["FileSearchIndex", "RetrievalService", "SearchError", "SearchIndex", "SearchService"]
