# KB Lookup — structured fetch from a `data_gap_report` (Phase 11.2)

> **Purpose**: when `gap_to_action.md` says "fetch this gap from a KB",
> use the structured `KBQuery` / `KBResult` contract instead of a
> free-form WebSearch string. The translation helpers in
> `themis.kb.translator` turn `data_gap_report` entries into
> `KBQuery` and turn returned `KBResult`s into the
> `parameter_fill_bundle` shape that `apply_patch_and_run` accepts.
>
> Pairs with [`gap_to_action.md`](gap_to_action.md) (decides *what* to
> fetch) and [`response_rendering.md`](response_rendering.md) (renders
> the result). This prompt covers *how* to do the structured fetch
> once you've decided to.

## Why structured

The Phase 11.1 loop already works without this prompt — `gap_to_action.md`
tells the orchestrator to WebSearch the gap and build a
`parameter_fill_bundle` by hand. That works, but:

- **Search strings are unaudited** — re-running the same gap a week
  later gives a different search query, so two cache hits diverge.
- **Provenance is loose** — `annotations.source: "PMID:12345"` is set
  by the LLM looking at messy WebSearch output; it can drop or hallucinate.
- **Adapters can't be plugged in** — when a client has a real
  PrimeKG / SciGraph / SemMedDB adapter, there's no shape for the
  LLM to route through it.

The structured `KBQuery` shape solves all three: deterministic over
gap, provenance carried through `KBProvenance`, and the same shape
adapters consume — so PrimeKG / SciGraph / WebSearch all fit one path.

## The flow

```
data_gap_report.gaps[i]                ← from themis.run
   │
   ├─ themis.kb.translator.gap_to_kb_query(gap, target=, given=, kb_hint=)
   │   → KBQuery (or None if gap_kind has no KB fix)
   ↓
KBRegistry.find(query)                ← client-side; routes by kb_name
   │
   ↓
adapter.query(query)                  ← actual fetch (network / DB / cache)
   │
   ↓
KBResult                              ← carries value + interval + provenance
   │
   ├─ themis.kb.translator.kb_results_to_bundle([result1, result2, ...])
   │   → parameter_fill_bundle dict
   ↓
themis.apply_patch_and_run(program, [bundle])
   │
   ↓
verifier (T10) checks provenance
```

The orchestrator (you) drives steps 1, 3, 5 in client code. Themis
provides the schemas + the two translator functions. Adapters live in
your client or third-party packages — Themis itself never makes a
network call.

## When to use this vs the §"Patch shapes" hand-build

| Situation | Use |
|---|---|
| Client has a real KB adapter registered (PrimeKG, SciGraph, ...) | structured KBQuery flow (this prompt) |
| Only WebSearch is available, fetching one number ad-hoc | either; structured is cleaner audit but hand-build is simpler |
| Debugging / one-off / first time integrating a new KB | structured — the typed contract surfaces mismatches early |
| You need provenance.confidence_grade / sample_size in the audit trail | structured — those fields don't have a slot in hand-built bundles |

When in doubt, structured. Hand-build is the fallback.

## Building the KBQuery

`gap_to_kb_query(gap, target=, given=, kb_hint=, ...)` is a pure
function. The caller supplies the structured atoms because
`gap.description` is freeform Chinese / mixed and not reliably
parseable.

```python
from themis.kb import gap_to_kb_query, KBQueryKind

# After themis.run returned a result with data_gap_report
gap = result.data_gap_report.gaps[0]   # the first blocking gap

# Atoms come from the kernel_ast you already constructed
target = {
    "predicate": "belly_fat_loss",
    "args": [{"type": "const", "name": "me"}],
    "value": True,
}
given = (
    {"predicate": "running",
     "args": [{"type": "const", "name": "me"}],
     "value": True},
)

q = gap_to_kb_query(
    gap,
    target=target,
    given=given,
    kb_hint="primekg",          # or omit; defaults to "websearch_proxy"
    constraints={"age_range": [25, 35]},   # optional refinements
)

if q is None:
    # gap_kind not KB-fixable (unidentifiable / missing_assumption /
    # ambiguous_variable_definition) — render and ask user instead
    ...
```

Mappings that translator applies:

