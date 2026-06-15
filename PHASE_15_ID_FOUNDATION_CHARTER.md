# Phase 15 — Identification on a theoretical foundation

> 状态：A+B 完成；Line 7（嵌套 ID）napkin 类完成，完整通用版待化简子系统。
> Phase A（语义验证骨干）已接入 verify_identify；Phase B（scheduler 塌缩为
> 「跑 ID/IDC 引擎 → 认图案标注 → 升级 IV」，公式统一 c-factor、图案降为图层
> 标注）已落地，修了两个真 `_id` 自由-VarRef bug。Pearl napkin 等 nested-ID
> 已非参数识别（f75508d）。**下一步大工程：公式化简子系统**（见文末「Line 7
> 与化简」）。全量绿。覆盖 backdoor / front-door / Tian / IDC。
>
> From *empirical-grade* (a pile of method-specific solvers + structural
> checkers) to *theory-grade* (one complete algorithm is the arbiter of
> truth; verification is semantic, not recipe-following).

## 根因假设 (root cause)

Themis identifies `P(Y|do(X)[,Z])` by trying methods in sequence —
backdoor → front-door → IV → Tian/ID → IDC — each with its **own**
scheduler builder and its **own** verifier rule. The system's
correctness is therefore *asserted by ~7 special-case structural
checkers*, not *derived from one theory*.

Evidence this is a real defect, not an aesthetic one (Phase 14.idc,
2026-06-15): the IDC fraction was **numerically wrong** (a degenerate
inner sum) yet passed the structural verifier, the JSON schema, and
shape-equality. Only a hand-written numeric check against a
latent-variable SCM caught it. A verifier built from per-method
*"did you follow the backdoor recipe"* checks structurally cannot catch
*"your formula computes the wrong number"*.

The deeper framing (user, 2026-06-15): the fragmentation is **the lack
of a unified mathematical treatment** — backdoor / front-door / Tian /
IDC are not sibling methods, they are *one* object (the complete ID/IDC
algorithm) wearing different recognizable faces.

## The honest theory (what unifies, what does NOT)

- **Nonparametric point identification is ONE complete theory:**
  do-calculus + the Shpitser-Pearl **ID/IDC** algorithm. It is provably
  complete — `P(Y|do(X)[,Z])` is identifiable from `graph + observational
  data` **iff** ID/IDC says so. backdoor / front-door / Tian / IDC are
  all **special cases / recognizable faces** of this one algorithm.
- **IV and bounds are NOT special cases of ID — they are the
  "ID-failed" escalation layer.** The classic IV graph (`Z→X→Y, X↔Y`) is
  nonparametrically **un**identifiable; ID returns "unidentifiable". IV
  produces an answer only by **adding an assumption** (monotonicity →
  LATE, linearity → Wald). So IV correctly lives *outside* ID, as
  "ID said no → add an assumption". Partial-ID bounds are the other
  escalation branch ("ID said no → report a range").
- **Mediation (NDE/NIE/CDE) and transport are different estimands** (not
  `P(Y|do(X))`), each with its own identification. Out of scope for this
  phase's backbone.

This hierarchy is *more* unified than "everything is ID": **ID is the
complete answer for point-identifiability from graph+data alone; every
other method is an explicit escalation when ID fails.**

## Target architecture

1. **ID/IDC is the sole identifiability ORACLE.** Every plain
   interventional identify query's verdict (identifiable / not) is owned
   by `c_factor.identify_via_tian` / `identify_via_idc` — the complete
   algorithm. Other "methods" never get to *disagree* with it.
2. **Verification is SEMANTIC, not recipe-following.** The verifier's
   trust rests on a single method-agnostic backbone: *does the claimed
   formula compute the actual interventional quantity in a model
   consistent with the stated graph?* — checked by probing against
   random SCMs (below). This one check backs backdoor, front-door, Tian,
   and IDC at once and would have caught the Phase-14 IDC bug.
3. **Pretty formulas become validated renderings.** The scheduler still
   emits the readable backdoor / front-door formulas (kernel-truth vs
   rendering: the canonical formula is truth, the pretty one is a *view*
   — consistent with the peelable-scaffolding contract). They are now
   *validated against the oracle*, not independent sources of truth.
   Per-method structural verifier rules become redundant first-line
   checks, retired over time.

## The semantic backbone (mechanism)

Given `(graph, bidirected, x, y, given, claimed_formula, claimed_verdict)`:

