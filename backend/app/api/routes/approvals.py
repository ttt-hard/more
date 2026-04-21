"""审批请求端点。

提供 `GET /api/approvals`（列表）、`POST .../{id}/approve` 和
`POST .../{id}/reject`。审批对应 agent 工具里 approval-gated 的动作
（move / delete）。只转发到 `ApprovalStore`。
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from ...stores.approvals import ApprovalStore
from ..deps import get_approval_store
from ..schemas import ApprovalDecisionRequest

router = APIRouter(prefix="/api/approvals")


@router.get("")
def list_approvals(approval_store: ApprovalStore = Depends(get_approval_store)) -> dict[str, object]:
    return {"approvals": [asdict(approval) for approval in approval_store.list_requests()]}


@router.post("/{approval_id}/approve")
def approve_request(
    approval_id: str,
    _: ApprovalDecisionRequest | None = None,
    approval_store: ApprovalStore = Depends(get_approval_store),
) -> dict[str, object]:
    approval, result = approval_store.approve(approval_id)
    return {"approval": asdict(approval), "result": result}


@router.post("/{approval_id}/reject")
def reject_request(
    approval_id: str,
    _: ApprovalDecisionRequest | None = None,
    approval_store: ApprovalStore = Depends(get_approval_store),
) -> dict[str, object]:
    approval = approval_store.reject(approval_id)
    return {"approval": asdict(approval)}
