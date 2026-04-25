"""MCP (Model Context Protocol) server wrapping for Themis (slice A1(b)).

Exposes Themis' four public JSON-in/JSON-out entry points as MCP tools
and the prompt / schema files as MCP resources, so any MCP-capable LLM
client (Claude Code, Claude Desktop, etc.) can drive the kernel without
copy-pasting prompts and inputs by hand.

The server itself does **not** call any LLM internally — that would
violate the kernel's "no LLM inside `themis/*`" rule. The MCP client
is responsible for the NL↔JSON translation, using the prompts exposed
as resources.

See ``themis/mcp/server.py`` for the entry point and
``themis/mcp/README.md`` for client setup instructions.
"""

from .server import build_server, main

__all__ = ["build_server", "main"]
