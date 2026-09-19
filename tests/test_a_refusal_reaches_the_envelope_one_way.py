"""The envelope's refusal block has one door, and the species owns its words.

:func:`themis.refusals.block` calls itself "the one shape a refusal takes on
the envelope", and its docstring says why two layers need it: an estimator
raises and dispatch catches, while identification has no exception to catch
and returns the result outright. Measured, it was one of TWO ways that shape
got written — four callers went through it, and twenty-three built the same
dict inline in ``themis/estimation/dispatch.py``. Not one of the twenty-three
named a species that owns a sentence, and eight species reached the envelope
only that way, so the gate #391 put in ``EstimatorFailure.__init__`` could
not see them: a caller with no exception to raise never passes a constructor.

Merging the doors is not enough on its own, because ``block`` took ``reason``
as a finished string — the second door let the call site write the sentence
even when it went through. So ``reason`` is optional here for the same reason
``message`` is optional there, and this module holds both halves.

Ten of the twenty-three were one fact: ``except (ValueError, KeyError)`` on
an estimator that raised something nobody had typed. Seven filed it as
``invalid_input``, whose kind is REQUEST — the browser renders that as "one
of your inputs has to change; change it and run again". The other three, on
the same exception types in the same position, filed it as ``unknown``
(BACKEND: "this decides nothing about the question or the data design").
One fact under two names, the name chosen by whoever wrote the handler, and
one of the two sent a reader off to fix an input that may be perfectly fine.

``invalid_input`` is a name from that history — #405 retired it into the
sixteen faults an argument can actually have — so it survives here only in
the past tense and in the doctored source below, which reproduces what the
seven wrote in order to watch the gate refuse it.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis import language, refusals

REPO = pathlib.Path(__file__).resolve().parent.parent
DISPATCH = REPO / "themis" / "estimation" / "dispatch.py"

#: The ratchet that used to stand here is gone: there are none left, and a
#: count of zero is a worse rule than the absence of the shape. What the last
#: seven cost is the reason the count had to reach zero rather than get small.
#:
#: ``test_a_refusal_says_one_thing_in_every_language`` counts the sites that
#: still compose their own sentence, and it finds them by looking for calls to
#: the three doors — so a dict literal was not a site it could see. Five
#: species reached the envelope ONLY that way and read there as species with
#: no sites at all, their wording never once inside the gate built to count
#: authors. One of the five said the wrong thing for as long as it existed:
#: the longitudinal refusal names its estimator conditionally and told an
#: ``ipw_msm`` run that "the g-formula estimate would be biased".
#:
#: A ratchet on the second door was therefore measuring the wrong thing twice
#: over. It read as a queue of renames, and the renames were what made five
#: species visible to the gate that judges them.


def _source(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _hand_built(tree: ast.Module) -> list[int]:
    """Lines assigning a dict literal that carries ``failure_type``."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        and any(isinstance(k, ast.Constant) and k.value == "failure_type"
                for k in node.keys)
    ]


# --- the door -----------------------------------------------------------------

def test_the_species_speaks_and_the_caller_could_not_have():
    """The block carries no sentence at all, in the shape that is used.

    A caller here has no reader in front of it — it is a kernel refusing —
    so a sentence written at this door would be a language chosen by the
    side that cannot know which one to choose.
    """
    built = refusals.block(
        estimator="backdoor",
        failure_type=refusals.Refusal.UNKNOWN,
        details={"diagnostic": "ZeroDivisionError: division by zero"},
    )
    assert "reason" not in built
    for lang in sorted(language.written()):
        assert refusals.said(built, lang) == language.fill(
            refusals.SAYS["unknown"], lang)
    assert built["details"] == {
        "diagnostic": "ZeroDivisionError: division by zero"}


def test_a_species_with_no_sentence_and_no_reason_is_refused(monkeypatch):
    """The counterexample the door exists to say no to.

    It used to be borrowed from the registry — a species whose raise sites
    still authored their own wording had no entry in SAYS, and there were
    always some. #433 spent the last of them, so the state this refuses is
    now one only the next maintainer can create: a species declared with no
    sentence beside it. Making it here is what keeps the check alive after
    the population it was reading ran out.
    """
    monkeypatch.delitem(refusals.SAYS, "sample_too_small")
    with pytest.raises(ValueError, match="has no sentence"):
        refusals.block(estimator="backdoor",
                       failure_type=refusals.Refusal.SAMPLE_TOO_SMALL)


def test_no_caller_can_write_a_reason_of_its_own():
    """The door has no way in for one, which is stronger than refusing it.

    ``reason=`` was a parameter through #410 and a caller that passed one
    got it onto the envelope verbatim — which is a second author for the
    species' sentence, and a language chosen by whoever refused. Removing
    the parameter rather than validating it is what makes "the sentence
    has one author" a fact about the signature.
    """
    with pytest.raises(TypeError):
        refusals.block(  # type: ignore[call-arg]
            estimator="backdoor",
            failure_type=refusals.Refusal.INSUFFICIENT_SUPPORT,
            reason="the stratum X=1 has no rows",
        )


