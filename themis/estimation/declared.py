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

The third decision is what a column IS once it is admitted, and it needed a
word the vocabulary did not have. ``scale`` said ``binary`` / ``discrete`` /
``continuous``, so a three-channel campaign and a visit count of 0..10
declared identically — and no column can tell them apart, because 0/1/2 and
a count are the same bytes. ``nominal`` is that word: ``discrete`` plus the
claim that the levels have no order and no spacing. Only a person can make
that claim, which is why it is a declaration and never an inference.

A declaration with no consumer would have changed nothing, and the consumer
did not exist: eight estimators each wrote ``df[cols].to_numpy(dtype=float)``,
which is not a conversion but a claim that every column is a quantity.
:func:`design_terms` is that decision, named once, with :func:`design_block`
and :func:`design_widths` as its two readings — and an estimator that cannot
use a set of levels says so through the contract's ``quantity_columns``
rather than through a ``float()`` four frames down.

Being able to say it is also what lets a labelled column keep its labels.
Coding moves the FRAME onto declared positions and leaves the PROGRAMME
naming levels by label, so the two encodings agree only for a column the
programme never mentions a level of. An unordered column is not coded at
all — it carries its own values to the design and becomes indicators there —
so the programme's words still name what the frame holds. Where a column is
labelled and ORDERED, the disagreement is still real and still ends the run
here (:func:`conform`), because an arm with no rows in it is a legal state
and would read as too little data rather than as two encodings disagreeing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .. import language as _lang
from ..assumption_glossary import ORDERED_COVARIATE_ASSUMPTION
from ..ledger import Provenance
from ..types import envelope_scalar
from .contract import DataContractError
from .refusal_words import Refuses


#: What a ``scale`` may say, spelled once. ``kernel_ast.schema.json`` is the
#: authority and a test pins the two equal; this is here because the reading
#: of a declaration happens here and a whitelist written inline is a second
#: copy of a vocabulary that has one.
#:
#: ``nominal`` is ``discrete`` plus one further claim — the levels have no
#: order and no spacing — and that extra claim is unfalsifiable by data. So it
#: reconciles exactly as ``discrete`` does, and the observed side of the
#: reconciliation has no such member.
SCALES = ("binary", "discrete", "continuous", "nominal")


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

        A ``domain`` alone never implies ``nominal``: listing the levels is
        how a discrete variable is declared at all, and reading an absence of
        order into it would make every enumerated variable nominal. The claim
        has to be made.
        """
        if self.scale in SCALES:
            return self.scale
        if self.domain is not None:
            return "binary" if len(self.domain) <= 2 else "discrete"
        return None

    @property
    def unordered(self) -> bool:
        """Whether the program said this column's levels have no order.

        The one thing a column cannot show, which is why it is asked of the
        declaration and of nothing else: codes 0/1/2 and a three-visit count
        are the same bytes, and a fit told to read an order into the first
        answers a question nobody asked. Declared, it changes how the column
        enters a design — one indicator per level rather than one term — and
        that is the only decision it makes.
        """
        return self.scale == "nominal"


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
    and the way out. A column declared ``nominal`` takes the other route and
    is never coded: it keeps its labels all the way to the design matrix,
    where each level becomes its own term and nothing numbered escapes into
    a programme or an envelope. That is the better answer wherever it is
    available, and it is available exactly when a person has said the levels
    have no order. Restating the programme is not an answer either way: the
    verifier and the producer both re-derive a bound's expression from the
    query, so both would agree on ``P(where=1)`` and show a reader a number
    nobody wrote.
    """
    if not isinstance(data, pd.DataFrame):
        return data

    decls = declarations(program)
    spoken = levels_named(program)
    recode: dict[str, Any] = {}
    for pred, declared in decls.items():
        if pred not in data.columns:
            continue
        series = data[pred]
        if declared.unordered:
            # Marked, not coded. A declaration that the levels have no order
            # is the one that makes coding unnecessary: the column carries
            # its own values all the way to the design, where it becomes one
            # indicator per level, and nothing numbered ever leaves that
            # matrix. So the programme's own words still name what the frame
            # holds, and the refusal below — which exists because coding
            # breaks exactly that — has nothing to refuse.
            if declared.domain is not None:
                extra = outside_domain(pd.unique(series.dropna()),
                                       declared.domain)
                if extra:
                    raise DataContractError(
                        Refuses.OUTSIDE_DECLARED_DOMAIN, column=pred,
                        extra=extra, domain=list(declared.domain))
            recode[pred] = _unordered(series, declared.domain)
            continue
        if not _is_labelled(series):
            continue
        if declared.domain is None:
            # Nothing licenses an order, so nothing here invents one. The
            # contract's own refusal follows and says what to declare.
            continue
        named = sorted({envelope_scalar(v) for v in spoken.get(pred, ())},
                       key=repr)
        if named:
            raise DataContractError(
                Refuses.LEVEL_NAMED_BY_LABEL, column=pred,
                domain=list(declared.domain), named=named,
                codes=list(range(len(declared.domain))))
        extra = outside_domain(pd.unique(series.dropna()), declared.domain)
        if extra:
            raise DataContractError(
                Refuses.OUTSIDE_DECLARED_DOMAIN, column=pred,
                extra=extra, domain=list(declared.domain))
        recode[pred] = _codes(series, declared.domain)

    if not recode:
        return data
    out = data.copy()
    for pred, coded in recode.items():
        out[pred] = coded
    return out


