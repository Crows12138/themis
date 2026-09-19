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
point, keep one envelope per ``numeric_estimate.method`` together with the
program that produced it, and run the suite over it.

WHICH one, and it is not what this paragraph said for a long time. The
guard below reads ``if method in seen``, and ``seen`` is empty until after
the suite has finished — so nothing stops a later producer overwriting an
earlier one, and the row a method is stored under is the LAST envelope
seen rather than the first. Measured, not inferred: a targeted refresh
naming the test that produced the stored run got a different run back
until that test was moved to the end of the argument list.

Left as it is on purpose. Swapping the two words makes it first-wins,
which is the same schedule dependence wearing the other sign, and would
silently re-key every numeric row on the next full collection. The
structural rows are already decided deterministically — by the shapes a
candidate brings, ties broken by name — and that is what these rows want
too; it is a change to what the corpus IS, not a typo to fix in passing.
Until then a refresh names its producers and puts the one it wants last.

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
shapes stop being new.

That question has to be asked of every envelope, and for a while it was
asked of one envelope per NAME. A structural name is the status, the
question kind and the terminal rule, and a name cannot see what a row
carries: twenty-one envelopes arrive called
``needs_investigation:effect:none`` with seven different sets of shapes
between them, and keeping the first dropped an entire
``missing_data_recovery`` block — along with the only rows that reach
three of the verifier's rules. The keep rule was right and it was being
applied to the survivors of a collapse that had already thrown away the
rows it would have kept.

So candidates are filed by the SHAPES they carry, and the name is a label
on them. Filing that way is also what makes the corpus independent of the
suite's schedule: a set of leaf shapes is the same set whichever order the
suite produced it in, and the pass that chooses between candidates walks
them in name order.

Which leaves WHEN. Asking what a row carries is asking about a finished
answer, and ``run``'s return is not where an answer is finished — it is
only the innermost function this collector can patch. ``estimate`` calls
``run`` and then writes into the very dicts ``run`` handed back: measured,
one object is ``needs_investigation`` carrying no number at ``run``'s
return and ``numerically_solved`` carrying three more blocks at
``estimate``'s. A candidate filed at the inner return is filed as a draft,
and every question asked of it there — its shapes, its name, whether it
carries a number — is answered about the draft while the corpus stores
the finished thing. So filing happens at the boundary the CALLER used:
both entry points are wrapped, they share a depth, and a candidate is
filed when that depth returns to zero.

A snapshot is a copy, and a copy that states no relationship to the thing
it copies is the defect this repository keeps finding. This one states one:
the gate re-verifies every pair honestly before sweeping it, so a producer
that has moved away from the snapshot fails there rather than silently
sweeping a fossil.

That relationship is a CLAIM, and for a long time nothing asked whether it
held at the moment of filing. A row is a program and an answer said to go
together; the answers reached through ``estimate(program, data, options)``
are a function of three things, two of which no snapshot carries, so
re-running the program alone gives a different answer and the pair is not
a pair. Measured on one widening: three rows of that kind, filed and only
found days later, in a gate that reported them as unfamiliar corpus rows.
So every pair is put to the door that reads it before it is filed, and
what is dropped is named — the collector cannot tell a pair that never
held from a producer whose own verifier refuses it, and that difference is
the reader's to draw.

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

A named row the PROGRAM ALONE reproduces needs none of that and needs no
suite either: the three inputs an answer is a function of are the program,
the data and the options, and for such a row the snapshot holds all of
them. So it is refreshed by running its own stored program — sameness by
construction rather than by comparison — and the suite runs only if
something else was named. It is also the only way to name one honestly: a
structural row's name carries a digest of the shapes that earned it its
place, and which candidate in a run wears the bare name depends on what
else that run collected.

