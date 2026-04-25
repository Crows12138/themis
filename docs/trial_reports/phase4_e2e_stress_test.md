# Phase 4 end-to-end blind stress test

Date: 2026-04-25

## Setup

Three blind sub-agents (isolated conversations, only access to A1 +
A5 + A2 prompts and one per-case input) produced the three structured
outputs needed to drive the full Phase 4 pipeline:

1. **A5 variable extraction** from the narrative
2. **A2 edge extraction** from the narrative
3. **A1 base kernel_ast** from the question

The orchestrator (this conversation) then ran:

```python
program = compose_program(a1_base, a5_variables, a2_edges)
themis.run(program)
```

Three cases covering different shapes:

- **Case 14** (late-night → tired) — simple temporal cause
- **Case 16** (hospitalized → diabetes) — selection bias / refusal
- **Case 21** (Mendelian randomization IV) — ADMG with bidirected confounder

## Aggregate result

| Case | Compose | Run | End state |
|---|---|---|---|
| 14 | OK | **fail** | SemanticError — query atoms with `time_index` not in V |
| 16 | OK | **fail** | SemanticError — A2 emitted only refusal, no cause edges → V empty |
| 21 | **fail → fix → OK** | OK | `needs_investigation` (no data; correct) |

1 of 3 ran end to end (after fixing one real bug). The other 2 hit
real architectural gaps that Phase 4 alone can't close.

## Bug found and fixed: cause + bidirected wrongly flagged as conflict

**Discovered by**: case 21.

`merge_edge_extractions` and `merge_edges_into_program` were treating
`cause(X→Y)` and `bidirected(X↔Y)` on the same predicate pair as a
**kind conflict**. This is wrong — ADMG semantics allow both edges
to coexist (a directed edge plus an unobserved confounder is exactly
the IV / front-door pattern).

**Fix**: track a *set* of kinds per pair instead of a single kind.
- `cause` + `bidirected` → coexist, no conflict
- `cause` + `refusal` → conflict (refusal means "don't draw any edge")
- `bidirected` + `refusal` → conflict (same reason)
- duplicate kinds → dedup (existing behavior)

Tests adjusted (3 tests rewritten); all 23 still pass. After the fix,
case 21 composes cleanly and runs to `needs_investigation` (the
correct answer — IV identification needs data to give a number).

## Real architectural gaps surfaced

### Gap 1: temporal atoms not first-class (case 14)

A1 prompt mentions `time_index: {kind: relative, value: -1}` for
"昨晚 X，今早 Y" patterns, but the kernel's atom schema doesn't
include `time_index` and V-set construction treats time-indexed
atoms as different from base atoms.

The agent emitted `time_index` on both the cause edge atoms AND the
query atoms; my merge helper stripped time_index from the cause edge
during injection (only `predicate` and `args` are kept), leaving the
query referencing time-indexed atoms that aren't in V.

**Status**: This is **Phase 5** territory (temporal / g-methods,
task #39). The fix is structural — needs first-class temporal atoms
in the schema, V-set, and downstream rules. Phase 4 cannot close it.

**Workaround for now**: A1 prompt could be patched to NOT emit
`time_index` until Phase 5 lands. Or `compose_program` could strip
`time_index` from query atoms (loses information silently — bad).

### Gap 2: refusal-only graphs trigger empty V (case 16)

A2 correctly emitted a refusal for `hospitalized → has_diabetes`
(selection bias). The variable declarations went into the program,
but no cause edges connect the atoms, so V (built from cause
statements) is empty. The kernel raises SemanticError.

The correct semantic answer is "cause(X, Y) is structurally false —
no path exists in the graph", not SemanticError. The user is
explicitly being told "I refuse to claim this", which is the right
narrative response, but the kernel currently can't represent that
result via the cause query path.

**Status**: kernel-level gap. Two possible fixes:
(a) Relax V-set construction to also include atoms from variable
    declarations (not just cause edges).
(b) Accept the strictness and have the orchestrator translate
    "refusal + no cause edge" into a synthesized response that
    bypasses `themis.run`.

Option (a) is the cleaner fix but touches multiple kernel sites
(V-set construction, ground rule, semantic validator). Option (b)
is a Phase 4 orchestrator workaround.

**Defer**: kernel relaxation is a separate slice. For now,
`compose_program` callers handling refusal-heavy narratives need to
short-circuit before `themis.run`.

### Gap 3: A2 prompt gaps (medium severity, surfaced by all 3 agents)

Consolidated from agent reports:

1. **Bidirected provenance with multiple edges**: A2 emits
   `narrative_proposal` for cause / bidirected / refusal uniformly.
   When all 3 kinds appear in one extraction (case 21), the schema
   shape varies (`from/to` vs `left/right` vs strings) — error-prone.
2. **`suggested_confounder` field name biases**: case 16 noted that
   for selection bias / collider patterns, the actual cause is "you
   conditioned on a collider", not "you missed a confounder". The
   field name is wrong for that pattern.
3. **A2 atom shape** (case 14): A2 prompt says atoms omit `args`,
   but examples include `time_index` — agents are uncertain whether
   to include it. Phase 5 dependency.
4. **`narrative_ambiguities` schema vs A1 ambiguity schema**: A2
   uses `description/chosen/alternatives`, A1 uses
   `reason/chosen/alternatives/disambiguation_ask`. Orchestrator has
   no canonical merge story.

These are documentation / prompt clarity gaps. Not blocking for the
3 cases that ran here, but would compound on more complex narratives.

## Recommendation

**Phase 4 mechanical layer is production-ready** for the case where
the narrative produces actual cause / bidirected edges (case 21).
The end-to-end pipeline:

```
narrative + question
  → 3 LLM calls (A5 / A2 / A1)
  → compose_program
  → themis.run
```

works on the canonical IV pattern with no human in the loop.

The 2 failing cases need work outside Phase 4:

- Case 14 → Phase 5 (temporal) [task #39]
- Case 16 → kernel V-set relaxation OR orchestrator-level
  refusal short-circuit (separate slice)

## Artifacts

- `docs/eval_set/phase4_e2e_run_v1/{14,16,21}_*_input.json` — agent inputs
- `docs/eval_set/phase4_e2e_run_v1/agent_outputs/{14,16,21}.json` — agent outputs
- 3 sub-agent transcripts in temp dir
- This report

## What's next

1. **Patch A2 prompt** to clarify atom shape (no `time_index` until
   Phase 5) and to add a `pattern: collider | confounder | reverse` field
   on refusals (replacing the `suggested_confounder` bias). Low effort.
2. **Defer** Phase 5 temporal work to task #39's slice.
3. **Defer** kernel V-set relaxation to a separate sub-slice if
   refusal-only narratives become a frequent pattern.