- **SCM probe.** Sample a random SCM consistent with the ADMG: a CPT
  `P(v | parents(v), latents(v))` per node, an independent latent per
  bidirected edge. Marginalize latents → observational `Theta`. Compute
  the **true** `P(Y=y | do(X=xv), Z=z)` by intervening on the SCM
  directly (sever X's mechanism, enumerate latents).
- **Identifiable case.** Evaluate `claimed_formula` against the
  observational `Theta` (with Y, Z bound) and require it to equal the
  true do-quantity, for every binding, across **K** independent random
  SCMs. A wrong formula matches the truth only on a measure-zero set, so
  K≥2–3 makes false-accept astronomically unlikely. *(Honest caveat:
  this is Monte-Carlo verification — overwhelming evidence, not a
  symbolic proof. It is strictly stronger than the current structural
  checks, which prove nothing about the number.)*
- **Unidentifiable case.** Exhibit **two** SCMs consistent with the
  graph that share the same observational distribution but give
  different true do-quantities — the textbook unidentifiability witness.
  Confirms a `value=False` claim semantically.
- **Exemptions (the escalation layer).** The backbone applies only to
  the nonparametric point-ID terminal rules
  (`identify_via_backdoor / _front_door / _tian / _idc`). IV
  (assumption-laden, formula often None), bounds (interval), mediation
  and transport (different estimands) are explicitly exempt — they are
  not claims of "this formula = the nonparametric do-quantity".

## Plan

**Phase A (this round) — foundation + backbone, no user-facing change:**

- A1. SCM probe infra: random ADMG-consistent SCM → observational Theta
  + true do-quantity. (`themis/verifier/semantic_probe.py`, new.)
- A2. Formula numeric eval with query bindings (productionize the
  Phase-14 test harness).
- A3. Semantic equivalence backbone: formula-vs-truth over K SCMs;
  verdict oracle; two-SCM unidentifiability witness.
- A4. Unit-test the backbone in isolation: accepts correct
  backdoor/front-door/IDC; rejects a numerically-wrong formula.
- A5. Wire into `verify_identify`, scoped to the four nonparametric
  terminal rules, exempting the escalation layer. Full suite green.
  **Expect the backbone to surface latent bugs in existing methods —
  that is the payoff, not a setback.**

**Phase B (in progress) — collapse the scheduler onto the ID engine.**
`_dispatch_identify` is restructured to *"run ID/IDC → recognize pattern
→ escalate"*:

- the **engine** (`identify_via_tian` for empty given, `identify_via_idc`
  for conditional) decides identifiability and provides the **canonical
  c-factor formula** for ALL point-ID queries — pure-DAG and ADMG alike;
- the per-method pretty-formula builders (`backdoor_formula`,
  `front_door_formula`) are **retired**. Decision (2026-06-15, user):
  *the formula is a machine artifact and need not be pretty — what
  humans read is the GRAPH.* So the user-facing formula is the canonical
  c-factor, and the identification's human value moves to **graph-level
  annotations**: the recognized pattern (backdoor / front-door /
  c_factor), the adjustment / mediator set ("control for W"), and — when
  unidentifiable — the hedge witness ("X and Y trapped in this
  c-component"). See [[feedback_graph_is_human_surface]].
- **IV / bounds remain the escalation layer**, fired only when the
  engine reports the query is not (nonparametrically) identifiable.

Churn (~19 test files: terminal rule names backdoor/front_door → tian/
idc, formula-shape assertions → c-factor) is accepted — the Phase-A
semantic backbone numerically validates every rerouted formula, so a
reroute that changes a formula cannot silently break correctness.

## Risks

- **Latent bugs surfaced.** Turning on semantic verification may fail
  existing methods whose formulas are subtly wrong. This is the point.
  Each is a real bug to fix, not a reason to weaken the check.
- **Probabilistic verification.** Random-SCM probing is Monte-Carlo.
  Mitigation: K independent SCMs + fixed seeds for reproducibility;
  documented as evidence-not-proof. Far stronger than status quo.
- **Verifier independence.** The probe must NOT call the runtime's
  identification path (that would be circular). It builds its own SCM
  and computes the true do-quantity by direct SCM intervention — fully
  independent of how the formula was derived.

## Line 7 (nested ID) and the simplification subsystem

The complete ID algorithm's hardest line is Line 7: when the c-component
S of G[V\X] is a strict subset of a c-component S' of G, the answer is
the recursive ID over the *substituted* distribution Q[S'], which
introduces RATIOS. The canonical example is Pearl's **napkin**
(W→Z→X→Y, W↔X, W↔Y).

**Status (2026-06-15).** A compact Q[S'] shortcut covers front-door-style
Line-7 cases. It leaves a free, unbound sum variable on genuine nested ID
(napkin: Z leaks out of S'). A real-usage stress test (independent agent
over the MCP) surfaced this as a public-API crash, then as an IV
degradation. The napkin is now **nonparametrically identified** via a
contained Tian-Identify subroutine, numerically verified by the semantic
backbone (f75508d). Mediator-bearing nested ID (extended napkin
W→Z→X→M→Y) is **safely punted** by the probe gate — never a wrong answer.

**The wall — why "complete general nested ID" is a SUBSYSTEM, not a bug.**
A full symbolic ID (`_id_symbolic`, running every line over the
observational joint as a symbolic distribution) was implemented and is
mathematically CORRECT (napkin probes match). But the *naive* symbolic ID
has **no algebraic simplification pass**, so its estimands explode
EXPONENTIALLY *during construction*: the extended napkin (5 nodes) reaches
depth in the thousands and overflows the stack of every recursive walk
(stamp / validate / probe); even the napkin's symbolic formula is complex
enough to intermittently destabilise the probe. It was reverted — the
exploration never touched master (the probe + validate_formula double net
+ "build → probe → revert-if-bad" kept the committed state green).

**The required next undertaking.** Complete, general nested ID needs a
formula-simplification subsystem, done as a dedicated round:

1. Represent the distribution as a **structured factor set** (not a flat
   FormulaExpr) and marginalise by **variable elimination** — sum out one
   variable at a time, multiplying only the factors that contain it.
2. The load-bearing simplifications: **sum-to-one** (`Σ_v P(v|·) = 1`
   when v appears in a single factor → drop it), **ratio cancellation**,
   and **pushing sums inward**. These keep intermediate estimands small.
3. **Read the references first, do NOT reconstruct from memory:**
   `causaleffect` (R, Tikka & Karvanen) and `ananke` (Python, Shpitser's
   group) both centre an aggressive simplification of the Probability
   expression — that is the part to study and port.
4. Validate throughout with the semantic probe; ship only probe-confirmed
   formulas, punt the rest.