def design_block(df: pd.DataFrame, columns: Iterable[str]) -> np.ndarray:
    """Those columns as design-matrix terms: one per column, or one per level.

    **The decision this function makes did not exist anywhere.** Eight
    estimators
    each wrote ``df[list(adjustment)].to_numpy(dtype=float)``, which is not a
    conversion but a claim — that every column is a quantity, so the distance
    from its first level to its third is twice the distance to its second.
    Written as a dtype cast it never looked like a claim, and all eight made
    it at once, which is why it belongs here rather than in a ninth copy: what
    a column IS is a fact about the variable, and the estimator is not where
    facts about variables live.

    A column marked as levels-without-order (``conform``, from a ``nominal``
    declaration) becomes one indicator per level, the first level dropped —
    which is what makes the block full rank when an intercept or a treatment
    column sits beside it, and which is why the declared domain's order
    matters here and nowhere else: it names the level the others are read
    against. Every other column passes through as itself, because a quantity
    IS one term and a binary column's single indicator is already saturated.

    Measured on the frame, like :func:`ordered_covariates` beside it and for
    the same reason: the estimators hold the frame and not the program, and
    what entered the fit is what the frame held.
    """
    terms = design_terms(df, columns)
    if not terms:
        return np.empty((len(df), 0), dtype=float)
    return np.column_stack([values for _, values in terms])


def design_terms(
    df: pd.DataFrame, columns: Iterable[str],
) -> list[tuple[str, np.ndarray]]:
    """The same terms, each beside the name it answers to.

    The primitive of the three functions here, because the reading it does —
    is this column a quantity or a set of levels — is the one fact, and a
    second implementation of it is the defect this whole change is about. A
    caller that needs a matrix takes :func:`design_block`; one that has to
    say which coefficient belongs to which variable takes this; one that
    reads coefficients by position takes :func:`design_widths`.

    An expanded level is named ``column=level`` so the term can still be
    traced to the column it came from, which is what a covariance indexed by
    name needs and what a reader of an effect table needs.
    """
    terms: list[tuple[str, np.ndarray]] = []
    for col in columns:
        series = df[col]
        if isinstance(series.dtype, pd.CategoricalDtype):
            indicators = pd.get_dummies(series, drop_first=True)
            for level in indicators.columns:
                terms.append((f"{col}={level}",
                              indicators[level].to_numpy(dtype=float)))
        else:
            terms.append((col, series.to_numpy(dtype=float)))
    return terms


def design_widths(df: pd.DataFrame, columns: Iterable[str]) -> list[int]:
    """How many design columns each named column becomes.

    The other half of :func:`design_block`, and it exists because a caller
    that reads a coefficient BY POSITION has to be told where its column
    went. Once a covariate can be k-1 terms, "the covariate's coefficient"
    is a block of them, and an offset computed from ``adjustment.index``
    points at a different variable.

    Read from ``dtype.categories`` rather than from the values, so the width
    is a property of the declaration and not of the sample: a level absent
    from a bootstrap draw still gets its indicator, which is what makes the
    designs of two draws comparable at all.
    """
    # Read from the declaration rather than from :func:`design_terms`, and
    # the difference is the point: a term list is built from the rows in
    # hand, and this has to be the same number for every draw. A test pins
    # the two equal on a full sample, which is where they must agree.
    widths: list[int] = []
    for col in columns:
        dtype = df[col].dtype
        if isinstance(dtype, pd.CategoricalDtype):
            widths.append(max(len(dtype.categories) - 1, 0))
        else:
            widths.append(1)
    return widths


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
        if isinstance(df[col].dtype, pd.CategoricalDtype):
            # Declared to have no order, so :func:`design_block` gave it one
            # indicator per level and there is no ordering left to disclose.
            # Silence here is the whole point of the declaration: a row that
            # kept appearing would be reporting an assumption the answer
            # stopped making.
            continue
        levels = int(df[col].nunique(dropna=True))
        if 2 < levels <= MAX_LEVELS and levels * _MIN_ROWS_PER_LEVEL <= n:
            found.append((col, levels))
    return tuple(found)


#: What one level costs before it is a level rather than a distinct value.
#: The same two :mod:`.support` charges a cell, and for the same reason:
#: below it, cardinality is measuring the sample rather than the variable.
_MIN_ROWS_PER_LEVEL = 2


#: ...and who settled it, carried beside the id because the estimator that
#: appends the row is not what decided it. Nobody named it — no argument
#: selects it — but the PROGRAM can retire it: declaring the column ``nominal``
#: gives it one indicator per level and the row stops being made, which is
#: exactly what :attr:`Provenance.DEFAULT` promises a reader they can do about
#: a shape. Carried rather than looked up because a consumer holding a table
#: of which ids stand outside the run's resolution is a consumer guessing at
#: the producer's levers, and it guessed wrong for four of them.
ORDERED_ENTRY_SHAPE = (ORDERED_COVARIATE_ASSUMPTION, Provenance.DEFAULT)


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


def _unordered(series: pd.Series, domain: tuple[Any, ...] | None) -> pd.Series:
    """The column as levels with no order, keeping the values it arrived with.

    A pandas categorical with ``ordered=False`` is the frame's own way of
    saying this, which is why the declaration is carried as a dtype rather
    than as a list of column names threaded through nine estimators: the
    estimators hold the frame and not the program, and every existing
    consumer — a groupby, a cardinality, an equality against a level the
    query named — reads a categorical unchanged.

    The declared ``domain`` supplies the category order when there is one.
    That order carries no magnitude; it decides which level a design leaves
    out as the reference, and being the declaring program's rather than this
    module's is what makes the choice reproducible instead of made here.
    """
    if domain is not None:
        categories = [envelope_scalar(v) for v in domain]
    else:
        categories = sorted(
            (envelope_scalar(v) for v in pd.unique(series.dropna())), key=repr)
    return pd.Series(
        pd.Categorical(series.map(envelope_scalar),
                       categories=categories, ordered=False),
        index=series.index, name=series.name,
    )
