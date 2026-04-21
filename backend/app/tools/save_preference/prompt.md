Persist user preference values (language / answer style / default note directory / theme).

## When to use
- User explicitly asks "reply in X language from now on" / "prefer concise answers" / "save new notes to Y folder by default" / "use dark theme".
- After the agent observes a consistent pattern the user confirmed (e.g., "you always ask for bullet points — should I remember that?").

## Do NOT use for
- **One-off request**: if the user wants just this single response in a different style, adapt in your answer, don't mutate preferences.
- **Undocumented preferences**: this tool only understands the 4 known fields below. For other state (tags, workspace layout), use `workspace_memory` via the appropriate service (not exposed as a tool in this turn).
- **Inferring preferences silently**: never call this without user intent. Preferences affect every future turn.

## Parameters (all optional — pass only fields you intend to change)
- `language` (string): user's preferred language code, e.g., `"zh-CN"`, `"en"`. Controls answer language default.
- `answer_style` (string): free-form style hint such as `"concise"`, `"detailed"`, `"bullet-points"`. The answer stage injects this into the system prompt.
- `default_note_dir` (string): workspace-relative default folder for new notes (used by `create_note` when `path` omitted). Common values: `"Inbox"`, `"Notes"`.
- `theme` (string): UI theme hint, e.g., `"light"`, `"dark"`, `"system"`.

Omitting a field leaves it unchanged; passing empty string is treated as "don't touch".

## Output
- `summary`: "Updated user preferences."
- `payload.preferences`: full `UserPreference` dict after update (shows you the merged state).
- No events — preferences changes do not emit UI events; the frontend reads them via settings endpoint.

## Chaining
- `read_preference` → `save_preference`: inspect current values, then update selected fields.
- `save_preference` → next-turn behavior: downstream prompts pick up new values immediately.

## Safety
- **Irreversible without asking again**: preferences persist across sessions. Always confirm with the user before saving anything they didn't explicitly ask for.
- **Localization**: `language` affects the **answer layer**, not retrieval. Notes stay in whatever language they were written in.
