"""What the shared risk cascade hands its doors, and at what type.

:func:`themis.estimation.binary_do_risk.choose_risk_route` answers one
question — which route reaches ``P(Y=1 | do(X=arm))`` — and two doors ask it:
probabilities of causation, and the single counterfactual cell. On the
general-ID route the answer carries an estimand per arm, and an estimand is
worth nothing to a door that cannot evaluate it.

The route used to carry those estimands as ``dict[bool, object]``. Nothing
about that was false — they are objects — but it was less than the cascade
knew, and the shortfall was not free. A door cannot call the evaluator with a
value typed ``object``, so each door recovered the type for itself, and both
doors did it with the same fifteen lines: an ``isinstance`` against the five
``FormulaExpr`` members, raising a bare ``TypeError`` outside either module's
declared ``Raises`` contract. Two readers, two copies; a third door would have
written a third. That is what a declaration narrower than the truth costs —
the same small job, pushed outward, once per reader, forever.

So these check the handoff rather than either door. The first is the property
the copies existed to supply, asked of the type checker instead: a consumer
takes ``route.formulas[arm]`` straight to :func:`evaluate_arm_risk`. The
second is that check's own honesty — if ``evaluate_arm_risk`` resolved to
``Any`` the first would pass for the wrong reason and go on passing after the
declaration widened again. The third asks the cascade at runtime, because the
identification layer it calls through is a module whose findings the config
still ignores, so agreement between what it declares and what it emits is not
something the static half can be reading.
"""
from __future__ import annotations

import typing

import networkx as nx

from themis.estimation.binary_do_risk import RiskRoute, choose_risk_route
from themis.risk_provenance import RiskProvenance
from themis.types import Atom, FormulaExpr

# The mypy harness lives next door, and copying it here is the move this
# module is about. Its own tests establish that it resolves ``themis`` names
# rather than silently typing them ``Any``.
from tests.test_static_exhaustiveness import _run_mypy

X = Atom(predicate="x", args=())
M = Atom(predicate="m", args=())
Y = Atom(predicate="y", args=())
_LATENT = frozenset({frozenset({X, Y})})


def _front_door():
    """X → M → Y with X and Y latently confounded — the one structure where
    no adjustment set exists and the general ID algorithm still reaches both
    arms, which is the only route that populates ``formulas`` at all."""
    graph = nx.DiGraph()
    graph.add_edges_from([(X, M), (M, Y)])
    return graph


def test_a_door_hands_the_estimand_straight_to_the_evaluator(tmp_path):
    """The property the two deleted copies existed to supply.

    A door that reads the cascade's estimand does exactly one thing with it:
    evaluates it on the frame. If that call does not type-check, the door is
    forced to re-derive the type before making it — which is how one helper
    became two, and would have become three. The probe is a third door, and
    it compiles.
    """
    src = tmp_path / "third_door.py"
    src.write_text(
        "import pandas as pd\n"
        "from themis.estimation.binary_do_risk import RiskRoute\n"
        "from themis.estimation.general_id import evaluate_arm_risk\n"
        "from themis.types import Atom\n"
        "def arm_risk(route: RiskRoute, df: pd.DataFrame,\n"
        "             domains: dict[Atom, tuple]) -> float:\n"
        "    return evaluate_arm_risk(route.formulas[True], df, domains=domains)\n",
        encoding="utf-8")
    out = _run_mypy(str(src))
    assert "Success" in out, out


def test_the_probe_above_would_have_noticed(tmp_path):
    """The way the check above could pass while stating nothing.

    ``evaluate_arm_risk`` is imported across a package boundary, and a name
    mypy cannot resolve is typed ``Any``, which accepts every argument. Then
    the probe compiles no matter what the cascade declares, and keeps
    compiling after it widens back. So: the same call, given something that
    is plainly not an estimand, has to be rejected.
    """
    src = tmp_path / "wrong_argument.py"
    src.write_text(
        "import pandas as pd\n"
        "from themis.estimation.general_id import evaluate_arm_risk\n"
        "from themis.types import Atom\n"
        "def arm_risk(df: pd.DataFrame, domains: dict[Atom, tuple]) -> float:\n"
        "    return evaluate_arm_risk('P(y|do(x))', df, domains=domains)\n",
        encoding="utf-8")
    out = _run_mypy(str(src))
    assert "Success" not in out, out
    assert "evaluate_arm_risk" in out, out


def test_the_cascade_declares_the_estimand_at_the_type_it_produces():
    """The half the type checker is not in a position to state.

    The estimands are built by the general ID algorithm, which reaches them
    through ``themis.runtime.c_factor`` — a module still named in the config's
    ignore list. So the declaration on ``RiskRoute`` is checked against a
    producer whose own findings are suppressed, and "declared" and "emitted"
    can drift apart without a finding anywhere. This runs the cascade and
    compares them.

    It also pins the declaration to ``FormulaExpr`` itself rather than to a
    hand-written list of node classes. A subset spelled out here would be a
    second copy of the union, free to fall behind the day a sixth node type
    is added — the same failure, one level up.
    """
    _arm_type, declared = typing.get_args(typing.get_type_hints(RiskRoute)["formulas"])
    members = typing.get_args(declared)
    assert members == typing.get_args(FormulaExpr), (
        f"RiskRoute.formulas is declared {declared!r}; a door that reads it "
        f"has to recover the estimand's type before it can evaluate it"
    )

    route = choose_risk_route(
        _front_door(), _LATENT, cause=X, effect=Y, arms=(True, False),
    )
    assert route is not None
    assert route.provenance is RiskProvenance.GENERAL_ID_PLUG_IN
    assert sorted(route.formulas) == [False, True]
    for arm, estimand in route.formulas.items():
        assert isinstance(estimand, members), (
            f"the arm {arm} estimand arrived as {type(estimand).__name__}, "
            f"which the route's own declaration does not admit"
        )
