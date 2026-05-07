"""Iter 122 — collider_conditioning_opens_backdoor gap_kind tests.

Pearl d-separation: a path is BLOCKED by conditioning set Z iff every
collider on the path AND none of its descendants are in Z. Therefore
conditioning ON a collider OPENS the path.

Themis's EffectQuery has a `given` field meant for "conditional ATE
on this subgroup". When `given` includes a node W where both X
(intervention) and Y (target) are ancestors, conditioning on W opens
a non-causal X→…→W←…←Y path → the returned conditional effect is
biased.

This is a pure structural signal — no estimator needed; the classifier
fires from program shape.
"""
from __future__ import annotations

import themis


def _run_collider_program(*, given_predicates: list[str]) -> dict:
    """Build the textbook X → W ← Y collider DAG plus optional extra
    nodes, run themis.run, return the (single) result dict."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "y", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "collider_test",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [
                     {"atom": {"predicate": p,
                               "args": [{"type": "const", "name": "me"}]},
                      "value": True}
                     for p in given_predicates
                 ],
             }},
        ],
    }
    return themis.run(program)["results"][0]


def _gap_kinds_in(result: dict) -> list[str]:
    return [g["kind"] for g in (result.get("data_gap_report") or {}).get("gaps", [])]


# ---------------------------------------------------------------------------
# Positive triggers
# ---------------------------------------------------------------------------


def test_textbook_collider_in_given_triggers_gap():
    """X → W ← Y, query `effect(y | do(x), given w)`. W is a collider
    on the X → W ← Y path — both X and Y are direct parents of W,
    so trivially both are ancestors."""
    result = _run_collider_program(given_predicates=["w"])
    assert "collider_conditioning_opens_backdoor" in _gap_kinds_in(result)


def test_collider_gap_has_important_severity():
    """Not informational — conditioning on a collider is real
    identification damage, not just a caveat."""
    result = _run_collider_program(given_predicates=["w"])
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "collider_conditioning_opens_backdoor"
    )
    assert gap["severity"] == "important"
    assert gap["blocks"] == "identification"


def test_collider_gap_names_collider_and_endpoints_in_description():
    result = _run_collider_program(given_predicates=["w"])
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "collider_conditioning_opens_backdoor"
    )
    desc = gap["description"]
    assert "`w`" in desc
    assert "`x`" in desc
    assert "`y`" in desc
    assert "collider" in desc.lower()


def test_collider_gap_provenance_names_trio():
    result = _run_collider_program(given_predicates=["w"])
    gap = next(
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "collider_conditioning_opens_backdoor"
    )
    prov = gap["provenance"]
    assert len(prov) == 1
    assert prov[0]["ref_kind"] == "verifier_check"
    rid = prov[0]["ref_id"]
    assert "w" in rid
    assert "x" in rid
    assert "y" in rid


def test_collider_explanation_mirror_via_must_disclose():
    """collider_conditioning_opens_backdoor is in
    scheduler._MUST_DISCLOSE_GAP_KINDS, so its description mirrors
    into result.explanation as a ⚠ line."""
    result = _run_collider_program(given_predicates=["w"])
    explanation = result.get("explanation", "")
    assert "⚠" in explanation
    assert "collider" in explanation.lower()


# ---------------------------------------------------------------------------
# Indirect collider (X → A → W ← B ← Y) — graph walk required
# ---------------------------------------------------------------------------


def test_indirect_collider_via_chain_triggers_gap():
    """X → A → W ← B ← Y. W is a collider on the longer path
    X → A → W ← B ← Y; X is ancestor through A, Y is ancestor
    through B."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "a", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "a", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "y", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "b", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "b", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "indirect_collider",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [
                     {"atom": {"predicate": "w",
                               "args": [{"type": "const", "name": "me"}]},
                      "value": True},
                 ],
             }},
        ],
    }
    result = themis.run(program)["results"][0]
    assert "collider_conditioning_opens_backdoor" in _gap_kinds_in(result)


# ---------------------------------------------------------------------------
# Negative cases — should NOT trigger
# ---------------------------------------------------------------------------


def test_no_given_no_gap():
    """Empty given → nothing to check, no gap fired."""
    result = _run_collider_program(given_predicates=[])
    assert "collider_conditioning_opens_backdoor" not in _gap_kinds_in(result)


def test_legitimate_confounder_in_given_no_gap():
    """Z → X, Z → Y (Z is a real confounder, not a collider). Y is
    NOT an ancestor of Z — only descendants of Y could be. Conditioning
    on Z is correct adjustment, not collider opening."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "confounder_test",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [
                     {"atom": {"predicate": "z",
                               "args": [{"type": "const", "name": "me"}]},
                      "value": True},
                 ],
             }},
        ],
    }
    result = themis.run(program)["results"][0]
    assert "collider_conditioning_opens_backdoor" not in _gap_kinds_in(result)


def test_only_x_ancestor_no_gap():
    """W is a descendant of X only (not Y). Path X → W → ? doesn't
    have W as a collider — W is on a directed chain, not a v-structure.
    No gap fired."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "w", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "x_ancestor_only",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [
                     {"atom": {"predicate": "w",
                               "args": [{"type": "const", "name": "me"}]},
                      "value": True},
                 ],
             }},
        ],
    }
    result = themis.run(program)["results"][0]
    assert "collider_conditioning_opens_backdoor" not in _gap_kinds_in(result)


def test_given_x_or_y_itself_not_treated_as_collider():
    """given includes X or Y itself — that's a degenerate query
    (conditioning on the intervention is intervention-as-treatment;
    conditioning on target is meaningless), but NOT a collider issue.
    Helper skips."""
    result = _run_collider_program(given_predicates=["x"])
    assert "collider_conditioning_opens_backdoor" not in _gap_kinds_in(result)


def test_meta_pin_must_disclose_set_includes_collider():
    """Iter 118 sync pin: every name in the must-disclose docstring
    section must be in scheduler._MUST_DISCLOSE_GAP_KINDS, and vice
    versa. Direct check the new gap_kind reaches the auto-mirror set."""
    from themis.runtime.scheduler import _MUST_DISCLOSE_GAP_KINDS
    assert "collider_conditioning_opens_backdoor" in _MUST_DISCLOSE_GAP_KINDS