Which rows those are is asked of the row and answered against the run, and
the answer was being used for one decision too many. A row with no chain
that loses shapes to its own program is not program-alone — that much the
measurement says — and the refusal said so and stopped, including when the
caller had already named the file that produced it. The sentence it stops
on is the instruction it refuses to carry out. So the measurement decides
which ROUTE a named row takes and not whether it may be refreshed at all:
with no files named there is nowhere else for it to come from and the
refusal stands, and with files named it goes through them like any other.

Which rows those are is NOT "the ones with no chain". ``estimate`` writes
into the very dicts ``run`` hands back, so a row can be numerically solved
and carry no chain, and re-running its program alone would answer a
different question and file the answer under its name. What separates them
is measurable: run the program and ask whether any of this row's LEAF
SHAPES went missing. A row that came from ``estimate`` loses whole blocks
that ``run`` never writes — measured on the corpus of the day, every one of
the 28 that fail lose between ten and fifty — while the 43 that pass lose
none, and 41 of those come back byte-identical.

Asked one way round on purpose. A shape GAINED is the producer writing
something it did not write before, which is what a refresh exists to pick
up: a route that used to name nothing now names the two variables its
sentence is about. A shape LOST is the only one of the two that says this
program is not the whole of what made the row.

One thing a refresh cannot see: a producer that only ADDS a field leaves
every stored pair still valid, so the honest-first gate passes and the sweep
quietly measures envelopes nobody writes any more. A fossil that still
verifies is still a fossil. Ask instead which blocks lack what the producer
would now put there.
"""
from __future__ import annotations

import copy
import hashlib
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

    ``--only`` hands back the files as given, empty included, because a
    row that its own program does not reproduce is refused where there is
    nowhere else to look and refreshed from the named files where there
    is. The suite-wide default is applied at the one place that runs
    pytest.
    """
    if argv and argv[0] == "--structural":
        paths = [str(ROOT / p) for p in argv[1:]] or [str(ROOT / "tests")]
        return "structural", set(), paths
    if not argv or argv[0] != "--only":
        return "all", set(), [str(ROOT / "tests")]
    wanted = {name for name in argv[1].split(",") if name}
    # Not defaulted here, unlike the other two modes: whether the caller
    # named files is a question the refresh below has to ask, and a default
    # filled in at the door is the answer already lost.
    return "only", wanted, [str(ROOT / p) for p in argv[2:]]


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


