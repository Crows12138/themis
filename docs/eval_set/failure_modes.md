# NL-layer failure-mode taxonomy

> Status: v2.1 (2026-04-24). 19 codes. Expanded when a real case
> exposes a mode the current set doesn't cover. F19 added with
> Phase 6.iv (IV identification slice).

Each code describes one way the A1 → A5 → merge → themis.run
pipeline can produce a result the user would consider wrong or
incomplete. Cases in the eval set reference these codes so the
attribution report can aggregate "X% of failures are F3" cleanly.

## F1 — Under-framed question

**Pattern**: NL question lacks operationalization (time window,
measurement protocol, threshold, direction, baseline, etc.) that
a correct numeric answer would require.

**Typical trigger**: "跑步能减肥吗" — no duration, no measurement,
no threshold.

**Expected correct behavior**: surface the gaps as framing asks
or DEFINE_VARIABLE investigation; do not invent numbers.

**Slice most relevant**: #41 framing fields v2 (already landed);
extensions would add new framing dimensions.

## F2 — Edge-in-narrative, not-in-question

**Pattern**: A causal link is stated / implied in the narrative
context but the question doesn't name it. A1 alone (which reads
only the question) misses it.

**Typical trigger**: "我上个月开始每天服用维生素 D，最近感冒次数明显少了。
维生素 D 真的能减少感冒吗？" — the cause edge `vitamin_d → fewer_colds`
is in both narrative and question; but something like "...。那益生菌呢？"
would rely on narrative context the question doesn't repeat.

**Expected correct behavior**: A5 narrative pass + edge extraction
lifts the edge from narrative into the kernel_ast.

**Slice most relevant**: #37.c `narrative_to_edges.md` prompt.

## F3 — Ambiguous intent (cause vs assoc vs effect)

**Pattern**: NL admits multiple valid query-kind readings; a
naive extractor silently picks one.

**Typical trigger**: "咖啡和失眠有关系吗" — could be cause ("does
coffee cause insomnia") or assoc ("are they correlated"); "跑步
影响肚子" — could be cause, effect, or direction-ambiguous.

**Expected correct behavior**: surface the ambiguity as a
clarifying ask or emit multiple candidate queries with
`status=proposal`; do not silently commit to one reading.

**Slice most relevant**: NL-layer prompt update (A1) + possibly
`reply_to_framing_patch.md` extension.

## F4 — Chain / multi-hop structure

**Pattern**: The user's mental model involves a chain of
mediators (A → B → C → D) but the extracted program reduces to a
degenerate direct question.

**Typical trigger**: "压力 → 暴饮暴食 → 肥胖 → 糖尿病，这条链可信吗？"
— the question is about the chain's validity, not just P(diabetes|stress).

**Expected correct behavior**: preserve the chain in the
structural output; if backdoor collapses to empty adjustment,
still communicate "the chain is the path" via supporting_paths
or an advisory.

**Slice most relevant**: output-layer improvement (response
rendering + structural result enrichment).

## F5 — Hidden confounder (ADMG)

**Pattern**: Narrative describes an unobserved common cause
between two observed variables; extraction should produce a
bidirected edge, not ignore or fake an observed node.

**Typical trigger**: "喝咖啡的人反应快，但可能是那些天生警觉性高
的人更倾向于喝咖啡" — genetic alertness U is unobserved,
drinks_coffee ↔ alertness is the right structure.

**Expected correct behavior**: narrative_to_edges (or a companion
prompt) proposes a bidirected statement with
`source=llm_proposal`.

**Slice most relevant**: #37.c with bidirected-awareness, or a
companion prompt.

## F6 — Alias / synonym collapse

**Pattern**: Same concept appears under different names in
narrative + question (e.g., "跑步" / "daily_running" / "慢跑").
Naive merge either silently aliases (loses information) or
over-splits (creates duplicate nodes).

**Typical trigger**: narrative says "我每天慢跑"; question says
"跑步能减肥吗".

**Expected correct behavior**: emit alias_candidate with
`status=proposal`; don't silently merge.

**Slice most relevant**: #37.d same-name warning (deferred per
my recent rec; this mode decides if it should move up).

## F7 — Negation / direction

**Pattern**: NL uses negated predicate or direction-specific
wording that a naive extractor flips.

**Typical trigger**: "不吃早餐会影响学习效率吗" — the intervention
is `eats_breakfast=False`, not `skips_breakfast=True` masking as
`eats_breakfast=True`.

**Expected correct behavior**: correctly encode the value in the
query's intervention / given fields; don't silently normalize
to positive form.

**Slice most relevant**: A1 prompt clarity.

## F8 — Must-not-infer (confounding ≠ causation)

**Pattern**: Surface-level correlation tempts a naive extractor
to posit a direct cause edge where the correct structure is
confounding.

**Typical trigger**: "夏天冰激凌卖得好的月份溺水事件也多，所以
吃冰激凌会导致溺水吗" — temperature is a common cause; direct
edge ice_cream → drowning is wrong.

