Read the current user preferences (language / answer_style / default_note_dir / theme).

## When to use
- Before calling `save_preference` to check current values (avoid clobbering unintended fields).
- When the user asks "what's my current setting for X?".
- For debugging why answers are in a specific language or style.

## Do NOT use for
- **Per-turn context enrichment**: preferences are already injected into `<workspace_state>` in the planner/answer prompt. You usually don't need to call this tool to see them — they're in the prompt.
- **Checking workspace settings**: that's a different store; this tool only covers the 4 user preference fields.

## Parameters
None. Any args passed are ignored.

## Output
- `summary`: "Loaded current user preferences."
- `payload.preferences`: full `UserPreference` dict: `{language, answer_style, default_note_dir, theme}`.
- No events, no side effects.

## Chaining
- `read_preference` → `save_preference`: inspect, then update selected fields.

## Note
Because preferences are already available in `<workspace_state>` of every planner prompt, calling `read_preference` explicitly is mostly useful for:
1. Double-checking after a recent `save_preference` that the update landed.
2. Surfacing current values to the user when they asked "what's configured?".
3. Feeding into a templated answer that needs the raw dict.

Otherwise prefer reading from the prompt context directly.
