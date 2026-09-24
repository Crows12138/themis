"""What a language model is handed of an artifact: the record, folded to fit.

The kernel's envelope is written for the verifier. It carries every cell
of every table the kernel needed, every step of the chain, every row of a
survival table, so that an audit can recompute the answer without trusting
the kernel. Its size is therefore set by the question — how many parents a
variable has, how many rows the data had — and it has no ceiling, nor
should it: whatever is cut from it is something an audit can no longer
check.

A model reading it has a ceiling. Claude Code warns at 10,000 tokens and
writes anything past 25,000 to a file, which a client with no file access
never reads; a model asked to write a reply pays for every character. So a
model is not handed the record. It is handed the record with whatever does
not fit folded in place into a marker — ``{"omitted": {...}}`` — that says
how large the folded part is and gives the JSON Pointer (RFC 6901) that
fetches it, and :func:`part` fetches it under the same budget, so a fold
can be followed as far down as a reader needs. Nothing is summarised or
reworded. An unfolded value is the record's own value, and following every
marker gives back the record exactly.

Which parts fold first is a judgement, declared here once rather than made
per call. The program echo goes first, because the caller wrote it; then
the derivation chain, which is the verifier's; then the flat
``missing_information`` list, whose items the other two gap surfaces say
again, grouped. What never folds is the answer: the status, what kind of
question it was, the value or interval, the tier, the assumption ledger,
and the name and verdict of each audit. Everything else shares what is
left — the smaller parts kept whole, the larger cut back evenly — and a
list that is cut keeps its head and says how many items follow.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

#: Characters of compact JSON. Claude Code warns at 10,000 tokens and moves
#: anything past 25,000 to a file; how many characters a token is depends on
#: the text, so this is set well under the warning line rather than at it.
DEFAULT_BUDGET = 24_000

#: The one key of a marker. No envelope field is called this, so a marker
#: cannot be mistaken for part of the record.
FOLD = "omitted"

Path = tuple[str | int, ...]
Pattern = tuple[str, ...]

#: The answer. Never folded, and charged before anything else shares.
KEEP: tuple[Pattern, ...] = (
    ("result_id",),
    ("results", "*", "status"),
    ("results", "*", "query_kind"),
    ("results", "*", "query_id"),
    ("results", "*", "numeric_result"),
    ("results", "*", "structural_result"),
    ("results", "*", "data_gap_report", "answer_tier"),
    ("results", "*", "extensions", "assumption_ledger"),
    ("audits", "*", "*", "audit"),
    ("audits", "*", "*", "ok"),
)

#: Folded as soon as the object holding them does not fit.
FIRST: tuple[Pattern, ...] = (
    ("program",),
    ("merged_program",),
    ("results", "*", "derivation"),
    ("results", "*", "missing_information"),
)


def size(value: Any) -> int:
    """Characters of ``value`` as compact JSON — what a reader is sent."""
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def pointer(path: Path) -> str:
    """RFC 6901: ``~`` and ``/`` inside a key are escaped as ``~0``, ``~1``."""
    return "".join(
        "/" + str(step).replace("~", "~0").replace("/", "~1") for step in path)


def resolve(artifact: Any, where: str) -> tuple[Any, Path]:
    """The value a pointer names, and its path. Raises ``KeyError`` with
    the pointer when nothing is there."""
    if where in ("", "/"):
        return artifact, ()
    if not where.startswith("/"):
        raise KeyError(f"{where!r} is not a JSON Pointer (it must start with /)")
    node: Any = artifact
    path: Path = ()
    for raw in where[1:].split("/"):
        step = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not step.isdigit() or int(step) >= len(node):
                raise KeyError(f"{where!r}: no item {step!r} in a list of {len(node)}")
            node, path = node[int(step)], (*path, int(step))
        elif isinstance(node, dict):
            if step not in node:
                raise KeyError(f"{where!r}: no key {step!r}")
            node, path = node[step], (*path, step)
        else:
            raise KeyError(f"{where!r}: {pointer(path) or '/'} holds a value, not a container")
    return node, path


def view(artifact: Any, budget: int = DEFAULT_BUDGET) -> Any:
    """The artifact, unchanged if it fits; otherwise folded to fit.

    It exceeds ``budget`` only when the parts in :data:`KEEP` alone do.
    """
    return _Folding().fit(artifact, budget, ())


def part(artifact: Any, where: str, start: int = 0,
         budget: int = DEFAULT_BUDGET) -> dict:
    """What a marker points at, folded to fit in its turn.

    A list or a string can be long in itself rather than deep, so for
    those ``start`` says where to resume: the items (or characters) before
    it were handed over already. A list that is cut again ends in a marker
    whose ``from`` is the next ``start``; a string that is cut carries
    ``next``, absent once the end has been reached.
    """
    node, path = resolve(artifact, where)
    frame = {"pointer": pointer(path), "from": start, "value": None}
    room = budget - size(frame) - len(',"next":') - 12
    if isinstance(node, list):
        frame["value"] = _Folding().fit_list(node, room, path, start)
        return frame
    if isinstance(node, str):
        text = node[start:]
        cut = _longest_prefix(text, room)
        frame["value"] = text[:cut]
        if start + cut < len(node):
            frame["next"] = start + cut
        return frame
    del frame["from"]
    frame["value"] = _Folding().fit(node, room, path)
    return frame


# ------------------------------------------------------------------ fitting


def _matches(pattern: Pattern, path: Path) -> bool:
    return len(pattern) == len(path) and all(
        p == "*" or p == str(k) for p, k in zip(pattern, path))


def _opens(path: Path) -> bool:
    """Whether something the reader must see lies strictly inside ``path``,
    so that it may be cut back but never folded whole."""
    return any(len(p) > len(path) and _matches(p[:len(path)], path)
               for p in KEEP)


def _kept(path: Path) -> bool:
    return any(_matches(p, path) for p in KEEP)


def _first(path: Path) -> bool:
    return any(_matches(p, path) for p in FIRST)


def _marker(path: Path, value: Any, start: int = 0,
            chars: int | None = None) -> dict:
    """``chars`` is passed when the caller already knows it — a list cut
    item by item would otherwise re-measure its whole tail at every item."""
    said: dict[str, Any] = {"pointer": pointer(path)}
    if isinstance(value, list):
        said["items"] = len(value) - start
        if start:
            said["from"] = start
    if chars is None:
        chars = size(value[start:] if isinstance(value, list) else value)
    said["chars"] = chars
    return {FOLD: said}


class _Folding:
    """One fitting of one artifact.

    Room is shared among the parts of an object by first charging each its
    FLOOR — what it measures folded as far as it can be — so a part's floor
    is asked for at every level above it. It is kept once known, keyed by
    the part's identity and path, both fixed for as long as one call runs;
    without that, each level would fold everything below it again.
    """

    def __init__(self) -> None:
        self._floors: dict[tuple[int, Path], Any] = {}

    def floor(self, value: Any, path: Path) -> Any:
        key = (id(value), path)
        if key not in self._floors:
            self._floors[key] = self.fit(value, 0, path)
        return self._floors[key]

    def fit(self, value: Any, budget: int, path: Path) -> Any:
        if size(value) <= budget:
            return value
        if isinstance(value, dict):
            fitted: Any = self.fit_dict(value, budget, path)
        elif isinstance(value, list):
            fitted = self.fit_list(value, budget, path, 0)
        else:
            fitted = value
        if size(fitted) <= budget or _opens(path):
            return fitted
        # A marker that would not be smaller than what it replaces saves
        # nothing and hides the value.
        marker = _marker(path, value)
        return marker if size(marker) < size(fitted) else fitted

    def fit_dict(self, d: dict, budget: int, path: Path) -> dict:
        out: dict[str, Any] = {}
        spent = 2 + max(len(d) - 1, 0) + sum(size(k) + 1 for k in d)
        open_: list[str] = []
        for key, value in d.items():
            here = (*path, key)
            if _kept(here):
                out[key] = value
                spent += size(value)
            elif _first(here) and not _opens(here):
                out[key] = _marker(here, value)
                spent += size(out[key])
            else:
                open_.append(key)
        shared = self.share_out([d[k] for k in open_],
                                [(*path, k) for k in open_], budget - spent)
        out.update(zip(open_, shared))
        return {key: out[key] for key in d}

    def share_out(self, values: list, paths: list[Path], room: int) -> list:
        """``values`` fitted into ``room`` between them.

        Each is charged its floor first, and only the room above the floors
        is shared: smallest first, each kept whole while it is within an
        even share of what is left, the rest cut back to that share.
        Sharing the whole room instead left the parts that came last with
        nothing, and the markers they were folded into were never paid for,
        so a view ran past its budget by the size of those markers.
        """
        floors = [self.floor(v, p) for v, p in zip(values, paths)]
        least = [size(f) for f in floors]
        above = room - sum(least)
        order = sorted(range(len(values)),
                       key=lambda i: size(values[i]) - least[i])
        out: list = [None] * len(values)
        for n, i in enumerate(order):
            extra = max(above, 0) // (len(values) - n)
            out[i] = (floors[i] if extra == 0
                      else self.fit(values[i], least[i] + extra, paths[i]))
            above -= size(out[i]) - least[i]
        return out

    def fit_list(self, items: Sequence, budget: int, path: Path,
                 start: int) -> list:
        """Items from ``start`` on. A list whose every item holds part of
        the answer is shared out like an object's fields; any other list
        keeps its head and ends in a marker for the rest."""
        rest = list(items[start:])
        if _opens((*path, start)):
            return self.share_out(
                rest, [(*path, start + i) for i in range(len(rest))],
                budget - 2 - max(len(rest) - 1, 0))
        sizes = [size(item) for item in rest]
        # tail[i]: what items[start + i:] measures as a list of its own.
        tail_chars = [0] * (len(rest) + 1)
        for i in range(len(rest) - 1, -1, -1):
            tail_chars[i] = tail_chars[i + 1] + sizes[i] + 1
        out: list[Any] = []
        spent = 2
        for i, item in enumerate(rest):
            tail = _marker(path, items, start + i, chars=tail_chars[i] + 1)
            sep = 1 if out else 0
            last = i == len(rest) - 1
            reserve = 0 if last else size(tail) + 1
            if spent + sep + sizes[i] + reserve <= budget:
                out.append(item)
                spent += sep + sizes[i]
                continue
            if not out:
                # Not even the first item fits whole: hand it over cut
                # back, so a list of one large item still shows its shape.
                room = budget - spent - reserve
                fitted = self.fit(item, room, (*path, start + i))
                if size(fitted) <= room and FOLD not in (
                        fitted if isinstance(fitted, dict) else {}):
                    out.append(fitted)
                    spent += size(fitted)
                    continue
            out.append(tail)
            break
        return out


def _longest_prefix(text: str, room: int) -> int:
    """How many leading characters of ``text`` fit in ``room`` as a JSON
    string — escapes make that fewer than ``room`` when the text has any."""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if size(text[:mid]) <= room:
            lo = mid
        else:
            hi = mid - 1
    return lo
