"""对话存储。

`ConversationStore` 把每个对话存成 `.more/sessions/<id>.json`（元数据 +
摘要 + 压缩 state + memory slots）+ `.more/sessions/<id>.jsonl`（消息
流）两份文件。所有变更（追加消息、改标题、改摘要、压缩等）都通过
`locked_path` 串行化，避免多并发 turn 竞态；`list_conversations` 会跳过
损坏的元数据文件并 warning。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from ..domain import Conversation, Message, utc_now_iso
from ..infrastructure.file_lock import locked_path
from ..workspace_fs import WorkspaceFS

logger = logging.getLogger(__name__)


class ConversationStore:
    def __init__(self, fs: WorkspaceFS) -> None:
        self.fs = fs
        self.sessions_root = self.fs.sidecar_root / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def create_conversation(self, title: str | None = None) -> Conversation:
        created_at = utc_now_iso()
        conversation = Conversation(
            id=uuid4().hex[:12],
            title=(title or "New Conversation").strip() or "New Conversation",
            created_at=created_at,
            updated_at=created_at,
        )
        messages_path = self._messages_path(conversation.id)
        self._write_metadata(conversation)
        with locked_path(messages_path):
            messages_path.write_text("", encoding="utf-8")
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation:
        path = self._metadata_path(conversation_id)
        if not path.exists():
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")
        with locked_path(path):
            payload = json.loads(path.read_text(encoding="utf-8"))
        return self._coerce_conversation(payload)

    def list_conversations(self, *, include_archived: bool = False) -> list[Conversation]:
        conversations: list[Conversation] = []
        for metadata_path in self.sessions_root.glob("*.json"):
            try:
                with locked_path(metadata_path):
                    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
                conversation = self._coerce_conversation(payload)
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Skipping corrupt conversation metadata %s: %s", metadata_path.name, exc)
                continue
            if not include_archived and conversation.status == "archived":
                continue
            conversations.append(conversation)
        conversations.sort(
            key=lambda conversation: conversation.updated_at or conversation.created_at,
            reverse=True,
        )
        return conversations

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation:
        metadata_path = self._metadata_path(conversation_id)
        with locked_path(metadata_path):
            conversation = self.get_conversation(conversation_id)
            updated = replace(
                conversation,
                title=title.strip() or conversation.title,
                updated_at=utc_now_iso(),
            )
            self._write_metadata(updated)
        return updated

    def archive_conversation(self, conversation_id: str) -> Conversation:
        metadata_path = self._metadata_path(conversation_id)
        with locked_path(metadata_path):
            conversation = self.get_conversation(conversation_id)
            archived_at = utc_now_iso()
            updated = replace(
                conversation,
                status="archived",
                archived_at=archived_at,
                updated_at=archived_at,
            )
            self._write_metadata(updated)
        return updated

    def resume_conversation(self, conversation_id: str) -> Conversation:
        metadata_path = self._metadata_path(conversation_id)
        with locked_path(metadata_path):
            conversation = self.get_conversation(conversation_id)
            updated = replace(
                conversation,
                status="active",
                archived_at=None,
                updated_at=utc_now_iso(),
            )
            self._write_metadata(updated)
        return updated

    def update_context(
        self,
        conversation_id: str,
        *,
        active_note_path: str | None = None,
        summary: str | None = None,
        compacted_token_estimate: int | None = None,
        compression_state: str | None = None,
        compression_count: int | None = None,
        last_compacted_at: str | None = None,
        labels: list[str] | None = None,
        pinned: bool | None = None,
    ) -> Conversation:
        metadata_path = self._metadata_path(conversation_id)
        with locked_path(metadata_path):
            conversation = self.get_conversation(conversation_id)
            patch: dict[str, object] = {"updated_at": utc_now_iso()}
            if active_note_path is not None:
                patch["active_note_path"] = active_note_path
            if summary is not None:
                patch["summary"] = summary.strip()
            if compacted_token_estimate is not None:
                patch["compacted_token_estimate"] = compacted_token_estimate
            if compression_state is not None:
                patch["compression_state"] = compression_state
            if compression_count is not None:
                patch["compression_count"] = compression_count
            if last_compacted_at is not None:
                patch["last_compacted_at"] = last_compacted_at
            if labels is not None:
                patch["labels"] = sorted({label.strip() for label in labels if label.strip()})
            if pinned is not None:
                patch["pinned"] = bool(pinned)
            updated = replace(conversation, **patch)
            self._write_metadata(updated)
        return updated

    def append_message(self, conversation_id: str, message: Message) -> None:
        metadata_path = self._metadata_path(conversation_id)
        messages_path = self._messages_path(conversation_id)
        # Hold metadata lock across the full RMW so concurrent appends cannot lose updates.
        with locked_path(metadata_path):
            conversation = self.get_conversation(conversation_id)
            with locked_path(messages_path):
                with messages_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(asdict(message), ensure_ascii=False) + "\n")
            added_tokens = self._estimate_tokens(message.content)
            new_token_estimate = conversation.token_estimate + added_tokens
            updated = replace(
                conversation,
                updated_at=message.created_at or utc_now_iso(),
                token_estimate=new_token_estimate,
                compression_state=self._compression_state_for_tokens(
                    new_token_estimate,
                    conversation.compacted_token_estimate,
                ),
            )
            self._write_metadata(updated)

    def list_messages(self, conversation_id: str) -> list[Message]:
        self.get_conversation(conversation_id)
        path = self._messages_path(conversation_id)
        if not path.exists():
            return []
        with locked_path(path):
            lines = path.read_text(encoding="utf-8").splitlines()
        messages: list[Message] = []
        for line in lines:
            if not line.strip():
                continue
            messages.append(Message(**json.loads(line)))
        return messages

    def _metadata_path(self, conversation_id: str) -> Path:
        return self.sessions_root / f"{conversation_id}.json"

    def _messages_path(self, conversation_id: str) -> Path:
        return self.sessions_root / f"{conversation_id}.jsonl"

    def _write_metadata(self, conversation: Conversation) -> None:
        metadata_path = self._metadata_path(conversation.id)
        with locked_path(metadata_path):
            metadata_path.write_text(
                json.dumps(asdict(conversation), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _coerce_conversation(self, payload: dict[str, object]) -> Conversation:
        conversation_id = payload.get("id")
        if not conversation_id:
            raise ValueError("Conversation payload missing 'id'")
        created_at = str(payload.get("created_at") or utc_now_iso())
        updated_at = str(payload.get("updated_at") or created_at)
        status = str(payload.get("status") or "active")
        archived_at = payload.get("archived_at")
        active_note_path = payload.get("active_note_path")
        summary = str(payload.get("summary") or "")
        token_estimate = int(payload.get("token_estimate") or 0)
        compacted_token_estimate = int(payload.get("compacted_token_estimate") or 0)
        compression_state = str(
            payload.get("compression_state")
            or self._compression_state_for_tokens(token_estimate, compacted_token_estimate)
        )
        compression_count = int(payload.get("compression_count") or 0)
        last_compacted_at = payload.get("last_compacted_at")
        labels = payload.get("labels") if isinstance(payload.get("labels"), list) else []
        pinned = bool(payload.get("pinned") or False)
        return Conversation(
            id=str(conversation_id),
            title=str(payload.get("title") or "New Conversation"),
            created_at=created_at,
            updated_at=updated_at,
            status=status,
            archived_at=str(archived_at) if archived_at else None,
            active_note_path=str(active_note_path) if active_note_path else None,
            summary=summary,
            token_estimate=token_estimate,
            compacted_token_estimate=compacted_token_estimate,
            compression_state=compression_state,
            compression_count=compression_count,
            last_compacted_at=str(last_compacted_at) if last_compacted_at else None,
            labels=[str(label).strip() for label in labels if str(label).strip()],
            pinned=pinned,
        )

    def _estimate_tokens(self, content: str) -> int:
        normalized = content.strip()
        if not normalized:
            return 0
        return max(1, len(normalized) // 4)

    def _compression_state_for_tokens(self, token_estimate: int, compacted_token_estimate: int) -> str:
        pending_tokens = max(0, token_estimate - compacted_token_estimate)
        if pending_tokens >= 2400:
            return "force"
        if pending_tokens >= 1800:
            return "compact"
        if pending_tokens >= 1200:
            return "warning"
        return "ok"
