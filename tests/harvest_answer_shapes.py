"""Regenerate ``tests/fixtures/answer_shapes.json`` from the suite itself.

Not collected as a test — a helper, run by hand when the snapshot beside it
goes stale::

    python tests/harvest_answer_shapes.py
    python tests/harvest_answer_shapes.py --only aipw,tmle <test files...>
    python tests/harvest_answer_shapes.py --structural [test files...]

The snapshot exists because the sweep it feeds has to ask about the answers
this system really produces. Writing one program per estimator would sweep
what somebody thought to build; the gate would then be a measurement of the
author's imagination, and the shapes nobody thought of are exactly the ones
carrying leaves nobody checks.

So the shapes are collected rather than invented: patch the estimate entry
point, keep the first envelope seen for each ``numeric_estimate.method``
together with the program that produced it, and run the suite over it.

That collected answers WITH A NUMBER, and nothing else, for twelve
frontiers. ``kernel.estimate`` takes data; the identification-only entry is
``kernel.run``, which nothing here watched, so "answer shape" quietly meant
"answer that carries an estimate". The fifteen cases this repository
documents in ``docs/l3_simulation`` produce no numeric answer at all —
eleven of them come back ``needs_investigation``, which is what the data-gap
diagnosis IS — and they carry leaf shapes the gate had never asked about, in
a top-level block it had never seen.

Those answers are collected from ``run``, and they are kept on a different
rule, because keying them by method is not available and keying them by
route would enumerate variants rather than cover shapes. A structural row
earns its place by carrying a LEAF SHAPE no row already kept carries, which
is the gate's own question asked of the corpus: rows stop being added when
shapes stop being new. It is order-dependent, like "first envelope seen"
above, and for the same reason — the suite's order is what produced it.

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


def _parse(argv: list[str]) -> tuple[str, set[str], list[str]]:
    """The three modes, as ``(mode, shapes wanted, where to look)``.

    ``--only`` refreshes named shapes; ``--structural`` adds the answers
    that carry no number to the snapshot already on disk, which is what a
    full re-collection must not be asked to do — re-running every numeric
    row would move the declared remainder because the sample moved rather
    than because a hole opened or closed.
    """
    if argv and argv[0] == "--structural":
        paths = [str(ROOT / p) for p in argv[1:]] or [str(ROOT / "tests")]
        return "structural", set(), paths
    if not argv or argv[0] != "--only":
        return "all", set(), [str(ROOT / "tests")]
    wanted = {name for name in argv[1].split(",") if name}
    paths = [str(ROOT / p) for p in argv[2:]] or [str(ROOT / "tests")]
    return "only", wanted, paths


def _leaf_shapes(node, path=(), out=None) -> set[str]:
    """Every leaf of an envelope, named with list positions collapsed.

    The same walk the gate sweeps with. It is written twice on purpose —
    the collector must not import the gate it feeds, or a narrowing of one
    would narrow the other and the two would agree about nothing.
    """
    out = set() if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            _leaf_shapes(value, path + (key,), out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _leaf_shapes(value, path + (index,), out)
    else:
        out.add(".".join("[]" if isinstance(p, int) else p for p in path))
    return out


def _structural_name(result: dict) -> str:
    """What a structural answer is called: what it is, in three words.

    No ``numeric_estimate.method`` to borrow, so the name is read off the
    envelope — the status it came back with, the question it answers, and
    the rule its reasoning ends in (or ``none``, which is what a gap
    diagnosis has).
    """
    steps = result.get("derivation")
    if isinstance(steps, dict):
        steps = steps.get("steps")
    terminal = steps[-1].get("rule") if steps else "none"
    return (f"{result.get('status')}:{result.get('query_kind')}:{terminal}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))

    import themis
    from themis import kernel

    mode, wanted, paths = _parse(sys.argv[1:])

    seen: dict[str, dict] = {}
    #: Which test supplied each pair. The collection rule is "first envelope
    #: seen", so this is what turns the next targeted refresh into naming a
    #: file rather than searching for one.
    supplied_by: dict[str, str] = {}
    #: Leaf shapes some kept row already carries. A structural row earns
    #: its place by adding one; a numeric row is kept by method whatever it
    #: adds, and contributes what it covers.
    covered: set[str] = set()
    if mode == "structural":
        for row in json.loads(OUT.read_text(encoding="utf-8")).values():
            covered |= _leaf_shapes(row["result"])
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
                covered.update(_leaf_shapes(result))
                supplied_by[method] = os.environ.get(
                    "PYTEST_CURRENT_TEST", "<unknown>")
        except Exception:  # a harvest must never change what the suite does
            pass
        return envelope

    if mode != "structural":
        kernel.estimate = _watch
        themis.estimate = _watch

    #: Candidate structural rows, first envelope seen per name. Which of
    #: them are KEPT is decided after the suite, in one deterministic pass,
    #: so the corpus does not depend on whether a structural answer
    #: happened to run before the numeric row that already covers it.
    candidates: dict[str, dict] = {}
    _real_run = kernel.run

    def _watch_run(program):
        envelope = _real_run(program)
        try:
            source = program
            if not isinstance(source, dict):
                source = json.loads(source)
            for result in envelope.get("results") or ():
                if isinstance(result.get("numeric_estimate"), dict):
                    continue  # collected by method, above
                name = _structural_name(result)
                if name in candidates:
                    continue
                candidates[name] = {
                    "program": source, "result": result,
                    "test": os.environ.get("PYTEST_CURRENT_TEST", "<unknown>")}
        except Exception:  # a harvest must never change what the suite does
            pass
        return envelope

    kernel.run = _watch_run
    themis.run = _watch_run

    import pytest

    pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "--tb=no",
                 *paths])

    # The second pass: a structural row is kept when it brings a leaf shape
    # nothing kept before it carries. Walked in name order rather than in
    # suite order, so the corpus is the same corpus whichever way the suite
    # was scheduled, and the numeric rows go first because they are kept
    # whatever they add.
    for name in sorted(candidates):
        row = candidates[name]
        mine = _leaf_shapes(row["result"])
        if not mine - covered:
            continue
        covered.update(mine)
        seen[name] = {"program": row["program"], "result": row["result"]}
        supplied_by[name] = row["test"]

    print(f"\nstructural answers seen: {len(candidates)} distinct names, "
          f"{len(candidates) and len([n for n in candidates if n in seen])} "
          f"kept for the shapes they bring")
    print("\nshapes seen, and the test that first produced each:")
    for method in sorted(seen):
        print(f"  {method:38s} {supplied_by[method]}")

    if mode == "structural":
        shapes = json.loads(OUT.read_text(encoding="utf-8"))
        added = sorted(set(seen) - set(shapes))
        shapes.update({name: seen[name] for name in added})
        OUT.write_text(
            json.dumps(shapes, ensure_ascii=False, sort_keys=True, indent=0),
            encoding="utf-8")
        print(f"\nadded {len(added)} structural rows -> {OUT} "
              f"({len(shapes)} shapes)")
        for name in added:
            print("  ", name)
        raise SystemExit(0)

    if mode == "all":
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(seen, ensure_ascii=False, sort_keys=True, indent=0),
            encoding="utf-8")
        numeric = sum(1 for row in seen.values()
                      if isinstance(row["result"].get("numeric_estimate"),
                                    dict))
        print(f"\nharvested {len(seen)} answer shapes -> {OUT} "
              f"({numeric} carry a number, {len(seen) - numeric} do not)")
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
            # A structural row has no estimate to compare runs by; equality
            # of the program is the whole of its sameness.
            before = (was["result"].get("numeric_estimate") or {}).get(key)
            after = (now["result"].get("numeric_estimate") or {}).get(key)
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
