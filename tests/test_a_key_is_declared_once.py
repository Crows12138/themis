"""A JSON object that declares a key twice keeps the last one, silently.

Nothing raises: ``json.load`` resolves the repeat by overwriting, so the
earlier declaration is still in the file, still readable, and no longer
in effect. In a schema that is the worst version of the problem —
``additionalProperties: false`` makes the surviving declaration the one
that decides what an envelope may carry, and the dead one is what a
person reads when asking whether the field exists.

Both duplicates this found had the same shape and it is worth naming:
neither author knew the key was already there. One had been described by
WHO WROTE IT rather than by what it is, so the other writer did not
recognise the slot as its own; the other was a bare re-declaration at the
end of a long object, which won over the described one above it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


_PACKAGE = Path(__file__).parent.parent / "themis"


#: The browser build tree, which belongs to a different toolchain: its
#: ``tsconfig.*.json`` are JSONC, so a JSON parser is right to reject them
#: and this gate would be wrong to call that a defect.
_NOT_OURS = _PACKAGE / "web" / "frontend"


def _shipped_json():
    """Every JSON file the package ships, found rather than listed."""
    return sorted(
        p for p in _PACKAGE.rglob("*.json")
        if _NOT_OURS not in p.parents
    )


def test_there_are_json_files_to_check():
    """The denominator is discovered, so it has to be shown to be non-empty."""
    assert len(_shipped_json()) >= 2


@pytest.mark.parametrize(
    "path", _shipped_json(), ids=lambda p: p.name)
def test_no_object_declares_the_same_key_twice(path):
    repeats: list[tuple[str, list[str]]] = []

    def hook(pairs):
        seen: dict = {}
        for key, value in pairs:
            if key in seen:
                repeats.append((key, [k for k, _ in pairs]))
            seen[key] = value
        return seen

    json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)

    assert not repeats, (
        f"{path.name} declares a key twice inside one object, and JSON "
        f"resolves that by keeping the LAST — so the earlier declaration is "
        f"dead text that still reads as if it were in force: "
        + "; ".join(
            f"{key!r} among {siblings}" for key, siblings in repeats
        )
    )
