"""Fix 6 (v0.1.5, audit follow-up) — IV-in-effect Wald LATE dispatch.

Classic IV setup: Z → X → Y with X ↔ Y latent confounder. Backdoor
fails structurally (the bidirected X↔Y is unblockable by any
observable Z). Front-door fails (no X→M→Y mediator). With monotonicity
assumption + boolean treatment + boolean instrument, kernel can
compute Wald LATE.

The numeric is the COMPLIER LATE — average effect among the
subpopulation whose treatment shifts with the instrument — NOT the
population ATE. Extensions surface this caveat explicitly so the
Skill / agent can disclose; Themis's contract is "we report the
quantity the formula actually computes, not the quantity the user
might naively conflate it with".
"""
from __future__ import annotations

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _gr(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target_pred, target_v, given_pairs, value):
    return {
        "kind": "probability",
        "target": _gr(target_pred, target_v),
        "given": [_gr(p, v) for p, v in given_pairs],
        "value": value,
    }


def _iv_program(monotonicity: str | None) -> dict:
    """Z (instrument) → X (treatment) → Y (outcome), with X ↔ Y latent
    confounder. Boolean throughout. Theta supplies the 4 conditionals
    Wald needs:

      P(Y=1 | Z=1) = 0.7,  P(Y=1 | Z=0) = 0.3
      P(X=1 | Z=1) = 0.8,  P(X=1 | Z=0) = 0.2

    Expected Wald LATE = (0.7 − 0.3) / (0.8 − 0.2) = 0.4 / 0.6 ≈ 0.667
    """
    stmts = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("y", True, [("z", True)],  0.7),
        _prob("y", True, [("z", False)], 0.3),
        _prob("x", True, [("z", True)],  0.8),
        _prob("x", True, [("z", False)], 0.2),
    ]
    query: dict = {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    stmts.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


# ---------------------------------------------------------------------------
# Happy path: IV numeric fires with monotonicity
# ---------------------------------------------------------------------------


def test_iv_with_monotonicity_resolves_to_numerically_solved():
    """Z→X→Y, X↔Y, theta supplied, monotonicity declared → status
    upgrades to numerically_solved via Wald LATE."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    assert r["status"] == "numerically_solved", (
        f"expected numerically_solved, got {r['status']}"
    )


def test_iv_wald_value_matches_textbook_formula():
    """Wald: LATE = (E[Y|Z=1] − E[Y|Z=0]) / (E[X|Z=1] − E[X|Z=0])
    = (0.7 − 0.3) / (0.8 − 0.2) = 2/3"""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    expected = (0.7 - 0.3) / (0.8 - 0.2)
    assert abs(r["numeric_result"]["value"] - expected) < 1e-9


def test_iv_extensions_block_carries_late_caveat():
    """extensions.iv_identification.late_caveat must explicitly tell
    downstream renderers LATE ≠ ATE. This is the substantive disclosure
    contract: vanilla IV deployments routinely conflate the two."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    ext = r["extensions"]["iv_identification"]
    assert "late_caveat" in ext
    assert "LATE" in ext["late_caveat"]
    assert "ATE" in ext["late_caveat"]


def test_iv_extensions_block_carries_numeric_components():
    """The component conditionals + the derived LATE are exposed in
    extensions for the renderer / agent to surface (parallel to
    mediation_decomposition.numeric / transport_identification.numeric).

    The four conditionals live inside a stratum, which is where their
    names are literally true. A marginal instrument has exactly one
    stratum, so nothing is buried — but the aggregate slots that a
    conditional instrument needs (`outcome_shift` / `treatment_shift`)
    are present in both regimes rather than appearing only when W is
    non-empty."""
    out = themis.run(_iv_program(monotonicity="non_decreasing"))
    r = out["results"][0]
    numeric = r["extensions"]["iv_identification"]["numeric"]
    for key in (
        "conditioning_order", "strata",
        "outcome_shift", "treatment_shift", "late",
    ):
        assert key in numeric
    assert len(numeric["strata"]) == 1
    for key in (
        "p_y_given_z_treated",
        "p_y_given_z_control",
        "p_x_given_z_treated",
        "p_x_given_z_control",
    ):
        assert key in numeric["strata"][0]


def test_iv_verify_round_trip():
    """Independent verifier accepts the IV Wald derivation —
    iv_criterion_check + identify_via_iv + iv_wald_numeric_evaluate +
    numeric_result, with the bundled rule re-running the 4 theta
    lookups + arithmetic independently."""
    program = _iv_program(monotonicity="non_decreasing")
    out = themis.run(program)
    themis.verify(program, out["results"][0])


# ---------------------------------------------------------------------------
# Without monotonicity: IV numeric skipped, kernel doesn't escalate
# ---------------------------------------------------------------------------


def test_iv_without_monotonicity_does_not_fire_wald():
    """Wald LATE requires the monotonicity assumption; without it,
    the kernel must NOT silently apply Wald and fabricate a LATE
    value. IV-numeric skipped → Tian fallback tries → if Tian also
    fails (hedge), stays needs_investigation."""
    out = themis.run(_iv_program(monotonicity=None))
    r = out["results"][0]
    assert r["status"] == "needs_investigation", (
        f"without monotonicity, IV-numeric must NOT silently fire; "
        f"got status={r['status']}"
    )


# ---------------------------------------------------------------------------
# Theta-incomplete IV: stays needs_investigation
# ---------------------------------------------------------------------------


def test_iv_with_incomplete_theta_falls_through():
    """If theta lacks any of the 4 Wald conditionals, IV-numeric must
    fall through to the next strategy (Tian) / final
    needs_investigation rather than crashing."""
    program = _iv_program(monotonicity="non_decreasing")
    # Drop one of the 4 needed conditionals
    program["statements"] = [
        s for s in program["statements"]
        if not (
            s.get("kind") == "probability"
            and s["target"]["atom"]["predicate"] == "x"
            and len(s["given"]) == 1
            and s["given"][0]["value"] is False
        )
    ]
    out = themis.run(program)
    r = out["results"][0]
    # Either Tian saves it (unlikely on hedge) or needs_investigation.
    # Either way, must NOT crash and must NOT silently produce a wrong LATE.
    assert r["status"] in ("needs_investigation", "structurally_solved")


# ---------------------------------------------------------------------------
# Conditional (Brito-Pearl) instruments on the theta end
#
# w → z, w → y, z → x, x → y, x ↔ y.
#
# z is NOT a marginal instrument — z ← w → y is open in G[x-bar] — but it
# IS one once w is held fixed. iv_sets has always returned that candidate
# and the identify path has always reported it; the numeric end used to
# bail the moment a candidate carried a conditioning set, so this exact
# graph came back "reachable by nothing" from the effect path while the
# identify path on the same graph said "identifiable via z given {w}".
# ---------------------------------------------------------------------------


_P_W1 = 0.4
# stratum value of w -> (p_x|z1, p_x|z0, p_y|z1, p_y|z0)
_STRATA = {
    True:  (0.9, 0.3, 0.7, 0.4),   # first stage 0.6, LATE(w=1) = 0.50
    False: (0.6, 0.2, 0.5, 0.2),   # first stage 0.4, LATE(w=0) = 0.75
}
# Ratio of averages — each stratum weighted by ITS OWN complier share:
#   (0.4·0.3 + 0.6·0.3) / (0.4·0.6 + 0.6·0.4) = 0.30 / 0.48
_RATIO_OF_AVERAGES = 0.625
# The plausible wrong answer: the stratum LATEs weighted by P(w).
#   0.4·0.50 + 0.6·0.75
_AVERAGE_OF_RATIOS = 0.65


def _conditional_iv_program(monotonicity: str | None = "non_decreasing") -> dict:
    stmts = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("w", True, [], _P_W1),
        _prob("w", False, [], 1 - _P_W1),
    ]
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        stmts += [
            _prob("x", True, [("z", True), ("w", wv)], pxz1),
            _prob("x", True, [("z", False), ("w", wv)], pxz0),
            _prob("y", True, [("z", True), ("w", wv)], pyz1),
            _prob("y", True, [("z", False), ("w", wv)], pyz0),
        ]
    query: dict = {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    stmts.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def _missing_names(result: dict) -> list[str]:
    return [m["name"] for m in (result.get("missing_information") or [])]


def test_conditional_instrument_is_answered_on_the_theta_end():
    """The premise first: no adjustment set exists here, and the only
    instrument the graph offers carries a conditioning set. Then the
    conclusion — the effect query gets a number anyway."""
    from themis.runtime import structural_solver
    from themis.types import Atom, ConstTerm
    import networkx as nx

    def a(p):
        return Atom(predicate=p, args=(ConstTerm(name="me"),))

    g = nx.DiGraph()
    g.add_edges_from([
        (a("w"), a("z")), (a("w"), a("y")),
        (a("z"), a("x")), (a("x"), a("y")),
    ])
    bi = frozenset({frozenset({a("x"), a("y")})})
    assert structural_solver.minimal_adjustment_sets(
        g, a("x"), a("y"), bidirected=bi
    ) == (), "premise broken: this graph is supposed to have no adjustment set"
    candidates = structural_solver.iv_sets(g, a("x"), a("y"), bidirected=bi)
    assert candidates, "premise broken: no instrument at all"
    assert all(c.conditioning for c in candidates), (
        "premise broken: a MARGINAL instrument exists, so this graph no "
        "longer exercises the conditional path"
    )

    r = themis.run(_conditional_iv_program())["results"][0]
    assert r["status"] == "numerically_solved", (
        f"conditional instrument left unanswered: {_missing_names(r)}"
    )


def test_conditional_wald_weights_strata_by_complier_share():
    """The estimand pin. Aggregating a stratified Wald has a plausible
    wrong answer — average the per-stratum LATEs by P(w) — that differs
    from the right one only when the instrument moves treatment by
    different amounts across strata. It does here, on purpose."""
    r = themis.run(_conditional_iv_program())["results"][0]
    assert abs(r["numeric_result"]["value"] - _RATIO_OF_AVERAGES) < 1e-9
    assert abs(r["numeric_result"]["value"] - _AVERAGE_OF_RATIOS) > 1e-3


def test_conditional_wald_exposes_every_stratum():
    numeric = themis.run(
        _conditional_iv_program()
    )["results"][0]["extensions"]["iv_identification"]["numeric"]
    assert numeric["conditioning_order"] == ["w(me)"]
    assert len(numeric["strata"]) == 2
    assert abs(sum(c["weight"] for c in numeric["strata"]) - 1.0) < 1e-12
    by_value = {c["values"][0]: c for c in numeric["strata"]}
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        cell = by_value[wv]
        assert cell["p_x_given_z_treated"] == pxz1
        assert cell["p_x_given_z_control"] == pxz0
        assert cell["p_y_given_z_treated"] == pyz1
        assert cell["p_y_given_z_control"] == pyz0
    # treatment_shift is the complier share, and it is reported as such.
    assert abs(numeric["treatment_shift"] - 0.48) < 1e-12


def test_conditional_wald_caveat_says_which_average_it_took():
    """`late` is not the average of the per-stratum LATEs also printed
    right next to it. A reader who assumes it is reads the wrong
    estimand, so the caveat has to say so."""
    ext = themis.run(
        _conditional_iv_program()
    )["results"][0]["extensions"]["iv_identification"]
    assert ext["conditioning"] == ["w(me)"]
    caveat = ext["late_caveat"]
    assert "LATE" in caveat and "ATE" in caveat
    assert "依从者比例" in caveat


def test_conditional_iv_verify_round_trip():
    program = _conditional_iv_program()
    out = themis.run(program)
    themis.verify(program, out["results"][0])


def test_marginal_wald_is_the_one_stratum_case_of_the_same_arithmetic():
    """W = ∅ is not a separate code path — it is one stratum of weight 1
    whose conditionals carry no W term. Pinned so the generalization
    cannot drift the classical answer."""
    numeric = themis.run(
        _iv_program(monotonicity="non_decreasing")
    )["results"][0]["extensions"]["iv_identification"]["numeric"]
    assert numeric["conditioning_order"] == []
    assert len(numeric["strata"]) == 1
    cell = numeric["strata"][0]
    assert cell["values"] == []
    assert cell["weight"] == 1.0
    assert cell["p_y_given_z_treated"] == 0.7
    assert cell["p_x_given_z_control"] == 0.2
    assert abs(numeric["late"] - (0.7 - 0.3) / (0.8 - 0.2)) < 1e-9


# ---------------------------------------------------------------------------
# What the kernel says when it CANNOT run the stratified Wald
#
# All three of these used to collapse into one refusal that enumerated
# backdoor / front-door / ID and named nothing else — while the identify
# path on the same graph named the instrument. The structural fact still
# stands (nonparametric point identification really did fail, and the
# answer tier downstream reads that), so the IV items ride alongside it
# rather than replacing it: an available escalation is not identification.
# ---------------------------------------------------------------------------


def _reason_of(result: dict, name: str) -> str:
    return next(
        m["reason"] for m in result["missing_information"] if m["name"] == name
    )


def test_undeclared_monotonicity_names_the_instrument_it_needs_it_for():
    r = themis.run(
        _conditional_iv_program(monotonicity=None)
    )["results"][0]
    assert r["status"] == "needs_investigation"
    names = _missing_names(r)
    assert "effect:iv_monotonicity_undeclared" in names
    reason = _reason_of(r, "effect:iv_monotonicity_undeclared")
    assert "z(me)" in reason and "w(me)" in reason
    # The structural refusal keeps its place but stops implying the IV
    # layer had nothing either.
    assert "query:effect_admg" in names
    assert "instrumental-variable escalation does reach it" in _reason_of(
        r, "query:effect_admg"
    )


def test_short_theta_names_the_probability_not_a_dead_end():
    """One stratum cell absent. What is missing is a parameter the user
    can supply, and it gets named — the refusal used to say only that no
    strategy reached the graph, which named nothing actionable."""
    program = _conditional_iv_program()
    program["statements"] = [
        s for s in program["statements"]
        if not (
            s.get("kind") == "probability"
            and s["target"]["atom"]["predicate"] == "y"
            and len(s["given"]) == 2
            and all(g["value"] is False for g in s["given"])
        )
    ]
    r = themis.run(program)["results"][0]
    assert r["status"] == "needs_investigation"
    names = _missing_names(r)
    named = [n for n in names if n.startswith("parameter:P(y=True|")]
    assert named, names
    assert "instrument" in _reason_of(r, named[0])
    assert {m["kind"] for m in r["missing_information"]} == {
        "structure", "parameter",
    }


def test_an_instrument_that_moves_nothing_says_so():
    """A first stage of zero means there are no compliers to average
    over. That used to be a bare `return None`, which read downstream as
    "the graph is beyond reach" rather than "this instrument is inert"."""
    program = _iv_program(monotonicity="non_decreasing")
    for s in program["statements"]:
        if (
            s.get("kind") == "probability"
            and s["target"]["atom"]["predicate"] == "x"
        ):
            s["value"] = 0.5
    r = themis.run(program)["results"][0]
    assert r["status"] == "needs_investigation"
    assert "effect:iv_first_stage_degenerate" in _missing_names(r)


def test_stratum_weights_that_are_not_a_distribution_are_refused():
    """The LATE ratio is scale-invariant, so incoherent stratum
    probabilities would still yield a number — one whose reported
    complier share is meaningless. Refuse instead."""
    program = _conditional_iv_program()
    for s in program["statements"]:
        if (
            s.get("kind") == "probability"
            and s["target"]["atom"]["predicate"] == "w"
            and s["target"]["value"] is False
        ):
            s["value"] = 0.5           # with P(w=True)=0.4 this sums to 0.9
    r = themis.run(program)["results"][0]
    assert r["status"] == "needs_investigation"
    assert "effect:iv_stratum_weights_not_normalized" in _missing_names(r)


def test_a_candidate_that_theta_cannot_serve_does_not_end_the_search():
    """Two marginal instruments, theta only covers the second. The
    search used to take candidate[0] and stop; a candidate being
    unusable says nothing about the next one."""
    stmts = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "za", "domain": [True, False]},
        {"kind": "variable", "predicate": "zb", "domain": [True, False]},
        {"kind": "cause", "from": _atom("za"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("zb"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("y", True, [("zb", True)],  0.7),
        _prob("y", True, [("zb", False)], 0.3),
        _prob("x", True, [("zb", True)],  0.8),
        _prob("x", True, [("zb", False)], 0.2),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": _gr("y", True),
            "given": [],
            "assumptions": {"monotonicity": "non_decreasing"},
        }},
    ]
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }
    r = themis.run(program)["results"][0]
    assert r["status"] == "numerically_solved", _missing_names(r)
    assert r["extensions"]["iv_identification"]["instrument"] == "zb(me)"
    assert abs(r["numeric_result"]["value"] - (0.4 / 0.6)) < 1e-9


