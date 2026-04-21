Import a local file into the workspace as a structured note via the ingest pipeline.

## When to use
- User drops a file path (PDF, docx, plain text, markdown) and asks to "import" / "add to workspace" / "turn into a note".
- Bulk-adding external reference material that should be searchable and link-able like any workspace note.
- Preserving source attribution — ingest jobs track `source_ref` for provenance.

## Do NOT use for
- **Content the user typed in chat**: use `create_note` with the content directly; don't ask the user to write to a temp file first.
- **Plain text copies with no transformation needed**: if the content is already markdown that fits the note format, `write_file` is lighter-weight.
- **Remote URLs**: use `import_url` — it handles fetching + cleanup.
- **Files that live outside the host OS or require authentication to access**: not supported; user must resolve access first.

## Parameters
- `source_path` (string, required): **host OS path** (absolute or relative to current working dir of the backend process). Note: this is NOT a workspace-relative path — it's outside the workspace. Example: `"C:\\Users\\me\\Downloads\\paper.pdf"`.
- `destination_dir` (string, optional, default `"Inbox"`): workspace-relative target folder. The pipeline places the resulting note inside this folder.

## Output
- `summary`: "Imported file <src> into <workspace path>".
- `citations`: [new note path, original `source_ref`].
- `payload.job`: full `IngestJob` (id, status, timestamps, content extraction metadata).
- `payload.note`: the freshly created note's metadata.
- Events: `note_created` + `tool_finished`. Search index is refreshed.

## Chaining
- `import_file` → `update_note_metadata`: add tags / summary / related after import.
- `import_file` → `read_note`: verify extracted content quality.
- `import_file` → `link_notes`: connect imported source to related workspace notes.

## Pipeline behavior
- Supported formats depend on `IngestService` (markdown passthrough, PDF text extraction, plain text, etc.). Unsupported formats return `ok=false` with a clear error.
- Duplicates: filename collisions in `destination_dir` get suffixed to avoid clobber.
- Large files: ingest may be slow; do not retry on timeout unless the user asks.

## Security
- This is a **host filesystem read** — only use paths the user explicitly mentioned. Never infer a "probably the downloads folder" path.
