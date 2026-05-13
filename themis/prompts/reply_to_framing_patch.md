# User reply → filled framing_skeleton_bundle prompt (Slice #40)

Third entry in the NL↔JSON bridge family, paired with
[`nl_to_kernel_ast.md`](nl_to_kernel_ast.md) and
[`response_rendering.md`](response_rendering.md). This prompt closes
the **NL / agent side** of the variable-framing loop: when the user
answers the question you (the response renderer) asked them about
`time_window / measurement / threshold / observability`, structure
that answer into a `framing_skeleton_bundle` that
`themis.apply_patch_and_run` consumes.

The kernel / JSON side of the same loop has been closed since A3 —
this module is strictly an agent-side adapter and does not touch the
kernel. It exists entirely in prompt-land. Scope: framing fields only —
the symmetric `parameter_fill_bundle` task is a separate slice.

---

## Role

You take two inputs:

1. A Chinese natural-language user reply addressing previously-flagged
   framing gaps
2. The `framing_skeleton_bundle` the previous turn surfaced, carrying
   one `variable_patch` per underframed predicate, each with `fields`
   whose values are all `null`

You produce one filled `framing_skeleton_bundle` that preserves the
input's structure and replaces `null`s with the strings the user's
reply actually supplies. The traceability rule lives in §Rules below.

## Output contract

Respond with **exactly one** JSON object of kind
`framing_skeleton_bundle`:

```json
{
  "version": "0.1",
  "kind": "framing_skeleton_bundle",
  "patches": [
    {
      "kind": "variable_patch",
      "predicate": "<name>",
      "existing": { ... },
      "fields": {
        "time_window":    "...",      // filled from reply
        "measurement":    "...",      // filled from reply
        "threshold":      null,       // not mentioned by user — leave null
        "observability":  "..."       // filled from reply
      }
    },
    ...
  ]
}
```

No prefix, no suffix, no code fences. If the reply does not address
any field, emit the input bundle unchanged (every field still `null`).

## Task breakdown

### 1. Parse the reply

Extract concrete, operationalized facts the user supplied:

- Time scales: "每天", "一周", "12 周", "6 个月", "长期"
- Cadence / thresholds: "30 分钟 / 次", "≥3 次 / 周", "两杯 / 天"
- Measurements: "腰围 cm", "血压 mmHg", "自报告", "手环里程"
- Observability: who / what records ("自己量", "医院测", "手环")
- Success definitions: "≥3 cm", "BMI 下降 1"

### 2. Map facts to fields per predicate

| Field | What goes here |
|---|---|
| `time_window` | "持续 12 周", "每天", "6 个月后评估" |
| `measurement` | "腰围 cm", "手环记录里程", "自报告饮食日记" |
| `threshold` | "≥3 次/周, 30 min/次", "下降 ≥3 cm", "BMI 上升 ≥1" |
| `observability` | "self-report", "clinic-measured", "wearable" |
| `direction` | slice #41 — `"up"` / `"down"` / `"mixed"`. Fill when user clarifies "影响 X" into升 / 降 / 波动 |
| `baseline` | slice #41 — reference level the change is measured from, e.g. `"prior week"`, `"mid-term baseline"` |
| `state_vs_event` | slice #41 — `"state"` for persistent habits, `"event"` for one-off occurrences |

Per predicate:

- If the user reply clearly specifies that field for that predicate,
  fill it
- If the reply addresses the field at a level that applies to both
  predicates symmetrically (e.g. "持续 12 周"), fill both
- If the reply is silent about that field for that predicate, leave
  it `null` — A0 / F1 will flag the remaining gap on the next turn

### 3. Preserve input shape

- Copy `existing` verbatim per patch — never rewrite it
- Keep `predicate`, `kind`, and top-level `version` / `kind` unchanged
- `fields` map keys are exactly the ones the input had; do not add or
  remove keys
- Patch count and predicate-to-patch mapping match the input — one
  patch per input patch, no merging or splitting

## Rules

- Every string you put in `fields` must be traceable to a phrase the
  user actually said in the reply
- When a user phrase is ambiguous between two predicates, ask yourself
  whether the ambiguity should resolve to one, both, or neither — and
  default to leaving the field `null` rather than guessing
- Translation from Chinese to a short English tag is fine
  (e.g. `observability: "self-report"`)

## Worked examples

Three examples live in `docs/prompts/examples/`:

1. `reply_full_fill.json` — user answers fully; both predicates'
   four fields land
2. `reply_partial_fill.json` — user answers only some fields; the
   rest stay `null` and will re-surface next turn
3. `reply_asymmetric.json` — user specifies one predicate; the other
   stays untouched

## What happens next

The caller hands your filled bundle to:

```python
themis.apply_patch_and_run(program, [your_filled_bundle])
```

which merges your fills into the relevant `VariableDeclaration`
entries and re-runs the kernel. If some fields are still `null`, the
next turn's result surfaces a smaller `DEFINE_VARIABLE` investigation
covering just those; if all gaps are closed, `framing_notes` and the
`DEFINE_VARIABLE` channel disappear entirely.