# ---------------------------------------------------------------------------
# Verifier: it re-derives, it does not replay
# ---------------------------------------------------------------------------


def _tampered(mutate) -> tuple[dict, dict]:
    program = _conditional_iv_program()
    result = themis.run(program)["results"][0]
    steps = result["derivation"]["steps"]
    step = next(s for s in steps if s["rule"] == "iv_wald_numeric_evaluate")
    mutate(step, result)
    return program, result


def test_verifier_rejects_a_marginal_wald_wearing_a_conditional_licence():
    """The sharp failure: a producer computes the ratio at W = ∅ on a
    graph where the instrument is only conditionally valid, and records
    W = ∅ honestly. Every number in the payload is then internally
    consistent — only the graph says otherwise."""
    def strip_conditioning(step, result):
        step["inputs"]["instrument_conditioning"] = {
            "kind": "atom_tuple", "items": [],
        }
    program, result = _tampered(strip_conditioning)
    with pytest.raises(Exception, match="IV2/IV3"):
        themis.verify(program, result)


def test_verifier_rejects_a_dropped_stratum():
    """Averaging over the strata that happened to be convenient is not
    averaging over the population."""
    def drop_one(step, result):
        step["output"]["items"]["strata"]["items"].pop()
    program, result = _tampered(drop_one)
    with pytest.raises(Exception, match="strata"):
        themis.verify(program, result)


