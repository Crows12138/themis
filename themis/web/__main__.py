"""``python -m themis.web`` — start the local UI server.

Defaults: bind to 127.0.0.1:8000. Use ``--host 0.0.0.0`` to share on
the local network.

This is a development server. A public deployment puts something in
front of it, and decides one more thing: whether it has a model behind
it, which ``THEMIS_WEB_LLM`` says and :mod:`themis.web.app` reads.
"""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m themis.web")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000,
                        help="bind port (default 8000)")
    parser.add_argument("--reload", action="store_true",
                        help="auto-reload on code changes (dev mode)")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run(
        "themis.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