| `gap.kind` | `KBQueryKind` |
|---|---|
| `missing_distribution` (signature=`marginal`) | `marginal_distribution` |
| `missing_distribution` (signature=`conditional`) | `conditional_distribution` |
| `missing_distribution` (signature=`joint`) | `joint_distribution` |
| `missing_population_distribution` | `target_population_marginal` |
| `transport_target_distribution_unknown` | `target_population_marginal` |
| `transport_source_conditional_unknown` | `stratified_subgroup` |
| `missing_iv_candidate` | `iv_candidate` |
| `missing_mediator_data` | `mediator_distribution` |
| `unidentifiable_no_admissible_set` | (None — structural) |
| `missing_assumption` | (None — user choice) |
| `ambiguous_variable_definition` | (None — user reframing) |

## Calling the adapter

If the client has a `KBRegistry`, route through it:

```python
from themis.kb import KBRegistry

reg: KBRegistry = ...   # client-side; populated at startup
adapter = reg.find(q)
if adapter is None:
    # No registered adapter handles this kb_name — fall back to
    # AskUser or hand-built WebSearch path
    ...
result = adapter.query(q)
```

If the client only has a single search function (no adapter framework),
use `WebSearchProxyAdapter` as the minimum-viable wrapper:

```python
from themis.kb.adapters.websearch_proxy import (
    WebSearchProxyAdapter, ParsedSearchResult
)

def search(q):
    # Your client-side logic: call WebSearch / parse the response /
    # return a ParsedSearchResult dict (or None if extraction failed)
    raw = call_websearch(...)
    parsed = extract_value_from_text(raw)
    if parsed is None:
        return None
    return ParsedSearchResult(
        value=parsed["mean"],
        interval=parsed.get("ci"),
        sample_size=parsed.get("n"),
        citation=parsed["pmid"],
        raw_response=raw,
        confidence_grade="rct_meta_analysis",
    )

adapter = WebSearchProxyAdapter(search)
result = adapter.query(q)
```

The reference adapter does no parsing — it expects the search function
to return a structured dict already. Parsing free text into numbers is
the LLM's domain, not the adapter's.

## Building the patch

`kb_results_to_bundle(results)` turns one or more `KBResult`s into the
`parameter_fill_bundle` shape. Two invariants govern the conversion:

- **Provenance is per-value, not aggregable.** Each `KBResult` carries
  its own `provenance.citation`. When two adapters answer the same
  gap, both become separate skeletons (each with its own citation) —
  values across sources are never averaged or otherwise combined,
  because the resulting number would have no single source to audit.
- **None is the contract for failure, not a bug.** Failed / value-less
  results are silently dropped from the bundle. Checking
  `len(bundle["skeletons"])` against `len(results)` tells you how many
  KB calls actually produced data; the missing ones leave their gap
  in `blocking` state, which is the intended signal.

```python
from themis.kb import kb_results_to_bundle

bundle = kb_results_to_bundle([result_for_gap1, result_for_gap2])
new_envelope = themis.apply_patch_and_run(program, [bundle])
```

`bundle["skeletons"][i]["annotations"]["source"]` is set verbatim from
`result.provenance.citation` — the verifier (T10) treats this as
sourced provenance and assigns the value `confidence > 0`. Without a
real citation in `provenance.citation`, the patch will be treated as
fabricated.

## Caching

KB facts are immutable across a session — the same `KBQuery` returns
the same answer the next turn, the next hour, and (usually) the next
week. The cache is therefore the canonical store for any query that
has been issued: re-issuing a query means reading the cache, not
re-fetching. Negative results are part of this contract — a cached
failure is just as authoritative as a cached success.

`themis.kb.KBCache` is local SQLite. The orchestrator manages it
(Themis doesn't touch it):

```python
from themis.kb import KBCache

cache = KBCache("kb_cache.sqlite")    # or ":memory:"

cached = cache.get(q)
if cached is not None:
    result = cached
else:
    result = adapter.query(q)
    cache.put(q, result)
```

No TTL — KB facts are not session state. To force a refresh, call
`cache.delete(q)` then re-query.

Negative results are cached too (failure with `failure_reason`) — that
prevents re-asking dead KBs every turn.

## When NOT to lookup

`gap_to_action.md` §"Three questions per gap" still owns the decision
of whether to fetch at all. This prompt only kicks in once you've
decided yes. Specifically, do NOT structured-lookup when:

- `gap.kind in {unidentifiable_no_admissible_set, missing_assumption,
  ambiguous_variable_definition}` — `gap_to_kb_query` returns None;
  no fetch is appropriate
- The dtype mismatches (kernel says bool, KB has continuous mmHg) —
  even if the lookup succeeds, the patch will be a fabrication of
  YOUR threshold. Surface the literature value via
  `response_rendering.md` §"Literature numeric rendering" instead
- The user has explicitly asked you to wait / not search