**Expected correct behavior**: propose the confounder (season /
temperature) as a variable, or refuse the direct edge with a
flagged must_not_infer.

**Slice most relevant**: narrative_to_edges proposal semantics +
abstention quality.

## F9 — Structural-vs-numeric framing mismatch

**Pattern**: User asks a purely structural question (cause / assoc
"is there a relationship?"); system over-eagerly asks for
numeric-path framing (time_window, measurement, threshold) even
though the query kind doesn't need them.

**Typical trigger**: "吸烟会导致肺癌吗" — cause query; answer
structural, but DEFINE_VARIABLE asks 7 fields on every predicate.

**Expected correct behavior**: scope DEFINE_VARIABLE
investigation to queries that need numeric resolution (effect /
probability); for cause / assoc / identify keep framing_notes
advisory but don't attach skeleton.

**Slice most relevant**: `framing_check` / `investigation_pusher`
scoping (local change).

## F10 — Multi-subject / multi-object

**Pattern**: The causal claim spans more than one subject (parent
vs child, doctor vs patient, company vs employee). The current
kernel pins `domain.objects` and every atom's args to a single
`"me"` const term.

**Typical trigger**: "父母受过高等教育会让孩子成绩更好吗" — two
subjects (`parent`, `child`) with per-subject predicates.

**Expected correct behavior**: the A1 prompt has no multi-subject
guidance today; the agent either flattens to `"me"` (loses the
relational structure) or invents compound predicates
(`parent_educated` / `child_high_grades`). Either workaround is a
semantic compression. The right answer structurally is multi-object
domain with a forall-quantified cause edge.

**Slice most relevant**: A1 prompt extension for multi-subject
patterns, or a new NL-layer decision to flatten + flag the
compression via `extensions.ambiguities.kind: "subject_scope"`.

## F11 — Temporal / time-lagged causation

**Pattern**: NL describes effects with time lag ("上个月 X, 这个月
Y") that the current DAG-only semantics can't express; no time
indexing in the AST.

**Typical trigger**: "最近连续熬夜，第二天总是没精神" — temporal
ordering IS the causal signal; flattening to `stays_up_late →
feels_tired` drops the implied same-day lag.

**Expected correct behavior**: A1 emits a timed edge/query using
`stays_up_late@t-1 → feels_tired@t` (or the equivalent target
predicate name) directly in the kernel AST. Clean `t-1 → t`
patterns should no longer be downgraded to
`extensions.ambiguities.kind: "temporal"`.

**Slice most relevant**: Phase 5 temporal semantics + A1 prompt
v2.2 time-index lifting.

## F12 — Categorical-domain numeric query

**Pattern**: User's domain is naturally categorical (low / mid /
high), not bool, AND wants a numeric answer. The kernel supports
categorical domains structurally (see eval case 02) but theta +
response_rendering may not have been stressed on categorical
distributions.

**Typical trigger**: "血压水平（低/中/高）和运动量（少/中/多）的
关系里，多运动能让血压从高变低吗" — asks for a specific
categorical-to-categorical effect.

**Slice most relevant**: unknown until exercised — this case's
role is to surface whichever layer cracks first.

## F13 — Long chain (5+ nodes)

**Pattern**: Like F4 but 5+ nodes deep. Stresses the chain
compression to a single CPT lookup, plus front-door / backdoor
candidate enumeration as the chain grows.

**Typical trigger**: "课外阅读量 → 词汇量 → 阅读理解 → 写作能力
→ 考试成绩 — 这条链真的吗" — 5-node chain, user explicitly names
the path.

**Expected correct behavior**: preserve all 5 variables and 4
edges; the answer may still collapse to a single CPT (if no
confounding), but the chain should be visible in the structural
result.

**Slice most relevant**: same as F4 (output shape change), plus
stress test on whether scheduler's adjustment-set enumeration
stays cheap at larger N.

## F14 — Reciprocal / bidirectional causation

**Pattern**: User's NL suggests both directions are plausible
("锻炼和心情是不是互相影响") — DAG assumes acyclicity, so the
extractor has to pick one direction or refuse.

**Typical trigger**: "长期锻炼能改善心情吗？反过来，心情好会让
人更愿意锻炼吗" — explicit both-directions framing.

**Expected correct behavior**: the most honest thing is to refuse
to pick one direction and flag it as
`extensions.ambiguities.kind: "reciprocal_causation"`; or pick
one direction for the query and acknowledge the other as a
separate investigation.

**Slice most relevant**: A1 prompt rule for bidirectional NL +
possibly Phase 5 cyclic / feedback-loop extension in the kernel.

## F15 — Selection bias (conditioning on collider)

**Pattern**: Narrative describes an observation made within a
selected subpopulation (住院病人中 / 某些用户里 / 入学的学生中);
the user reads the conditional association as evidence of
causation between two causes of the selection variable.

**Typical trigger**: "住院病人中糖尿病患者比例更高，所以住院会
导致糖尿病吗" — is_hospitalized is a collider caused by both
underlying illness and by diabetes; conditioning on it induces a
spurious association.

