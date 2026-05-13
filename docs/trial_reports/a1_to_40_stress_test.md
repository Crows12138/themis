# A1–#40 stress test report (task #33)

Date: 2026-04-21

## Setup

Fresh Claude sub-agents given `themis/prompts/nl_to_kernel_ast.md` +
three few-shot examples, asked to produce a canonical kernel_ast
JSON for one new Chinese NL question each. Four domain-varied
questions:

1. **医疗**: *"长期吃外卖会影响血糖吗"*
2. **教育**: *"多做练习题能提高数学成绩吗"*
3. **职场**: *"跟同事闹矛盾会让工作效率下降吗"*
4. **心理**: *"养宠物能减轻抑郁吗"*

Each output was then run through `themis.run`. One was taken through
a full three-turn loop (turn 1 → framing fill → turn 2 → parameter
fill → turn 3 → `themis.verify` audit).

## Technical findings — all four pass the boundary

Every agent produced a structurally valid kernel_ast:

- Intent correctly classified as `effect` in all four cases
- Predicates in English snake_case
- One `llm_proposal`-tagged cause edge per program
- All four framing fields left `null` on every predicate
- `themis.run` returned `needs_investigation` with both
  `validate_parameter` and `define_variable` investigation requests
- `validate_result` passes on every envelope

No parse errors, no schema failures, no rejected bundles. **The A1
(NL→JSON) + A2 (provenance) + A3 + A5 + F1 machinery works
end-to-end on previously unseen questions.**

## Semantic findings — four systemic gaps

Every agent self-reported an ambiguity the current framing fields
could not capture. The pattern is consistent across all four
cases and not specific to any one domain:

| Case | Agent-flagged ambiguity | Missing framing concept |
|---|---|---|
| 血糖 | "影响" direction unclear (up/down/variability) | **direction / polarity** |
| 数学 | "提高" has no baseline | **baseline / reference level** |
| 闹矛盾 | single event vs persistent state | **state vs event** semantics |
| 抑郁 | healthy-population vs clinical-patient scope | **population scope** (currently hard-coded to `"me"`) |

The `time_window / measurement / threshold / observability` set —
sufficient for *measurable quantitative claims* like
`exercise_waist` — systematically fails to surface these four
question types as asking the right clarifying follow-up.

## Systemic finding — response is too generic

Because the A1 prompt instructs the LLM to leave all four framing
fields null on every predicate, and the F1 channel then surfaces
those nulls as gaps, **every NL question gets the same four-field
clarifying ask**. The per-question nuance (direction, baseline,
scope) gets compressed into a generic list of four fields that
doesn't actually cover what the agent itself noticed.

The response-rendering prompt can paper over some of this by
picking semantic-appropriate filled-in examples per predicate, but
that's a workaround — the underlying framing dimensions are
under-specified.

## Correctness bug — apply_patch_and_run / verify round-trip

A real bug fell out of the three-turn audit test:

```python
out = themis.apply_patch_and_run(original_program, [framing, parameter])
themis.verify(original_program, out["results"][0])  # FAILED
```

The verifier rejected the patched result because Theta built from
the *original* program lacked the user-supplied parameter entry.
The result had been computed on a merged program; verifying it
against the pre-merge program is a category error.

**Fixed in the same commit as this report**:
`apply_patch_and_run` now returns
`{"results": [...], "merged_program": <ast_dict>}`. Callers audit with
`themis.verify(out["merged_program"], out["results"][i])`. Tests pin
both the positive round-trip (accepts) and the regression guard
(verifying against the original program still fails — the
correctness boundary is explicit).

## Recommendations

Priority order for follow-up:

1. **#36 Strong framing gate** — stays the scheduled path; now has a
   clearer mandate ("gate on insufficiency of the four fields" was
   always the plan). Unchanged.

2. **Framing fields v2 (new charter)** — extend the advisory /
   DEFINE_VARIABLE channel with `direction`, `baseline`,
   `state_vs_event`. Deliberately conservative — `population_scope`
   is a larger AST change (needs multi-object support beyond `"me"`)
   and should go through its own charter.

3. **Per-question custom framing asks** — iterate the response
   rendering prompt so when the structured output has framing gaps,
   the LLM tailors the concrete filled-in examples to the
   question's semantics (already happens in practice; now codify).

4. **#37 Phase 4 world modeling** — the stress-test confirms the NL
   layer is stable enough to sit above richer upstream; this
   unblocks Phase 4 work with a confident A1–#40 base.

## Artifacts

- All four agent-produced kernel_asts ran cleanly through
  `themis.run` in this session; outputs were temporary scratch and
  not committed (the four domain questions are recorded above; the
  structured outputs are reproducible from `nl_to_kernel_ast.md`).
- The correctness fix (`merged_program` in envelope) shipped as
  its own commit alongside this report.
- Tests: `tests/test_apply_patch_verify_roundtrip.py` (9 new)
  pin the correctness fix.
