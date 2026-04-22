# Post-Phase-2.latent stress test report

Date: 2026-04-22

## Setup

Six hand-constructed (NL question, kernel_ast) pairs run through
`themis.run`. Unlike the task #33 report (four questions, four real
Claude sub-agents producing the kernel_ast), this round has the
author playing A1's role to cover dimensions the first round didn't:

1. **Cause structural query** — 吸烟会导致肺癌吗
2. **Categorical (non-bool) domain** — 血压水平（低/中/高）和运动量有关系吗
3. **Conditional effect (non-empty given)** — 对于糖尿病患者，减少糖分摄入能改善血糖吗
4. **Multi-hop chain (4 variables, 3 edges)** — 长期压力 → 暴饮暴食 → 肥胖 → 糖尿病
5. **ADMG hidden confounder (post-Phase-2.latent)** — 喝咖啡能提神吗（基因型 U 未观测）
6. **Ambiguous cause/assoc intent** — 咖啡和失眠有关系吗

Driver: `scripts/stress_test_post_phase2_latent.py`.

Caveat: author-produced kernel_ast is less rigorous than real
sub-agent output. This round targets Themis's *runtime* behavior
across new dimensions, not A1's prompt robustness — task #33 already
covered that angle.

## Technical findings — all six pass the boundary

No crashes, no schema failures, no unexpected exceptions. Every
case produced a well-formed `results[0]` conforming to
`query_result.schema.json`. Phase 2.latent 的 ADMG 路径在 case 5
上端到端工作（front-door-via-m-separation 正确触发，derivation 带
`identify_via_front_door` 规则链）。

## Semantic findings — four recurring gaps

### (G1) Framing asks are over-eager on pure-structural queries

Cases 1 (cause) and 6 (assoc) both returned `structurally_solved`
— the query was answered at the graph level alone, no CPT needed —
but the response still carried a `DEFINE_VARIABLE` investigation
request asking the user to fill seven framing fields
(`time_window / measurement / threshold / observability / direction
/ baseline / state_vs_event`) on every referenced predicate.

**Problem**: a user asking "吸烟会导致肺癌吗" does not need to
operationalize measurement before getting an answer; the causal
claim exists at the graph level. The framing ask belongs to the
*numeric* path, not the *structural* one.

**Current rule**: A0 / F1 fire framing notes on any predicate
referenced by any query. Structural-vs-numeric distinction is not
used when deciding whether framing is relevant.

**Follow-up candidate**: scope framing asks to predicates whose
values will be consumed numerically — target + intervention of
`effect` and `probability` queries, not `cause` / `assoc` /
`identify`. Advisory only; still emit as `framing_notes` but drop
the `define_variable` investigation request when the query is
purely structural and solved.

### (G2) Chain queries don't communicate the path

Case 4 (stress → overeating → obesity → diabetes, effect query
with empty given) reduced to asking for a single CPT entry
`P(diabetes=True | chronic_stress=True)`. This is *technically*
correct — with no observed confounders and empty given, the
backdoor formula degenerates to a direct conditional — but the
result hides the user's mental model of "a chain I want to reason
through".

The derivation was not attached (result went to
`needs_investigation` before hitting the derivation path), so
there's nothing in the output to surface the chain structure to
the user. A user reading `results[0]` sees "give me
P(diabetes|stress)" without any indication that the four-node
chain is the reason this simplifies.

**Follow-up candidate**: when a chain of mediators exists but
backdoor collapses adjustment to empty (no hidden confounding
identified), attach an *advisory* note or derivation-like trace
summarizing the structural path. Informational, not gating.

### (G3) Ambiguous intent isn't surfaced

Case 6 (咖啡和失眠有关系吗) — "有关系" is ambiguous between
`assoc`-style ("statistical correlation") and `cause`-style ("one
affects the other"). A1 prompt chooses one silently per example.
The system gives an answer without flagging "this question has two
valid readings; I chose X."

In this session I chose `assoc` — the result was
`structurally_solved / True`. If A1 had chosen `cause`, the result
would have been the same value (`cause_via_directed_path` on
drinks_coffee → has_insomnia), so the accidental match hides the
issue. But for other questions the two readings diverge
(`cause` = "does X cause Y?" is strictly stronger than `assoc` =
"are they statistically related?").

**Follow-up candidate**: either (a) A1 prompt updated to output a
secondary structure for ambiguous cases and let the agent ask, or
(b) post-hoc check: if NL contains "有关系 / 相关" without
intervention markers, run both kinds and report the difference.

### (G4) Non-empty `given` exposes the A6 front-door gap

Case 3 (conditional effect with `given=[diabetic=True]`) works
here because backdoor adjustment applies after conditioning on
`diabetic`. But the A6 charter (§77) explicitly excludes
conditional front-door:

> 多 mediator 前门（需要链式 P(Z1..Zk|X) 分解）
> 条件化前门（`given` 非空时）

A variant of case 3 where backdoor *doesn't* apply (e.g., a hidden
confounder between intervention and target in the conditioned
subpopulation) would hit this gap. Not reproduced here, but the
limitation is pre-known and documented.

**Follow-up candidate**: no action until a real case needs it. The
gap is captured by the A6 charter.

## What didn't break

- Case 2 (categorical `["low","medium","high"]` domain): assoc
  query on non-bool runs cleanly through structural dispatch.
  Numeric path not exercised (would need CPT fills); leaving this
  as a future probe.
- Case 5 (ADMG hidden confounder): Phase 2.latent's S3.a
  ADMG-aware front-door fires exactly as designed. The bidirected
  edge carries `source: llm_proposal / confidence: 0.6` and lands
  in the graph without tripping any gate. Reality check ✓.
- All six cases produced schema-valid JSON output reproducing
  through `syntactic_validator.validate_result`.

## Recommendations

Priority order for follow-up:

1. **(G1) Structural-vs-numeric framing gate** — concrete
   refactor. Not a new concept, just scoping existing A0/F1
   behavior. Low risk, good UX win for cause / assoc / identify
   queries. Worth a charter-free slice.

2. **(G3) Intent disambiguation** — live in the A1 prompt, not in
   the kernel. A1 prompt update + reply_to_framing_patch extension
   to handle "二选一" style questions. NL-layer change.

3. **(G2) Chain-path advisory** — smaller payoff, larger surface;
   would extend result shape. Defer until a real case pushes for
   it.

4. **(G4) Conditional front-door** — already captured in A6 charter
   as out-of-scope. No action.

## Artifacts

- `scripts/stress_test_post_phase2_latent.py` — driver + inlined
  six cases. Runs via `PYTHONPATH=. python scripts/...`.
- Structured outputs reproducible from the driver.
- No commits beyond this report + the driver script.
