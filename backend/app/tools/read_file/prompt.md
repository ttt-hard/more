Read a UTF-8 text file from the workspace and return its contents.

## When to use
- Verifying content before editing (always `read_file` first, then `edit_file` or `write_file`).
- Reading a note, config, or source file whose exact path you already have (e.g., from `list_directory`, `glob_search`, a retrieval hit, or an earlier tool result).
- Confirming that a previous `write_file` / `edit_file` landed correctly.

## Do NOT use for
- **Binary files** (images, PDFs, archives): this tool will fail to decode. For PDFs / documents the user wants turned into notes, use `import_file` to route through the ingest pipeline.
- **Searching by content**: use `grep_search` first to locate files, then `read_file` on the hits.
- **Listing a folder**: use `list_directory` — `read_file` on a directory will error.
- **Large binary dumps**: the workspace filesystem will refuse oversize or non-text reads; do not attempt to stream them through this tool.

## Parameters
- `path` (string, required): workspace-relative path. Must NOT start with `..` or an absolute prefix; the workspace FS will reject those. Example: `"Notes/project.md"`.

## Output
- Success: `summary` contains up to **800 characters** of the file content (trimmed). The full path is echoed in `payload.path`. Citations include `path` so downstream `retrieval_evidence` can reference it.
- Failure: `ok=false` with `error` explaining the cause (file missing, decode error, permission denied, path escape).

## Chaining
- `list_directory` → `read_file`: explore a folder, then inspect a specific entry.
- `grep_search` → `read_file`: find a match, then read context around it.
- `write_file` / `edit_file` → `read_file`: verify the change was written.
- `search_notes` / `search_workspace` → `read_file`: follow up on retrieval hits with full content.

## Error handling
- If the file does not exist, ask the user rather than guessing another path. Do not silently try variants.
- If the path is outside the workspace (starts with `..` or absolute), the call will fail — fix the path, never try to bypass.
- If the content is empty, still return success with an empty summary; do not retry.