def test_verifier_rejects_the_average_of_ratios():
    """The wrong aggregation, planted as the answer."""
    def swap_estimand(step, result):
        step["output"]["items"]["late"] = _AVERAGE_OF_RATIOS
        result["numeric_result"]["value"] = _AVERAGE_OF_RATIOS
    program, result = _tampered(swap_estimand)
    with pytest.raises(Exception, match="late"):
        themis.verify(program, result)


def test_verifier_rejects_a_reweighted_stratum():
    def reweight(step, result):
        cells = step["output"]["items"]["strata"]["items"]
        cells[0]["items"]["weight"] = 0.5
    program, result = _tampered(reweight)
    with pytest.raises(Exception, match="weight"):
        themis.verify(program, result)


def test_proposal_edge_on_the_conditioning_set_is_disclosed():
    """W is not in the query — it reaches the answer only by being the
    thing that makes Z an instrument. An unverified proposal edge on it
    is therefore on the query path, and now that W is load-bearing for
    the NUMBER and not only the identification claim, the disclosure has
    to hold on this path too."""
    program = _conditional_iv_program()
    for s in program["statements"]:
        if (
            s.get("kind") == "cause"
            and s["from"]["predicate"] == "w"
            and s["to"]["predicate"] == "y"
        ):
            s["annotations"] = {"source": "llm_proposal"}
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved"
    assert result["extensions"]["iv_identification"]["conditioning"] == ["w(me)"]
    kinds = {
        g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", ())
    }
    assert "unverified_proposal_edge_on_query_path" in kinds, sorted(kinds)


