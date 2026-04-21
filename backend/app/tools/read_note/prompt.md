Read a note (frontmatter + body) and return structured metadata plus a content snippet.

## When to use
- Reading a workspace markdown note when you need structured metadata (`title`, `tags`, `summary`, `related`, `source_type`) in addition to the body.
- Previewing the active note referenced in `workspace_state.current_note_path` — this tool defaults `path` to `current_note_path` if omitted.
- Following up on a retrieval hit where the path points to a `.md` note.

## Do NOT use for
- **Plain text / code / non-markdown files**: use `read_file` (no frontmatter parsing).
- **Full content when you need more than 400 chars**: `read_note` truncates its summary. Use `read_file` on the same path for the full body.
- **Binary / imported artifacts**: use `import_file` to re-ingest them.

## Parameters
- `path` (string, optional): workspace-relative `.md` path. If omitted, falls back to `current_note_path` from `ToolContext`. If that is also missing, the tool errors.

## Output
- `summary`: `"Current note <title> summary:\n\n<first 400 chars>"`.
- `citations`: includes the note's canonical relative path.
- `payload.note`: full `NoteMeta` dict (`id`, `title`, `tags`, `summary`, `related`, `source_type`, `created_at`, `updated_at`, `relative_path`).
- Event: `tool_started` + `tool_finished` pair, no side effects.

## Chaining
- `read_note` → `update_note_metadata`: inspect metadata, then update selected fields.
- `read_note` → `link_notes`: see current `related` list, then extend it.
- `search_notes` → `read_note`: follow up on a hit with structured metadata.

## Errors
- If the path is not a `.md` note or frontmatter is corrupt, `NoteError` bubbles up. For invalid frontmatter where the raw text is still useful, use `read_file` instead.
- If `current_note_path` is unset and `path` is omitted, the call errors — always provide an explicit `path` when unsure.
