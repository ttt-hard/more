Load the full procedure (SKILL.md body) for a skill listed in `<active_skills>`.

## When to use
- `<active_skills>` lists one or more skills whose `when_to_use` matches the current request. Each entry has a `load_with` hint like `load_skill(skill_id='drafting')`. Call this tool with that `skill_id` to read the full procedure before planning execution.
- You decided to follow a known workflow (drafting / interview-prep / research / etc.) and want the detailed steps the skill encodes — rather than improvising.
- The user explicitly invoked a skill by name (`@drafting`, "use the research skill") — load it, read it, follow it.

## Do NOT use for
- **Every turn unconditionally**: don't load skills defensively. If the request is straightforward (e.g., a greeting, a simple file read), no skill is needed. The `active_skills` block is a suggestion, not a mandate.
- **Loading skills that are not in `<active_skills>`**: the planner only sees resolved skills. If you need to know what's available, the SkillStore is a workspace config concern, not a runtime concern — ask the user or check settings.
- **Loading the same skill twice in one turn**: the content is stable; cache the first response mentally.

## Parameters
- `skill_id` (string, required): the id shown in `<active_skills>`. Aliases: `id`, `name` (accepted for LLM ergonomics, but `skill_id` is the canonical key).

## Output
- Success: `summary` contains the skill's name, when_to_use, preferred tools, and the full SKILL.md body. `payload.skill` holds the dict form of the `SkillDefinition` (id / name / description / when_to_use / tool_subset / examples / keywords / prompt_prefix). `citations` points at `.more/skills/<id>/SKILL.md`.
- Not found: `ok=false`, `error="skill_not_found"` — the skill_id is wrong or the skill was deleted after the planner saw `active_skills`. Do not retry with variants; tell the user.
- Disabled: `ok=false`, `error="skill_disabled"` — treat the same as not found; do not silently enable.

## How to use the result
After loading, incorporate the skill's body into your plan:
1. Prefer the tools listed in `tool_subset` when choosing your next call.
2. Follow the procedure described in the body verbatim unless the user explicitly deviates.
3. Treat `examples` as calibration for style / phrasing of the final answer.

## Gotchas
- Skills are loaded **lazily** precisely to keep the planner prompt small. Don't try to "preview all skills" by loading every entry — that defeats the purpose.
- The `prompt_prefix` returned here replaces the old behavior where skills were inlined into the planner prompt. If you see stale behavior referencing "system-injected skill prompts", ignore it; the runtime now expects explicit `load_skill` calls.
