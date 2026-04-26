"""S.11.2.4 — KBCache (SQLite) tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.kb.cache import KBCache, cache_key
from themis.kb.schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBQueryKind,
    KBResult,
)


def _q(kb: str = "primekg") -> KBQuery:
    return KBQuery(
        kb_name=kb,
        query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
        target={"predicate": "y"},
        given=({"predicate": "x"},),
    )


def _r(q: KBQuery, value: float = 0.42) -> KBResult:
    return KBResult(
        query=q,
        success=True,
        provenance=KBProvenance(
            source_kb=q.kb_name,
            query_used=q,
            retrieved_at="2026-04-27T00:00:00Z",
            raw_response_hash="hash",
            citation="PMID:1",
            confidence_grade=KBConfidenceGrade.RCT_META_ANALYSIS,
        ),
        value=value,
    )


def test_cache_key_deterministic():
    """Two equal queries → same key, every call."""
    q1 = _q()
    q2 = _q()
    assert cache_key(q1) == cache_key(q2)


def test_cache_key_kb_name_changes_key():
    """Different KB → different key (otherwise cross-KB collisions)."""
    assert cache_key(_q("primekg")) != cache_key(_q("scigraph"))


def test_cache_key_query_kind_changes_key():
    a = KBQuery(kb_name="x", query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
                target={"predicate": "y"})
    b = KBQuery(kb_name="x", query_kind=KBQueryKind.CONDITIONAL_DISTRIBUTION,
                target={"predicate": "y"})
    assert cache_key(a) != cache_key(b)


def test_cache_key_target_changes_key():
    a = _q()
    b = KBQuery(**{**a.__dict__, "target": {"predicate": "z"}})
    assert cache_key(a) != cache_key(b)


def test_cache_key_constraints_change_key():
    """Same predicates but different age constraints — different lookups."""
    a = _q()
    b = KBQuery(**{**a.__dict__, "constraints": {"age_range": [40, 70]}})
    assert cache_key(a) != cache_key(b)


def test_in_memory_get_miss_returns_none():
    with KBCache() as cache:
        assert cache.get(_q()) is None


def test_in_memory_round_trip():
    with KBCache() as cache:
        q, r = _q(), _r(_q(), 0.42)
        cache.put(q, r)
        got = cache.get(q)
        assert got == r


def test_persisted_round_trip(tmp_path: Path):
    db = tmp_path / "kb.sqlite"
    q, r = _q(), _r(_q(), 0.18)
    with KBCache(db) as cache:
        cache.put(q, r)
    with KBCache(db) as cache:
        got = cache.get(q)
        assert got == r


def test_put_overwrites():
    with KBCache() as cache:
        q = _q()
        cache.put(q, _r(q, 0.1))
        cache.put(q, _r(q, 0.9))
        assert cache.get(q).value == 0.9


def test_delete_returns_true_when_present():
    with KBCache() as cache:
        q = _q()
        cache.put(q, _r(q))
        assert cache.delete(q) is True
        assert cache.get(q) is None


def test_delete_returns_false_when_absent():
    with KBCache() as cache:
        assert cache.delete(_q()) is False


def test_clear_wipes_all():
    with KBCache() as cache:
        for kb in ("a", "b", "c"):
            cache.put(_q(kb), _r(_q(kb)))
        assert cache.stats()["entries"] == 3
        removed = cache.clear()
        assert removed == 3
        assert cache.stats()["entries"] == 0


def test_stats_empty():
    with KBCache() as cache:
        s = cache.stats()
        assert s == {"entries": 0, "oldest_at": None, "newest_at": None}


def test_stats_after_puts():
    with KBCache() as cache:
        cache.put(_q("a"), _r(_q("a")))
        cache.put(_q("b"), _r(_q("b")))
        s = cache.stats()
        assert s["entries"] == 2
        assert s["oldest_at"] is not None
        assert s["newest_at"] >= s["oldest_at"]


def test_different_kb_no_collision():
    """Same query target but different kb_name — separate entries."""
    with KBCache() as cache:
        q_a, q_b = _q("primekg"), _q("scigraph")
        cache.put(q_a, _r(q_a, 0.1))
        cache.put(q_b, _r(q_b, 0.2))
        assert cache.get(q_a).value == 0.1
        assert cache.get(q_b).value == 0.2
        assert cache.stats()["entries"] == 2


def test_failure_result_cached_too():
    """Negative results count — caching them avoids re-asking dead KBs."""
    with KBCache() as cache:
        q = _q()
        failed = KBResult(
            query=q, success=False,
            provenance=_r(q).provenance,
            failure_reason="no_match",
        )
        cache.put(q, failed)
        got = cache.get(q)
        assert got.success is False
        assert got.failure_reason == "no_match"


def test_chinese_payload_round_trip():
    """ensure_ascii=False so 中文 citations / queries round-trip."""
    with KBCache() as cache:
        q = KBQuery(
            kb_name="cdc_cn",
            query_kind=KBQueryKind.TARGET_POPULATION_MARGINAL,
            target={"predicate": "年龄"},
            population="中国成人",
        )
        r = KBResult(
            query=q, success=True,
            provenance=KBProvenance(
                source_kb="cdc_cn", query_used=q,
                retrieved_at="2026-04-27", raw_response_hash="h",
                citation="中国 CDC 2023 人口结构表",
            ),
            value=0.025,
        )
        cache.put(q, r)
        got = cache.get(q)
        assert got.provenance.citation == "中国 CDC 2023 人口结构表"


def test_close_idempotent():
    cache = KBCache()
    cache.close()
    # Second close should not raise
    cache.close()