# ---------------------------------------------------------------------------
# The IV escalation must not preempt non-parametric point identification
# ---------------------------------------------------------------------------


def _napkin_with_theta(monotonicity: str | None) -> dict:
    """Pearl's napkin (w→z→x→y, w↔x, w↔y) carrying a full, self-consistent
    theta.

    The napkin is point-identified by general ID and by nothing weaker — no
    back-door set, no front-door set — AND it carries an instrument (z, valid
    once w is held fixed). It is therefore the graph on which the order
    between the two matters.

    Theta is every conditional the validator admits (parents ∪ ancestors ∪
    bidirected siblings), derived from one explicit joint so the entries are
    mutually consistent and the conditioning-stratum weights sum to exactly 1.
    """
    import itertools

    cells = {}
    total = 0.0
    for w, z, x, y in itertools.product([True, False], repeat=4):
        # arbitrary but strictly positive and deterministic
        p = 1.0 + 0.7 * w + 0.5 * z + 0.3 * x + 0.2 * y + 0.4 * (w and y)
        cells[(w, z, x, y)] = p
        total += p
    for k in cells:
        cells[k] /= total

    names = ("w", "z", "x", "y")

    def marginal(assign: dict) -> float:
        return sum(
            p for key, p in cells.items()
            if all(key[names.index(n)] == v for n, v in assign.items())
        )

    admissible = {
        "w": ["x", "y"], "z": ["w"], "x": ["w", "z"], "y": ["w", "z", "x"],
    }
    stmts = []
    for tgt, adm in admissible.items():
        for k in range(len(adm) + 1):
            for cond_vars in itertools.combinations(adm, k):
                for cond_vals in itertools.product([True, False], repeat=k):
                    cond = dict(zip(cond_vars, cond_vals))
                    denom = marginal(cond)
                    for tv in (True, False):
                        stmts.append(_prob(
                            tgt, tv, list(cond.items()),
                            marginal({**cond, tgt: tv}) / denom,
                        ))

    query: dict = {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]}
              for p in names),
            {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("x")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("y")},
            *stmts,
            {"kind": "query", "id": "q", "query": query},
        ],
    }


