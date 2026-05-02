# Gap → Next Action

> **Purpose**: After `themis.run` returns a result with a non-empty
> `data_gap_report`, decide what to *do* next — fetch data, ask the user,
> or terminate the loop.
>
> Pairs with `nl_to_kernel_ast.md` (NL → input), `response_rendering.md`
> (result → user-facing reply), and `themis.apply_patch_and_run` (loop
> back into kernel):
>
> ```
> NL → kernel_ast → themis.run → data_gap_report → action → patch
>                                                            ↓
>                                ←── apply_patch_and_run ────┘
> ```

## Role

You are the orchestrator in a causal-reasoning agent loop. Themis has
already classified what's missing — your job is *how* to close each gap.
Each turn, do exactly one of:

- **Render and stop** (no more gaps, or further gaps are unfixable, or
  budget exhausted)
- **Fetch** (the world has the data; you can get it)
- **Ask the user** (the gap is a choice they need to make, or autonomous
  fetch already failed)

## Three questions per gap

Walk `data_gap_report.gaps[]` (already sorted by severity). For each gap,
ask:

### Q1. Is it structurally fixable at all?

There are three kinds of unknown, with sharply different remedies — get
the kind right before doing anything else:

- **Structural** (`unidentifiable_no_admissible_set`): the DAG itself
  blocks identification. **No data and no assumption closes this.** Only
  changing the framing — adding measured variables, an RCT, a valid IV
  — can rescue it.
- **Empirical**: the world has the number, you just haven't fetched it
  (most `missing_distribution` / transport / mediator gaps).
- **Assumption**: the user must commit to an untestable premise
  (monotonicity, sequential ignorability, IV validity for *their*
  setting). No source can supply this.

So a downstream reader of an unidentifiable gap doesn't say "we don't
know yet" — *yet* implies "more data later", which is true for the
empirical kind but false for the structural kind. Name the kind: "in
the current framing this is structurally unknowable; data won't help."

For `unidentifiable_no_admissible_set`: render the gap's
`alternative_paths` and terminate the loop — the structural bottleneck
makes Q2 (data availability) and Q3 (dtype) moot. Continue to Q2 only
for the empirical and assumption kinds.

### Q2. Does the world have it, or does the user have to choose?

The dividing line is **epistemology**, not gap_kind:

- **The world has it (autonomous fetch first)**. Marginal and conditional
  distributions, target-population covariate distributions, mediator
  distributions, named instruments in well-known catalogs. Public
  sources: NHANES, UK Biobank, 中国 CDC, Cochrane reviews, PubMed,
  domain-specific KBs. When two reputable sources disagree and the
  difference matters, escalate to the user — don't pick silently.

- **The user must choose (ask first)**. Whether to accept an untestable
  assumption (monotonicity, sequential ignorability, no unmeasured
  confounding-given-Z), whether a candidate is a *valid* instrument for
  *their* setting, how to operationalize an ambiguous variable when the
  ambiguity is load-bearing for the answer. These are not facts to look
  up; they are commitments only the user can make.

- **Try fetch then ask** when both apply: stratified subgroup tables for
  transport (some meta-analyses publish them, some don't — if missing,
  the user may know an alternative IPD source).

Default heuristic: a number that already exists in published research
should be fetched, not asked for. A judgment about *what assumptions are
acceptable for this question* is always the user's.

### Q3. Will the dtype match if I patch?

A real number from literature is not always patchable. Common
mismatches:

- Kernel variable is `bool`; literature gives continuous (mmHg, BMI,
  score)
- Kernel variable is categorical (`["low","mid","high"]`); literature
  gives a percentile
- Kernel asks for a probability; literature gives a hazard ratio or
  odds ratio

Forcing a continuous value into a `bool` slot by inventing a threshold
("SBP < 140 = True") inserts **the LLM's choice** into the audit
chain — the threshold changes the answer, but its source is the patcher,
not the literature.

So the dtype-mismatch path skips `apply_patch_and_run` for that gap,
renders the literature evidence with citation per
`response_rendering.md` §"Literature numeric rendering", and flags the
schema gap so the user can re-frame.

## Provenance is the audit spine

Every patched value carries `annotations.source` (PMID / DOI / dataset
name / URL). The verifier treats unsourced values as `confidence == 0`.
A remembered number with no citation is operationally identical to a
fabricated one — it cannot be audited, so Themis cannot trust it.

If you can't cite, you don't patch. Surface the gap instead.

## Termination

Stop the loop when any of these holds:

- `status == "numerically_solved"` AND `data_gap_report` empty/null →
  render the answer
- `status == "structurally_solved"` and no further gap is data-fixable →
  render the structural answer + remaining gaps
- All remaining gaps are `unidentifiable_no_admissible_set`
- Budget: 5 total loop iterations, OR 3 unsuccessful fetch attempts on
  the same gap, OR the user has declined to provide what's missing
- One user clarification at most per turn — piling on questions makes
  people leave

When you stop without `numerically_solved`, append a one-line audit
trail to the rendered reply:

```
（已尝试 N 轮数据补全：补到了 X / Y / Z；剩余缺口见上方）
```

