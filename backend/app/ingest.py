"""外部内容导入服务。

`IngestService` 把本地文件（.md/.txt/.pdf）或 HTTP URL 转成工作区内的笔记：
读取源 → 文本归一化 → 分配去重路径 → 通过 `NoteService.create_note` 写入 →
在 `.more/imports/<id>.json` 记录 `ImportJob`。HTML 走 `_HTMLTextExtractor`
抽正文；PDF 走 `pypdf`（可选依赖）；失败一律抛 `IngestError`。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from .domain import ImportJob, NoteDocument, utc_now_iso
from .notes import NoteService
from .workspace_fs import WorkspaceFS


class IngestError(Exception):
    """Base error for ingest operations."""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "section", "article", "main", "br", "li", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or self._skip_depth:
            return
        if self._in_title and not self.title:
            self.title = text
        self._parts.append(text)

    def as_text(self) -> str:
        merged = " ".join(self._parts)
        merged = re.sub(r"\s*\n\s*", "\n", merged)
        merged = re.sub(r"[ \t]{2,}", " ", merged)
        merged = re.sub(r"\n{3,}", "\n\n", merged)
        return merged.strip()


class IngestService:
    def __init__(self, fs: WorkspaceFS, note_service: NoteService | None = None) -> None:
        self.fs = fs
        self.note_service = note_service or NoteService(fs)
        self.imports_root = self.fs.sidecar_root / "imports"
        self.imports_root.mkdir(parents=True, exist_ok=True)

    def import_file(
        self,
        source_path: str,
        *,
        destination_dir: str = "Inbox",
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
    ) -> tuple[ImportJob, NoteDocument]:
        source = Path(source_path).expanduser()
        if not source.exists():
            raise IngestError(f"Import source does not exist: {source}")
        if not source.is_file():
            raise IngestError(f"Import source is not a file: {source}")

        suffix = source.suffix.casefold()
        if suffix in {".md", ".markdown"}:
            content = self._read_text_file(source)
            source_type = "markdown"
        elif suffix == ".txt":
            content = self._read_text_file(source)
            source_type = "text"
        elif suffix == ".pdf":
            content = self._read_pdf_file(source)
            source_type = "pdf"
        else:
            raise IngestError(f"Unsupported import file type: {source.suffix or '<none>'}")

        return self._create_imported_note(
            source_type=source_type,
            source_ref=str(source.resolve()),
            content=content,
            destination_dir=destination_dir,
            title=title or source.stem,
            tags=tags,
            summary=summary,
        )

    def import_url(
        self,
        url: str,
        *,
        destination_dir: str = "Inbox",
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
    ) -> tuple[ImportJob, NoteDocument]:
        if not url.strip():
            raise IngestError("URL must not be empty")
        fetched_title, content = self._fetch_url_text(url)
        return self._create_imported_note(
            source_type="url",
            source_ref=url.strip(),
            content=content,
            destination_dir=destination_dir,
            title=title or fetched_title or url.strip(),
            tags=tags,
            summary=summary,
        )

    def _create_imported_note(
        self,
        *,
        source_type: str,
        source_ref: str,
        content: str,
        destination_dir: str,
        title: str,
        tags: list[str] | None,
        summary: str | None,
    ) -> tuple[ImportJob, NoteDocument]:
        cleaned_content = content.strip()
        if not cleaned_content:
            raise IngestError("Imported content is empty")

        safe_title = title.strip() or "Imported Note"
        note_path = self._allocate_note_path(destination_dir, safe_title)
        note_content = self._as_markdown_body(safe_title, cleaned_content)
        note = self.note_service.create_note(
            note_path,
            note_content,
            title=safe_title,
            tags=tags or [],
            summary=(summary or self._build_summary(cleaned_content)),
            source_type=source_type,
        )
        job = ImportJob(
            id=uuid4().hex[:12],
            source_type=source_type,
            source_ref=source_ref,
            status="completed",
            output_path=note.meta.relative_path,
            created_at=utc_now_iso(),
        )
        self._job_path(job.id).write_text(
            json.dumps(asdict(job), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return job, note

    def _read_text_file(self, source: Path) -> str:
        raw = source.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise IngestError(f"Unable to decode text file: {source}")

    def _read_pdf_file(self, source: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise IngestError("PDF import requires pypdf to be installed") from exc

        reader = PdfReader(str(source))
        parts: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                parts.append(text.strip())
        content = "\n\n".join(parts).strip()
        if not content:
            raise IngestError(f"No extractable text found in PDF: {source}")
        return content

    def _fetch_url_text(self, url: str) -> tuple[str | None, str]:
        request = Request(
            url.strip(),
            headers={
                "User-Agent": "more-ingest/0.1 (+https://local.more)",
                "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read()
        except URLError as exc:
            raise IngestError(f"Unable to fetch URL: {url}") from exc

        text = self._decode_response(raw)
        if "html" not in content_type.casefold():
            return None, text

        parser = _HTMLTextExtractor()
        parser.feed(text)
        extracted = parser.as_text()
        if not extracted:
            raise IngestError(f"No readable content found at URL: {url}")
        return parser.title or None, extracted

    def _decode_response(self, raw: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise IngestError("Unable to decode imported response body")

    def _allocate_note_path(self, destination_dir: str, title: str) -> str:
        base_dir = destination_dir.strip().replace("\\", "/").strip("/") or "Inbox"
        slug = self._slugify(title)
        candidate = f"{base_dir}/{slug}.md"
        if not self.fs.resolve_path(candidate).exists():
            return candidate
        for index in range(2, 1000):
            next_candidate = f"{base_dir}/{slug}-{index}.md"
            if not self.fs.resolve_path(next_candidate).exists():
                return next_candidate
        raise IngestError(f"Unable to allocate note path for title: {title}")

    def _as_markdown_body(self, title: str, content: str) -> str:
        stripped = content.lstrip()
        if stripped.startswith("#"):
            return content.rstrip()
        return f"# {title}\n\n{content.rstrip()}"

    def _build_summary(self, content: str, limit: int = 180) -> str:
        flattened = re.sub(r"\s+", " ", content).strip()
        if len(flattened) <= limit:
            return flattened
        return flattened[: limit - 3].rstrip() + "..."

    def _slugify(self, text: str) -> str:
        normalized = text.strip().casefold()
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        return normalized or "imported-note"

    def _job_path(self, job_id: str) -> Path:
        return self.imports_root / f"{job_id}.json"
