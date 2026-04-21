"""Langfuse self-hosted observability integration.

This module is the SINGLE place that knows about Langfuse. The rest of the
backend imports:

    from .observability_langfuse import observe, observed_tool, set_turn_session

...and uses these wrappers unconditionally. When Langfuse is NOT configured
(package missing, or env keys absent) every wrapper degrades to a
pass-through that executes the underlying function with zero overhead and
no network traffic. This lets us instrument coordinator/runtime/tool code
without a per-site `if langfuse_enabled:` guard and without making Langfuse
a required dependency.

Activation rules (all must hold for tracing to actually happen):
  1. `langfuse` package is installable and importable.
  2. Environment variable `LANGFUSE_SECRET_KEY` is set.
  3. Environment variable `LANGFUSE_PUBLIC_KEY` is set.

When active:
  - `init_langfuse()` is called from FastAPI's startup and wires the
    `litellm.success_callback` so every `litellm.completion(...)` call
    is automatically uploaded as a generation span attached to the
    currently-active span (coordinator's `run_stream`, runtime step, ...).
  - `observe(...)` / `observed_tool(...)` are thin re-exports of
    `langfuse.observe` so decorator semantics match upstream docs.
  - `set_turn_session(conversation_id, ...)` tags the current trace so the
    Langfuse UI groups multi-turn conversations under one session.

When inactive:
  - `init_langfuse()` is a no-op (does NOT import langfuse).
  - `observe(...)` returns the undecorated function unchanged.
  - `set_turn_session(...)` is a silent no-op.

This design means adding a `@observe()` to a hot path costs literally zero
in production if Langfuse is not enabled, because the symbol resolves to
the identity function at import time.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Resolved at module import, flipped to True by a successful `init_langfuse`.
# Every wrapper consults this to decide whether to hit the real SDK.
_LANGFUSE_ACTIVE: bool = False

# Lazily bound to the real langfuse decorator / client once init_langfuse
# succeeds. Kept `Any` because we intentionally avoid importing langfuse at
# module import time (the package may not even be installed).
_observe_decorator: Any = None
_langfuse_client: Any = None


def _identity_decorator(*_args: Any, **_kwargs: Any) -> Callable[[F], F]:
    """No-op decorator factory used when Langfuse is disabled.

    Supports both `@observe` (bare) and `@observe(as_type="tool")` (with
    arguments) so callers don't need to branch on activation state. The
    returned decorator simply gives back the original function so there is
    truly zero per-call overhead (not even a wrapper frame).
    """

    # Called as `@observe` without parens: the first positional is the function.
    if _args and callable(_args[0]) and not _kwargs:
        return _args[0]  # type: ignore[return-value]

    def wrap(fn: F) -> F:
        return fn

    return wrap


def is_active() -> bool:
    """Return True when Langfuse has been successfully initialised.

    Callers should treat this as advisory only; prefer using the `observe`
    wrapper so instrumentation code doesn't fork on activation state. The
    main use case for this function is letting tests assert that env-gating
    works as documented.
    """

    return _LANGFUSE_ACTIVE


def init_langfuse() -> bool:
    """Wire up Langfuse tracing if configured; otherwise stay dormant.

    Returns True iff Langfuse is now active and subsequent `observe`
    decorators will emit spans. Safe to call more than once: after the
    first successful init, further calls are a quick no-op.
    """

    global _LANGFUSE_ACTIVE, _observe_decorator, _langfuse_client

    if _LANGFUSE_ACTIVE:
        return True

    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    if not secret_key or not public_key:
        # Env not wired → stay disabled, don't even import langfuse.
        # Use WARNING level so uvicorn's default log config surfaces this
        # (INFO is filtered for non-uvicorn loggers), otherwise operators
        # have no signal that tracing is silently off.
        logger.warning(
            "Langfuse tracing disabled: LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set"
        )
        return False

    try:
        import langfuse as _langfuse_pkg  # type: ignore
        from langfuse import get_client, observe  # type: ignore
    except ImportError:
        logger.warning(
            "Langfuse credentials set but `langfuse` package is not installed; "
            "run `pip install -e .[observability]` to enable tracing."
        )
        return False

    # Shim the removed-in-v4 `langfuse.version` module.
    #
    # LiteLLM ships two Langfuse integrations (a logging callback and a
    # PromptManagement client) which BOTH do:
    #     self.langfuse_sdk_version = langfuse.version.__version__
    # That submodule existed in Langfuse v2/v3 but was deleted in v4. The
    # PromptManagement logger auto-registers on first LiteLLM call — there
    # is no config flag to turn it off — so without this shim every single
    # LLM call spams a multi-line AttributeError traceback into stderr
    # forever (LiteLLM catches it as "non-blocking" and keeps going, which
    # is the worst possible failure mode: noisy logs, zero generation
    # spans, and traces in the Langfuse UI look mysteriously empty).
    #
    # The shim gives LiteLLM a synthetic `langfuse.version` module whose
    # `__version__` attribute forwards to the real v4 value. Cheap,
    # reversible, and matches the exact access pattern LiteLLM uses.
    try:
        import sys
        import types

        if "langfuse.version" not in sys.modules:
            _version_mod = types.ModuleType("langfuse.version")
            _version_mod.__version__ = getattr(_langfuse_pkg, "__version__", "4.0.0")
            sys.modules["langfuse.version"] = _version_mod
            _langfuse_pkg.version = _version_mod  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — shim is best-effort, never crash startup
        pass

    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3000").strip()
    try:
        client = get_client()  # SDK reads env itself; this just returns the singleton.
    except Exception as exc:  # noqa: BLE001 — never crash startup on observability
        logger.warning("Failed to initialise Langfuse client: %s", exc)
        return False

    # DELIBERATELY do NOT register `"langfuse"` in `litellm.success_callback`.
    #
    # LiteLLM's built-in Langfuse integration was written against Langfuse
    # SDK v2/v3 and hard-codes `langfuse.version.__version__` — that module
    # was removed in Langfuse v4. Any LLM call triggers
    #   AttributeError: module 'langfuse' has no attribute 'version'
    # inside LiteLLM's logger init, and since LiteLLM marks the error
    # "non-blocking" the app keeps running but zero generation spans ever
    # reach Langfuse cloud. Classic silent-failure trap: traces look like
    # they're configured, Sessions view stays empty forever.
    #
    # Instead we emit generation spans ourselves at the LiteLLM provider
    # seam (see `app/llm/providers/litellm_provider.py` — wrapped with
    # `@observe(as_type="generation")` + `update_current_observation(...)`).
    # That keeps us on Langfuse v4's first-class decorator API and pays
    # zero runtime cost when the observability extra isn't installed.

    _observe_decorator = observe
    _langfuse_client = client
    _LANGFUSE_ACTIVE = True

    # WARNING not INFO: uvicorn's default logging config only surfaces
    # uvicorn.* INFO lines; everything else defaults to WARNING. Without
    # this bump we'd silently activate and operators couldn't tell.
    logger.warning(
        "Langfuse tracing ENABLED (host=%s, public_key=%s...)",
        host,
        public_key[:10],
    )
    return True


def observe(*dargs: Any, **dkwargs: Any) -> Any:
    """Cross-state decorator: real `@observe` when active, identity otherwise.

    Resolves lazily on every call so tests that flip activation at runtime
    (via `init_langfuse()` after setting env) see the new state without
    having to re-import the module.

    Usage mirrors langfuse upstream exactly:

        @observe()                      # default span
        @observe(name="foo")            # custom name
        @observe(as_type="tool")        # langfuse tool span kind
    """

    if _LANGFUSE_ACTIVE and _observe_decorator is not None:
        return _observe_decorator(*dargs, **dkwargs)
    return _identity_decorator(*dargs, **dkwargs)


def observed_tool(*dargs: Any, **dkwargs: Any) -> Any:
    """Shortcut for `@observe(as_type="tool")`.

    Kept separate so runtime._execute_tool can be decorated with a tool-kind
    span without callers having to remember the magic string.
    """

    dkwargs.setdefault("as_type", "tool")
    return observe(*dargs, **dkwargs)


def update_current_generation(
    *,
    input: Any = None,
    output: Any = None,
    model: str | None = None,
    usage_details: dict[str, Any] | None = None,
    model_parameters: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Fill in the currently-active generation span's payload.

    Call this from INSIDE a function decorated with
    `@observe(as_type="generation")` to attach the real LLM I/O to the
    span that's already been opened. The Langfuse UI renders those four
    fields specially (prompt / completion / model badge / token counter)
    so getting them right is what turns a generic span into a proper
    "LLM call" card.

    Silent no-op when Langfuse is disabled, when the shim decorator is
    in use (no active span), or when the client rejects the call for
    any reason — observability must never break the user-visible flow.
    """

    if not _LANGFUSE_ACTIVE or _langfuse_client is None:
        return
    # Only forward fields the caller actually set; Langfuse treats a
    # literal `None` as "clear this field", which is usually not what
    # the caller meant.
    payload: dict[str, Any] = {}
    if input is not None:
        payload["input"] = input
    if output is not None:
        payload["output"] = output
    if model is not None:
        payload["model"] = model
    if usage_details is not None:
        payload["usage_details"] = usage_details
    if model_parameters is not None:
        payload["model_parameters"] = model_parameters
    if metadata is not None:
        payload["metadata"] = metadata
    if not payload:
        return
    try:
        _langfuse_client.update_current_generation(**payload)
    except Exception as exc:  # noqa: BLE001 — observability must never crash
        logger.debug("Langfuse update_current_generation failed: %s", exc)


