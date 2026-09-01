"""Residual Zero as a Model Context Protocol server. Read-only. Never writes CLEARED."""

from residual_zero.mcp.registry import call_tool, list_tools

__all__ = ["call_tool", "handle_rpc", "list_tools"]


def __getattr__(name: str):
    if name == "handle_rpc":
        from residual_zero.mcp.protocol import handle_rpc

        return handle_rpc
    raise AttributeError(name)
