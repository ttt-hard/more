# more backend

Workspace and filesystem foundation for the `more` project.

## LLM

The agent supports an OpenAI-compatible chat completion endpoint.

- `MORE_LLM_BASE_URL`
- `MORE_LLM_MODEL`
- `MORE_LLM_API_KEY` (optional for local providers)

If these variables are not set, the coordinator falls back to the deterministic rule runtime.

## Observability (optional — Langfuse)

Tracing is wired up but **opt-in**: nothing is reported by default, no extra package is installed by default, hot paths pay zero overhead unless you flip the switch.

### Enable

1. **Start the Langfuse stack** (from the repo root):

   ```powershell
   docker compose -f docker-compose.langfuse.yml up -d
   ```

   Brings up `langfuse-web` on `:3000`, plus `langfuse-worker`, Postgres, ClickHouse, Redis, MinIO. Data lives in named volumes; `docker compose ... down` keeps traces, `down -v` wipes them.

2. **Install the optional extra** in the backend virtualenv:

   ```powershell
   pip install -e ".[observability]"
   ```

3. **Create a project** in the Langfuse UI at <http://localhost:3000> (default seed login `admin@local.host` / `admin1234` — override via `LANGFUSE_INIT_USER_*` env). Copy the project's `pk-lf-...` / `sk-lf-...` into `backend/.env`:

   ```env
   LANGFUSE_HOST=http://localhost:3000
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

4. **Restart uvicorn.** The startup log line `Langfuse tracing enabled (host=...)` confirms activation. Send a prompt; traces appear in the UI under **Sessions**, each conversation grouped by its `conversation_id`.

### Trace shape

The instrumentation mirrors the ReAct structure:

```
conversation.turn            [session_id=conv_xxx] ← coordinator.run_stream
├── agent.run                                       ← runtime.run
│   └── agent.react_loop                            ← _run_llm_loop
│       ├── <planner LLM call>                      ← auto via LiteLLM callback
│       ├── agent.tool                              ← _execute_tool (input=tool args)
│       └── <next planner LLM call>
├── memory.build_context                            ← memory.MemoryService
└── answer.generate                                 (if runtime didn't fast-path)
```

Spans are correlated by `session_id = conversation_id`, so the UI's Session view folds all turns of one conversation into a single replay.

### Disabling

Remove `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` from the env (or simply don't set them). The wrapper re-reads them at `init_langfuse()` time; startup skips the whole setup and every `@observe` decorator resolves to the identity function. No need to uninstall the `langfuse` package or strip decorators.

## Docs

- [P2-A — Streaming Function Calling](docs/p2a-streaming-function-calling.md)
