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

from ..audits import Artifact, artifact_of


class SyntacticError(Exception):
    """Raised when the AST dict violates kernel_ast.schema.json."""


def _default_schema_dir() -> Path:
    # themis/input/syntactic_validator.py -> themis/schemas/
    # Schemas live inside the package so they ship with the wheel
    # (`pip install themis-causal` puts themis/schemas/ alongside the
    # rest of the package; importing from a git clone resolves to the
    # same path because parent.parent / "schemas" works in both modes).
    return Path(__file__).resolve().parent.parent / "schemas"


@lru_cache(maxsize=4)
def _load_registry(schema_dir_str: str) -> Registry:
    """Every shipped schema, by its own ``$id``.

    Globbed rather than listed. The list it replaced named four of seven,
    which was invisible while nothing outside those four was referenced —
    and the orientation artifacts reference each other by ``$id`` (a session
    embeds a propagation and a question set; an export embeds a session),
    so a document missing from the registry is a reference that resolves to
    nothing and a subtree that goes unchecked while reading as checked.
    """
    schema_dir = Path(schema_dir_str)
    resources = []
    for path in sorted(schema_dir.glob("*.schema.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


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

    Used for self-checks before returning results to the caller. Named
    explicitly rather than routed through :func:`validate_artifact`, because
    an envelope carries no ``kind`` of its own and its callers know what they
    built: routing it would let a stray ``kind`` on an envelope send it to
    somebody else's document.
    """
    return _validate(result, Artifact.QUERY_RESULT.schema, schema_dir)


def validate_artifact(payload: dict, schema_dir: Path | None = None) -> dict:
    """Validate any artifact against the schema its own ``kind`` names.

    One entry point for all six, because which document describes a payload
    is not a decision a producer should be making a second time — the
    recogniser (:func:`themis.audits.artifact_of`) already answers it for the
    audit layer, and answering it differently here is how the two lists came
    apart in the first place.
    """
    return _validate(payload, artifact_of(payload).schema, schema_dir)