**Expected correct behavior**: refuse the direct edge; declare
`extensions.ambiguities[kind=selection_bias]` naming the
conditioning and, where possible, the collider structure. The
observed association is conditional-on-S, not P(Y|do(X)).

**Slice most relevant**: A1 prompt §3a extension (selection-
bias-aware confounder refusal) OR narrative_to_edges when the
selection cue sits in narrative. Orthogonal to ordinary
confounder refusal: here the structure is different (collider
being conditioned on, not unobserved common cause).

## F16 — Counterfactual (Layer 3) vs interventional (Layer 2)

**Pattern**: NL uses counterfactual phrasing ("如果当初我...",
"要是没...", "假如我当时...") asking about a specific individual's
alternative outcome.

**Typical trigger**: "如果当初我选的是计算机专业，现在收入会
更高吗" — counterfactual for THIS individual, conditional on
actually observed choice=history.

**Expected correct behavior**: when the question fits the current
narrow Layer-3 fragment, emit a real `counterfactual` query instead
of collapsing it to an `effect` proxy. If monotonicity is not stated,
the correct kernel response is `needs_assumption`, not a hidden
Layer-2 substitution. Reserve
`extensions.ambiguities[kind=counterfactual_query]` for wider
counterfactuals that still exceed the fragment.

**Slice most relevant**: Phase 5 counterfactuals (§C).

## F17 — Mechanism-vs-existence

**Pattern**: NL uses "为什么" / "怎么" / "通过什么机制" asking for
the biological / physical mechanism (mediator chain) rather than
whether a causal path exists. The kernel's cause query answers
existence of a path, not the structural story of the mediators.

**Typical trigger**: "吸烟为什么会导致肺癌" — the "是否会导致"
is presupposed; the user wants the 焦油→DNA损伤→突变→癌变
chain.

**Expected correct behavior**: declare
`extensions.ambiguities[kind=mechanism_vs_existence]`; either
answer existence as a proxy with that flag OR ask clarifying
"do you want mechanism or existence?". Mechanism answering
requires full mediator enumeration not available in current
kernel.

**Slice most relevant**: A1 prompt extension (detect 为什么/
怎么 pattern) + response rendering disclosure.

## F18 — Individual-vs-population estimand

**Pattern**: Narrative supplies a POPULATION-average effect
(临床试验平均降压 10 mmHg / 研究发现 X% 的人...); question asks
about an INDIVIDUAL (对我有效吗 / 我会不会...). These are
different estimands (E[Y(1)−Y(0)] vs Y_i(1)−Y_i(0) | covariates).

**Typical trigger**: "这药在试验里平均降压 10 mmHg。对我有效吗"

**Expected correct behavior**: answer with the population
effect as the available proxy AND declare
`extensions.ambiguities[kind=individual_vs_population]` marking
the estimand gap. Optionally request moderators (age, baseline
BP) if an individual prediction is genuinely wanted.

**Slice most relevant**: A1 prompt extension (detect 对我 / 我
会 patterns against population-level narrative) + response
rendering disclosure.

## F19 — IV identification (valid use, or IV assumption violation)

**Pattern**: NL proposes a specific variable Z as工具变量 /
instrumental variable / natural experiment for identifying
X → Y when X and Y have an unobserved confounder. The system
must check IV1 / IV2 / IV3 structurally:

- IV1 (relevance): Z has a directed path to X
- IV2 (exclusion): Z affects Y ONLY through X — no alternative
  path
- IV3 (independence): Z does not share latent confounders with Y

**Typical trigger, valid IV**: "血清胆固醇 → 心脏病 identification
via 某基因变异 (affects cholesterol only, independent of lifestyle)"
→ structure should resolve via IV fallback (identify_via_iv).

**Typical trigger, IV violation**: "教育 → 收入 via 距离学校，
但距离同时和社区经济水平相关" → IV2 exclusion violated via
distance → community → income alt-path. System must refuse IV
identification, not silently accept.

**Expected correct behavior**:

- Structurally valid: return `structurally_solved` +
  `extensions.iv_identification` populated + `iv_validity`
  ambiguity listing the three assumptions
- Structurally invalid: do NOT return iv_identification success;
  either structurally_solved with value=False (unidentifiable) or
  needs_investigation. Surface the specific criterion that failed
  (IV1/IV2/IV3) in framing_notes or extensions.

**Slice most relevant**: Phase 6.iv (identification) +
iv_criterion_check verifier rule.

## Growth rule

Add a new code only when a real case exposes a failure that
doesn't fit existing codes. Don't pre-invent codes for
hypothetical problems — schema only extends under real pressure,
per charter principle. F10–F14 were added when the eval set grew
from 10 to 13 and each probed a genuinely new dimension.
F15–F18 were added at 13 → 20 growth: F15 selection / collider
conditioning (distinct from F8's unobserved confounder), F16
counterfactual vs interventional estimand gap, F17 mechanism-vs-
existence question-kind mismatch, F18 individual-vs-population
estimand gap. Each exposes a failure not reducible to the
F1–F14 set.
