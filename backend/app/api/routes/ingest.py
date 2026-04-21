"""导入端点。

暴露 `POST /api/ingest/file` 和 `POST /api/ingest/url`，转发到
`IngestService`；成功后同步触发搜索索引 refresh。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from ...ingest import IngestService
from ...services.search import SearchService
from ..deps import get_ingest_service, get_search_service
from ..schemas import ImportFileRequest, ImportUrlRequest

router = APIRouter(prefix="/api/imports")


@router.post("/file")
def import_file(
    request: ImportFileRequest,
    ingest_service: IngestService = Depends(get_ingest_service),
    search_service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    job, note = ingest_service.import_file(
        request.source_path,
        destination_dir=request.destination_dir,
        title=request.title,
        tags=request.tags,
        summary=request.summary,
    )
    search_status = search_service.rebuild()
    return {"job": asdict(job), "note": asdict(note), "search_status": asdict(search_status)}


@router.post("/url")
def import_url(
    request: ImportUrlRequest,
    ingest_service: IngestService = Depends(get_ingest_service),
    search_service: SearchService = Depends(get_search_service),
) -> dict[str, object]:
    job, note = ingest_service.import_url(
        request.url,
        destination_dir=request.destination_dir,
        title=request.title,
        tags=request.tags,
        summary=request.summary,
    )
    search_status = search_service.rebuild()
    return {"job": asdict(job), "note": asdict(note), "search_status": asdict(search_status)}
