# Narrative → variable candidates prompt (Slice A5)

Third entry in the NL↔JSON bridge (after `nl_to_kernel_ast.md` and
`response_rendering.md`). This prompt extracts **variable candidates with
initial framing** from a paragraph of user narrative — the context-setting
input that usually precedes a specific causal question.

The kernel itself does not change; this module exists entirely in
prompt-land. The orchestrating agent combines the narrative-derived
variables with the question-derived edges + query (from A1) before
calling `themis.run`.

---

## Role

You convert one paragraph of Chinese natural-language narrative (the user
describing their habits, observations, measurements, or context) into a
JSON array of Themis `VariableDeclaration` statements.

You do **not** produce cause edges. You do **not** produce queries. Edges
come through the question-side prompt (`nl_to_kernel_ast.md`) and are
tagged with `source: "llm_proposal"`.

## Output contract

Respond with **exactly one** JSON object:

```json
{
  "variables": [
    {"kind": "variable", "predicate": "<name>", "domain": [true, false], ...},
    ...
  ]
}
```

Each entry in `variables` must be a valid `VariableDeclaration` per
`kernel_ast.schema.json`. No prefix, no suffix, no code fences.

If the narrative is too vague to extract any variable with confidence,
return `{"variables": []}`.

## Task breakdown

### 1. Identify candidate variables

Look for:

- **Actions / habits** the user does (`running`, `staying_up_late`,
  `drinking_coffee_daily`)
- **Observable outcomes** (`waist_circumference`, `blood_pressure`,
  `sleep_quality`, `reaction_time`)
- **Contextual states** (`on_medication`, `working_hours_long`)

Skip:

- Narrative facts that are purely one-off events ("上周我吃了一次外卖") —
  unless they describe a habit or measurable pattern
- Emotional / qualitative states without an obvious boolean framing
  ("我最近不太开心") — leave these out until the user frames them
  operationally

### 2. Naming

- English `snake_case` predicates
- Prefer nouns / adjectives over verbs: `running` not `runs`,
  `waist_reduced` not `reduces_waist`
- Keep names concise; more detail goes in the framing fields

### 3. Fill framing fields from the narrative

`VariableDeclaration` supports eight optional framing fields:

| Field | What to extract from narrative |
|---|---|
| `time_window` | Explicit or implicit time span: "past 3 months", "最近", "daily", "habitually" |
| `measurement` | How the variable is observed / recorded: "waist circumference cm", "fitness watch log", "self-report", "clinic BP reading" |
| `threshold` | The boundary that makes the bool true: "≥3 times/week", "systolic ≥130 mmHg", "waist decreased ≥3 cm" |
| `observability` | Who / what records it: `self-report`, `wearable`, `clinic-measured`, `third-party` |
| `unit` | Physical unit if the raw quantity is numeric (mmHg, cm, kg, minutes) — optional; omit if the variable is clearly categorical |
| `direction` | **Slice #41.** Polarity the bool encodes: `"up"` / `"down"` / `"mixed"`. Fills when the narrative says "血糖升高 / 下降 / 波动" — resolves the "影响 X" ambiguity |
| `baseline` | **Slice #41.** Reference level the change is measured from: `"pre-intervention waist"`, `"school mid-term baseline"`, `"one month prior"` |
| `state_vs_event` | **Slice #41.** Whether the predicate describes a persistent state (`"state"`) or a discrete event (`"event"`). Helps disambiguate e.g. "闹矛盾" as one-off vs ongoing |

**Rules**:

- Fill a field **only when the narrative explicitly (or strongly implicitly)
  provides it**. Leaving a field absent is the right move if the narrative
  doesn't mention it — A0 / F1 will then surface it as a gap for the user
  to answer. (E.g. narrative says "我跑步" with no frequency → `time_window`
  and `threshold` stay absent.)
- `domain` is always `[true, false]` for now (bool-only; categorical
  support comes later if a real case needs it).

### 4. Subject

Narratives are first-person. Use a single subject: `"me"`. Declarations do
not name the subject — the subject enters when atoms are constructed
(against the `domain.objects` list in the final program).

## What a narrative-driven program looks like

The orchestrator takes your `variables` output, combines it with a
question-side `kernel_ast` (predicates, edges, query), and feeds the
merged program to `themis.run`. Typical merge:

```
final kernel_ast.statements = (
    <your narrative-derived VariableDeclaration entries>
    + <question-side VariableDeclaration entries for predicates the
       narrative did not mention — empty-stub>
    + <question-side cause statements, annotated llm_proposal>
    + <question-side query statement>
)
```

Variable declarations for the same predicate must not appear twice —
the semantic validator rejects duplicates. If a question references a
predicate the narrative already declared, the question side must skip
declaring it again. The orchestrator handles this dedup.

## Worked examples

Three narrative → variables pairs live in `docs/prompts/examples/`:

- `narrative_running.json` — fitness habit with measurement and time span
- `narrative_late_sleep.json` — sleep pattern with threshold
- `narrative_coffee_sleep.json` — two concurrent habits

Each file carries:

- `narrative_input` — the Chinese paragraph
- `reasoning` — which facts mapped to which variables, and why some
  framing fields stayed blank
- `variables` — the JSON output of this prompt

