"""Syntactic validation of a raw AST dict against kernel_ast.schema.json.

This layer uses the standard JSON Schema validator (Draft 2020-12).
It answers: "is this a structurally valid kernel program?" — nothing more.

Semantic rules (e.g. probability.given ⊆ parents(target), no free value
variables in formula, sum.over is ground) are the job of
``semantic_validator``.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


class SyntacticError(Exception):
    """Raised when the AST dict violates kernel_ast.schema.json."""


def _default_schema_dir() -> Path:
    # project_root/causal_kernel/input/syntactic_validator.py -> project_root
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=4)
def _load_registry(schema_dir_str: str) -> Registry:
    schema_dir = Path(schema_dir_str)
    atom = json.loads((schema_dir / "atom.schema.json").read_text(encoding="utf-8"))
    kernel = json.loads((schema_dir / "kernel_ast.schema.json").read_text(encoding="utf-8"))
    result = json.loads((schema_dir / "query_result.schema.json").read_text(encoding="utf-8"))
    return Registry().with_resources(
        [
            (atom["$id"], Resource.from_contents(atom)),
            (kernel["$id"], Resource.from_contents(kernel)),
            (result["$id"], Resource.from_contents(result)),
        ]
    )


def _validate(payload: dict, schema_name: str, schema_dir: Path | None) -> dict:
    schema_dir = schema_dir or _default_schema_dir()
    registry = _load_registry(str(schema_dir))
    schema_doc = json.loads(
        (schema_dir / schema_name).read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema_doc, registry=registry)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        formatted = "; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise SyntacticError(formatted)
    return payload


def validate_ast(ast: dict, schema_dir: Path | None = None) -> dict:
    """Validate an AST dict against kernel_ast.schema.json.

    Returns the same dict unchanged on success.
    Raises SyntacticError with a structured failure report on failure.
    """
    return _validate(ast, "kernel_ast.schema.json", schema_dir)


def validate_result(result: dict, schema_dir: Path | None = None) -> dict:
    """Validate an outgoing result dict against query_result.schema.json.

    Used for self-checks before returning results to the caller.
    """
    return _validate(result, "query_result.schema.json", schema_dir)
