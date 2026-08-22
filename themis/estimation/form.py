"""Which shape the model takes, and who settled it.

Ten estimators resolved a caller's ``model=`` into a concrete form, and every
one of them computed the same by-product on the way and threw it away: whether
the shape was CHOSEN by the system because nothing was specified, or NAMED by
the caller. The two are not distinguishable afterwards — a resolved
``"logistic"`` and a caller's ``"logistic"`` are the same string — so a
disclosure surface asking "who decided the functional form" downstream has
nothing to read, and the one that asked wrote ``"default"`` as a literal at
fourteen call sites. A constant is not an answer, and for the families whose
form is fixed by the method it was the wrong one.

Seven of those ten resolutions are also the SAME resolution — a bool outcome is
a probability and takes the logit link, anything else is a mean and takes the
line — written in seven spellings across four modules. The other three ask
different questions (a backend by sample size, a Wald family by the instrument's
support) but answer the same second question, so :func:`chosen_by` is what they
share and :func:`outcome_form` is what the seven share.

A form nothing resolved at all — the plug-in families, whose method IS its
shape — is :attr:`Provenance.INHERENT`, and those estimators say so beside the
constant they carry rather than through here: there is no resolution to hook.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

import pandas as pd

from ..ledger import Provenance


#: What a caller writes to leave the shape to the system. Spelled once because
#: it is the value the whole distinction turns on.
AUTO = "auto"


def chosen_by(model: str) -> Provenance:
    """Who settled the form: the system, or the caller.

    The reader can act on the difference and on nothing else here — a form the
    system picked is one they can override by naming another, and a form they
    named is one they already own. Which is what
    :attr:`Provenance.DEFAULT.answerable` and
    :attr:`Provenance.CALLER_ASSERTED.answerable` say in the vocabulary this
    returns into.
    """
    return Provenance.DEFAULT if model == AUTO else Provenance.CALLER_ASSERTED


def outcome_form(
    model: str, outcome: pd.Series, *, logistic: str = "logistic",
) -> tuple[str, Provenance]:
    """The outcome model's shape, and its origin.

    ``auto`` reads the outcome column: bool is a probability and takes the
    non-linear link, anything else is a mean and takes the line. Anything the
    caller names is passed through untouched — including a name this function
    has never heard of, because which forms an estimator can fit is that
    estimator's question and refusing here would answer it for all of them.

    ``logistic`` names the non-linear arm because the mediation family spells
    it ``logit`` on its estimate, in its method string and in its tests.
    Spelling is not what this unifies.
    """
    if model == AUTO:
        is_bool = pd.api.types.is_bool_dtype(outcome)
        return (logistic if is_bool else "linear"), Provenance.DEFAULT
    return model, Provenance.CALLER_ASSERTED


#: What a caller leaves a NON-STRING shape lever at to say nothing about it.
#: ``AUTO`` above is the same idea for ``model=``, and a lever whose default
#: is a real value — a floor of 0.01, a ``stabilized=True`` — cannot tell a
#: caller who named that value from a caller who named nothing, so the answer
#: to "who settled this" is destroyed at the call and there is nothing
#: downstream to read. Which is how one estimate came to report the same
#: unchanged propensity floor as ``inherent``, ``default`` and
#: ``caller_asserted`` on three different runs.
UNSET = None

#: A family that settles every shape it has with the outcome model reports no
#: exceptions, and this is that. Immutable rather than a fresh ``{}``: it is a
#: dataclass default on every estimate in this layer, and a shared mutable
#: there is a bug waiting for the first estimator that edits its own.
NO_OTHER_SHAPES: Mapping[str, Provenance] = MappingProxyType({})


def pulled_by(value: object) -> Provenance:
    """Who set a shape lever this run: the caller, or nobody.

    :func:`chosen_by` one axis over. That one reads ``model=``, whose
    do-nothing value is a word the caller writes; this one reads a lever
    whose do-nothing value is the absence of one, which is what
    :data:`UNSET` is for.
    """
    return Provenance.DEFAULT if value is UNSET else Provenance.CALLER_ASSERTED


def shapes_settled(assumptions: Sequence[str],
                   *pairs: tuple[str, Provenance]) -> Mapping[str, str]:
    """Who settled each shape a lever BESIDE the outcome model decided.

    An estimator names the pairs it MIGHT emit, and the declaration list it is
    about to publish decides which of them are real: a shape this run did not
    assume must not arrive with an answer about who assumed it. Reading the
    same tuple that goes on the envelope is also what keeps an origin from
    being filed under an id no reader will ever see.

    Deliberately absent is the outcome model's own shape. That one is the
    estimate's ``form_provenance``, which answers for every id restating it,
    so this map holds the EXCEPTIONS rather than everything: a family with one
    lever has one answer, and repeating it per id would be the same
    one-field-for-N-facts written out longer.
    """
    declared = set(map(str, assumptions))
    return MappingProxyType(
        {name: str(origin) for name, origin in pairs if name in declared})
