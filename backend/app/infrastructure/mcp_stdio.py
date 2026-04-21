"""MCP over stdio 客户端。

`MCPStdioClient` 启动外部 MCP server 子进程，以 JSON-RPC（content-length
分帧）收发消息，封装 `initialize / list_tools / call_tool`；生命周期用
上下文管理器或 `close()` 显式回收子进程 / 流。是 `MCPService` 的传输层。
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from ..domain import MCPServerDefinition, MCPToolDefinition


class MCPTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class MCPToolCallResult:
    summary: str
    payload: dict[str, object]
    citations: list[str]
    ok: bool
    error: str | None = None


class MCPStdioClient:
    _READ_TIMEOUT_SECONDS = 10.0

    def __init__(self, server: MCPServerDefinition) -> None:
        self.server = server
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def list_tools(self) -> list[MCPToolDefinition]:
        try:
            self._start()
            self._initialize()
            response = self._request("tools/list", {})
            return self._extract_tools(response)
        finally:
            self.close()

    def call_tool(self, tool_name: str, arguments: dict[str, object]) -> MCPToolCallResult:
        try:
            self._start()
            self._initialize()
            response = self._request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            return self._extract_call_result(response)
        finally:
            self.close()

    def close(self) -> None:
        if self._process is None:
            return
        try:
            if self._process.stdin is not None:
                self._process.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._process.poll() is None:
                self._process.terminate()
                self._process.wait(timeout=2)
        except Exception:  # noqa: BLE001
            try:
                self._process.kill()
            except Exception:  # noqa: BLE001
                pass
        self._process = None

    def _start(self) -> None:
        if self._process is not None:
            return
        if not self.server.command.strip():
            raise MCPTransportError(f"MCP stdio server `{self.server.id}` is missing a command.")
        env = os.environ.copy()
        env.update(self.server.env)
        cwd = self.server.working_directory or None
        if cwd:
            Path(cwd).mkdir(parents=True, exist_ok=True)
        self._process = subprocess.Popen(
            [self.server.command, *self.server.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

    def _initialize(self) -> None:
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "more-backend", "version": "0.1.0"},
            },
        )
        if "error" in response:
            raise MCPTransportError(f"MCP initialize failed: {response['error']}")
        self._notify("notifications/initialized", {})

    def _request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self._request_id += 1
        request_id = self._request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._receive()
            if message.get("id") != request_id:
                continue
            return message

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: dict[str, object]) -> None:
        if self._process is None or self._process.stdin is None:
            raise MCPTransportError("MCP stdio process is not available.")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._process.stdin.write(header + body)
        self._process.stdin.flush()

    def _receive(self) -> dict[str, object]:
        result: dict[str, object] | None = None
        error: BaseException | None = None

        def receive_frame() -> None:
            nonlocal result, error
            try:
                result = self._receive_frame()
            except BaseException as exc:  # noqa: BLE001
                error = exc

        thread = threading.Thread(target=receive_frame, daemon=True)
        thread.start()
        thread.join(self._READ_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise MCPTransportError(
                f"MCP stdio server `{self.server.id}` did not return a complete frame within "
                f"{self._READ_TIMEOUT_SECONDS:.0f}s."
            )
        if error is not None:
            raise MCPTransportError(str(error)) from error
        if result is None:
            raise MCPTransportError(f"MCP stdio server `{self.server.id}` returned no message.")
        return result

    def _receive_frame(self) -> dict[str, object]:
        if self._process is None or self._process.stdout is None:
            raise MCPTransportError("MCP stdio process is not available.")
        headers: dict[str, str] = {}
        while True:
            line = self._process.stdout.readline()
            if not line:
                stderr = b""
                if self._process.stderr is not None:
                    stderr = self._process.stderr.read() or b""
                raise MCPTransportError(f"MCP stdio server `{self.server.id}` closed unexpectedly: {stderr.decode('utf-8', errors='ignore')}")
            decoded = line.decode("ascii", errors="ignore").strip()
            if not decoded:
                break
            key, _, value = decoded.partition(":")
            headers[key.casefold()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            raise MCPTransportError(f"MCP stdio server `{self.server.id}` returned an invalid frame header: {headers}")
        body = self._process.stdout.read(length)
        if len(body) != length:
            raise MCPTransportError(f"MCP stdio server `{self.server.id}` returned a truncated frame.")
        message = json.loads(body.decode("utf-8"))
        if not isinstance(message, dict):
            raise MCPTransportError(f"MCP stdio server `{self.server.id}` returned a non-object message.")
        return message

    @staticmethod
    def _extract_tools(message: dict[str, object]) -> list[MCPToolDefinition]:
        result = dict(message.get("result") or {})
        raw_tools = result.get("tools") or []
        tools: list[MCPToolDefinition] = []
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            tools.append(
                MCPToolDefinition(
                    name=name,
                    description=str(item.get("description") or ""),
                    input_schema=dict(item.get("inputSchema") or item.get("input_schema") or {}),
                    execution_mode="stdio",
                    builtin_action="",
                    enabled=True,
                )
            )
        return tools

    @staticmethod
    def _extract_call_result(message: dict[str, object]) -> MCPToolCallResult:
        result = dict(message.get("result") or {})
        is_error = bool(result.get("isError", False))
        content = result.get("content") or []
        text_chunks: list[str] = []
        citations: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    text_chunks.append(text)
                    citations.extend(_extract_citations_from_text(text))
        summary = "\n\n".join(text_chunks).strip()
        if not summary:
            summary = str(result.get("structuredContent") or result.get("content") or "").strip()
        error = None
        if is_error:
            error = summary or "MCP tool returned an error."
        return MCPToolCallResult(
            summary=summary,
            payload={"result": result},
            citations=sorted(set(citations)),
            ok=not is_error,
            error=error,
        )


def _extract_citations_from_text(text: str) -> list[str]:
    citations: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("path:"):
            citations.append(stripped.removeprefix("path:").strip())
    return citations


__all__ = ["MCPStdioClient", "MCPToolCallResult", "MCPTransportError"]
