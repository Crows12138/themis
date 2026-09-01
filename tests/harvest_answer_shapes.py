"""Regenerate ``tests/fixtures/answer_shapes.json`` from the suite itself.

Not collected as a test — a helper, run by hand when the snapshot beside it
goes stale::

    python tests/harvest_answer_shapes.py

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
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "answer_shapes.json"

if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

    import themis
    from themis import kernel

    seen: dict[str, dict] = {}
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
        except Exception:  # a harvest must never change what the suite does
            pass
        return envelope

    kernel.estimate = _watch
    themis.estimate = _watch

    import pytest

    pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "--tb=no",
                 str(ROOT / "tests")])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(seen, ensure_ascii=False, sort_keys=True, indent=0),
        encoding="utf-8")
    print(f"\nharvested {len(seen)} answer shapes -> {OUT}")
