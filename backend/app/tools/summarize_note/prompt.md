Return the note's existing summary (from frontmatter), or a first-240-char fallback.

## When to use
- Quickly previewing a note before deciding whether to read it in full.
- Displaying a one-paragraph overview to the user without regenerating.
- Populating citation context for the final answer.

## Do NOT use for
- **Generating a new summary**: this tool does not call the LLM. It reads the existing `summary` field from frontmatter. To regenerate, read the note body, compose a summary in the answer, then write it back via `update_note_metadata`.
- **Reading the full body**: use `read_note` (400-char body preview) or `read_file` (full body).

## Parameters
- `path` (string, optional): note path. Defaults to `current_note_path`; errors if both are missing.

## Output
- `summary`: "Summary for <title>:\n\n<summary text>".
  - If the note has a `summary` field in frontmatter → that text.
  - Otherwise → first 240 chars of the body (trimmed).
- `citations`: note's relative path.
- `payload.summary`: the raw summary string (without the header prefix).

## Chaining
- `summarize_note` → `read_note`: if the fallback 240-char preview isn't enough, escalate.
- `search_notes` (hits with snippets) → `summarize_note` (get the full per-note summary) → `read_note` (deep dive).

## Notes
- **Passive tool**: no side effects, no write, no event emitted.
- **Fallback is truncated**: if the body has no frontmatter summary and starts with a `#` heading or metadata block, the 240-char fallback may look awkward. Consider calling `update_note_metadata` to set a proper `summary` so future calls are clean.
