"""Regenerate ``tests/fixtures/answer_shapes.json`` from the suite itself.

Not collected as a test — a helper, run by hand when the snapshot beside it
goes stale::

    python tests/harvest_answer_shapes.py
    python tests/harvest_answer_shapes.py --only aipw,tmle <test files...>

The snapshot exists because the sweep it feeds has to ask about the answers
this system really produces. Writing one program per estimator would sweep
what somebody thought to build; the gate would then be a measurement of the
author's imagination, and the shapes nobody thought of are exactly the ones
carrying leaves nobody checks.

So the shapes are collected rather than invented: patch the estimate entry
point, keep the first envelope seen for each ``numeric_estimate.method``
together with the program that produced it, and run the suite over it.

A snapshot is a copy, and a copy that states no relationship to the thing
it copies is the defect this repository keeps finding. This one states one:
the gate re-verifies every pair honestly before sweeping it, so a producer
that has moved away from the snapshot fails there rather than silently
sweeping a fossil.

**THE FULL RUN IS SERIAL AND TAKES HOURS**, because the collector patches an
entry point in this process and so cannot be distributed. When one producer
moved, re-collecting forty-four pairs confuses the unit of collection with
the unit of refresh. ``--only`` refreshes named shapes from named files and
merges them in.

What makes a targeted refresh honest is not running the files in suite order
— that is a proxy, and it fails: naming the obvious ``test_aipw.py`` for the
fitted diagnostics returned a DIFFERENT run of the same shape (n=3000 where
the snapshot holds n=4000, and three shapes lost a block entirely), which
would shrink a declared remainder because the sample changed rather than
because a hole closed. What makes it honest is PROVING sameness: same
program, same data digest, same size. So ``--only`` refuses any pair that
differs in those, and every run prints which test first produced each shape,
so the next targeted refresh is a roll-call instead of a search.

One thing a refresh cannot see: a producer that only ADDS a field leaves
every stored pair still valid, so the honest-first gate passes and the sweep
quietly measures envelopes nobody writes any more. A fossil that still
verifies is still a fossil. Ask instead which blocks lack what the producer
would now put there.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "answer_shapes.json"

#: What must match for a re-collected pair to be the same run rather than a
#: different one wearing the same method name.
SAME_RUN = ("data_hash", "sample_size")


def _parse(argv: list[str]) -> tuple[set[str], list[str]]:
    """``--only a,b <paths...>`` → the shapes wanted and where to look."""
    if not argv or argv[0] != "--only":
        return set(), [str(ROOT / "tests")]
    wanted = {name for name in argv[1].split(",") if name}
    paths = [str(ROOT / p) for p in argv[2:]] or [str(ROOT / "tests")]
    return wanted, paths


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

    import themis
    from themis import kernel

    wanted, paths = _parse(sys.argv[1:])

    seen: dict[str, dict] = {}
    #: Which test supplied each pair. The collection rule is "first envelope
    #: seen", so this is what turns the next targeted refresh into naming a
    #: file rather than searching for one.
    supplied_by: dict[str, str] = {}
    _real = kernel.estimate

    def _watch(program, data=None, **options):
        envelope = _real(program, data, **options)
        try:
            for result in envelope.get("results") or ():
                estimate = result.get("numeric_estimate")
                if not isinstance(estimate, dict):
                    continue
                method = str(estimate.get("method"))
                if method in seen or not result.get("derivation"):
                    continue
                source = program
                if not isinstance(source, dict):
                    source = json.loads(source)
                seen[method] = {"program": source, "result": result}
                supplied_by[method] = os.environ.get(
                    "PYTEST_CURRENT_TEST", "<unknown>")
        except Exception:  # a harvest must never change what the suite does
            pass
        return envelope

    kernel.estimate = _watch
    themis.estimate = _watch

    import pytest

    pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "--tb=no",
                 *paths])

    print("\nshapes seen, and the test that first produced each:")
    for method in sorted(seen):
        print(f"  {method:38s} {supplied_by[method]}")

    if not wanted:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(seen, ensure_ascii=False, sort_keys=True, indent=0),
            encoding="utf-8")
        print(f"\nharvested {len(seen)} answer shapes -> {OUT}")
        raise SystemExit(0)

    shapes = json.loads(OUT.read_text(encoding="utf-8"))
    missing = sorted(wanted - set(seen))
    if missing:
        raise SystemExit(
            f"\n{missing} not produced by those files; snapshot untouched")

    for method in sorted(wanted):
        was, now = shapes.get(method), seen[method]
        if was is None:
            continue
        if json.dumps(was["program"], sort_keys=True) != json.dumps(
                now["program"], sort_keys=True):
            raise SystemExit(
                f"\n{method}: a different PROGRAM produced this, so it is a "
                f"different run and not a refresh; snapshot untouched")
        for key in SAME_RUN:
            before = was["result"]["numeric_estimate"].get(key)
            after = now["result"]["numeric_estimate"].get(key)
            if before != after:
                raise SystemExit(
                    f"\n{method}: {key} {before!r} -> {after!r}, so it is a "
                    f"different run and not a refresh; snapshot untouched")

    for method in sorted(wanted):
        shapes[method] = seen[method]
    OUT.write_text(
        json.dumps(shapes, ensure_ascii=False, sort_keys=True, indent=0),
        encoding="utf-8")
    print(f"\nrefreshed {sorted(wanted)} -> {OUT} ({len(shapes)} shapes)")
