"""A graph with no directed path from X to Y says so, beside the answer.

"Does eating ice cream cause drowning?" is now asked as an effect (#783),
and the translator draws hot weather into both, with no edge from ice cream
to drowning. On that graph the question is settled: by the third rule of
the do-calculus P(drowning | do(ice cream)) = P(drowning), whatever ice
cream is set to. The kernel knew it — the back-door formula drops X for
exactly that reason — and said it nowhere. The result read "needs data" and
listed P(drowning | heat) and P(heat), and the model writing the reply said
the question was one for data to test, which is the wrong way round: data
gives the number P(drowning) and cannot change whether ice cream moves it.

A conditional question P(Y | do(X), Z) is settled the same way only when X
reaches no Z either, and then P(Y | do(X), Z) = P(Y | Z). A Z downstream of
X can open a path: with ice cream -> news <- drowning, knowing the news
lets ice cream move drowning although no directed path joins them.

What is held:

- the identification block names the two ends a directed path does not
  join, on an effect question with and without data, on an identify
  question and on a question conditioned on a variable upstream of X; it
  is silent where a path runs and where the question conditions on a
  variable downstream of X;
- the verifier asks the graph both ways and holds the names to the
  question's: a claim where a path runs to Y or to Z, silence where none
  does, and ends that are not the question's are each refused;
- the report says it in every language, with Z in the identity when the
  question has one, and the page says it beside the verdict rather than
  inside the foldout.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

import themis
from themis import language
from themis.output import analysis_report
from themis.verifier.errors import VerificationError

FRONTEND = Path(__file__).resolve().parents[1] / "themis" / "web" / "frontend" / "src"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b),
            "annotations": {"source": "llm_proposal"}}


def _prob(t, v, p, given=()):
    return {"kind": "probability", "target": {"atom": _atom(t), "value": v},
            "given": [{"atom": _atom(a), "value": b} for a, b in given], "value": p}


EFFECT = {"kind": "effect", "target": {"atom": _atom("drowning"), "value": True},
          "intervention": {"atom": _atom("ice_cream"), "value": True}, "given": []}
IDENTIFY = {"kind": "identify", "intervention": {"atom": _atom("ice_cream"), "value": True},
            "target": _atom("drowning"), "given": []}
DATA = (_prob("heat", True, 0.3),
        _prob("drowning", True, 0.02, [("heat", True)]),
        _prob("drowning", True, 0.005, [("heat", False)]))
ENDS = {"from": "ice_cream(me)", "to": "drowning(me)"}


def _given(*names):
    return {**EFFECT, "given": [{"atom": _atom(n), "value": True} for n in names]}


#: ice cream -> news <- drowning: a variable downstream of X that the
#: question can condition on.
NEWS = (_var("news"), _edge("ice_cream", "news"), _edge("drowning", "news"))


def _program(query=EFFECT, extra=()):
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [_var("heat"), _var("ice_cream"), _var("drowning"),
                           _edge("heat", "ice_cream"), _edge("heat", "drowning"), *extra,
                           {"kind": "query", "id": "q", "query": query}]}


def _identification(program):
    return themis.run(program)["results"][0]["extensions"]["identification"]


@pytest.mark.parametrize("program", [
    _program(), _program(extra=DATA), _program(IDENTIFY),
    _program(_given("heat"), extra=NEWS),
], ids=["effect, no data", "effect, data", "identify", "given a cause of X"])
def test_the_block_names_the_ends_no_directed_path_joins(program):
    assert _identification(program)["no_directed_path"] == ENDS


@pytest.mark.parametrize("program", [
    _program(extra=(_edge("ice_cream", "drowning"),)),
    _program(_given("news"), extra=NEWS),
], ids=["a path to Y", "given a variable downstream of X"])
def test_it_is_silent_where_x_can_move_y(program):
    assert "no_directed_path" not in _identification(program)


def _refused(program, tamper, says):
    """What the answer says is audited with or without a derivation — the
    question is most often asked before the data is in — so it is held
    through ``verify_answer_claims``: the untouched result passes, the
    tampered one is refused with ``says``."""
    result = themis.run(program)["results"][0]
    themis.verify_answer_claims(program, result)
    tampered = copy.deepcopy(result)
    tamper(tampered["extensions"]["identification"])
    with pytest.raises(VerificationError, match=re.escape(says)):
        themis.verify_answer_claims(program, tampered)


@pytest.mark.parametrize("tamper, says", [
    (lambda b: b.pop("no_directed_path"), "leaves unsaid"),
    (lambda b: b["no_directed_path"].update({"from": "heat(me)"}),
     "where the question asks from ice_cream(me) to drowning(me)"),
], ids=["dropped", "the wrong end"])
@pytest.mark.parametrize("program", [_program(), _program(extra=DATA)],
                         ids=["no data", "data"])
def test_the_verifier_holds_the_claim_to_the_graph(program, tamper, says):
    _refused(program, tamper, says)


@pytest.mark.parametrize("program, reached", [
    (_program(extra=(_edge("ice_cream", "drowning"),)),
     "ice_cream(me) to drowning(me), and"),
    (_program(_given("news"), extra=NEWS),
     "ice_cream(me) to drowning(me) or to news(me), and"),
], ids=["a path to Y", "given a variable downstream of X"])
def test_the_verifier_refuses_the_claim_where_x_can_move_y(program, reached):
    _refused(program, lambda b: b.update(no_directed_path=dict(ENDS)), reached)


@pytest.mark.parametrize("program, identity", [
    (_program(), "P(drowning(me) | do(ice_cream(me))) = P(drowning(me))"),
    (_program(_given("heat"), extra=NEWS),
     "P(drowning(me) | do(ice_cream(me)), heat(me)) = P(drowning(me) | heat(me))"),
], ids=["unconditional", "conditional"])
@pytest.mark.parametrize("lang", sorted(language.written()))
def test_the_report_says_it_in_every_language(lang, program, identity):
    report = analysis_report.build_analysis_report(
        themis.run(program)["results"][0], program=program, lang=lang)
    assert identity in report


def test_the_page_says_it_beside_the_verdict_and_not_only_in_the_foldout():
    verdict = (FRONTEND / "components" / "Verdict.tsx").read_text(encoding="utf-8")
    shown = verdict.index('className="verdict__settled"')
    assert shown < verdict.index("<Foldout")
    # Beside the verdict the sentence ends on what the number is, or on what
    # the data asked for can give, by whether a number was computed.
    assert ("unreachedTarget(result.extensions, lang, "
            "num?.point != null || runNum != null)") in verdict
    words = (FRONTEND / "lib" / "verdict.ts").read_text(encoding="utf-8")
    assert "IDENTIFICATION_SAYS.unreached_computed" in words
    assert "IDENTIFICATION_SAYS.unreached_needs" in words
    assert "if (b.no_directed_path)" in words
