# Narrative → edge candidates prompt

Fourth entry in the NL↔JSON bridge. Complements
`narrative_to_variables.md`: same narrative input, this prompt
emits **edge candidates** instead of variable candidates. The
orchestrator merges variables + edges + A1's question-side ast
before calling `themis.run`.

The kernel itself does not change; this module exists entirely in
prompt-land.

## Role

You read one paragraph of Chinese narrative and emit a JSON list
of causal edge candidates that the narrative **actually supports**
— directed edges for stated causal relationships, bidirected edges
for unobserved common causes, and explicit refusals for patterns
that look causal but should not get a direct edge.

Edges from common knowledge belong in the question-side prompt
(`nl_to_kernel_ast.md` §3). This prompt only emits edges that are
evidenced *in the narrative itself*.

## Output contract

Respond with **exactly one** JSON object:

```json
{
  "edges": [
    {"kind": "cause", "from": {"predicate": "..."}, "to": {"predicate": "..."},
     "annotations": {"source": "narrative_proposal", "evidence": "..."}},
    {"kind": "bidirected", "left": {"predicate": "..."}, "right": {"predicate": "..."},
     "annotations": {"source": "narrative_proposal", "evidence": "..."}}
  ],
  "refusals": [
    {"kind": "refuse_direct_edge", "from": "...", "to": "...",
     "reason": "...",
     "pattern": "confounder | collider | reverse_causation | coincidence",
     "suggested_node": "..."}
  ],
  "narrative_ambiguities": [
    {"kind": "...", "description": "...", "chosen": "...", "alternatives": ["..."]}
  ]
}
```

Atoms omit `args` — the orchestrator injects `[{type:"const",
name:"me"}]` when merging into the final program.

If the narrative has no causal content, return
`{"edges": [], "refusals": [], "narrative_ambiguities": []}`.

## Task breakdown

### 1. Read for causal structure

Three passes through the narrative:

**Pass A — stated causal claims**. Look for explicit cause
language: `导致`, `让`, `使得`, `带来`, `因为`, `所以`, `之后 X
就 Y 了`. Also look for implicit-but-clear temporal
sequencing: "上个月我开始 X，这个月 Y 减少了" — the user is
clearly implying X → Y. Emit `cause` edges.

**Pass B — unobserved common cause hints**. Look for narratives
that describe a mechanism, propensity, or trait that plausibly
causes both sides of a pair — especially when the trait is
*unmeasured* in the narrative. Patterns:

- "天生就 X" / "体质上" / "基因" → latent biological cause
- "他们本来就是 X 的人" / "性格使然" → latent trait
- "工作环境让他们 X 且 Y" → shared exposure
- "住在同一个社区" → shared context

Emit `bidirected` edges. The two predicates should both be
variables the narrative or question will declare; the unobserved
common cause is implicit.

**Pass C — refusal patterns**. Look for narratives that *look*
causal but whose structure is confounding / selection /
coincidence. Same §3a logic as A1:

- Temporal co-occurrence without mechanism ("夏天 X 多了，Y 也
  多了")
- Observation within a selected subpopulation ("住院病人中…")
- Group-level / population statistic applied to an individual
  ("每天吃海鲜的族群 Y 高")
- Clinical study of one drug → generalized ("某药的研究发现")

Emit a `refusals` entry naming the **structural pattern** that
explains why a direct edge is the wrong reading:

| `pattern` value | When to use | `suggested_node` is… |
|---|---|---|
| `confounder` | Both X and Y share an unobserved common cause | the confounder Z |
| `collider` | The narrative conditioned on a node that is a descendant of both X and Y (selection bias) | the collider being conditioned on (e.g. `is_hospitalized`) |
| `reverse_causation` | The arrow likely runs Y → X, not X → Y | optional — the actual causal direction's source if knowable |
| `coincidence` | No mechanism, just temporal / spatial co-occurrence | omit — there's no canonical alternative |

Use `suggested_node` (v2). The older `suggested_confounder` field
biased toward confounder patterns and is misleading for collider /
reverse-causation cases — emit `suggested_node` instead. If both
patterns plausibly apply (e.g. confounder AND collider), pick the
dominant one and mention the alternative in `reason`.

### 2. Tagging evidence

Every `edges` entry carries
`annotations.source: "narrative_proposal"` (distinct from
`"llm_proposal"` in the question prompt) plus
`annotations.evidence` — a short Chinese quote from the narrative
that justifies the edge. The quote is required: an edge without one
has no narrative support and belongs in the question-side prompt.

### 3. Narrative-specific ambiguities

If the narrative exhibits one of these patterns, declare it —
same kinds as A1 §5 but scoped to narrative reading:

| Pattern in narrative | `kind` |
|---|---|
| Narrative describes t→t+1 lag ("上个月 X，这个月 Y") | `temporal` |
| Narrative conditions on a selected subpopulation | `selection_bias` |
| Narrative gives population statistic; user is individual | `individual_vs_population` |
| Narrative names a latent trait driving both sides | `admg_unobserved_common_cause` |
| Narrative and question name concepts that may / may not alias | `alias` |

The orchestrator merges these with any A1-produced ambiguities
into `extensions.ambiguities` on the final program.

## Worked examples

Three narrative → edges pairs live in `docs/prompts/examples/`:

- `narrative_edges_vitamin_d.json` — straightforward stated cause
  (vitamin D → fewer colds) with temporal evidence
- `narrative_edges_coffee_alertness.json` — F5-style ADMG:
  narrative names "天生警觉性高" as a latent trait, emit
  bidirected `drinks_coffee ↔ alertness`
- `narrative_edges_ice_cream_drowning.json` — F8 refusal: summer
  co-occurrence pattern, refuse direct edge, propose
  `hot_weather` as confounder

Each file carries `narrative_input`, `reasoning` (which pass
picked up which edges and why), and the JSON output of this
prompt.

## Integration

The orchestrator calls:

1. `narrative_to_variables` → variable declarations with framing
2. `narrative_to_edges` (this prompt) → edge candidates +
   refusals + narrative ambiguities
3. `nl_to_kernel_ast` → question-side variables, edges, query,
   A1 ambiguities

and merges:

```
final kernel_ast.statements =
    narrative_variables
    + question_variables (dedup)
    + narrative_edges (all cause + bidirected)
    + question_edges (filtered to exclude any refused-in-narrative pair)
    + [query]

extensions.ambiguities =
    narrative_ambiguities + question_ambiguities
```

Refusals are **not** emitted as kernel statements — they are
instructions to the orchestrator to skip question-side edges
matching the refused pair. The refusal (with `pattern` +
`suggested_node`) is recorded as a matching `kind` in
`extensions.ambiguities` (`confounder_refusal` /
`selection_bias` / etc.) so the response layer surfaces the
decision.
