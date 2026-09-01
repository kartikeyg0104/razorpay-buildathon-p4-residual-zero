"""JSON-RPC 2.0 MCP subset. Content-Length framing and newline JSON. No writes."""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO, Mapping

from residual_zero.mcp.registry import (
    INSTRUCTIONS,
    SERVER_NAME,
    SERVER_VERSION,
    call_tool,
    list_tools,
)

PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")
DEFAULT_PROTOCOL = "2024-11-05"


def _protocol_version(requested: object) -> str:
    text = str(requested or "")
    if text in PROTOCOL_VERSIONS:
        return text
    return DEFAULT_PROTOCOL


def handle_rpc(message: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a JSON-RPC response, or None for a notification."""
    method = str(message.get("method") or "")
    req_id = message.get("id", None)
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if req_id is None and method.startswith("notifications/"):
        return None
    try:
        result = _dispatch(method, params)
    except ValueError as exc:
        if req_id is None:
            return None
        if method == "tools/call":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(exc), "written": False})}],
                    "isError": True,
                },
            }
        code = -32601 if "not implemented" in str(exc) else -32602
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": str(exc)},
        }
    if req_id is None:
        return None
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _dispatch(method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    if method == "initialize":
        return {
            "protocolVersion": _protocol_version(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }
    if method in {"ping", "notifications/initialized", "notifications/cancelled"}:
        return {}
    if method == "tools/list":
        return {"tools": list_tools()}
    if method == "resources/list":
        return {"resources": []}
    if method == "prompts/list":
        return {"prompts": []}
    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        payload = call_tool(name, arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
            "isError": False,
        }
    raise ValueError(f"method {method!r} is not implemented")


def encode_message(message: Mapping[str, Any]) -> bytes:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    line = stream.readline()
    if not line:
        return None
    if line.lstrip().startswith(b"{"):
        payload = json.loads(line.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON-RPC message must be an object")
        return payload
    headers: dict[str, str] = {}
    current = line
    while current not in (b"\r\n", b"\n", b""):
        decoded = current.decode("ascii", errors="replace")
        if ":" in decoded:
            key, value = decoded.split(":", 1)
            headers[key.strip().casefold()] = value.strip()
        current = stream.readline()
        if not current:
            return None
    length = int(headers.get("content-length") or "0")
    if length <= 0:
        raise ValueError("MCP frame missing Content-Length")
    raw = stream.read(length)
    if len(raw) < length:
        return None
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON-RPC message must be an object")
    return payload


def serve(stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout.buffer
    while True:
        try:
            message = read_message(incoming)
        except ValueError as exc:
            outgoing.write(
                encode_message(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
                )
            )
            outgoing.flush()
            continue
        if message is None:
            return
        reply = handle_rpc(message)
        if reply is None:
            continue
        outgoing.write(encode_message(reply))
        outgoing.flush()
