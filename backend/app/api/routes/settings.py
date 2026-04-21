"""LLM 设置端点。

读 / 写 `LLMSettings`（base_url / api_key / model / timeout），api_key 返回时
会做前缀预览脱敏。`test_connection` 端点实际发一次 ping 探活。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...llm import LLMService
from ...stores.preferences import LLMSettingsStore
from ...workspace_fs import WorkspaceFS
from ..deps import get_llm_service, get_workspace_fs
from ..schemas import UpdateLLMSettingsRequest

router = APIRouter(prefix="/api/settings")


def _serialize_settings(service: LLMService) -> dict[str, object]:
    api_key_preview = ""
    if len(service.api_key) >= 8:
        api_key_preview = service.api_key[:4] + "****" + service.api_key[-4:]
    elif service.api_key:
        api_key_preview = "****"
    return {
        "base_url": service.base_url,
        "api_key_set": bool(service.api_key),
        "api_key_preview": api_key_preview,
        "model": service.model,
        "timeout": service.timeout,
        "is_configured": service.is_configured(),
    }


@router.get("/llm")
def get_llm_settings(llm_service: LLMService = Depends(get_llm_service)) -> dict[str, object]:
    return {"settings": _serialize_settings(llm_service)}


@router.put("/llm")
def update_llm_settings(
    request: UpdateLLMSettingsRequest,
    fs: WorkspaceFS = Depends(get_workspace_fs),
) -> dict[str, object]:
    store = LLMSettingsStore(fs)
    settings = store.save(
        {
            "base_url": request.base_url,
            "api_key": request.api_key,
            "model": request.model,
            "timeout": request.timeout,
        }
    )
    return {"settings": _serialize_settings(LLMService(settings=settings))}


@router.post("/llm/test")
def test_llm_connection(llm_service: LLMService = Depends(get_llm_service)) -> dict[str, object]:
    return {"result": llm_service.test_connection()}
