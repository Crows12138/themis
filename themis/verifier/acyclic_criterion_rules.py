"""What a declared loop leaves an identification free to claim.

Five of the six patterns this package recognises a graph by -- the back
door, the front door, the c-factor decomposition, and the two joint forms
of those -- are theorems about an ACYCLIC graph. Where the program
declares a reciprocal loop that reaches the estimand, the diagram such a
criterion would be re-derived on is not the model the program states, and
the one sentence a reader is given about where the answer came from
describes a derivation on the wrong picture.

The graph-level re-derivations beside this one do not notice, and cannot.
A loop is declared as a ``feedback`` STATEMENT and is not an edge, so the
graph they are handed is acyclic and the criterion holds on it. On the
stored answer of this shape the empty set really IS a valid back-door set
in that graph: the run reached for an instrument because of something
recorded elsewhere on the envelope, not because of anything the graph
shows. So the word could be rewritten to ``backdoor`` and every reading
that looks at the graph agreed with it.

The sixth word is why this is a roster and not a blanket refusal.
``instrumental_variable`` identifies a structural coefficient in a
simultaneous system -- being an escape from exactly this is what it is
FOR -- so it is the one pattern that still says something true under a
loop, and it is the one the stored answer honestly carries.

Read from the PROGRAM. The withdrawal block on the same envelope also
says these routes went, and reading it here would be asking the answer to
confirm itself; the loops are the ones the program declares and the
reaching is recomputed, by the same transcription the other two claims
about which loops an estimand reaches already use.
"""
from __future__ import annotations

from collections.abc import Mapping

from .errors import VerificationError

_RULE = "acyclic_criterion_under_a_loop_check"

#: The pattern words that name a criterion defined on an acyclic graph.
#: Both identification surfaces are here because the question is about the
#: criterion and not about which block spells it: the scalar surface and
#: the joint one carry disjoint vocabularies, and a rule that knew only
#: the first would leave the second free -- the shape this repository has
#: already repaired three times. The joint vocabulary is here in full,
#: which is the whole of it: it has no escape word, because an instrument
#: for a vector of treatments is a different block again.
_ACYCLIC_ONLY = frozenset({
    "backdoor", "front_door", "c_factor",
    "joint_backdoor", "joint_general_id",
})

#: And the one that holds under a loop, named rather than left to be the
#: absence of the others. A word in neither roster is passed over here:
#: membership in the vocabulary is the schema's question, and the two
#: pattern re-derivations refuse an unknown word already, so answering it
#: a third time would be a weaker check standing in front of the real one.
_HOLDS_UNDER_A_LOOP = frozenset({"instrumental_variable"})


def verify_no_acyclic_criterion_is_claimed_under_a_loop(
    surface: object, graph, feedback, query, where: str,
) -> None:
    """A criterion about an acyclic graph, claimed where the program
    declares a loop that reaches the estimand.

    ``where`` is the subject rather than a switch, for the reason
    :func:`themis.verifier.verify.verify_the_conditioning_a_question_asks_is_named`
    gives: which block a reader is shown depends on the answer, and a
    refusal that could not say which sentence it is about sends a reader
    looking through both.
    """
    from .rules import _atom_label_verifier as _label
    from .rules import declared_loops_reaching

    if not isinstance(surface, Mapping) or not feedback:
        return
    if surface.get("pattern") not in _ACYCLIC_ONLY:
        return

    x = getattr(getattr(query, "intervention", None), "atom", None)
    target = getattr(query, "target", None)
    y = getattr(target, "atom", target)
    if x is None or y is None:
        return

    # The estimand's two ends, which is the question the other two claims
    # resting on reachability ask, asked here the same way. A joint
    # question's extra treatments are not asked separately: one that
    # causes the outcome is already reached through it, and one that
    # causes nothing of the estimand is one whose loop the intervention
    # itself may cut -- a case this does not have a theorem for and will
    # not guess at.
    reaching = declared_loops_reaching(graph, feedback, x, y)
    if not reaching:
        return

    loops = sorted(sorted(_label(a) for a in loop) for loop in reaching)
    raise VerificationError(
        f"{where}: claims {surface.get('pattern')!r} while the program "
        f"declares {loops}, which reach this estimand; that criterion is a "
        f"theorem about an acyclic graph, so the diagram it would be read "
        f"off is not the model the program states",
        step_index=None, rule=_RULE,
    )
