Replace a string inside an existing file. Preserves everything else.

## When to use
- Making a targeted change to a few lines of an existing file (fix a typo, update a value, rename a reference).
- Replacing an exact known snippet when you already know what's there (from a prior `read_file`).
- Small iterative refactors where overwriting the whole file with `write_file` would be wasteful and risky.

## Do NOT use for
- **Whole-file rewrites**: use `write_file` when you've regenerated all content.
- **Fuzzy matches / regex**: `search_text` is matched **literally** (exact substring), not as a pattern. If the target text shifts formatting or whitespace, the edit will silently fail to find it.
- **Creating new files**: `edit_file` errors if the file does not exist. Use `write_file` to create.
- **Multi-file refactors**: call `edit_file` per file.

## Parameters
- `path` (string, required): workspace-relative path to the existing file.
- `search_text` (string, required): **exact** substring to find. Must be unique in the file unless `replace_all=true`.
- `replace_text` (string, required): text to replace it with. Can be empty to delete.
- `replace_all` (boolean, optional, default `false`): when `true`, replaces every occurrence; otherwise requires `search_text` to match exactly once.

## Output
- Success: summary confirms the replacement. For `.md` files, emits `note_updated` with fresh meta if frontmatter parses; otherwise `file_written`. Search index refreshed.
- Failure: `ok=false` with `error` explaining (file missing, `search_text` not found, multiple matches without `replace_all`).

## Chaining
- `read_file` → `edit_file`: always read first to copy the exact `search_text`, including whitespace and punctuation.
- `edit_file` → `read_file`: verify the edit landed and produced the expected output.
- `grep_search` → `edit_file`: find occurrences before attempting a targeted change.

## Risks and common mistakes
- **Ambiguous `search_text`**: if the substring appears multiple times and `replace_all` is off, the call fails. Fix: include enough surrounding context in `search_text` to make it unique.
- **Whitespace mismatch**: copying from a rendered view can collapse tabs/spaces. Always source the exact text from a recent `read_file`.
- **Frontmatter breakage**: editing YAML frontmatter by hand can corrupt it. Prefer `update_note_metadata` for frontmatter-level changes.
