Search workspace notes via the retrieval pipeline (lexical + embeddings hybrid). Returns ranked hits.

This module exposes two tool IDs that behave identically: `search_notes` and `search_workspace`. The second is an alias kept for prompt compatibility; prefer `search_notes`.

## When to use
- Finding notes semantically related to the user's question ("what did I write about transformers?").
- Discovering precedent before answering ("has this been addressed in existing notes?").
- Populating evidence for the final answer with grounded citations.

## Do NOT use for
- **Exact filename lookup**: use `glob_search`.
- **Exact substring matching**: use `grep_search`.
- **Fetching a specific note by path**: use `read_note` / `read_file`.
- **First-turn greeting / preference-only requests**: no retrieval needed; respond directly.

## Parameters
- `query` (string, optional): free-text search string. **Defaults to the user's current prompt** if omitted — this is usually what you want for one-shot retrieval.
- `limit` (integer, optional, default `5`): max number of hits to return. The pipeline internally may rerank more.

## Output
- Hits found: summary includes hit count, top hit path, top snippet; `citations` lists the top 3 paths.
- No hits: summary says "No matching notes were found" with `payload.count = 0`.
- `payload.count`: total hits.
- Events: `tool_started` / `tool_finished` with the query echoed.

## Chaining
- `search_notes` → `read_note`: follow up on a promising hit.
- `search_notes` → `read_file`: if the hit is non-markdown or you need full body.
- `search_notes` → `link_notes`: connect a newly-written note to related hits.

## Pipeline notes
- The retrieval service combines lexical (BM25 via the SearchIndex) and optional embedding-based ranking. Behavior is transparent to the caller; just pass `query`.
- Hits include `score` and `snippet` already extracted around the match — surface those directly, don't re-read unless the snippet is insufficient.
- **Do not over-fetch**: `limit=5` is usually enough; a `limit=20` call floods context and costs accuracy in the final answer.

## When results look wrong
- Reformulate the query: synonyms, different wording, specific jargon.
- Fall back to `grep_search` for exact terms the user used.
- If the workspace is new / empty, expect `count=0` — this is not an error.
