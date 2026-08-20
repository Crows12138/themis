"""Phase 9 §S9.1: Bareinboim-Pearl recoverability from selection bias.

The constructive counterpart to the ``selection_on_collider_opens_path``
detector. That classifier *detects* that a sample restricted
on an observed node W (an ``ObservationStatement``) conditions on a
collider and therefore biases the estimate. This module answers the
*next* question the detector never did: given the declared selection
mechanism, **can the unbiased quantity be recovered from the biased
data P(v | S), and if so with what formula — and if not, what external
(unbiased) data would close the gap?**

Selection is modeled the Hernán-2004 "structural approach" way: the
sample is restricted to units with S = selected, where S is a *real
node in G* carrying an ``ObservationStatement``. Its parents (declared
``CauseStatement`` edges into it) are the selection mechanism. Data
available to the analyst is P(v | S). This reuses the existing program
shape — no new statement type — and turns the existing one-sided
warning into a recoverability verdict.

Two textbook results are implemented:

- **Conditional** P(y | x) — COMPLETE characterization (Bareinboim,
  Tian & Pearl 2014, "Recovering from Selection Bias in Causal and
  Statistical Inference", AAAI): P(y | x) is s-recoverable from the
  selection diagram G_s **iff (Y ⊥ S | X)**. Recovered as P(y | x, S).
  When the independence fails, a set Z with (Y ⊥ S | X, Z) plus
  *external* unbiased data on (X, Z) still recovers it.

- **Causal effect** P(y | do(x)) — the **selection backdoor criterion**
  (SBD, Bareinboim & Pearl 2012 "Controlling Selection Bias in Causal
  Inference"; restated as Assumption 3.4 / Theorem 3.5 in Chen et al.
  2025, arXiv:2503.20546). A SUFFICIENT criterion: decompose
  Z = Z⁺ ∪ Z⁻ where Z⁺ are non-descendants of X and Z⁻ are descendants
  of X. Z is selection-backdoor admissible iff
    (1) S ⊥ Y | {X, Z}      (X and Z block every S–Y path), and
    (2) Z⁺ blocks every back-door path X → Y (ordinary back-door).
  Then, with the required unbiased data (condition 3):
    Z⁻ = ∅:  P(y | do(x)) = Σ_{z⁺} P(y | x, z⁺, S) · P(z⁺)
    Z⁻ ≠ ∅:  P(y | do(x)) =
               Σ_{z⁺} [ Σ_{z⁻} P(y | x, z⁺, z⁻, S) · P(z⁻ | x, z⁺) ] · P(z⁺)
  The unbiased weights P(z⁺) (and P(z⁻ | x, z⁺) when Z⁻ ≠ ∅) collapse to
  their biased counterparts when S ⊥ Z, in which case NO external data is
  needed and the effect is fully s-recoverable from P(v | S) alone.

Scope (structural identification only, mirroring transport.py §T9.1):
- SBD is a *sufficient* criterion. A negative verdict says "not
  recoverable via selection-backdoor adjustment", NOT "provably
  non-recoverable" — the complete algorithm (Bareinboim-Tian-Pearl 2014
  RC) is deferred, exactly as the general nested-ID case is.
- No numeric estimation here: this returns the recovery formula and the
  external-data ledger, not a number. Numeric evaluation is a follow-up
  slice (as it was for transport, §T9.2).
- Selection nodes are observed substantive nodes conditioned via
  ``ObservationStatement``. A separate non-substantive S-indicator with
  latent parents is out of scope for v1.

The working graph G(M) is never mutated; every test is a read-only
d-separation query against it.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx

from ..types import Atom


# ============================================================= result


@dataclass(frozen=True)
class SelectionRecoveryResult:
    """Verdict of a recoverability analysis under selection bias.

    ``query_kind`` is ``"conditional"`` (target P(y|x)) or ``"effect"``
    (target P(y|do(x))). Read ``recoverable`` first; ``criterion`` names
    the theorem that succeeded, ``formula_repr`` the recovery expression,
    and ``external_data_needed`` the unbiased distributions required
    beyond the biased sample P(v|S) (empty tuple ⇒ recoverable from the
    biased data alone).
    """
    query_kind: str
    recoverable: bool
    criterion: str | None                 # conditional_independence |
                                          # external_data | selection_backdoor | None
    selection_nodes: tuple[Atom, ...]
    adjustment_set: tuple[Atom, ...]      # the full Z (effect) or external Z (conditional)
    z_plus: tuple[Atom, ...]              # non-descendants of X within Z
    z_minus: tuple[Atom, ...]             # descendants of X within Z
    formula_repr: str
    external_data_needed: tuple[str, ...]
    failure_reason: str | None = None


# ============================================================= helpers


def _sorted_atoms(atoms) -> tuple[Atom, ...]:
    """Deterministic ordering of an atom collection by predicate name."""
    return tuple(sorted(atoms, key=lambda a: a.predicate))


def _names(atoms) -> str:
    return ", ".join(a.predicate for a in atoms)


def _dsep(graph: nx.DiGraph, a: Atom, b: Atom, conditioning) -> bool:
    """True iff a and b are d-separated given the conditioning set."""
    from .structural_solver import is_d_connected
    return not is_d_connected(graph, a, b, tuple(conditioning))


def _s_all_dsep_from_y(
    graph: nx.DiGraph, s_nodes, y: Atom, conditioning,
) -> bool:
    """SBD condition (1): every S node d-separated from Y given conditioning."""
    return all(_dsep(graph, s, y, conditioning) for s in s_nodes)


def _zplus_blocks_backdoor(
    graph: nx.DiGraph, x: Atom, y: Atom, z_plus,
) -> bool:
    """SBD condition (2): Z⁺ blocks every back-door path X → Y.

    Z⁺ contains no descendants of X by construction, so it is a valid
    back-door candidate; this only checks the blocking. Vacuously True
    when there are no back-door paths.
    """
    from .structural_solver import backdoor_paths, _path_is_open
    cond = frozenset(z_plus)
    for path in backdoor_paths(graph, x, y):
        if _path_is_open(graph, path, cond):
            return False
    return True


def _z_recoverable_from_biased(
    graph: nx.DiGraph, s_nodes, z,
) -> bool:
    """True iff P(z) is recoverable from the biased sample, i.e. S ⊥ Z.

    A node set Z is (marginally) d-separated from S exactly when every
    member is d-separated from every S node under empty conditioning; a
    path from S to the SET is a path to one of its members. When this
    holds, P(z) = P(z | S), so no external data is needed.
    """
    if not z:
        return True
    return all(_dsep(graph, s, zi, ()) for zi in z for s in s_nodes)


# ============================================================= conditional


def _find_conditional_external_z(
    graph: nx.DiGraph, x: Atom, y: Atom, s_nodes, max_size: int,
):
    """Smallest observed Z with (Y ⊥ S | X, Z), for external-data recovery."""
    forbidden = {x, y} | set(s_nodes)
    candidates = [n for n in graph.nodes if n not in forbidden]
    for size in range(1, min(len(candidates), max_size) + 1):
        for combo in combinations(candidates, size):
            cond = (x,) + combo
            if _s_all_dsep_from_y(graph, s_nodes, y, cond):
                return _sorted_atoms(combo)
    return None


def recover_conditional(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    s_nodes: tuple[Atom, ...],
    max_size: int = 4,
) -> SelectionRecoveryResult:
    """Recoverability of the conditional P(y | x) under selection bias.

    COMPLETE for the direct case: recoverable iff (Y ⊥ S | X). Falls back
    to external-data recovery via a Z with (Y ⊥ S | X, Z).
    """
    kind = "conditional"
    if x not in graph or y not in graph:
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=False, criterion=None,
            selection_nodes=s_nodes, adjustment_set=(), z_plus=(), z_minus=(),
            formula_repr="", external_data_needed=(),
            failure_reason="处理或结局不在图中",
        )
    if not s_nodes:
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=True, criterion=None,
            selection_nodes=(), adjustment_set=(), z_plus=(), z_minus=(),
            formula_repr=f"P({y.predicate} | {x.predicate})",
            external_data_needed=(),
            failure_reason=None,
        )

    if _s_all_dsep_from_y(graph, s_nodes, y, (x,)):
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=True,
            criterion="conditional_independence",
            selection_nodes=s_nodes, adjustment_set=(), z_plus=(), z_minus=(),
            formula_repr=(
                f"P({y.predicate} | {x.predicate}) = "
                f"P({y.predicate} | {x.predicate}, S)"
            ),
            external_data_needed=(),
            failure_reason=None,
        )

    z = _find_conditional_external_z(graph, x, y, s_nodes, max_size)
    if z is not None:
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=True, criterion="external_data",
            selection_nodes=s_nodes, adjustment_set=z, z_plus=z, z_minus=(),
            formula_repr=(
                f"P({y.predicate} | {x.predicate}) = "
                f"Σ_{{{_names(z)}}} P({y.predicate} | {x.predicate}, "
                f"{_names(z)}, S) · P({_names(z)} | {x.predicate})"
            ),
            external_data_needed=(
                f"unbiased P({x.predicate}, {_names(z)})",
            ),
            failure_reason=None,
        )

    return SelectionRecoveryResult(
        query_kind=kind, recoverable=False, criterion=None,
        selection_nodes=s_nodes, adjustment_set=(), z_plus=(), z_minus=(),
        formula_repr="",
        external_data_needed=(),
        failure_reason=(
            "给定 X 时，Y 与选择节点不可 d-分离（在搜索预算内，"
            "给定 X 再加上任何一组已观测的 Z 也不行）；"
            "P(y|x) 无法从选择偏倚中 s-恢复"
        ),
    )


# ============================================================= effect (SBD)


def _effect_formula_repr(
    x: Atom, y: Atom, z_plus, z_minus,
) -> str:
    """Render the SBD recovery formula (Theorem 3.5) symbolically.

    Four shapes, by whether Z⁺ / Z⁻ are present:
      ∅, ∅ :  P(y|do(x)) = P(y|x,S)
      Z⁺, ∅:  P(y|do(x)) = Σ_{z⁺} P(y|x,z⁺,S) · P(z⁺)
      ∅, Z⁻:  P(y|do(x)) = Σ_{z⁻} P(y|x,z⁻,S) · P(z⁻|x)
      Z⁺, Z⁻: P(y|do(x)) = Σ_{z⁺}[ Σ_{z⁻} P(y|x,z⁺,z⁻,S)·P(z⁻|x,z⁺) ]·P(z⁺)
    """
    yv, xv = y.predicate, x.predicate
    zp, zm = _names(z_plus), _names(z_minus)

    def _cond(*parts: str) -> str:
        # join the conditioning list, dropping empty pieces
        return ", ".join(p for p in parts if p)

    if not z_plus and not z_minus:
        return f"P({yv} | do({xv})) = P({yv} | {xv}, S)"
    if not z_minus:
        return (
            f"P({yv} | do({xv})) = "
            f"Σ_{{{zp}}} P({yv} | {_cond(xv, zp)}, S) · P({zp})"
        )
    if not z_plus:
        return (
            f"P({yv} | do({xv})) = "
            f"Σ_{{{zm}}} P({yv} | {_cond(xv, zm)}, S) · P({zm} | {xv})"
        )
    return (
        f"P({yv} | do({xv})) = "
        f"Σ_{{{zp}}} [ Σ_{{{zm}}} P({yv} | {_cond(xv, zp, zm)}, S) · "
        f"P({zm} | {_cond(xv, zp)}) ] · P({zp})"
    )


def _external_ledger(
    graph: nx.DiGraph, x: Atom, s_nodes, z_plus, z_minus,
) -> tuple[str, ...]:
    """Unbiased distributions the SBD formula needs beyond P(v | S).

    Per Assumption 3.4 condition (3): the adjustment weights come from
    unbiased data T. They collapse to biased marginals when S ⊥ Z, so no
    external data is needed in that case.
    """
    z_all = tuple(z_plus) + tuple(z_minus)
    if not z_all:
        return ()
    if _z_recoverable_from_biased(graph, s_nodes, z_all):
        return ()
    if not z_minus:
        return (f"unbiased P({_names(z_plus)})",)
    # Z⁻ ≠ ∅ ⇒ the inner reweighting P(z⁻ | x, z⁺) is unbiased, so X must
    # also be in the unbiased sample (condition 3: "if Z⁻ ≠ ∅ then X ⊂ T").
    joint = ", ".join(
        p for p in (x.predicate, _names(z_plus), _names(z_minus)) if p
    )
    return (f"unbiased P({joint})",)


def recover_effect(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    s_nodes: tuple[Atom, ...],
    max_size: int = 4,
) -> SelectionRecoveryResult:
    """Recoverability of the causal effect P(y | do(x)) under selection bias.

    Searches for the smallest selection-backdoor admissible Z (SBD,
    sufficient). Among equally small admissible sets it prefers one that
    needs no external data. A ``recoverable=False`` verdict means "not
    via selection-backdoor adjustment", not "provably non-recoverable".
    """
    kind = "effect"
    if x not in graph or y not in graph:
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=False, criterion=None,
            selection_nodes=s_nodes, adjustment_set=(), z_plus=(), z_minus=(),
            formula_repr="", external_data_needed=(),
            failure_reason="处理或结局不在图中",
        )
    if not s_nodes:
        # No selection declared — ordinary identification territory; this
        # analysis is inert. Report trivially recoverable with no formula
        # so callers only surface it when selection is actually present.
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=True, criterion=None,
            selection_nodes=(), adjustment_set=(), z_plus=(), z_minus=(),
            formula_repr="", external_data_needed=(),
            failure_reason="no selection nodes declared",
        )

    descendants_x = nx.descendants(graph, x)
    forbidden = {x, y} | set(s_nodes)
    candidates = [n for n in graph.nodes if n not in forbidden]

    max_size = min(len(candidates), max_size)
    for size in range(0, max_size + 1):
        admissible: list[tuple[tuple[Atom, ...], tuple[Atom, ...]]] = []
        for combo in combinations(candidates, size):
            z = frozenset(combo)
            # SBD condition (1): S ⊥ Y | {X, Z}
            if not _s_all_dsep_from_y(graph, s_nodes, y, (x,) + tuple(combo)):
                continue
            z_plus = _sorted_atoms(z - descendants_x)
            z_minus = _sorted_atoms(z & descendants_x)
            # SBD condition (2): Z⁺ blocks every back-door path X → Y
            if not _zplus_blocks_backdoor(graph, x, y, z_plus):
                continue
            admissible.append((z_plus, z_minus))
        if not admissible:
            continue
        # Prefer an admissible set that needs no external data. The size was
        # skipped above unless ``admissible`` is non-empty, so its first entry
        # is always available as the fallback, and the scan below only ever
        # replaces it with a cheaper one.
        z_plus, z_minus = admissible[0]
        chosen_ledger = _external_ledger(graph, x, s_nodes, z_plus, z_minus)
        for cand_plus, cand_minus in (admissible[1:] if chosen_ledger else ()):
            ledger = _external_ledger(graph, x, s_nodes, cand_plus, cand_minus)
            if not ledger:
                z_plus, z_minus, chosen_ledger = cand_plus, cand_minus, ledger
                break
        return SelectionRecoveryResult(
            query_kind=kind, recoverable=True, criterion="selection_backdoor",
            selection_nodes=s_nodes,
            adjustment_set=tuple(z_plus) + tuple(z_minus),
            z_plus=z_plus, z_minus=z_minus,
            formula_repr=_effect_formula_repr(x, y, z_plus, z_minus),
            external_data_needed=chosen_ledger,
            failure_reason=None,
        )

    return SelectionRecoveryResult(
        query_kind=kind, recoverable=False, criterion=None,
        selection_nodes=s_nodes, adjustment_set=(), z_plus=(), z_minus=(),
        formula_repr="",
        external_data_needed=(),
        # Reaches the report as prose, so it is written in the reader's
        # language. The last clause is the load-bearing one: this search is
        # not the complete recovery algorithm, so "没找到" and "不存在" are
        # different statements and the reader must not read the first as
        # the second.
        failure_reason=(
            "在搜索预算内没找到可用的选择-后门调整集 Z，"
            "所以 P(y|do(x)) 无法用选择-后门调整恢复"
            "（完整的可恢复性算法不在本实现范围内 —— "
            "这里的「没找到」不等于「证明了恢复不出来」）"
        ),
    )
