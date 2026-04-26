"""Phase 11.2 — KB adapter abstract base class + client-side registry.

Themis provides only the contract; concrete adapters live in client code
(or sibling packages). KBRegistry is a *client-side* container — Themis
never instantiates it during kernel runs. The registry exists here so
adapters across different clients have a uniform shape.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .schemas import KBQuery, KBResult


class KBAdapter(ABC):
    """Implement this in client / sibling-package code to plug a real KB
    (PrimeKG, SciGraph, SemMedDB, etc.) into the gap-fill loop.

    `name` is the unique adapter identifier KBQuery.kb_name routes on.
    Subclasses set it as a class attribute.

    `query()` is the only required method. It MUST be deterministic over
    the given KBQuery — same query in, same KBResult out — so the cache
    layer can dedupe safely. If the underlying KB is non-deterministic
    (e.g. ranked search), the adapter is responsible for stabilizing
    (deterministic seed, top-1 only, etc.).

    `supports()` lets the registry route a query to the right adapter
    when multiple are registered. Default: kb_name match. Override if
    the adapter handles a subset of query_kinds.
    """

    name: str = ""

    @abstractmethod
    def query(self, q: KBQuery) -> KBResult: ...

    @classmethod
    def supports(cls, q: KBQuery) -> bool:
        return q.kb_name == cls.name


class KBRegistry:
    """Client-side container for registered adapters.

    Themis never instantiates this during kernel runs — it's a helper
    for client orchestrators that want a uniform routing layer. Clients
    can also bypass the registry and call adapters directly.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, KBAdapter] = {}

    def register(self, adapter: KBAdapter) -> None:
        """Add an adapter. Re-registering the same name overwrites
        (so test fixtures can swap mocks without explicit cleanup)."""
        if not adapter.name:
            raise ValueError(
                f"adapter {type(adapter).__name__} has empty `name`; "
                "set the class attribute"
            )
        self._adapters[adapter.name] = adapter

    def unregister(self, name: str) -> None:
        self._adapters.pop(name, None)

    def find(self, q: KBQuery) -> KBAdapter | None:
        """Route a query to the first registered adapter that supports
        it. Returns None when no adapter matches — the caller decides
        whether to fall back to AskUser, alternative KB, or surface
        the gap unfilled."""
        # Prefer exact kb_name match
        adapter = self._adapters.get(q.kb_name)
        if adapter is not None and adapter.supports(q):
            return adapter
        # Fall back to scanning (allows adapters that handle "any kb_name"
        # by overriding supports())
        for adapter in self._adapters.values():
            if adapter.supports(q):
                return adapter
        return None

    def list(self) -> list[str]:
        """Names of registered adapters, in registration order."""
        return list(self._adapters.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._adapters

    def __len__(self) -> int:
        return len(self._adapters)
