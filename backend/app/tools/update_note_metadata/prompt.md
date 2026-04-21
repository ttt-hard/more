Update frontmatter fields of an existing note. Preserves the body.

## When to use
- Setting or refining `title`, `summary`, `tags`, `related`, or `source_type` on a note.
- After `create_note` to attach richer metadata.
- After the user says "tag this as X" / "summarize to Y" / "link to Z".

## Do NOT use for
- **Editing body text**: use `edit_file` or `write_file`. This tool only rewrites the YAML frontmatter block.
- **Adding related links**: you can pass `related` here, but `link_notes` is purpose-built for extending the related list without replacing it (safer default).
- **Non-markdown files**: only `.md` notes with frontmatter are supported.

## Parameters (all optional except `path`)
- `path` (string, optional): target note path. Defaults to `current_note_path` if available.
- `title` (string, optional): new title.
- `summary` (string, optional): one-paragraph summary for the frontmatter `summary` field.
- `source_type` (string, optional): origin tag (`agent`, `user`, `import`, etc.).
- `tags` (array of strings, optional): **replaces** existing tag list. Pass the full new list, not a diff.
- `related` (array of strings, optional): **replaces** existing related links. Pass full list. To append, use `link_notes` instead.

Fields not passed in the call keep their current values; passing `null` or an empty string has no effect (treated as "don't touch").

## Output
- `summary`: "Updated metadata for <path>".
- `citations`: the note path.
- `payload.note`: fresh `NoteMeta` after update.
- Event: `note_updated` so the frontend can refresh the note card.
- Search index is refreshed for this path.

## Chaining
- `read_note` → `update_note_metadata`: inspect then patch.
- `update_note_metadata` → `read_note`: verify.
- After bulk organizing: `list_directory` / `glob_search` → `update_note_metadata` per path.

## Gotchas
- **Full replacement of `tags` / `related`**: always read current list first via `read_note`, then send the full intended list. Missing this step silently drops entries.
- **Frontmatter corruption**: if the note had hand-written invalid YAML, this tool may fail. Re-save with `write_file` in that case.