def test_the_occasions_numbers_are_coerced_at_this_door_too():
    """The constructor coerces ``details``; a caller with no exception to
    raise reaches the envelope without passing it, and a numpy scalar left
    standing there is what ``envelope_scalar`` exists to prevent."""
    numpy = pytest.importorskip("numpy")
    built = refusals.block(
        estimator="backdoor",
        failure_type=refusals.Refusal.UNKNOWN,
        details={"rows": numpy.int64(7), "levels": {numpy.float64(1.5)}},
    )
    assert built["details"] == {"rows": 7, "levels": [1.5]}
    assert type(built["details"]["rows"]) is int


# --- what the species says ----------------------------------------------------

def test_the_unknown_sentence_says_nothing_about_the_occasion():
    """A species that means "we do not know why" must not sound like it does.

    The exception's own text is a maintainer's, and interpolating it here
    would hand a reader a stack-trace fragment in the position where the
    answer goes — the shape #403 took off the web edge. It rides in
    ``details.diagnostic``, which no reader surface renders.
    """
    for lang in sorted(language.written()):
        said = language.fill(refusals.SAYS["unknown"], lang)
        assert "{" not in said and "}" not in said
        assert "diagnostic" not in said.lower()


# --- the door is the only one -------------------------------------------------

def test_only_refusals_assembles_the_block():
    """Every other module goes through ``block``. No exceptions and no count.

    Twenty-three inline dicts is how the shape came to have two authors, and
    nothing in the source distinguishes "assembled here because it carries an
    extra key" from "assembled here because that is what the line above did".
    An absolute rule rather than a ratchet because the second door is not a
    backlog: while it exists, the gate that counts who writes the reader's
    sentence is counting a subset it cannot name.
    """
    offenders = {
        path.relative_to(REPO).as_posix(): _hand_built(_source(path))
        for path in sorted((REPO / "themis").rglob("*.py"))
        if path.name != "refusals.py"
    }
    offenders = {k: v for k, v in offenders.items() if v}
    assert not offenders, (
        f"{offenders} assemble a refusal block by hand; themis.refusals.block "
        f"is where the species gets to speak, and a site that does not go "
        f"through it is invisible to every gate that judges what it says"
    )


def test_the_check_sees_a_block_assembled_by_hand():
    """The rule above, watched saying no — otherwise a rule with nothing left
    to find passes by finding nothing."""
    doctored = ast.parse(
        "result['estimator_failure'] = {\n"
        "    'estimator': 'e',\n"
        "    'failure_type': Refusal.UNKNOWN,\n"
        "    'reason': 'because',\n"
        "}\n"
    )
    assert _hand_built(doctored) == [1]
    assert _hand_built(ast.parse(
        "refusals.block(estimator='e', failure_type=Refusal.UNKNOWN)")) == []


def _handlers_that_did_not_catch_a_refusal(tree: ast.Module) -> list[ast.ExceptHandler]:
    """``except`` clauses that caught something nobody typed as a refusal."""
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
        and "EstimatorFailure" not in ast.unparse(node.type or ast.Constant(""))
    ]


def _species_filed_in(handler: ast.ExceptHandler) -> list[str]:
    """Every species this handler writes onto the envelope."""
    said = []
    for node in ast.walk(handler):
        if isinstance(node, ast.keyword) and node.arg == "failure_type":
            said.append(ast.unparse(node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "failure_type":
                    said.append(ast.unparse(value))
    return said


def test_an_untyped_exception_is_never_filed_as_the_callers_mistake():
    """The ten handlers, held to one species.

    An estimator that raised ``ValueError`` told nobody whose fault it was.
    Filing that as ``invalid_input`` is a claim — REQUEST kind, "change an
    input and run again" — and seven handlers made it because the handler
    beside them did. What the reader is owed is the species that claims
    nothing, and the exception's text where a maintainer will find it.
    """
    wrong = [
        (handler.lineno, said)
        for handler in _handlers_that_did_not_catch_a_refusal(_source(DISPATCH))
        for said in _species_filed_in(handler)
        if said != "Refusal.UNKNOWN"
    ]
    assert not wrong, (
        f"{wrong} file an exception nobody typed under a species that claims "
        f"to know whose fault it was"
    )


def test_the_check_sees_a_handler_that_blames_the_caller():
    """The gate above, watched saying no — doctored the way the seven read."""
    doctored = ast.parse(
        "try:\n"
        "    run()\n"
        "except EstimatorFailure as exc:\n"
        "    refusals.record(result, estimator='e', exc=exc)\n"
        "except (ValueError, KeyError) as exc:\n"
        "    result['estimator_failure'] = {\n"
        "        'estimator': 'e',\n"
        "        'failure_type': Refusal.INVALID_INPUT,\n"
        "        'reason': str(exc),\n"
        "    }\n"
    )
    handlers = _handlers_that_did_not_catch_a_refusal(doctored)
    assert len(handlers) == 1, "the EstimatorFailure arm must be passed over"
    assert _species_filed_in(handlers[0]) == ["Refusal.INVALID_INPUT"]
