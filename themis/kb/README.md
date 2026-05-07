# `themis.kb` — KB adapter contract

Themis owns the **contract**. Adapters that hit a real knowledge
base (PrimeKG, SciGraph, SemMedDB, Wikidata, a custom RAG index, …)
live in your own repo or sibling package — never vendored into
`themis/` proper.

This README is the 30-minute guide for someone implementing their
first adapter. It covers what to build, where to put it, and how
the contract gates correctness.

## What lives here vs. what you write

| Concern | Owner |
|---|---|
| `KBQuery` / `KBResult` / `KBProvenance` schemas | `themis.kb` (this dir) |
| `KBAdapter` ABC + registry | `themis.kb.contract` |
| `gap → KBQuery` translator, `KBResult → patch` translator | `themis.kb.translator` |
| Deterministic cache (SQLite, in-memory) | `themis.kb.cache` |
| Reference adapter (websearch proxy) | `themis.kb.adapters.websearch_proxy` |
| **Your real KB adapter** | **Your sibling repo** (e.g. `themis-kb-primekg`) |
| HTTP / SQL / vector-search / API IO | Your adapter |
| API auth, rate limiting, retries | Your adapter |

Themis itself never opens a socket. If your adapter wants to talk
to PubMed, that connection is in your code, not in `themis/`.

## The contract in one screen

```python
from themis.kb.contract import KBAdapter
from themis.kb.schemas import (
    KBQuery, KBResult, KBProvenance,
    KBConfidenceGrade,
)


class MyKBAdapter(KBAdapter):
    name = "my_kb"  # routes KBQuery.kb_name == "my_kb" here

    def query(self, q: KBQuery) -> KBResult:
        # 1. Translate q (structured: target/given/constraints) into
        #    your KB's native query language.
        # 2. Hit the KB. Catch failures.
        # 3. Return a KBResult — success or failure path; never raise.
        ...
```

That's the whole surface. Everything else flows from these
dataclasses.

## Required guarantees

1. **Determinism.** Same `KBQuery` in → same `KBResult` out, byte-
   for-byte (so the cache layer can dedupe). If your KB is
   stochastic (e.g. ranked search), stabilize: fix a seed, take
   top-1 only, hash sort.
2. **No exceptions out of `query()`.** Always return a `KBResult`,
   even on failure. Use `success=False` + `failure_reason` for
   no_match / parse_error / dtype_mismatch / unauthorized.
3. **Provenance always populated.** Even failed lookups carry a
   `KBProvenance` so the audit trail captures what was tried.
4. **No mutation of the query.** Treat `KBQuery` as frozen (it is).

## End-to-end example

```python
import themis
from themis.kb.contract import KBRegistry
from themis.kb.translator import gap_to_kb_query, kb_results_to_bundle

# 1. Run a question; collect data gaps.
out = themis.run(program)
result = out["results"][0]
gaps = result["data_gap_report"]["gaps"]

# 2. Translate each gap into a KBQuery, route to an adapter.
registry = KBRegistry()
registry.register(MyKBAdapter())

kb_results = []
for gap in gaps:
    q = gap_to_kb_query(gap, kb_name="my_kb")
    if q is None:
        continue  # gap kind not addressable by KB
    adapter = registry.find(q)
    if adapter is None:
        continue
    kb_results.append(adapter.query(q))

# 3. Translate KBResults back into a parameter_fill_bundle.
bundle = kb_results_to_bundle(kb_results)

# 4. Re-run with the patch applied.
out2 = themis.apply_patch_and_run(program, [bundle])
```

The gap → query → result → patch → re-run loop is the canonical
flow. `themis.apply_patch_and_run` round-trips the patch through the
verifier, which reads the `annotations.source` your adapter
populated as the `KBProvenance.citation` and re-routes confidence.

## Mapping gaps to query kinds

`gap_to_kb_query` (in `themis/kb/translator.py`) handles the most
common shapes:

| `data_gap_report.kind` | `KBQueryKind` |
|---|---|
| `missing_distribution` (marginal `P(...)`) | `MARGINAL_DISTRIBUTION` |
| `missing_distribution` (conditional `P(...|...)`) | `CONDITIONAL_DISTRIBUTION` |
| `missing_distribution` (joint `P(a,b)`) | `JOINT_DISTRIBUTION` |
| `missing_population_distribution` | `TARGET_POPULATION_MARGINAL` |
| `transport_target_distribution_unknown` | `TARGET_POPULATION_MARGINAL` |
| `transport_source_conditional_unknown` | `STRATIFIED_SUBGROUP` |
| `missing_iv_candidate` | `IV_CANDIDATE` |
| `missing_mediator_data` | `MEDIATOR_DISTRIBUTION` |

If a gap kind isn't mapped, the translator returns `None` —
that gap stays a user-facing ask (or surfaces as an unmet need in
the agent loop).

## Confidence grading

`KBConfidenceGrade` is a coarse five-level GRADE-style ladder plus an
`unknown` sentinel — six enum values total:
`rct_meta_analysis` > `single_rct` > `cohort` > `case_control` >
`expert_opinion` > `unknown`. Set it from your KB's quality metadata
when available; default to `unknown` when not.

This grade is **not** Themis's confidence value (`annotations.
confidence` ∈ [0, 1]). It's metadata for a future conflict-resolution
pass (S.11.7) that may weight competing answers from multiple KBs.

## What to test

For a new adapter, mirror the tests in
`tests/test_kb/test_websearch_proxy.py`:

- One test per `KBQueryKind` your adapter supports
- Failure path returns `success=False` with sensible
  `failure_reason`, never raises
- Determinism test: same query twice → identical `KBResult`
- Round-trip via `kb_result_to_dict` + `kb_result_from_dict`
- Cache integration: `cache_key(q)` is stable across runs

If your adapter wraps an HTTP API, mock the transport layer in
tests. Don't hit real endpoints in CI.

## What you should never do

- Don't import anything from `themis.runtime` or `themis.kernel`.
  Adapters speak only the KB schema.
- Don't mutate or extend the `KBQuery` / `KBResult` schemas. If
  your KB needs metadata that doesn't fit, put it in
  `KBProvenance.notes` or `KBQuery.constraints`.
- Don't raise on partial success. Return `KBResult` with
  `success=True` + `interval=(low, high)` when you have a range
  rather than a point.
- Don't cache inside the adapter. The `themis.kb.cache` layer
  handles that — adapters should be pure functions of their input.

## See also

- `PHASE_11_2_KB_ADAPTER_CHARTER.md` — full design rationale
- `kb_query.schema.json` / `kb_result.schema.json` — JSON mirrors
- `themis/kb/adapters/websearch_proxy.py` — reference adapter
