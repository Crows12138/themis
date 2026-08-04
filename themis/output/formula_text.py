"""The identification formula, said out loud.

``formula`` is a first-class field on the envelope and 788 results in one
suite run carried one. Every one of them was told the same thing: the
answer line offered "估计式已生成，见文末审计" and the audit footer it
pointed at said "估计式已生成（机器可读，见 ``result.formula``）". Two
pointers, and nothing at the end of either — the report has never rendered
the expression it keeps promising.

It is the residue of a section that was built one round too early. When
the report gained its "怎么算出来的" section, ten renderers were bound to
the ten identification blocks in ``extensions``; ``formula`` is a *field*,
not a block, so the binding that would have caught a missing renderer
never looked at it. The comment left behind is the tell, and it is the
shape :mod:`themis.blocks` was written to remove: a sentence that names
the field instead of saying what is in it.

The browser has had ``lib/formula.ts`` all along, and copying it would
have carried two defects across. The schema declares five node kinds and
that file handles four — a ``constant`` renders as the word "constant" —
and it prints every bound value as the letter ``z`` while writing the
sum's subscript from the atom, so one formula names one variable two ways
and nested sums (89 results, to depth 6) collapse distinct bindings into
one letter. Here a sum's binding is carried down as an environment, so a
value bound by an enclosing sum reads as the variable that sum ranges
over: ``Σ_z P(y | x, z) · P(z)``, which is the notation the reader of a
g-formula already knows.
"""
from __future__ import annotations

from typing import Callable, Mapping

# The closed set of node kinds in ``query_result.schema.json``'s
# ``formulaExpression``. Bound below, both ways: a kind the schema admits
# and this module cannot render would reach a reader as its own name, and
# a renderer for a kind the schema does not admit is dead prose.
CONSTANT = "constant"
PROBABILITY_REF = "probability_ref"
PRODUCT = "product"
SUM = "sum"
FRACTION = "fraction"

DECLARED: tuple[str, ...] = (
    CONSTANT, PROBABILITY_REF, PRODUCT, SUM, FRACTION,
)


# Not an identifier, so no bind name the schema admits can collide with it.
_PINNED = "@pinned"


class UnknownNodeKind(KeyError):
    """A formula node names a kind no renderer is declared for.

    Reachable only past the schema, whose ``formulaExpression`` this
    module covers exactly. Raised rather than defaulted: the default is
    what put the word "constant" on the browser's screen.
    """


def bind(renderers: Mapping[str, Callable]) -> dict[str, Callable]:
    missing = sorted(k for k in DECLARED if k not in renderers)
    if missing:
        raise ValueError(
            f"no renderer for formula node kind {missing}; a formula "
            f"containing one would reach a reader as its own kind name"
        )
    extra = sorted(k for k in renderers if k not in DECLARED)
    if extra:
        raise ValueError(
            f"renderer bound for {extra}, which the formula grammar does "
            f"not admit (themis.output.formula_text.DECLARED)"
        )
    return dict(renderers)


def _atom_name(atom: dict | None) -> str:
    """A formula names variables, not instances.

    The atom carries its arguments — ``y(me)`` — and every atom in one
    formula carries the same ones, so printing them would repeat the unit
    on every term of the expression without distinguishing anything.
    """
    return (atom or {}).get("predicate") or "?"


def _valued_atom(node: dict | None, env: dict[str, str]) -> str:
    """One atom with the value the formula fixes it at.

    ``True`` is the bare predicate and ``False`` its negation, which is
    how the reader writes them. A value bound by an enclosing sum is that
    sum's variable, and since the sum ranges over this very atom the
    variable IS the predicate — writing ``P(z=z)`` would be noise. A value
    the query binds from outside is absent, and the bare predicate is
    again right.
    """
    node = node or {}
    name = _atom_name(node.get("atom"))
    if "value" not in node:
        return name
    value = node["value"]
    if value is True:
        return name
    if value is False:
        return f"¬{name}"
    if isinstance(value, dict) and value.get("kind") == "var_ref":
        # The sum that bound this name ranges over this very atom, so the
        # atom IS the variable: ``P(z)``, never ``P(z=z)``. The symbol may
        # be primed, and then it is the primed one that belongs here.
        return env.get(value.get("name"), name)
    return f"{name}={value}"


def _render_constant(node: dict, env: dict[str, str]) -> str:
    return str(node.get("value"))


def _render_probability_ref(node: dict, env: dict[str, str]) -> str:
    target = _valued_atom(node.get("target"), env)
    given = [_valued_atom(g, env) for g in node.get("given") or []]
    return f"P({target} | {', '.join(given)})" if given else f"P({target})"


def _render_product(node: dict, env: dict[str, str]) -> str:
    return " · ".join(render(t, env) for t in node.get("terms") or [])


def _pinned_predicates(node, out: set[str] | None = None) -> set[str]:
    """The predicates this formula holds at a value somewhere.

    A front-door estimand sums over the treatment while the treatment is
    also held at the value being intervened on, so ``x`` would name both
    the intervention and the index of the sum — and the two occurrences
    sit in different subtrees, so a sum cannot tell by reading its own
    body. Standard notation primes the index; this is what says when to.
    """
    out = set() if out is None else out
    if not isinstance(node, dict):
        return out
    if node.get("kind") == PROBABILITY_REF:
        for atom in [node.get("target"), *(node.get("given") or [])]:
            atom = atom or {}
            value = atom.get("value")
            if "value" in atom and not (
                isinstance(value, dict) and value.get("kind") == "var_ref"
            ):
                out.add(_atom_name(atom.get("atom")))
        return out
    for key in ("body", "numerator", "denominator"):
        _pinned_predicates(node.get(key), out)
    for term in node.get("terms") or []:
        _pinned_predicates(term, out)
    return out


def _render_sum(node: dict, env: dict[str, str]) -> str:
    over = _atom_name(node.get("over"))
    name = (node.get("bind") or {}).get("name")
    symbol = f"{over}'" if over in env.get(_PINNED, ()) else over
    inner = dict(env)
    if name:
        inner[name] = symbol
    return f"Σ_{symbol} [ {render(node.get('body'), inner)} ]"


def _render_fraction(node: dict, env: dict[str, str]) -> str:
    return (f"( {render(node.get('numerator'), env)} )"
            f" / ( {render(node.get('denominator'), env)} )")


_RENDERERS = bind({
    CONSTANT: _render_constant,
    PROBABILITY_REF: _render_probability_ref,
    PRODUCT: _render_product,
    SUM: _render_sum,
    FRACTION: _render_fraction,
})


def render(node, env: dict[str, str] | None = None) -> str:
    """One formula node as the expression it stands for.

    ``env`` maps a bound value-variable's name to the symbol its sum
    ranges over; callers start with none and the sums fill it in on the
    way down. It also carries, computed once at the top, the predicates
    the whole formula pins to a value — which a sum cannot see from its
    own body.
    """
    if not isinstance(node, dict):
        return ""
    if env is None:
        env = {_PINNED: _pinned_predicates(node)}
    kind = node.get("kind")
    try:
        renderer = _RENDERERS[kind]
    except KeyError:
        raise UnknownNodeKind(
            f"no renderer declared for formula node kind {kind!r}; add it "
            f"to themis.output.formula_text beside the grammar"
        ) from None
    return renderer(node, env or {})
