"""A digest is a claim about a set of columns; the set has to travel too.

``data_hash`` is a SHA-256 of the columns the estimator was handed — the
column NAMES mixed in, then their values. Read without that list, two
digests that differ say only "not the same run": they cannot say whether
what changed was the measurements or which columns were measured. Five
containers shipped the digest and none shipped its denominator, so the
one question a reproducibility fingerprint exists to answer — *the same
as what?* — had no answer anywhere on the envelope.

The rule is therefore about pairing, not about any one field: wherever a
container declares a ``…data_hash``, it declares the matching
``…data_columns``, and ``dependentRequired`` ties the two so a digest
cannot ship alone. Enforced against the schema rather than against a
list written here, so a container added tomorrow is inside the
denominator the day it is added.

The tie is ``dependentRequired`` and not ``required`` on purpose: two of
the five carry the digest optionally, and making the pair unconditional
would say something false about them — that they always fingerprint.
"""
from __future__ import annotations

import json
import pathlib

import pytest

_SCHEMA_DIR = (
    pathlib.Path(__file__).resolve().parents[1] / "themis" / "schemas"
)
_HASH_SUFFIX = "data_hash"
_COLUMNS_SUFFIX = "data_columns"


def _schema_files() -> list[pathlib.Path]:
    """Every shipped schema. Globbed, so the rule has no list to update."""
    return sorted(_SCHEMA_DIR.glob("*.json"))


def _containers(node, path: str = "<root>"):
    """Yield (path, object-schema) for every object schema in the document.

    Walks values rather than keys, so a container reached through
    ``$defs`` / ``allOf`` / ``items`` / a property named ``properties``
    is found the same way as one reached directly.
    """
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            yield path, node
        for key, value in node.items():
            yield from _containers(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _containers(value, f"{path}/{i}")


def _pairings(doc) -> list[tuple[str, dict, str, str]]:
    """(path, container, hash_key, columns_key) for every digest declared."""
    out = []
    for path, container in _containers(doc):
        for key in container["properties"]:
            if key.endswith(_HASH_SUFFIX):
                prefix = key[: -len(_HASH_SUFFIX)]
                out.append((path, container, key, prefix + _COLUMNS_SUFFIX))
    return out


def _violations(doc) -> list[str]:
    """Every digest in ``doc`` that is not paired with its denominator.

    One function, used by the rule and by the counterexample below, so
    the thing shown to fire is the thing that guards.
    """
    problems = []
    for path, container, hash_key, columns_key in _pairings(doc):
        declared = container["properties"].get(columns_key)
        if declared is None:
            problems.append(
                f"{path} declares {hash_key} but not {columns_key}"
            )
            continue
        if declared.get("type") != "array" or \
                (declared.get("items") or {}).get("type") != "string":
            problems.append(
                f"{path}/{columns_key} must be an array of column names; "
                f"got {declared.get('type')!r}"
            )
        tied = (container.get("dependentRequired") or {}).get(hash_key) or []
        if columns_key not in tied:
            problems.append(
                f"{path} does not require {columns_key} when {hash_key} "
                f"is present (dependentRequired[{hash_key}] = {tied!r})"
            )
    return problems


@pytest.mark.parametrize("path", _schema_files(), ids=lambda p: p.name)
def test_every_declared_digest_declares_what_it_covers(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert not _violations(doc)


def test_the_rule_has_something_to_check():
    """A pairing rule over zero pairings passes by saying nothing."""
    found = [
        (p.name, path, hash_key)
        for p in _schema_files()
        for path, _, hash_key, _ in _pairings(
            json.loads(p.read_text(encoding="utf-8"))
        )
    ]
    assert len(found) >= 5, found


@pytest.mark.parametrize("break_it", ["drop_property", "drop_tie", "wrong_type"])
def test_the_rule_says_no_to_a_digest_without_its_denominator(break_it):
    """The counterexample: each way of shipping a lone digest is caught."""
    doc = json.loads(
        (_SCHEMA_DIR / "query_result.schema.json").read_text(encoding="utf-8")
    )
    path, container, hash_key, columns_key = _pairings(doc)[0]
    if break_it == "drop_property":
        del container["properties"][columns_key]
    elif break_it == "drop_tie":
        del container["dependentRequired"][hash_key]
    else:
        container["properties"][columns_key] = {"type": "string"}

    problems = _violations(doc)
    assert problems, f"{break_it} on {path}/{hash_key} was not caught"
    assert any(columns_key in p for p in problems), problems
