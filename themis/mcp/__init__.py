"""MCP (Model Context Protocol) server wrapping for Themis (slice A1(b)).

Exposes Themis' eight public JSON-in/JSON-out entry points as MCP tools
(``themis_run`` / ``themis_apply_patch_and_run`` / ``themis_verify`` /
``themis_verify_data_gap_report`` / ``themis_verify_bounds_result`` /
``themis_estimate`` / ``themis_discover`` / ``themis_list_resources``)
and twelve prompt / schema files as MCP resources, so any MCP-capable
LLM client (Claude Code, Claude Desktop, etc.) can drive the kernel
without copy-pasting prompts and inputs by hand.

Public Python surface: ``build_server()`` constructs the FastMCP app
for in-process tests; ``main()`` runs it over stdio (the default MCP
transport).

The server itself does **not** call any LLM internally — that would
violate the kernel's "no LLM inside `themis/*`" rule. The MCP client
is responsible for the NL↔JSON translation, using the prompts exposed
as resources.

See ``themis/mcp/server.py`` for the entry point and
``themis/mcp/README.md`` for client setup instructions.
"""

from .server import build_server, main

__all__ = ["build_server", "main"]
