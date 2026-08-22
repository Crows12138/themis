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