def _rules(result: dict) -> list[str]:
    return [s.get("rule") for s in (result.get("derivation") or {}).get("steps", ())]


def test_declaring_an_assumption_does_not_replace_the_assumption_free_answer():
    """The IV escalation used to run BEFORE general ID in the identification
    cascade, so on a graph reachable by both, declaring monotonicity swapped
    the answer: from the query's own P(Y=1|do(x=1)), identified without any
    assumption, to a Wald LATE — a contrast, among compliers, resting on the
    assumption just declared. Supplying more information degraded the
    estimand. The estimation dispatch already ordered these two the other way
    and said why; identification now agrees.
    """
    program = _napkin_with_theta(None)

    # Guard against a vacuous pass: the IV branch must genuinely be able to
    # claim this graph, otherwise "IV did not preempt" proves nothing.
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.runtime import structural_solver
    from themis.runtime.graph_projection import project
    from themis.runtime.instantiation import instantiate

    ground = instantiate(validate_program(validate_ast(program)))
    graph = project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    x = next(a for a in graph.nodes if a.predicate == "x")
    y = next(a for a in graph.nodes if a.predicate == "y")
    assert structural_solver.iv_sets(graph, x, y, bidirected=bidirected)
    assert not structural_solver.minimal_adjustment_sets(
        graph, x, y, given=(), bidirected=bidirected
    )
    assert not structural_solver.front_door_sets(
        graph, x, y, bidirected=bidirected
    )

    plain = themis.run(program)["results"][0]
    declared = themis.run(
        _napkin_with_theta("non_decreasing")
    )["results"][0]

    assert "identify_via_tian" in _rules(plain)
    assert "identify_via_tian" in _rules(declared), _rules(declared)
    assert "identify_via_iv" not in _rules(declared), _rules(declared)
    assert (
        declared["numeric_result"]["value"] == plain["numeric_result"]["value"]
    )
