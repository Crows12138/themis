"""What the program said each column is, applied where the program is known.

A variable's measurement scale is DECLARED — ``scale``, or an enumerated
``domain``, on the ``variable`` statement — and until this module the
declaration reached exactly one consumer: a diagnostic that reports
disagreements (``dispatch._attach_type_reconciliation``). Nothing that
DECIDED anything read it. Two decisions were made from the column's storage
instead, and both are wrong for the same reason.

The first is admissibility. ``contract.validate_data`` accepts a column
whose dtype is bool or numeric and rejects everything else, so a three-level
channel stored as text — the commonest shape business data arrives in — was
refused, while the same variable re-encoded as 0/1/2 was accepted. The
second is what the column then IS: accepted as numeric, it enters an outcome
regression as ONE ordered term, so three channels become the numbers 0, 1
and 2 and the fitted model is asked to believe that 社交 sits halfway
between 搜索 and 邮件.

Together those make the encoding decide the answer. Re-typing a column as
labels rather than codes changed a run from an estimate to a traceback, and
neither outcome was a statement about the data.

So the declaration is applied here, once, where the program is in scope —
:func:`conform` — and everything downstream sees a frame that already
matches what was declared. The contract keeps its dtype rule for columns
that declared nothing, which is why a program that never said anything is
unaffected: this adds a route rather than changing one.

What it does NOT do, and cannot yet: decide that a column's levels have no
ORDER. ``scale`` admits ``binary`` / ``discrete`` / ``continuous``
(``kernel_ast.schema.json``) and there is no member for "nominal", so a
three-channel campaign and a visit count of 0..10 declare identically.
One-hot encoding on that evidence would replace one silent misspecification
with another — fourteen indicator columns for a count. So a covariate with
more than two levels still enters as one ordered term, and
:func:`ordered_covariates` is what makes the estimators say so.

The same missing member bounds what coding can reach. Recoding moves the
FRAME onto the declared positions and leaves the PROGRAMME naming levels by
label, so the two encodings agree only for a column the programme never
mentions a level of — a covariate. Name one, as a treatment arm or an
observed value does, and every comparison downstream misses silently: an
arm with no rows is a legal state and reads as too little data. So a
labelled column the programme talks about ends the run here
(:func:`conform`) rather than answering with a data gap that is not one.
What removes the boundary is coding that never leaves the design matrix,
which is the same charter as the paragraph above.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from .. import language as _lang
from ..types import envelope_scalar
from .contract import DataContractError


#: What this module says to a person. One sentence so far, and it is here
#: rather than inline for the reason every reader-facing sentence in this
#: repository is: a text written in one language is one a reader of the other
#: cannot be answered in, and an f-string leaves nowhere for the second to be
#: written beside the first.
#:
#: The neighbouring sentences on this same surface — ``contract.py``'s own
#: refusals — are still in one language and are registered as such. They move
#: together, and that is #391's work rather than this module's.
_SAID: dict[str, _lang.Words] = {
    "outside_declared_domain": {
        "zh": "列 {column} 里出现了 {extra}，而程序给它声明的取值范围 {domain} "
              "里没有这些值；带标签的列只能落在它声明过的那些档上",
        "en": "column {column} holds {extra}, which the program's declared "
              "domain {domain} does not list; a labelled column can only be "
              "placed on the levels it was declared with",
    },
    "level_named_by_label": {
        "zh": "列 {column} 带的是标签，要放进模型必须先编码成声明域 {domain} "
              "里的位置；而程序又在用标签 {named} 称呼它的档（比如查询里的干预值）。"
              "编码之后数据说的是位置、程序说的还是标签，两边对不上，"
              "每一条臂都会是空的——那看起来会像数据不够，而不是像编码不一致。"
              "改法：把这一列按 {domain} 的顺序自己编成 {codes}，"
              "domain 也声明成 {codes}，程序里那些档改用对应的数",
        "en": "column {column} carries labels, so entering a model means "
              "coding it to positions in the declared domain {domain} — and "
              "the program also names its levels by label ({named}), an "
              "intervention value for instance. Coded, the data would speak "
              "positions while the programme still speaks labels; no arm "
              "would match, and that reads as too little data rather than as "
              "two encodings disagreeing. Supply the column already coded to "
              "{codes} in the order {domain} declares, declare the domain as "
              "{codes}, and name those numbers in the programme",
    },
}


@dataclass(frozen=True)
class Declared:
    """One variable's declared measurement type, as the program wrote it."""

    scale: str | None
    #: The enumerated levels, in the order they were written. That order is
    #: the only order a labelled column has, and it is the declaring
    #: program's rather than this module's — which is what makes coding a
    #: label column reproducible instead of a choice made here.
    domain: tuple[Any, ...] | None

    @property
    def positive(self) -> str | None:
        """The POSITIVE declaration, or None for "didn't say".

        ``scale`` wins when set; otherwise an enumerated ``domain`` implies
        binary (two levels or fewer) or discrete (more). Neither declared is
        never read as "said continuous" — an undeclared variable is one
        nobody has told us about, and treating silence as a claim is how a
        diagnostic starts reporting on programs that said nothing.
        """
        if self.scale in ("binary", "discrete", "continuous"):
            return self.scale
        if self.domain is not None:
            return "binary" if len(self.domain) <= 2 else "discrete"
        return None


