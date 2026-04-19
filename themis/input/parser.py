"""Parse textual DSL or JSON input into a raw AST dict.

v0.1 accepts JSON only. A textual surface syntax may be added later
without changing the downstream pipeline.
"""
from __future__ import annotations

import json


def parse_json(source: str | bytes) -> dict:
    """Parse a JSON string/bytes into a raw AST dict.

    The returned dict has not been validated yet — call
    ``syntactic_validator`` next.
    """
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    return json.loads(source)


def parse_dsl(source: str) -> dict:
    """Parse the textual DSL (v0.2+) into a raw AST dict.

    Not implemented in v0.1.
    """
    raise NotImplementedError
