"""本地全文检索索引。

`SearchService` 遍历工作区可读文本文件，按标题 / 段落 / token 切成 chunks，
建立 `manifest.json` + `inverted_index.json` + `chunks.json` 三份侧车文件
（`.more/index/`），支持按 token 打分的 lexical 搜索和增量 refresh。index
读写统一用 `locked_path(index_root)` 串行化，避免并发读到半写 JSON。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .domain import SearchHit, SearchIndexStatus, utc_now_iso
from .infrastructure.file_lock import locked_path
from .notes import NoteError, NoteFormatError, NoteService
from .workspace_fs import WorkspaceFS, WorkspaceTextError

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}")
CHUNK_MIN_TOKENS = 400
CHUNK_MAX_TOKENS = 700
CHUNK_OVERLAP_TOKENS = 60
TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
}


class SearchError(Exception):
    """Base error for search operations."""


class SearchService:
    def __init__(self, fs: WorkspaceFS, note_service: NoteService | None = None) -> None:
        self.fs = fs
        self.note_service = note_service or NoteService(fs)
        self.index_root = self.fs.sidecar_root / "index"
        self.manifest_path = self.index_root / "manifest.json"
        self.inverted_index_path = self.index_root / "inverted_index.json"
        self.chunks_path = self.index_root / "chunks.json"

    def rebuild(self) -> SearchIndexStatus:
        return self.refresh()

    def refresh(self, paths: list[str] | None = None) -> SearchIndexStatus:
        self.index_root.mkdir(parents=True, exist_ok=True)

        # Hold the index-root lock across the full rebuild so concurrent search
        # readers never observe partially written JSON files.
        with locked_path(self.index_root):
            if not paths:
                manifest, chunks = self._build_full_index()
            else:
                manifest, chunks = self._load_or_rebuild_structures_unlocked()
                manifest_by_path = {
                    str(entry["path"]): entry
                    for entry in manifest
                }
                chunks = [chunk for chunk in chunks if str(chunk["path"]) not in set(paths)]
                for path in paths:
                    manifest_by_path.pop(path, None)
                    manifest_entry, new_chunks = self._build_document_index(path)
                    if manifest_entry is not None:
                        manifest_by_path[path] = manifest_entry
                        chunks.extend(new_chunks)
                manifest = sorted(manifest_by_path.values(), key=lambda item: str(item["path"]).lower())

            chunks, inverted_index = self._reindex_chunks(chunks)
            built_at = utc_now_iso()
            self.manifest_path.write_text(
                json.dumps(
                    {
                        "built_at": built_at,
                        "files": manifest,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.inverted_index_path.write_text(
                json.dumps(inverted_index, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.chunks_path.write_text(
                json.dumps(chunks, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        return SearchIndexStatus(
            indexed_files=len(manifest),
            indexed_chunks=len(chunks),
            built_at=built_at,
            manifest_path=str(self.manifest_path),
            inverted_index_path=str(self.inverted_index_path),
            chunks_path=str(self.chunks_path),
        )

    def retrieve(self, query: str, limit: int = 10) -> list[SearchHit]:
        return self.search(query, limit=limit)

    def load_indexed_chunks(self) -> list[dict[str, object]]:
        _, _, chunks = self._load_or_rebuild_index()
        return list(chunks)

    def search(self, query: str, limit: int = 10) -> list[SearchHit]:
        if not query.strip():
            return []
        manifest, inverted_index, chunks = self._load_or_rebuild_index()
        del manifest

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        candidate_ids: set[int] = set()
        for token in query_tokens:
            candidate_ids.update(inverted_index.get(token, []))

        scored_by_path: dict[str, SearchHit] = {}
        for chunk_id in candidate_ids:
            chunk = chunks[chunk_id]
            score = self._score_chunk(chunk, query_tokens)
            if score <= 0:
                continue
            snippet = self._make_snippet(chunk["text"], query_tokens)
            hit = SearchHit(
                path=str(chunk["path"]),
                kind=str(chunk["kind"]),
                title=str(chunk["title"]),
                score=score,
                snippet=snippet,
                chunk_id="" if chunk.get("chunk_id") is None else str(chunk.get("chunk_id")),
                section=str(chunk.get("section") or ""),
                token_count=int(chunk.get("token_count") or 0),
                start_offset=int(chunk.get("start_offset") or 0),
            )
            existing = scored_by_path.get(hit.path)
            if existing is None or hit.score > existing.score:
                scored_by_path[hit.path] = hit

        return sorted(
            scored_by_path.values(),
            key=lambda hit: (-hit.score, hit.path),
        )[:limit]

    def _load_or_rebuild_index(self) -> tuple[dict[str, object], dict[str, list[int]], list[dict[str, object]]]:
        if not (self.manifest_path.exists() and self.inverted_index_path.exists() and self.chunks_path.exists()):
            self.rebuild()
        # Take the shared index lock so we do not observe a partially written set
        # of JSON files while refresh() is swapping them.
        with locked_path(self.index_root):
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            inverted_index = json.loads(self.inverted_index_path.read_text(encoding="utf-8"))
            chunks = json.loads(self.chunks_path.read_text(encoding="utf-8"))
        return manifest, inverted_index, chunks

    def _load_or_rebuild_structures_unlocked(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        # Caller (``refresh``) already holds ``locked_path(self.index_root)`` — the
        # lock is reentrant so a nested acquire is safe, but avoiding it keeps the
        # intent explicit.
        if not (self.manifest_path.exists() and self.inverted_index_path.exists() and self.chunks_path.exists()):
            return [], []
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        chunks = json.loads(self.chunks_path.read_text(encoding="utf-8"))
        return list(manifest.get("files", [])), list(chunks)

    def _build_full_index(self) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        manifest: list[dict[str, object]] = []
        chunks: list[dict[str, object]] = []
        for file_path in self.fs.iter_paths():
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(self.fs.root).as_posix()
            manifest_entry, document_chunks = self._build_document_index(rel_path)
            if manifest_entry is None:
                continue
            manifest.append(manifest_entry)
            chunks.extend(document_chunks)
        manifest.sort(key=lambda item: str(item["path"]).lower())
        return manifest, chunks

    def _build_document_index(
        self,
        relative_path: str,
    ) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
        path = self.fs.resolve_path(relative_path)
        if not path.exists() or not path.is_file():
            return None, []
        if path.suffix.lower() not in TEXT_SUFFIXES:
            return None, []
        try:
            document = self._read_search_document(relative_path)
        except (WorkspaceTextError, NoteError, NoteFormatError):
            return None, []
        if not str(document["content"]).strip() and document["kind"] != "note":
            return None, []

        stat = path.stat()
        manifest_entry = {
            "path": relative_path,
            "kind": document["kind"],
            "title": document["title"],
            "size": stat.st_size,
            "modified_at": stat.st_mtime,
        }

        chunks: list[dict[str, object]] = []
        for chunk in self._build_chunks(str(document["content"])):
            searchable_text = "\n".join(
                [
                    str(document["title"]),
                    " ".join(str(tag) for tag in document["tags"]),
                    str(document["summary"]),
                    str(chunk["text"]),
                ]
            ).strip()
            if not searchable_text:
                continue
            chunks.append(
                {
                    "path": relative_path,
                    "kind": document["kind"],
                    "title": document["title"],
                    "tags": document["tags"],
                    "summary": document["summary"],
                    "text": chunk["text"],
                    "section": chunk["section"],
                    "start_offset": chunk["start_offset"],
                    "token_count": chunk["token_count"],
                }
            )
        return manifest_entry, chunks

    def _reindex_chunks(
        self,
        chunks: list[dict[str, object]],
    ) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
        inverted_index: dict[str, list[int]] = defaultdict(list)
        reindexed_chunks: list[dict[str, object]] = []
        for chunk_id, chunk in enumerate(chunks):
            normalized_chunk = {**chunk, "chunk_id": chunk_id}
            reindexed_chunks.append(normalized_chunk)
            searchable_text = "\n".join(
                [
                    str(normalized_chunk["title"]),
                    " ".join(str(tag) for tag in normalized_chunk["tags"]),
                    str(normalized_chunk["summary"]),
                    str(normalized_chunk["text"]),
                ]
            ).strip()
            for token in sorted(set(self._tokenize(searchable_text))):
                inverted_index[token].append(chunk_id)
        return reindexed_chunks, dict(inverted_index)

    def _read_search_document(self, relative_path: str) -> dict[str, object]:
        suffix = Path(relative_path).suffix.lower()
        if suffix == ".md":
            note = self.note_service.get_note(relative_path)
            return {
                "kind": "note",
                "title": note.meta.title,
                "tags": note.meta.tags,
                "summary": note.meta.summary,
                "content": note.content,
            }
        content = self.fs.read_text(relative_path)
        return {
            "kind": "file",
            "title": Path(relative_path).name,
            "tags": [],
            "summary": "",
            "content": content,
        }

    def _build_chunks(self, content: str) -> list[dict[str, object]]:
        normalized = content.strip()
        if not normalized:
            return [{"text": "", "section": "", "start_offset": 0, "token_count": 0}]
        chunks: list[dict[str, object]] = []
        current_section = ""
        chunk_section = ""
        current_parts: list[str] = []
        current_tokens = 0
        chunk_start = 0
        overlap_prefix = ""

        for paragraph, start_offset in self._split_paragraphs(normalized):
            is_heading = paragraph.startswith("#")
            next_section = paragraph.lstrip("#").strip() if is_heading else current_section
            if is_heading and current_parts:
                chunk_text = "\n\n".join(part for part in current_parts if part).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "section": chunk_section or current_section,
                            "start_offset": chunk_start,
                            "token_count": len(self._tokenize(chunk_text)),
                        }
                    )
                current_parts = []
                current_tokens = 0
                overlap_prefix = ""
            paragraph_tokens = len(self._tokenize(paragraph))
            if not current_parts:
                chunk_start = start_offset
                chunk_section = next_section
                if overlap_prefix:
                    current_parts.append(overlap_prefix)
                    current_tokens = len(self._tokenize(overlap_prefix))
                    overlap_prefix = ""
            if current_tokens and current_tokens + paragraph_tokens > CHUNK_MAX_TOKENS and current_tokens >= CHUNK_MIN_TOKENS:
                chunk_text = "\n\n".join(part for part in current_parts if part).strip()
                if chunk_text:
                    chunks.append(
                        {
                            "text": chunk_text,
                            "section": chunk_section or current_section,
                            "start_offset": chunk_start,
                            "token_count": len(self._tokenize(chunk_text)),
                        }
                    )
                    overlap_prefix = self._overlap_tail(chunk_text)
                current_parts = []
                current_tokens = 0
                chunk_start = start_offset
                chunk_section = next_section
            current_parts.append(paragraph)
            current_tokens += paragraph_tokens
            if is_heading:
                current_section = next_section

        if current_parts:
            chunk_text = "\n\n".join(part for part in current_parts if part).strip()
            if chunk_text:
                chunks.append(
                    {
                        "text": chunk_text,
                        "section": chunk_section or current_section,
                        "start_offset": chunk_start,
                        "token_count": len(self._tokenize(chunk_text)),
                    }
                )
        return chunks

    def _split_paragraphs(self, text: str) -> list[tuple[str, int]]:
        paragraphs: list[tuple[str, int]] = []
        offset = 0
        for block in re.split(r"\n\s*\n", text):
            stripped = block.strip()
            if not stripped:
                offset += len(block) + 2
                continue
            start_offset = text.find(stripped, offset)
            if start_offset == -1:
                start_offset = offset
            paragraphs.append((stripped, start_offset))
            offset = start_offset + len(stripped)
        return paragraphs

    def _overlap_tail(self, text: str) -> str:
        tokens = self._tokenize(text)
        if len(tokens) <= CHUNK_OVERLAP_TOKENS:
            return text
        return " ".join(tokens[-CHUNK_OVERLAP_TOKENS:])

    def _tokenize(self, text: str) -> list[str]:
        return [match.group(0).casefold() for match in TOKEN_PATTERN.finditer(text)]

    def _score_chunk(self, chunk: dict[str, object], query_tokens: list[str]) -> float:
        title_text = str(chunk["title"]).casefold()
        body_text = str(chunk["text"]).casefold()
        summary_text = str(chunk["summary"]).casefold()
        tags_text = " ".join(str(tag).casefold() for tag in chunk["tags"])
        score = 0.0
        for token in query_tokens:
            if token in title_text:
                score += 6.0
            if token in tags_text:
                score += 4.0
            if token in summary_text:
                score += 2.5
            score += body_text.count(token)
        return score

    def _make_snippet(self, text: str, query_tokens: list[str]) -> str:
        lowered = text.casefold()
        first_index = min(
            (lowered.find(token) for token in query_tokens if lowered.find(token) != -1),
            default=0,
        )
        start = max(first_index - 80, 0)
        end = min(first_index + 200, len(text))
        snippet = text[start:end].strip().replace("\n", " ")
        return snippet[:240]
