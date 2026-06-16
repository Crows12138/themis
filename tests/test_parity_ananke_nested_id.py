"""Dev-time parity calibration: Themis nested-ID vs ananke OneLineID.

Confirms Themis's complete nonparametric point-identification
(``c_factor.identify_via_tian``) agrees with ananke's ``OneLineID`` — the
reference complete algorithm (Richardson/Shpitser one-line ID) — on the
identifiability verdict for ``P(Y | do(X))``.

This is the empirical evidence that the graph-aware simplification
completeness layer (Phase 16 "slice 3") is NOT needed: across every
connected 4-node ADMG, Themis already matches the reference, with no miss
(identifiable-but-punted) and no overclaim (punted-but-claimed).

ananke is a PARITY-CALIBRATION tool only — never a production dependency
(see COVERAGE_MAP.md "外部库的位置"). The whole module skips when ananke
is not importable, so the normal suite is unaffected. Install for dev with
``python -m pip install --no-deps ananke-causal``.
"""
from __future__ import annotations

import itertools

import networkx as nx
import pytest

pytest.importorskip("ananke", reason="ananke is a dev-only parity tool")

from ananke.graphs import ADMG  # noqa: E402
from ananke.identification import OneLineID  # noqa: E402

from themis.runtime import c_factor  # noqa: E402
from themis.types import Atom, ConstTerm  # noqa: E402


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _themis_id(vertices, di_edges, bi_edges, x="X", y="Y") -> bool:
    g = nx.DiGraph()
    g.add_nodes_from(_A(v) for v in vertices)
    g.add_edges_from((_A(u), _A(v)) for u, v in di_edges)
    bd = frozenset(frozenset({_A(u), _A(v)}) for u, v in bi_edges)
    return c_factor.identify_via_tian(g, bd, _A(x), _A(y), True).identifiable


def _ananke_id(vertices, di_edges, bi_edges, x="X", y="Y") -> bool:
    g = ADMG(list(vertices), list(di_edges), list(bi_edges))
    return OneLineID(graph=g, treatments=[x], outcomes=[y]).id()


# ============================================ literature controls

_LITERATURE = [
    # (label, vertices, di, bi, expected_identifiable)
    ("napkin", ["W", "Z", "X", "Y"], [("W", "Z"), ("Z", "X"), ("X", "Y")],
     [("W", "X"), ("W", "Y")], True),
    ("extended_napkin", ["W", "Z", "X", "M", "Y"],
     [("W", "Z"), ("Z", "X"), ("X", "M"), ("M", "Y")],
     [("W", "X"), ("W", "Y")], True),
    ("parallel_mediators", ["X", "M", "N", "Y"],
     [("X", "M"), ("M", "Y"), ("X", "N"), ("N", "Y")], [("X", "Y")], True),
    ("bow_arc", ["X", "Y"], [("X", "Y")], [("X", "Y")], False),
    ("front_door", ["X", "M", "Y"], [("X", "M"), ("M", "Y")],
     [("X", "Y")], True),
    ("iv_shape", ["Z", "X", "Y"], [("Z", "X"), ("X", "Y")],
     [("X", "Y")], False),
]


@pytest.mark.parametrize("label,verts,di,bi,expected",
                         _LITERATURE, ids=[c[0] for c in _LITERATURE])
def test_literature_cases_match_ananke(label, verts, di, bi, expected):
    a = _ananke_id(verts, di, bi)
    t = _themis_id(verts, di, bi)
    assert a == expected, f"ananke disagrees with the literature on {label}"
    assert t == a, f"Themis != ananke on {label}: themis={t} ananke={a}"


# ============================================ exhaustive 4-node sweep


def _enumerate_4node():
    """All connected ADMGs on {X, Y, V0, V1} with an X→…→Y directed path,
    ≤6 directed edges (DAG), and 1–3 bidirected edges. Deduplicated."""
    vertices = ["X", "Y", "V0", "V1"]
    dpairs = [(u, v) for u in vertices for v in vertices if u != v]
    bpairs = [(vertices[i], vertices[j])
              for i in range(len(vertices)) for j in range(i + 1, len(vertices))]

    def _is_dag(di):
        g = nx.DiGraph(); g.add_nodes_from(vertices); g.add_edges_from(di)
        return nx.is_directed_acyclic_graph(g)

    def _has_xy(di):
        g = nx.DiGraph(); g.add_nodes_from(vertices); g.add_edges_from(di)
        return nx.has_path(g, "X", "Y")

    def _connected(di, bi):
        g = nx.Graph(); g.add_nodes_from(vertices)
        g.add_edges_from(di); g.add_edges_from(bi)
        return nx.is_connected(g)

    di_subsets = []
    for k in range(1, 7):
        for combo in itertools.combinations(dpairs, k):
            if _is_dag(combo) and _has_xy(combo):
                di_subsets.append(combo)

    seen = set()
    for di in di_subsets:
        for kb in range(1, 4):
            for bcombo in itertools.combinations(bpairs, kb):
                if not _connected(di, bcombo):
                    continue
                key = (frozenset(di), frozenset(frozenset(b) for b in bcombo))
                if key in seen:
                    continue
                seen.add(key)
                yield vertices, di, bcombo


def test_exhaustive_4node_parity_with_ananke():
    """Themis nested-ID matches ananke on EVERY connected 4-node ADMG:
    no miss (identifiable but punted), no overclaim (unidentifiable but
    claimed). This is the proof that slice 3 is not currently needed."""
    tested = agree = identifiable = 0
    misses = []
    overclaims = []
    for verts, di, bi in _enumerate_4node():
        a = _ananke_id(verts, di, bi)
        t = _themis_id(verts, di, bi)
        tested += 1
        if a:
            identifiable += 1
        if a == t:
            agree += 1
        elif a and not t:
            misses.append((di, bi))
        else:
            overclaims.append((di, bi))

    # Non-vacuous: the sweep genuinely exercised the identifiable region.
    assert tested > 5000, f"expected a full 4-node sweep, got {tested}"
    assert identifiable > 1000, (
        f"sweep barely hit identifiable graphs ({identifiable}); not a real "
        f"completeness check"
    )
    assert not misses, (
        f"{len(misses)} identifiable-but-punted graphs (slice-3 drivers), "
        f"e.g. di={list(misses[0][0])} bi={list(misses[0][1])}"
    )
    assert not overclaims, (
        f"{len(overclaims)} unidentifiable-but-claimed graphs (OVERCLAIM — "
        f"worse than a miss), e.g. di={list(overclaims[0][0])} "
        f"bi={list(overclaims[0][1])}"
    )
    assert agree == tested
