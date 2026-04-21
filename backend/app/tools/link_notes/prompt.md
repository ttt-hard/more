Append related note links to a source note. Non-destructive union with existing `related` list.

## When to use
- Connecting a just-written note to the note it was inspired by.
- After user says "link this to X" / "add cross-reference to Y".
- Building a graph of related notes without overwriting existing connections.

## Do NOT use for
- **Replacing** the `related` list wholesale: use `update_note_metadata(related=[...])` with the full intended list.
- **Unidirectional link removal**: this tool only adds. To remove, use `update_note_metadata` with the pruned list.
- **Linking non-note files**: `related` is intended for `.md` note paths.

## Parameters
- `source_path` (string, optional): the note to modify. Defaults to `current_note_path`; errors if both are missing.
- `target_paths` (array of strings OR single string, required): one or more note paths to add to `related`. Duplicates are deduped against existing `related` via set union.

## Output
- `summary`: "Linked <source> to N note(s)" where N is the **requested count**, not necessarily the number actually added (duplicates skipped).
- `citations`: source + all targets.
- `payload.note`: updated `NoteMeta` with the new `related` list (sorted, deduped).
- Event: `note_updated`.
- Search index refreshed for `source_path` (not the targets — they were not modified).

## Chaining
- `search_notes` (find related candidates) → `link_notes` (connect).
- `create_note` → `link_notes`: connect the fresh note back to its inspiration.
- `read_note` → `link_notes` → `read_note`: verify the new `related` shows up.

## Notes
- **Bidirectional linking is NOT automatic**: this adds to `source.related` only; targets are not updated to mention source. If you want both directions, call `link_notes` twice with source/target swapped.
- **Idempotent**: re-running with the same args does nothing harmful; the set union drops duplicates.