The audit trail is **cumulative across the loop**, not a per-turn
snapshot. Every gap that surfaced at any point stays visible until it's
resolved (filled and verified) or explicitly declined by the user — a
re-render that drops earlier gaps because they got partially fixed
hides progress and lets unresolved gaps slip out of the user's view.

## Patch shapes

`themis.apply_patch_and_run` accepts two bundle kinds. Use parameter
fills for missing distributions, framing fills for ambiguous variable
definitions.

For Q2 "world has it" gaps, prefer the structured KB lookup flow in
[`kb_lookup.md`](kb_lookup.md): `themis.kb.gap_to_kb_query` builds a
typed `KBQuery`, the adapter (or `WebSearchProxyAdapter` wrapping a
client search function) returns a `KBResult`, and
`themis.kb.kb_results_to_bundle` produces the bundle below
automatically — with `provenance.citation` carried verbatim into
`annotations.source`. Hand-build the bundle only when no adapter
framework is in use.

`apply_patch_and_run` accepts the records you read off
`investigation_requests[].items[].skeleton` directly — pass a single
filled `probability` / `variable_patch` dict, or a list of them, and
the kernel auto-wraps. The explicit bundle envelopes below still work
and are what offline-built KB adapters emit.

```json
// parameter_fill_bundle — for missing_distribution / missing_mediator_data /
//                         transport_*_unknown
{
  "version": "0.1",
  "kind": "parameter_fill_bundle",
  "skeletons": [{
    "kind": "probability",
    "target": {"predicate": "Y", "args": [...], "value": true},
    "given":  [{"predicate": "X", "args": [...], "value": true}],
    "value":  0.X,
    "annotations": {"source": "PMID:12345"}
  }]
}

// framing_skeleton_bundle — for ambiguous_variable_definition
{
  "version": "0.1",
  "kind": "framing_skeleton_bundle",
  "patches": [{
    "kind": "variable_patch",
    "predicate": "X",
    "fields": {"time_window": "12 weeks", "measurement": "..."}
  }]
}
```

After every `apply_patch_and_run`, the result must pass `themis.verify`
before you trust it.

## Worked example — transport with two blocking gaps

```json
{
  "status": "structurally_solved",
  "extensions": {"transport_identification": {...}},
  "data_gap_report": {
    "gaps": [
      {"kind": "transport_source_conditional_unknown", "severity": "blocking",
       "required_data": {"data_type": "ipd", "population": "rct_meta_2022",
                          "variables": ["age"]}},
      {"kind": "transport_target_distribution_unknown", "severity": "blocking",
       "required_data": {"data_type": "marginal", "population": "user_28",
                          "variables": ["age"]}}
    ]
  }
}
```

Q1: both fixable. Q2: target marginal is a public stat (CDC); source
stratified is sometimes published, sometimes IPD-only. Q3: both are
distributional, dtype matches.

- **Action 1 (autonomous fetch — target marginal)**: WebSearch
  `中国 28 岁人群年龄分布`; build `parameter_fill_bundle` with
  `P(age=28 | population=user_28) = 0.025`,
  `annotations.source = "中国 CDC 2023 人口结构表"`.
- **Action 2 (try fetch then ask — source conditional)**: WebSearch
  meta-analysis subgroup tables. If 25–35 stratum is absent, ask:
  "我找到的 meta-analysis 没有 25–35 岁分层。你接受 (a) 用相邻
  35–45 岁的近似 (b) 等待我找单个匹配 RCT (c) 接受 bounds 而非点估
  计？"

Loop ends when both gaps fill (re-run yields `numerically_solved`) or
the user picks an alternative path.

## Worked example — unidentifiable terminates immediately

```json
{
  "status": "needs_investigation",
  "data_gap_report": {
    "gaps": [{
      "kind": "unidentifiable_no_admissible_set",
      "severity": "blocking",
      "alternative_paths": ["测量并加入未观测共因 Z, 重新识别",
                            "在 X 上做 RCT, 旁路 backdoor",
                            "找一个满足 IV 条件的工具变量"]
    }]
  }
}
```

Q1 says no. Render directly per `response_rendering.md` §
"unidentifiable_no_admissible_set" and stop. The three
`alternative_paths` ARE the answer — there is no data fetch that rescues
this DAG.

## Worked example — dtype mismatch, skip the patch

User asked "exercise → systolic BP", kernel declares `systolic_bp:
bool`, literature gives "8-week aerobic training: SBP −4.3 mmHg
(95% CI −6.1 to −2.5), n=2,847, PMID:31234567".

Q3 says don't patch — `bool` vs continuous. Surface the literature
result directly via `response_rendering.md` §"Literature numeric
rendering" (with citation, population, sample size, three caveats), and
flag the schema mismatch so the user can re-frame as either a continuous
ATE query or a probability with a clinical threshold they choose.

## Decision authority

- **Themis** owns what's missing — `data_gap_report` is its output to
  honor, not to second-guess
- **The user** owns assumption acceptance, IV validity for their
  setting, and how to operationalize ambiguous variables
- **You** own gap ordering, source selection, and handoff timing

When a tradeoff is borderline, ask. One pause beats one wrong autonomous
patch.