def set_turn_session(
    conversation_id: str,
    *,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> None:
    """Tag the CURRENT trace with session/user/metadata for UI grouping.

    Called from `coordinator.run_stream` right after entering its top-level
    `@observe()` span. In the Langfuse UI, traces sharing the same
    `session_id` collapse into a single conversation view so the reviewer
    can replay multi-turn histories in one click.

    Implementation notes: Langfuse v4 dropped the v3-era
    `client.update_current_trace(...)` method. Trace-level attributes
    (`session_id`, `user_id`, `tags`, `metadata`) are now stored as
    OpenTelemetry attributes on the span itself, using well-known keys
    from `langfuse._client.attributes.LangfuseOtelSpanAttributes`. The
    Langfuse backend picks these up during ingestion and promotes them
    to trace-level fields. See:
    https://langfuse.com/docs/sdk/python/sdk-v3#update-trace-attributes
    (the SDK v3 page describes the OTEL attribute approach that v4
    standardized on).

    Silent no-op when Langfuse is disabled.
    """

    if not _LANGFUSE_ACTIVE:
        return

    try:
        # Reach into OTEL directly: grab whatever span is currently on the
        # stack and stamp the Langfuse-recognised attribute keys on it.
        # Doing it this way (instead of via a langfuse-specific helper)
        # is version-stable: the attribute keys ARE the API contract that
        # Langfuse's server-side ingestion cares about.
        from opentelemetry import trace as _otel_trace  # local import keeps cold-start fast

        span = _otel_trace.get_current_span()
        if not span.is_recording():
            logger.warning(
                "[lf] set_turn_session: no recording span active for "
                "conversation_id=%s — trace will miss session_id",
                conversation_id,
            )
            return

        span.set_attribute("session.id", conversation_id)
        if user_id is not None:
            span.set_attribute("user.id", user_id)
        if tags:
            # TRACE_TAGS expects a JSON-encoded string array; OTEL also
            # permits list[str] directly but langfuse's attribute reader
            # handles both, so prefer the native list form for legibility.
            span.set_attribute("langfuse.trace.tags", list(tags))
        if metadata:
            # Metadata is arbitrary JSON; OTEL attributes are flat
            # scalar/scalar-array only, so we JSON-encode the whole dict
            # onto a single string attribute. Langfuse's ingestion layer
            # re-parses this at read time.
            import json as _json

            span.set_attribute("langfuse.trace.metadata", _json.dumps(metadata))

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[lf] set_turn_session stamped session.id=%s on span_id=%s",
                conversation_id,
                format(span.get_span_context().span_id, "016x"),
            )
    except Exception as exc:  # noqa: BLE001 — observability must never crash the turn
        logger.warning("Langfuse set_turn_session failed: %s", exc)


__all__ = [
    "init_langfuse",
    "is_active",
    "observe",
    "observed_tool",
    "set_turn_session",
    "update_current_generation",
]
