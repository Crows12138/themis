"""S.11.2.2 — KBAdapter ABC + KBRegistry tests."""
from __future__ import annotations

import pytest

from themis.kb.contract import KBAdapter, KBRegistry
from themis.kb.schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBQueryKind,
    KBResult,
)


def _q(kb_name: str = "mock_kb", kind: KBQueryKind = KBQueryKind.MARGINAL_DISTRIBUTION) -> KBQuery:
    return KBQuery(kb_name=kb_name, query_kind=kind, target={"predicate": "y"})


class _MockAdapter(KBAdapter):
    name = "mock_kb"

    def __init__(self) -> None:
        self.calls: list[KBQuery] = []

    def query(self, q: KBQuery) -> KBResult:
        self.calls.append(q)
        return KBResult(
            query=q,
            success=True,
            provenance=KBProvenance(
                source_kb=self.name,
                query_used=q,
                retrieved_at="2026-04-27T00:00:00Z",
                raw_response_hash="h",
                citation="mock",
            ),
            value=0.5,
        )


class _PickyAdapter(KBAdapter):
    """Only handles conditional_distribution queries."""
    name = "picky"

    def query(self, q: KBQuery) -> KBResult:
        return KBResult(
            query=q, success=True,
            provenance=KBProvenance(
                source_kb=self.name, query_used=q,
                retrieved_at="2026-04-27", raw_response_hash="h",
                citation="picky",
            ),
            value=0.7,
        )

    @classmethod
    def supports(cls, q: KBQuery) -> bool:
        return (
            q.kb_name == cls.name
            and q.query_kind == KBQueryKind.CONDITIONAL_DISTRIBUTION
        )


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        KBAdapter()  # type: ignore[abstract]


def test_register_and_find():
    reg = KBRegistry()
    a = _MockAdapter()
    reg.register(a)
    assert reg.find(_q()) is a


def test_find_returns_none_when_no_match():
    reg = KBRegistry()
    reg.register(_MockAdapter())
    assert reg.find(_q(kb_name="other")) is None


def test_register_empty_name_rejected():
    reg = KBRegistry()
    class _NoName(KBAdapter):
        name = ""
        def query(self, q): ...  # noqa
    with pytest.raises(ValueError, match="empty"):
        reg.register(_NoName())


def test_re_register_overwrites():
    reg = KBRegistry()
    a1 = _MockAdapter()
    a2 = _MockAdapter()
    reg.register(a1)
    reg.register(a2)
    assert reg.find(_q()) is a2


def test_unregister():
    reg = KBRegistry()
    a = _MockAdapter()
    reg.register(a)
    reg.unregister(a.name)
    assert reg.find(_q()) is None


def test_unregister_missing_no_raise():
    reg = KBRegistry()
    reg.unregister("never_registered")  # should be a no-op


def test_list_preserves_order():
    reg = KBRegistry()
    class A(KBAdapter):
        name = "a"
        def query(self, q): ...  # noqa
    class B(KBAdapter):
        name = "b"
        def query(self, q): ...  # noqa
    reg.register(A())
    reg.register(B())
    assert reg.list() == ["a", "b"]


def test_contains_and_len():
    reg = KBRegistry()
    assert "mock_kb" not in reg
    assert len(reg) == 0
    reg.register(_MockAdapter())
    assert "mock_kb" in reg
    assert len(reg) == 1


def test_picky_supports_filters_by_query_kind():
    reg = KBRegistry()
    reg.register(_PickyAdapter())

    # marginal — picky's supports() returns False
    assert reg.find(_q(kb_name="picky", kind=KBQueryKind.MARGINAL_DISTRIBUTION)) is None

    # conditional — picky accepts
    found = reg.find(_q(kb_name="picky", kind=KBQueryKind.CONDITIONAL_DISTRIBUTION))
    assert isinstance(found, _PickyAdapter)


def test_query_dispatches_through_adapter():
    reg = KBRegistry()
    a = _MockAdapter()
    reg.register(a)
    q = _q()
    result = reg.find(q).query(q)
    assert a.calls == [q]
    assert result.success
    assert result.value == 0.5


def test_default_supports_uses_kb_name():
    """Adapter that doesn't override supports() — exact kb_name match."""
    a = _MockAdapter()
    assert a.supports(_q(kb_name="mock_kb"))
    assert not a.supports(_q(kb_name="other"))
