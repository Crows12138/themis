"""pgmpy-based oracle for d-separation, back-door, and directed-path
queries.

Used only for differential testing against runtime.structural_solver
and runtime.scheduler. The oracle layer is never imported by runtime.

Translation:
- Each ground atom becomes a pgmpy node whose name is the canonical
  ``predicate(arg1,arg2,...)`` string.
- A parallel ``name_to_atom`` dict is carried alongside the pgmpy
  network so comparison results can be converted back to Atom objects.

pgmpy's CausalInference enumerates ALL valid back-door adjustment
sets (not only minimal). The oracle returns that raw list; the
differential comparator decides how strict to be.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Sequence

import networkx as nx
from pgmpy.inference import CausalInference
from pgmpy.models import DiscreteBayesianNetwork

from ..runtime.instantiation import instantiate
from ..types import Atom, CauseStatement, Program


def _atom_name(atom: Atom) -> str:
    args = ",".join(a.name for a in atom.args)
    return f"{atom.predicate}({args})"


@dataclass(frozen=True)
class OracleNetwork:
    """Oracle-side representation of a Program, paired with the name↔atom map."""

    bn: DiscreteBayesianNetwork
    name_to_atom: dict[str, Atom]


def build_network(program: Program) -> OracleNetwork:
    """Translate a validated Program into a pgmpy DiscreteBayesianNetwork.

    Structure only — no CPTs are attached. pgmpy's d-separation and
    back-door adjustment APIs do not require CPTs.
    """
    ground = instantiate(program)
    edges: list[tuple[str, str]] = []
    name_to_atom: dict[str, Atom] = {}
    for stmt in ground:
        if not isinstance(stmt, CauseStatement):
            continue
        u = _atom_name(stmt.from_atom)
        v = _atom_name(stmt.to_atom)
        name_to_atom[u] = stmt.from_atom
        name_to_atom[v] = stmt.to_atom
        edges.append((u, v))
    bn = DiscreteBayesianNetwork(edges)
    return OracleNetwork(bn=bn, name_to_atom=name_to_atom)


def has_directed_path(network: OracleNetwork, src: Atom, dst: Atom) -> bool:
    """Oracle version of directed-path existence."""
    u, v = _atom_name(src), _atom_name(dst)
    if u not in network.bn or v not in network.bn or u == v:
        return False
    return nx.has_path(network.bn, u, v)


def is_d_connected(
    network: OracleNetwork,
    left: Atom,
    right: Atom,
    conditioning: Sequence[Atom] = (),
) -> bool:
    """Oracle version of d-connectivity."""
    lname, rname = _atom_name(left), _atom_name(right)
    if lname not in network.bn or rname not in network.bn or lname == rname:
        return False
    observed = [_atom_name(c) for c in conditioning]
    return network.bn.is_dconnected(lname, rname, observed=observed or None)


def backdoor_adjustment_sets(
    network: OracleNetwork,
    x: Atom,
    y: Atom,
) -> tuple[frozenset[Atom], ...]:
    """Oracle version of back-door adjustment enumeration.

    Returns every valid back-door adjustment set pgmpy finds — not
    necessarily subset-minimal. The differential comparator reconciles
    with the runtime's minimal-only output by checking that the
    runtime's chosen set appears among pgmpy's valid sets.

    Quirk: pgmpy 1.1.0's ``get_all_backdoor_adjustment_sets`` silently
    omits the empty set even when it is a valid adjustment (e.g. a
    direct edge with no confounder). We explicitly probe for that case
    and prepend ``frozenset()`` when valid, so the oracle's view of
    identifiability matches the back-door criterion.
    """
    xn, yn = _atom_name(x), _atom_name(y)
    if xn not in network.bn or yn not in network.bn or xn == yn:
        return ()
    ci = CausalInference(network.bn)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        raw = ci.get_all_backdoor_adjustment_sets(xn, yn)
        empty_is_valid = bool(
            ci.is_valid_backdoor_adjustment_set(xn, yn, frozenset())
        )
    sets = [frozenset(network.name_to_atom[n] for n in s) for s in raw]
    if empty_is_valid and frozenset() not in sets:
        sets.insert(0, frozenset())
    return tuple(sets)


def is_valid_backdoor_adjustment_set(
    network: OracleNetwork,
    x: Atom,
    y: Atom,
    z: frozenset[Atom],
) -> bool:
    """Check whether Z is a valid back-door adjustment set per pgmpy."""
    xn, yn = _atom_name(x), _atom_name(y)
    if xn not in network.bn or yn not in network.bn:
        return False
    zn = frozenset(_atom_name(a) for a in z)
    ci = CausalInference(network.bn)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return bool(ci.is_valid_backdoor_adjustment_set(xn, yn, zn))