def declarations(program: Mapping[str, Any]) -> dict[str, Declared]:
    """Every ``variable`` statement's declared type, by predicate."""
    out: dict[str, Declared] = {}
    for stmt in program.get("statements", []):
        if stmt.get("kind") != "variable":
            continue
        pred = stmt.get("predicate")
        if not isinstance(pred, str):
            continue
        domain = stmt.get("domain")
        out[pred] = Declared(
            scale=stmt.get("scale"),
            domain=tuple(domain) if isinstance(domain, (list, tuple)) else None,
        )
    return out


def outside_domain(values: Iterable[Any], domain: Iterable[Any]) -> list:
    """The values the declaration cannot place, as the envelope spells them.

    One answer for the two questions that ask it: the reconciliation
    diagnostic reports these to a reader, and :func:`conform` cannot code a
    labelled column while any of them are present. Two computations of "is
    this value one of the declared levels" could disagree about a frame, and
    the disagreement would read as the diagnostic passing a frame the
    contract then refused.

    Values rather than a column, because the two callers hold different
    things — one a column, one the distinct set it already read off — and
    the question is about neither.
    """
    allowed = {envelope_scalar(v) for v in domain}
    return sorted({envelope_scalar(v) for v in values} - allowed, key=repr)


#: The keys that can sit beside a ``value`` and say which variable's level it
#: is. Two rather than one because the counterfactual shapes read a base
#: variable under a subscript and call it ``variable``, where every other
#: shape carries a grounded ``atom``.
_NAMES_A_VARIABLE = ("atom", "variable")


def levels_named(program: Mapping[str, Any]) -> dict[str, list]:
    """Which levels the programme names by hand, per predicate.

    A level is always written next to the atom whose predicate names its
    column — ``{"atom": …, "value": …}`` for an intervention, a grounded
    atom, an observation; ``{"variable": …, "value": …}`` for a
    counterfactual event. So the shape is the criterion, and no list of
    query kinds has to be kept in step with the schema.

    The shape is also what separates a level from the one ``value`` on the
    programme that is not one: a ``probability`` statement's is a number in
    [0, 1] and sits beside ``target`` / ``given``, with no atom of its own.
    Its target and conditions ARE grounded atoms and are found on the way
    down, which is the right answer both times.
    """
    found: dict[str, list] = {}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            if "value" in node:
                for key in _NAMES_A_VARIABLE:
                    named = node.get(key)
                    if not isinstance(named, Mapping):
                        continue
                    pred = named.get("predicate")
                    if isinstance(pred, str):
                        found.setdefault(pred, []).append(node["value"])
                        break
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(program)
    return found


def conform(program: Mapping[str, Any], data: pd.DataFrame) -> pd.DataFrame:
    """The frame the program declared, from the frame the user supplied.

    Today that means one thing: a column carrying LABELS — text, or a pandas
    categorical — is replaced by its position in the declared domain, so the
    contract downstream sees the same numbers it would have seen had the
    user coded the levels themselves. Everything else is returned untouched,
    which is what keeps every program that arrives already numeric
    byte-identical.

    The declared order is used because it is the only order there is, and it
    is the program's own. Where the column holds a value the declaration
    does not list, no coding is possible and the frame is refused naming the
    values — the same fatal shape the contract uses for a column it cannot
    place, because that is what this is.

    It codes only what the PROGRAMME does not also talk about. Recoding
    changes the frame's encoding and leaves the programme's alone, so a
    column whose levels the programme names by label — a treatment arm, an
    observed value, a counterfactual event — would end up compared against
    positions it never mentions. Nothing downstream can notice: an arm with
    no rows in it is a legal state, and forty estimators would agree the
    data is thin. That is the one thing this system must not get wrong, so
    the disagreement ends the run here instead, naming the two encodings
    and the way out. Which is a smaller answer than the right one — the
    right one keeps labels all the way to the design matrix and lets nothing
    coded escape into a programme or an envelope, and it needs the ``scale``
    member ``kernel_ast.schema.json`` has not got yet. Restating the
    programme instead is not that answer: the verifier and the producer both
    re-derive a bound's expression from the query, so both would agree on
    ``P(where=1)`` and show a reader a number nobody wrote.
    """
    if not isinstance(data, pd.DataFrame):
        return data

    decls = declarations(program)
    spoken = levels_named(program)
    recode: dict[str, pd.Series] = {}
    for pred, declared in decls.items():
        if pred not in data.columns:
            continue
        series = data[pred]
        if not _is_labelled(series):
            continue
        if declared.domain is None:
            # Nothing licenses an order, so nothing here invents one. The
            # contract's own refusal follows and says what to declare.
            continue
        named = sorted({envelope_scalar(v) for v in spoken.get(pred, ())},
                       key=repr)
        if named:
            raise DataContractError(_lang.fill(
                _SAID["level_named_by_label"], _lang.DEFAULT,
                column=pred, domain=list(declared.domain), named=named,
                codes=list(range(len(declared.domain)))))
        extra = outside_domain(pd.unique(series.dropna()), declared.domain)
        if extra:
            raise DataContractError(_lang.fill(
                _SAID["outside_declared_domain"], _lang.DEFAULT,
                column=pred, extra=extra,
                domain=list(declared.domain)))
        recode[pred] = _codes(series, declared.domain)

    if not recode:
        return data
    out = data.copy()
    for pred, coded in recode.items():
        out[pred] = coded
    return out


