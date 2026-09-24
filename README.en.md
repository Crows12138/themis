# themis-causal

> *English README · [中文 README](README.md)*

**A causal-reasoning backbone for LLM agents.** When your agent receives a causal question — "Does X cause Y?" / "What's the effect of X on Y?" / "If we'd intervened on X, would Y have changed?" — Themis forces the agent to articulate the variables, the DAG, and the query as JSON, then runs Pearl-style identification, surfaces specific data gaps as named `GapKind`s with paper-level citations, and **refuses to fabricate effect sizes** when the data isn't there.

## Why this exists

LLMs answering causal questions have three failure modes that don't go away with bigger models:

1. **Fabricated effect sizes** — confident "X reduces Y by 20%" with no traceable source.
2. **Conflated mechanisms** — mixing confounding with collider bias in the same paragraph.
3. **Soft caveats over hard "not identifiable"** — papering over identification failures with "depends on many factors".

For AI agents whose causal claims will be *acted on, audited, or cited* — medical decision support, A/B test attribution, policy analysis, scientific research assistance — those failure modes are load-bearing risks.

Themis sits between the LLM and the answer. Mechanically:

- The kernel returns no number unless data was supplied — the LLM literally cannot output a fabricated effect size through this path.
- Every result carries a DAG, an identification formula, a `GapKind` list with citations (Pearl, Hernán, Manski, MacMahon, …), and a derivation chain. Auditable.
- When identification fails, the kernel says `not_identifiable` or returns Manski natural bounds — no soft fallback to a guessed number.

## Quick start

```bash
pip install themis-causal
```

Then add the Themis MCP server to your Claude Code config (`.mcp.json` in your project, or `~/.claude/.mcp.json` for user-level):

```json
{
  "mcpServers": {
    "themis": {
      "command": "themis-mcp"
    }
  }
}
```

Restart Claude Code. Your agent now has `mcp__themis__*` tools:

- `themis_run(program)` — main entry: runs identification + emits `data_gap_report`
- `themis_apply_patch_and_run(program, patches)` — multi-turn fill-back loop
- `themis_verify(program, result)` — independent V0-V5 re-check
- `themis_estimate(program, csv_path)` — numeric estimate with CSV data
- `themis_discover(csv_path, ...)` — PC / FCI / LiNGAM DAG discovery
- `themis_list_resources()` — schema + prompt URI catalog
- `themis_result(result_id, pointer)` — a result too large to hand over whole is kept on the server and handed over with parts folded; this fetches a folded part
- `themis_guide(doc, section)` — the guides and schemas, one section at a time

### Install the agent-integration Claude Skill

The package ships a Claude Skill that auto-triggers `mcp__themis__*` when the user asks a causal question. Install it user-level:

```bash
# Find where themis is installed:
python -c "import themis, os; print(os.path.dirname(themis.__file__))"

# Copy the skill (replace <INSTALL_DIR> with the path above):
mkdir -p ~/.claude/skills
cp -r <INSTALL_DIR>/claude_skills/themis-causal-check ~/.claude/skills/
```

After restart, when a user asks any causal question, Claude auto-loads the skill body and routes through Themis.

## What you get vs. what you don't

**Themis adds**:

- A mechanical block on number-fabrication for causal claims (validated in the [reverse benchmark](benchmarks/agent_integration/) — 0/3 vs 3/3 vanilla on Q1/Q2/Q3 effect-size hallucinations).
- A formal audit trail (DAG + identification formula + `GapKind` list + paper citations + bounds expressions) that downstream agents / reviewers / compliance can inspect.
- A conservative default — `needs_investigation` with structured "what data would unblock this" instead of an answer with a vague caveat.

**Themis does not**:

- Make up data. No data → Manski natural bounds (or `[0, 1]` if nothing is supplied).
- Infer the causal DAG. The LLM proposes edges; the kernel checks identification on the proposed DAG. Garbage in = garbage out. (`themis_discover` exists for CSV-driven discovery as a separate, opt-in workflow.)
- Replace strong base-LLM causal knowledge. Modern frontier models recognize Berkson's paradox and ill-defined-intervention concerns unaided — what Themis adds is *forcing* those recognitions into formal output, not knowing more.

## Programmatic Python API (non-MCP path)

```python
from themis import run, apply_patch_and_run, estimate, verify

# Main entry: JSON dict in, JSON dict out
out = run(program)

# Multi-turn fill-back
out2 = apply_patch_and_run(program, [filled_bundle])

# Numeric estimation with a DataFrame
estimated = estimate(program, df)

# Independent re-verification
verify(program, out["results"][0])
```

Boundary contract:

- `run` / `verify` are pure JSON — no network, no disk reads outside the package schemas.
- `estimate` accepts a `pandas.DataFrame` — a numeric estimation side-channel; doesn't alter kernel semantics.
- KB adapters / external resource lookups happen in client code or sibling repos. Themis itself sends no requests.

**MCP server note**: the MCP server is a long-running process and does not auto-reload code changes. After upgrading `themis-causal` (e.g., `pip install -U themis-causal`), restart your MCP server (`/mcp restart` in Claude Code, or exit and reopen the session).

## Reverse benchmark — what we measured

`benchmarks/agent_integration/` contains a reproducible comparison: three real NL causal questions × (vanilla LLM with no tools vs. LLM + Themis-MCP + agent-integration prompt), scored against 5 binary rubric criteria. Latest run (2026-05-12):

| | Vanilla LLM | LLM + Themis |
|---|---|---|
| Q1 (running → waist, confounding + measurement error) | 1.5 / 5 | 5 / 5 |
| Q2 (smoking → cancer, Berkson collider) | 3 / 5 | 5 / 5 |
| Q3 (obesity → CHD, ill-defined intervention) | 2.5 / 5 | 5 / 5 |
| **Total** | **7 / 15** | **15 / 15** |

The decisive gaps are on (1) "didn't fabricate effect sizes" — vanilla failed all three — and (4) "audit trail" — vanilla produced free-text prose, Themis produced DAGs + `GapKind`s + bounds.

Full per-question rubric: [benchmarks/agent_integration/findings_2026-05-12.md](benchmarks/agent_integration/findings_2026-05-12.md).

## License

MIT. Author: Crows12138 (`ucapxux@ucl.ac.uk`).

## Status

- 1943 passing tests
- 15 reproducible L3 case fixtures (each anchored to an authoritative causal-inference paper)
- 30+ `GapKind`s mapped to specific identification / measurement / framing failure modes

For deeper documentation in Chinese, see [README.md](README.md) and [CORE_STATUS.md](CORE_STATUS.md).
