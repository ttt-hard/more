"""LiteLLM provider 实现。

优先用 `litellm.completion` 走模型路由；若未安装则降级成直接 POST 到
OpenAI 兼容 `/chat/completions`（httpx 同步客户端）。`stream_chunks` /
`_stream_chunks_with_httpx` 解析 SSE 增量，把 `choices[0].delta.content`
和 `reasoning_content` 分流为 `StreamChunk` 的 content/reasoning 字段。

**Streaming function calling**：当 `CompletionRequest.tools` 非空时，两条
路径都把 `tools` + `tool_choice` 透传到请求，并用 `_ToolCallAccumulator`
把每个 `delta.tool_calls[index]` 的 `id/name/arguments` 增量合并。流
结束时 yield **恰好一个** `finished=True` 的 StreamChunk，携带完整的
`tool_calls` 列表和 `finish_reason`。这样上游 planner 可以在单个
`stream_chunks()` 调用里同时拿到：
  - 逐 token 的 content（立即 relay 给前端，产生打字机效果）
  - 最后累积好的 tool_calls（决定下一步 react 行为）
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
import json
import os
from time import perf_counter

import httpx

from ..observability_langfuse import observe, update_current_generation
from .base import (
    CompletionRequest,
    CompletionResponse,
    ModelProvider,
    ProviderError,
    StreamChunk,
    ToolCall,
)


class LiteLLMProvider(ModelProvider):
    """Provider facade around LiteLLM with an httpx fallback for OpenAI-compatible APIs."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        self._configure_litellm()

    def is_configured(self) -> bool:
        return True

    # `capture_input/output=False` because we push the real chat messages
    # and completion text through `update_current_generation` below — the
    # default capture would serialise the whole Python arguments tuple
    # (including the ModelProvider `self`) which is noisy and useless in
    # the Langfuse UI. `as_type="generation"` tells Langfuse to render
    # this span as an LLM call card with prompt / completion / model /
    # token-usage badges rather than a generic box.
    @observe(name="llm.complete", as_type="generation", capture_input=False, capture_output=False)
    def complete(self, request: CompletionRequest) -> CompletionResponse:
        try:
            from litellm import completion  # type: ignore
        except ImportError:
            return self._complete_with_httpx(request)

        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]
        completion_kwargs: dict[str, object] = {
            "model": request.model,
            "api_base": request.base_url or None,
            "api_key": request.api_key or None,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout,
        }
        if request.tools:
            completion_kwargs["tools"] = request.tools
            if request.tool_choice is not None:
                completion_kwargs["tool_choice"] = request.tool_choice
        try:
            response = completion(**completion_kwargs)
        except Exception as exc:  # noqa: BLE001
            # Record the attempted prompt + error message on the span
            # before re-raising so failures are visible in Langfuse too
            # (otherwise they'd be orphan spans with empty output).
            update_current_generation(
                input=messages,
                output=f"<error: {exc}>",
                model=request.model,
                model_parameters={
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
            )
            raise ProviderError(f"Provider request failed: {exc}") from exc

        raw = self._coerce_raw_payload(response)
        try:
            message = raw["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Provider response did not contain a completion message") from exc
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = self._parse_tool_calls(message.get("tool_calls") if isinstance(message, dict) else None)
        # OpenAI returns content=None when tool_calls is present; coerce to "".
        content_str = str(content) if content is not None else ""

        # Populate the generation span with everything Langfuse wants to
        # see. Usage is a dict like {prompt_tokens, completion_tokens,
        # total_tokens} on OpenAI-compatible responses; we copy it
        # verbatim and Langfuse renders the token counts + computed cost
        # if a price is configured for the model.
        usage_details: dict[str, object] | None = None
        raw_usage = raw.get("usage") if isinstance(raw, dict) else None
        if isinstance(raw_usage, dict):
            usage_details = {str(k): v for k, v in raw_usage.items()}
        generation_output: object = content_str
        if tool_calls:
            # A tool-call-only response has empty content; surface the
            # tool calls themselves as the span output so reviewers can
            # see what the planner decided to do.
            generation_output = {
                "content": content_str,
                "tool_calls": [
                    {"name": tc.name, "arguments": tc.arguments} for tc in tool_calls
                ],
            }
        update_current_generation(
            input=messages,
            output=generation_output,
            model=request.model,
            usage_details=usage_details,
            model_parameters={
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            },
        )

        return CompletionResponse(
            content=content_str,
            tool_calls=tool_calls,
            raw=raw,
        )

    def stream_complete(self, request: CompletionRequest) -> Iterator[str]:
        for chunk in self.stream_chunks(request):
            if chunk.content:
                yield chunk.content

    # Generator version of `complete`. MUST keep `capture_output=True`
    # (the default) — Langfuse v4's `@observe` only wraps generators
    # with its context-preserving iterator wrapper when
    # `capture_output is True`; with False it hits `finally:
    # span.end()` the instant `stream_chunks(...)` returns the
    # un-iterated generator object, closing the span before any
    # yielded StreamChunk is produced. We override the auto-captured
    # output (a noisy list of every StreamChunk) via the explicit
    # `update_current_generation(output=...)` call in the finally
    # block below, which gives us a single clean completion string +
    # tool_calls payload in the Langfuse UI.
    @observe(name="llm.stream", as_type="generation", capture_input=False)
    def stream_chunks(self, request: CompletionRequest) -> Iterator[StreamChunk]:
        try:
            from litellm import completion  # type: ignore
        except ImportError:
            yield from self._stream_chunks_with_httpx(request)
            return

        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]
        stream_kwargs: dict[str, object] = {
            "model": request.model,
            "api_base": request.base_url or None,
            "api_key": request.api_key or None,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout,
            "stream": True,
        }
        if request.tools:
            stream_kwargs["tools"] = request.tools
            if request.tool_choice is not None:
                stream_kwargs["tool_choice"] = request.tool_choice
        try:
            response = completion(**stream_kwargs)
        except Exception as exc:  # noqa: BLE001
            # Surface the failure on the open generation span before
            # bubbling. Without this Langfuse would show an empty span.
            update_current_generation(
                input=messages,
                output=f"<error: {exc}>",
                model=request.model,
                model_parameters={
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                },
            )
            raise ProviderError(f"Provider request failed: {exc}") from exc

        accumulator = _ToolCallAccumulator()
        finish_reason: str | None = None
        # Accumulate for the terminal span update. Kept separate from the
        # streamed chunks so consumers still see real-time deltas — we
        # only use these strings to populate the generation span at end.
        content_buffer: list[str] = []
        reasoning_buffer: list[str] = []
        try:
            for chunk in response:
                content, reasoning, tc_deltas, fr = self._extract_stream_delta_parts(
                    self._coerce_raw_payload(chunk)
                )
                if tc_deltas:
                    accumulator.feed(tc_deltas)
                if fr is not None:
                    finish_reason = fr
                if content:
                    content_buffer.append(content)
                if reasoning:
                    reasoning_buffer.append(reasoning)
                if content or reasoning:
                    yield StreamChunk(content=content, reasoning=reasoning)
            tool_calls = accumulator.finalize()
            yield StreamChunk(
                tool_calls=tool_calls,
                finished=True,
                finish_reason=finish_reason,
            )
        finally:
            # Runs regardless of whether the generator exhausted normally
            # or the consumer abandoned it mid-stream (e.g. SSE client
            # disconnected). Langfuse's `@observe` closes the span on
            # generator teardown, but the span stays empty unless we
            # push the accumulated payload here.
            final_content = "".join(content_buffer)
            final_output: object = final_content
            if accumulator._by_index:  # noqa: SLF001 — private but stable
                # Partial or complete tool_calls: present them structured
                # so reviewers can see the planner decision even when the
                # stream was truncated.
                final_output = {
                    "content": final_content,
                    "reasoning": "".join(reasoning_buffer),
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in accumulator.finalize()
                    ],
                    "finish_reason": finish_reason,
                }
            update_current_generation(
                input=messages,
                output=final_output,
                model=request.model,
                model_parameters={
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "stream": True,
                },
            )

    def test_connection(self, request: CompletionRequest) -> dict[str, object]:
        probe = CompletionRequest(
            model=request.model,
            system_prompt="You are a connectivity probe.",
            user_prompt="hi",
            temperature=0,
            max_tokens=4,
            timeout=min(request.timeout, 15.0),
            base_url=request.base_url,
            api_key=request.api_key,
        )
        started_at = perf_counter()
        try:
            response = self.complete(probe)
        except ProviderError as exc:
            return {"ok": False, "error": str(exc)}
        latency_ms = round((perf_counter() - started_at) * 1000)
        return {
            "ok": True,
            "model": request.model,
            "provider": "litellm",
            "preview": response.content[:32],
            "latency_ms": latency_ms,
        }

    def _complete_with_httpx(self, request: CompletionRequest) -> CompletionResponse:
        if not request.base_url:
            raise ProviderError("base_url is required when LiteLLM is unavailable")
        payload: dict[str, object] = {
            "model": request.model,
            "temperature": request.temperature,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
            if request.tool_choice is not None:
                payload["tool_choice"] = request.tool_choice
        headers = {"Content-Type": "application/json"}
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"
        try:
            if self._client is None:
                with httpx.Client() as client:
                    response = client.post(
                        f"{request.base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=request.timeout,
                    )
            else:
                response = self._client.post(
                    f"{request.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=request.timeout,
                )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Provider response was not valid JSON") from exc
        try:
            message = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Provider response did not contain a completion message") from exc
        content = message.get("content") if isinstance(message, dict) else None
        tool_calls = self._parse_tool_calls(message.get("tool_calls") if isinstance(message, dict) else None)
        return CompletionResponse(
            content=str(content) if content is not None else "",
            tool_calls=tool_calls,
            raw=body,
        )

    def _stream_chunks_with_httpx(self, request: CompletionRequest) -> Iterator[StreamChunk]:
        if not request.base_url:
            raise ProviderError("base_url is required when LiteLLM is unavailable")
        payload: dict[str, object] = {
            "model": request.model,
            "temperature": request.temperature,
            "stream": True,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
            if request.tool_choice is not None:
                payload["tool_choice"] = request.tool_choice
        headers = {"Content-Type": "application/json"}
        if request.api_key:
            headers["Authorization"] = f"Bearer {request.api_key}"
        accumulator = _ToolCallAccumulator()
        finish_reason: str | None = None
        try:
            client = self._client or httpx.Client()
            close_client = self._client is None
            try:
                with client.stream(
                    "POST",
                    f"{request.base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=request.timeout,
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        data = line[5:].strip() if line.startswith("data:") else line.strip()
                        if not data or data == "[DONE]":
                            continue
                        payload_line = json.loads(data)
                        content, reasoning, tc_deltas, fr = self._extract_stream_delta_parts(payload_line)
                        if tc_deltas:
                            accumulator.feed(tc_deltas)
                        if fr is not None:
                            finish_reason = fr
                        if content or reasoning:
                            yield StreamChunk(content=content, reasoning=reasoning)
            finally:
                if close_client:
                    client.close()
            yield StreamChunk(
                tool_calls=accumulator.finalize(),
                finished=True,
                finish_reason=finish_reason,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Provider request failed: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("Provider stream response was not valid JSON") from exc

    def _parse_tool_calls(self, raw_calls: object) -> list[ToolCall]:
        """Parse OpenAI-style tool_calls from a chat completion message.

        Shape expected::

            [
                {
                    "id": "call_...",
                    "type": "function",
                    "function": {
                        "name": "tool_name",
                        "arguments": "{...JSON...}"  # always a JSON string
                    }
                }
            ]
        """
        if not isinstance(raw_calls, list):
            return []
        results: list[ToolCall] = []
        for index, call in enumerate(raw_calls):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id") or f"call_{index}")
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            name = str(function.get("name") or "").strip()
            if not name:
                continue
            raw_args = function.get("arguments")
            arguments: dict[str, object] = {}
            if isinstance(raw_args, str):
                text = raw_args.strip()
                if text:
                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        arguments = {str(key): value for key, value in parsed.items()}
            elif isinstance(raw_args, dict):
                arguments = {str(key): value for key, value in raw_args.items()}
            results.append(ToolCall(id=call_id, name=name, arguments=arguments))
        return results

    def _coerce_raw_payload(self, response: object) -> dict[str, object]:
        if isinstance(response, dict):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            dumped = to_dict()
            if isinstance(dumped, dict):
                return dumped
        if hasattr(response, "__dict__"):
            return dict(asdict(response)) if hasattr(response, "__dataclass_fields__") else dict(response.__dict__)
        raise ProviderError("Unable to normalize provider response")

    def _extract_stream_delta(self, payload: dict[str, object]) -> StreamChunk:
        """Legacy: return just the content/reasoning view of a streamed chunk.

        Kept for callers that don't care about tool_calls. New code paths
        should use `_extract_stream_delta_parts` and build the StreamChunk
        with accumulated tool_calls separately.
        """
        content, reasoning, _tc_deltas, _fr = self._extract_stream_delta_parts(payload)
        return StreamChunk(content=content, reasoning=reasoning)

    def _extract_stream_delta_parts(
        self, payload: dict[str, object]
    ) -> tuple[str, str, list[dict[str, object]], str | None]:
        """Split a raw SSE chunk payload into four streams.

        Returns: (content_delta, reasoning_delta, tool_call_deltas, finish_reason).
        Every return value is "empty" by default so callers can safely ignore
        dimensions they don't care about.
        """

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            return "", "", [], None
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return "", "", [], None

        content_value = ""
        reasoning_value = ""
        tool_call_deltas: list[dict[str, object]] = []
        finish_reason: str | None = None

        raw_finish = first_choice.get("finish_reason")
        if isinstance(raw_finish, str) and raw_finish:
            finish_reason = raw_finish

        delta = first_choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                content_value = content
            reasoning = delta.get("reasoning_content")
            if isinstance(reasoning, str):
                reasoning_value = reasoning
            elif isinstance(delta.get("reasoning"), str):
                reasoning_value = str(delta.get("reasoning"))
            tc = delta.get("tool_calls")
            if isinstance(tc, list):
                for item in tc:
                    if isinstance(item, dict):
                        tool_call_deltas.append(item)

        if not content_value:
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    content_value = content
                if not reasoning_value:
                    reasoning = message.get("reasoning_content")
                    if isinstance(reasoning, str):
                        reasoning_value = reasoning
                # Some non-streaming-style chunks put full tool_calls on message.
                if not tool_call_deltas:
                    tc = message.get("tool_calls")
                    if isinstance(tc, list):
                        for item in tc:
                            if isinstance(item, dict):
                                tool_call_deltas.append(item)

        if not content_value:
            text = first_choice.get("text")
            if isinstance(text, str):
                content_value = text

        return content_value, reasoning_value, tool_call_deltas, finish_reason

    def _configure_litellm(self) -> None:
        try:
            import litellm  # type: ignore
        except ImportError:
            return

        litellm.suppress_debug_info = True
        if hasattr(litellm, "set_verbose"):
            litellm.set_verbose = False
        if hasattr(litellm, "turn_off_message_logging"):
            litellm.turn_off_message_logging = True


class _ToolCallAccumulator:
    """Merge streaming `delta.tool_calls` items into complete `ToolCall`s.

    OpenAI (and any compatible function-calling API) splits a single tool
    invocation across many SSE chunks keyed by a stable `index`. The first
    chunk usually carries `id`, `type="function"`, and `function.name`.
    Subsequent chunks carry progressively longer prefixes of the JSON-encoded
    `function.arguments`. This accumulator joins them by index.

    Also tolerates providers that emit *complete* tool_calls (non-streaming-
    style) on a single chunk — in that case `feed` sees one delta and
    `finalize` just returns it.
    """

    def __init__(self) -> None:
        self._by_index: dict[int, dict[str, str]] = {}

    def feed(self, deltas: list[dict[str, object]]) -> None:
        for delta in deltas:
            if not isinstance(delta, dict):
                continue
            raw_index = delta.get("index")
            # Fallbacks: some providers omit index when there is only one tool
            # call; use its id if present, else 0.
            if isinstance(raw_index, int):
                index = raw_index
            else:
                index = len(self._by_index)
            entry = self._by_index.setdefault(
                index,
                {"id": "", "name": "", "args_text": ""},
            )
            call_id = delta.get("id")
            if isinstance(call_id, str) and call_id:
                entry["id"] = call_id
            function = delta.get("function")
            if isinstance(function, dict):
                name = function.get("name")
                if isinstance(name, str) and name:
                    entry["name"] = name
                args = function.get("arguments")
                if isinstance(args, str):
                    entry["args_text"] += args
                elif isinstance(args, dict):
                    # Already-complete tool_call (non-streaming shape); json-dump
                    # so finalize() can parse a single time.
                    entry["args_text"] = json.dumps(args)

    def finalize(self) -> list[ToolCall]:
        results: list[ToolCall] = []
        for index in sorted(self._by_index.keys()):
            entry = self._by_index[index]
            if not entry["name"]:
                continue
            arguments: dict[str, object] = {}
            args_text = entry["args_text"].strip()
            if args_text:
                try:
                    parsed = json.loads(args_text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict):
                    arguments = {str(k): v for k, v in parsed.items()}
            results.append(
                ToolCall(
                    id=entry["id"] or f"call_{index}",
                    name=entry["name"],
                    arguments=arguments,
                )
            )
        return results