def ordered_covariates(
    df: pd.DataFrame, columns: Iterable[str],
) -> tuple[tuple[str, int], ...]:
    """Which design columns have LEVELS and more than two of them, and how many.

    A design matrix built by column takes each column as ONE term, so the
    distance from the first level to the third is twice the distance to the
    second — an ordering, and a spacing, that nothing declared.

    Two boundaries, and both are the point. Two levels cannot carry that
    assumption at all: an indicator is an indicator whichever two labels it
    was built from. And a CONTINUOUS covariate entering as one term is not
    this finding — it is what ``linear_outcome_regression`` already says, and
    a quantity's order and spacing are its own. Reporting it here would bury
    the case that matters under one that is on the envelope already.

    So "has levels" is asked with the judgement :mod:`.support` settled: at
    most :data:`~themis.estimation.support.MAX_LEVELS` of them, and enough
    rows that they are levels rather than a continuum wearing low
    cardinality. That constant is not tuned — a level needs at least the two
    rows a within-cell comparison costs — and it is the same one, because
    "can this column be cut into strata" is the same question here.

    Measured on the frame rather than read off the declaration, because the
    estimators that call it hold the frame and not the program, and because
    what entered the fit is what the frame held: a column that declared
    eleven levels and shows two contributed one indicator.
    """
    from .support import MAX_LEVELS

    n = len(df)
    found = []
    for col in columns:
        if col not in df.columns or pd.api.types.is_bool_dtype(df[col]):
            continue
        levels = int(df[col].nunique(dropna=True))
        if 2 < levels <= MAX_LEVELS and levels * _MIN_ROWS_PER_LEVEL <= n:
            found.append((col, levels))
    return tuple(found)


#: What one level costs before it is a level rather than a distinct value.
#: The same two :mod:`.support` charges a cell, and for the same reason:
#: below it, cardinality is measuring the sample rather than the variable.
_MIN_ROWS_PER_LEVEL = 2


#: The assumption a design matrix makes about every column in
#: :func:`ordered_covariates`. Named for the fact and not for the columns:
#: an id that carries this run's values is an id no glossary can hold a word
#: for, and the columns are on the envelope already.
ORDERED_COVARIATE_ASSUMPTION = "multi_level_covariates_entered_as_ordered_numbers"


def ordered_entry(df: pd.DataFrame, columns: Iterable[str]) -> tuple[str, ...]:
    """The assumption to declare, or nothing to declare.

    Called by each estimator that builds its design BY COLUMN, beside the
    assumption list it already states, because the estimator is what knows
    which shape it fitted — a stratifying route makes no such assumption and
    must not carry the row. One line per estimator rather than one rule in
    the dispatcher keyed on method names: that rule would be a second
    registry of which estimators regress, and it would drift from them.
    """
    return ((ORDERED_COVARIATE_ASSUMPTION,)
            if ordered_covariates(df, columns) else ())


def _is_labelled(series: pd.Series) -> bool:
    """Whether this column carries labels rather than numbers."""
    return (pd.api.types.is_object_dtype(series)
            or isinstance(series.dtype, pd.CategoricalDtype))


def _codes(series: pd.Series, domain: tuple[Any, ...]) -> pd.Series:
    """The column's values as positions in the declared domain."""
    position = {envelope_scalar(v): i for i, v in enumerate(domain)}
    return series.map(lambda v: position[envelope_scalar(v)]).astype("int64")