def _refusal(doors, program, result) -> str | None:
    """``None`` when this pair holds at every door that reads it.

    Every door, not the strongest one. The gate this corpus feeds asks
    what an answer SAYS of every row and re-runs the chain wherever there
    is one, so a collector that asked only the stronger would be asking a
    weaker question than the gate — and a pair passing the weaker question
    can still be refused later, which is the whole thing this filing check
    exists to stop. Measured on the corpus of the day, no row parts the
    two; that is a fact about today's rows and not a reason to ask less.
    """
    for door in doors:
        try:
            door(copy.deepcopy(program), copy.deepcopy(result))
        except Exception as exc:  # noqa: BLE001 — any refusal is a refusal
            return f"{type(exc).__name__}: {exc}"
    return None


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
    #: Numeric rows as collected, before the door has been asked. Held
    #: apart from ``seen`` for the reason the structural candidates are:
    #: what the corpus keeps is decided in one pass after the suite, where
    #: a verification can run without changing what the suite does.
    numeric: dict[str, dict] = {}
    #: What this harvest would not file, and why. Printed, never silent —
    #: a pair dropped without a word is the previous defect with the sign
    #: flipped.
    dropped: list[tuple[str, str, str]] = []
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

    #: Named shapes a stored program alone brings back, refreshed without
    #: the suite. What ``--only`` proves before merging is sameness of the
    #: run, and for a numeric row that takes a data digest and a sample
    #: size because two of the three inputs are not in the snapshot. Where
    #: the program IS the whole input, re-running it is the same run by
    #: construction rather than by comparison, and the suite is only being
    #: used to find an object already in hand.
    #:
    #: Whether it is, is a question rather than a property of having no
    #: chain — ``estimate`` writes into the dicts ``run`` returns, so a
    #: numerically solved answer can carry none. A LOST leaf shape answers
    #: it: an ``estimate`` row loses the blocks ``run`` never writes. A
    #: gained one is the producer writing more than it used to, which is
    #: the thing being picked up.
    refreshed: dict[str, dict] = {}
    if mode == "only":
        stored = json.loads(OUT.read_text(encoding="utf-8"))
        for name in sorted(wanted):
            row = stored.get(name)
            if row is None or row["result"].get("derivation") is not None:
                continue
            envelope = kernel.run(copy.deepcopy(row["program"]))
            fresh = [r for r in envelope.get("results") or ()
                     if r.get("query_id") == row["result"].get("query_id")]
            if len(fresh) != 1:
                raise SystemExit(
                    f"\n{name}: its program came back with {len(fresh)} "
                    f"answers to {row['result'].get('query_id')!r}, so which "
                    f"one it is is not settled; snapshot untouched")
            again = json.loads(json.dumps(fresh[0], ensure_ascii=False))
            was, now = _leaf_shapes(row["result"]), _leaf_shapes(again)
            if was - now:
                if not paths:
                    raise SystemExit(
                        f"\n{name}: its program alone answers with "
                        f"{len(was - now)} of this row's shapes missing, so "
                        f"the program is not the whole of what produced it "
                        f"— name the test that did, and it refreshes "
                        f"through the suite like any other row; snapshot "
                        f"untouched")
                print(f"{name}: {len(was - now)} of its shapes are ones its "
                      f"program alone does not bring back, so it refreshes "
                      f"from the named files rather than from itself")
                continue
            refreshed[name] = {"program": row["program"], "result": again}
        wanted = wanted - set(refreshed)

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
                # Snapshotted for the same reason as in ``_file`` below:
                # the corpus must stop sharing an object with the suite.
                numeric[method] = {
                    "program": copy.deepcopy(source),
                    "result": copy.deepcopy(result),
                    "test": os.environ.get(
                        "PYTEST_CURRENT_TEST", "<unknown>")}
        except Exception:  # a harvest must never change what the suite does
            pass
        return envelope

    #: Candidate structural rows, keyed by the leaf shapes they carry, so
    #: two envelopes filed under one name are two candidates. Which of them
    #: are KEPT is decided after the suite, in one deterministic pass, so
    #: the corpus does not depend on whether a structural answer happened
    #: to run before the numeric row that already covers it.
    candidates: dict[str, dict] = {}
    #: How deep inside a themis entry point we are. ``estimate`` calls
    #: ``run`` and then WRITES INTO the very result dicts ``run`` returned:
    #: measured, an answer is ``needs_investigation`` with no number when
    #: ``run`` returns and ``numerically_solved`` with three more blocks on
    #: it when ``estimate`` does — one object, two moments. So a candidate
    #: filed at ``run``'s return is filed before it is finished, and every
    #: question asked of it there is asked of a draft: what it carries,
    #: what to call it, and whether it carries a number at all. Filing
    #: happens at the boundary the CALLER used, which is where the answer
    #: is the answer.
    depth = 0

    def _file(program, envelope):
        # WHICH program is this answer about? For two of the three entry
        # points it is the one the caller passed. ``apply_patch_and_run``
        # merges patch bundles into that program, runs the kernel on the
        # merged one and hands it back — its own docstring tells an
        # auditor to verify against ``merged_program`` — so the program an
        # answer is about is on the RETURN whenever the return carries
        # one. That is this frontier's sentence one argument along: the
        # object in the caller's hand is not the object the answer is
        # about, for the program exactly as for the answer.
        source = envelope.get("merged_program") or program
        if not isinstance(source, dict):
            source = json.loads(source)
        for result in envelope.get("results") or ():
            # Snapshotted HERE, where the answer is the answer. Filing at
            # the right moment settles when the questions are asked; it
            # does not settle what the corpus keeps, and a corpus holding
            # the suite's own object keeps whatever that object LAST
            # became. The file is written after every test has run, and
            # the tests around here bend an envelope to check that a rule
            # refuses it — one row of the previous harvest states no
            # confidence level because the test that produced it deletes
            # that key on the way to a refusal it expects.
            row = copy.deepcopy(result)
            shapes = _leaf_shapes(row)
            digest = hashlib.sha256(
                "\n".join(sorted(shapes)).encode("utf-8")).hexdigest()
            if digest in candidates:
                continue
            candidates[digest] = {
                "name": _structural_name(row), "shapes": shapes,
                "program": copy.deepcopy(source), "result": row,
                "test": os.environ.get("PYTEST_CURRENT_TEST", "<unknown>")}

    def _watching(entry):
        """Wrap one entry point so it files only when it is the outermost."""
        def wrapper(*args, **kwargs):
            global depth
            depth += 1
            try:
                envelope = entry(*args, **kwargs)
            finally:
                depth -= 1
            if depth == 0:
                try:
                    _file(args[0] if args else kwargs["program"], envelope)
                except Exception:  # a harvest must never change the suite
                    pass
            return envelope
        return wrapper

    # Every entry point a caller can ask a question through, wrapped the
    # same way and in every mode — a defect fixed only where its author was
    # standing is the shape this whole frontier is about. The method-keyed
    # collection above stays what ``estimate`` does; it is now what
    # ``estimate`` does INSIDE the boundary, so the numeric rows are
    # gathered exactly as before and the filing still happens where the
    # answer is finished.
    #
    # Nothing is skipped for carrying a number. The old rule skipped those
    # "collected by method, above" — but above is not installed in
    # structural mode, so in that mode the sentence was never true, and the
    # count printed to defend it was taken at ``run``'s return, where no
    # answer carries a number yet. What each candidate turns out to be is
    # counted below instead, off the finished object.
    _watched_run = _watching(kernel.run)
    kernel.run = _watched_run
    themis.run = _watched_run

    _watched_estimate = _watching(
        kernel.estimate if mode == "structural" else _watch)
    kernel.estimate = _watched_estimate
    themis.estimate = _watched_estimate

    # The third entry point that answers a question. It reaches the
    # pipeline through an internal, so patching ``run`` never saw it, and
    # an answer a caller can get is an answer this corpus should be able
    # to carry.
    _watched_patch = _watching(kernel.apply_patch_and_run)
    kernel.apply_patch_and_run = _watched_patch
    themis.apply_patch_and_run = _watched_patch

    import pytest

    # Not run when every named shape came back from its own program. The
    # suite is this collector's way of FINDING answers, and there is
    # nothing left to find.
    if mode != "only" or wanted:
        pytest.main(["-q", "--no-header", "-p", "no:cacheprovider", "--tb=no",
                     *(paths or [str(ROOT / "tests")])])

    #: Which public door reads an answer: ``verify`` re-runs the chain and
    #: needs one, ``verify_answer_claims`` holds what the answer says. Two
    #: lines, written here rather than imported from the gate's helpers for
    #: the reason ``_leaf_shapes`` is written twice — a collector that asks
    #: the gate's question with the gate's own code agrees with it by
    #: construction, and then neither of them is checking anything.
    def _doors(result):
        steps = result.get("derivation")
        if isinstance(steps, dict):
            steps = steps.get("steps")
        return ([themis.verify_answer_claims, themis.verify] if steps
                else [themis.verify_answer_claims])

    # The numeric rows are filed here now, and asked first, because they
    # are kept by method whatever they add and so decide what a structural
    # row still brings. A refused pair contributes no coverage: a row that
    # is not going into the corpus must not stand in the way of one that
    # would have carried the same shapes honestly.
    for method in sorted(numeric):
        row = numeric[method]
        refusal = _refusal(_doors(row["result"]), row["program"],
                           row["result"])
        if refusal:
            dropped.append((method, row["test"], refusal))
            continue
        seen[method] = {"program": row["program"], "result": row["result"]}
        supplied_by[method] = row["test"]
        covered.update(_leaf_shapes(row["result"]))

    # The second pass: a structural row is kept when it brings a leaf shape
    # nothing kept before it carries. Walked in name order rather than in
    # suite order, so the corpus is the same corpus whichever way the suite
    # was scheduled, and the numeric rows go first because they are kept
    # whatever they add.
    #
    # A name is a label here, not a key, so several candidates can wear
    # one. The second and later of them are named for the shapes that
    # distinguish them, which is what earned them their place; a candidate
    # whose shapes are all covered is dropped before it needs a name, so a
    # row already in the snapshot never comes back wearing a new one.
    #: Names the snapshot already carries, so a row in it does not come back
    #: wearing a new one. That reason holds for a targeted refresh exactly as
    #: it does for an addition, and reading it in only one of the two modes
    #: is why ``--only`` could not name a row it had already stored: a
    #: structural candidate whose bare name is taken wears its shape digest,
    #: and a refresh asking for that digest was told the shape was never
    #: produced. The digest is a function of the shapes, so a row whose
    #: shapes did not move comes back under the name it went in with.
    existing = set(json.loads(OUT.read_text(encoding="utf-8"))
                   if mode in ("structural", "only") else ())
    kept = 0
    for digest, row in sorted(candidates.items(),
                              key=lambda item: (item[1]["name"], item[0])):
        if not row["shapes"] - covered:
            continue
        refusal = _refusal(_doors(row["result"]), row["program"],
                           row["result"])
        if refusal:
            dropped.append((row["name"], row["test"], refusal))
            continue
        covered.update(row["shapes"])
        name = row["name"]
        if name in seen or name in existing:
            name = f"{name}#{digest[:6]}"
        seen[name] = {"program": row["program"], "result": row["result"]}
        supplied_by[name] = row["test"]
        kept += 1

    print(f"\nanswers seen: {len(candidates)} distinct shape "
          f"sets over "
          f"{len({row['name'] for row in candidates.values()})} names, "
          f"{kept} kept for the shapes they bring")
    carrying = sum(1 for row in candidates.values()
                   if isinstance(row["result"].get("numeric_estimate"), dict))
    print(f"of those shape sets, carrying a number: {carrying} — counted off "
          f"the finished answer, which is the only moment the question has "
          f"an answer")
    if dropped:
        print(f"\nNOT FILED — {len(dropped)} pair(s) refused by the door "
              f"that reads them. A row is a claim that a program and an "
              f"answer go together; either these do not (the answer came "
              f"from a call the program alone does not reproduce) or the "
              f"producer writes what its own verifier refuses. A collector "
              f"cannot tell those apart, so it reports both:")
        for name, test, refusal in dropped:
            print(f"  {name}\n      from {test}\n      {refusal[:220]}")

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
    for name, row in sorted(refreshed.items()):
        refusal = _refusal(_doors(row["result"]), row["program"],
                           row["result"])
        if refusal:
            raise SystemExit(
                f"\n{name}: its own program brings back an answer the door "
                f"refuses ({refusal[:200]}); snapshot untouched")
        shapes[name] = row
    missing = sorted(wanted - set(seen))
    if missing:
        # "Not produced" and "produced, then refused" are different facts
        # about a named shape, and the second one is the interesting one.
        refused = sorted({name for name, _, _ in dropped} & set(missing))
        also = (f" ({refused} were produced and then refused — see NOT "
                f"FILED above)" if refused else "")
        raise SystemExit(
            f"\n{missing} not produced by those files{also}; "
            f"snapshot untouched")

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
    print(f"\nrefreshed {sorted(wanted | set(refreshed))} -> {OUT} "
          f"({len(shapes)} shapes"
          + (f", {len(refreshed)} from their own programs)" if refreshed
             else ")"))
