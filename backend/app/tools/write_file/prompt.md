Create a new file or overwrite an existing one in the workspace.

## When to use
- Creating a new file whose content you already have fully prepared.
- Replacing a file wholesale when the changes span most of it (rewriting a note, regenerating a config, etc.).
- Writing non-markdown files (e.g., JSON data, plain text drafts).

## Do NOT use for
- **Small edits inside an existing file**: use `edit_file` — it preserves the rest of the content and is far safer. `write_file` overwrites everything.
- **Creating structured notes** where the user wants frontmatter auto-filled (title / tags / summary): use `create_note` instead, which owns the frontmatter schema.
- **Binary content**: this tool writes UTF-8 text only.
- **Files outside the workspace**: the FS will reject escape paths.

## Parameters
- `path` (string, required): workspace-relative path. Parent directory will be created if missing. Example: `"Drafts/plan.md"`.
- `content` (string, required): full file body. If you only want to change a few lines, STOP and use `edit_file` instead.

## Output
- Success: summary indicates "Created" or "Updated" based on whether the path existed. Citations include `path`. For `.md` files, a `note_updated` event is emitted if frontmatter parses; otherwise a `file_written` event.
- Search index is refreshed automatically for the written path.

## Chaining
- `list_directory` → `write_file`: confirm the target folder exists first.
- `read_file` → `write_file`: read existing content, mutate in memory, then write. Prefer `edit_file` for small mutations.
- `write_file` → `read_file`: verify what actually landed after write.

## Risks
- **Irreversible overwrite**: `write_file` with `overwrite=True` (always on) will clobber any existing content without asking. If unsure whether a file exists, call `read_file` first or use `edit_file`.
- **Frontmatter corruption**: if writing a `.md` file, ensure the YAML frontmatter block is valid. Invalid frontmatter still writes, but the file will downgrade to a plain text event (`file_written`) and won't show up as a structured note.
- **Empty content**: writing an empty string truncates the file. This is allowed but usually unintended; confirm intent before doing it.
