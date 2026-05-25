"""themis-kb-causenet-mcp: MCP server exposing CauseNet for Themis."""
from .server import build_server, main

__version__ = "0.1.0-dev"
__all__ = ["build_server", "main"]
