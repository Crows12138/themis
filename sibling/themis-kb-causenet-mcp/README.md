# themis-kb-causenet-mcp

**Sibling package** to [themis-causal](../../themis/): exposes [CauseNet](https://causenet.org/) as a [Model Context Protocol](https://modelcontextprotocol.io/) server so any Themis instance (or any MCP client) can verify LLM-proposed causal edges against the **11M causal relations** Heindorf et al. 2020 extracted from the web.

## Why sibling, not part of themis main

- **Independent installability** — Themis users who only need the causal kernel shouldn't carry a multi-GB knowledge graph
- **License separation** — CauseNet data is CC-BY 4.0; vendoring it into Themis (MIT) would force attribution downstream
- **Versioning independence** — CauseNet updates / re-extractions don't force Themis releases

Per `~/.claude/.../memory/kb_adapter_invariants.md` and `kb_adapter_invariants` memory entry:
> Themis 拥有契约和 translator，adapter 拥有 IO；接 PrimeKG/SciGraph/SemMedDB 必须走 sibling repo 形态，不能 vendor 进 themis 主仓.

## Why nested git (single repo) for now

Solo-dev convenience. Maintaining two separate git repos for one developer's project is overhead without offsetting collaboration benefit. The **package boundary** (separate `pyproject.toml`, separate Python namespace) preserves the architectural separation; the git boundary can be split later via `git subtree split` if/when published to PyPI as a separate package.

When that happens, this directory becomes the root of its own repo and is removed from `因果性ai/`'s git.

## Architecture — tiered-confidence routing

```
Themis kernel (themis/kb/contract.py KBAdapter)
       ↑
       │  KBQuery / KBResult
       │
themis/kb/adapters/causenet_mcp_adapter.py
       ↑  (Themis-side adapter, lives in themis main package)
       │  MCP tool calls
       │
causenet_mcp.server (this package)
       ↑
       ├── Tier 1: data/causenet-precision.sqlite (197K relations, ~83%)
       │              ↓ miss
       └── Tier 2: data/causenet-full.sqlite      (~11M relations, ~60-70%)
                      ↓ miss
                   verdict=not_found
```

Two-tier design (per `decided_at_tier` pattern from Auto-Research's
cascade verifier):

- **Tier 1 (precision)** — query first. ~83% extraction precision per
  Heindorf 2020. Confident hits labelled `confidence_tier=high_confidence`.
- **Tier 2 (full)** — fallback when precision misses. ~11M relations
  but lower precision (~60-70% estimated; no formal number published).
  Hits labelled `confidence_tier=extracted`. Themis-side adapter surfaces
  this caveat in `extensions.llm_proposed_review` so users see which
  tier validated each edge.
- **Not found** in either tier → `confidence_tier=not_found`. Honest
  "no support" — NOT "false", just unsupported by CauseNet.

Either DB is optional — if user only built precision, server runs
precision-only (smaller deployment). If only full, runs full-only
(with a warning since precision is the high-confidence path).

## Status

| Phase | Status |
|---|---|
| A — Data download + schema | 🔄 in progress |
| B — SQLite + indexes | ⏳ |
| C — Minimal MCP server (1 tool: query_edge) | ⏳ |
| D — Themis-side adapter | ⏳ (in themis main) |
| E — Integration into apply_patch_and_run | ⏳ (in themis main) |
| F — Real-question test | ⏳ |

## Honest caveats

- **CauseNet is a 2020 static snapshot**, not a living KG. "Verified by CauseNet" means "extracted from web/Wikipedia in 2020", not "definitely true now".
- **Precision ~83%** — about 17% of relations are extraction errors. The semantic of a `kb_verified` tag here should be "supported by a KG with ~83% precision", not "ground truth".
- **Concept matching is fuzzy** — Themis atom `predicate="aspirin"` vs CauseNet concept `"aspirin"` / `"acetylsalicylic acid"` / `"ASA"` — `translator.py` does normalization but won't catch all aliases.
- **Coverage is partial** — many real-world causal claims aren't in CauseNet. `kb_unverified` in such cases is a legitimate output, not a bug.

## License

Code: MIT (same as themis).

Data (`data/causenet-*.jsonl.bz2`, `data/causenet-sample.json`): CC-BY 4.0, attributed to Stefan Heindorf et al. "CauseNet: Towards a Causality Graph Extracted from the Web", CIKM 2020.
