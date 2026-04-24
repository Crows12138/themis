# Themis NL evaluation set

> Status: v2.1 (2026-04-24). 22 cases across 19 failure modes
> (F1–F19). F19 (IV identification) + cases 21/22 added with
> Phase 6.iv slice.

This directory holds evaluation cases for the NL layer (A1 prompt,
A5 narrative prompt, and the A1→themis.run→response_rendering
pipeline). Each case is a single JSON file with handwritten gold
labels; the set is intended to be run through a real-LLM driver
(pending) to produce measurable failure attributions. For now a
baseline run uses author-simulated A1/A5 outputs and is reported
separately in `docs/trial_reports/`.

**Purpose** — answer the data-driven question: which slice should
land next? `#41` framing extension, `#37.c` narrative_to_edges
prompt, `#37.e` e2e helper, something else? The evaluation set +
attribution metrics make that decision empirical instead of
intuitive.

## Per-case JSON schema

```json
{
  "id": "short_slug",
  "failure_modes": ["F1", "F4"],
  "narrative": "chinese paragraph setting context, optional",
  "question": "chinese NL question",

  "gold_variables": [
    {
      "predicate": "expected_name",
      "domain_hint": "bool | categorical:[low,mid,high] | ...",
      "role": "target | intervention | mediator | confounder | observed",
      "operationalization_hints": {
        "time_window": "suggested value or null if untestable",
        "measurement": "...",
        ...
      }
    }
  ],

  "gold_edges": [
    {
      "from": "pred_a",
      "to": "pred_b",
      "kind": "directed | bidirected",
      "severity": "must | should",
      "source": "narrative | common_knowledge | question_intent",
      "source_span": "chinese substring from narrative or question, optional"
    }
  ],

  "must_not_infer": [
    {"kind": "edge", "from": "...", "to": "...",
     "reason": "e.g. confounding not causation (ice cream vs drowning)"}
  ],

  "ambiguities": [
    {
      "kind": "intent | scope | direction | ...",
      "description": "text",
      "expected_behavior": "abstain | proposal | surface as clarifying ask"
    }
  ],

  "gold_answerability": "answerable | needs_framing | needs_data |
                         needs_structural_info | unanswerable",

  "gold_query_kind": "cause | assoc | effect | identify | probability"
}
```

Field meaning:

- `failure_modes` — which of the taxonomy codes this case targets
  (see `failure_modes.md`)
- `gold_variables` — what a correct extraction should produce;
  domain_hint and operationalization_hints are advisory
- `gold_edges.severity` — `must` = any correct system has to
  extract it; `should` = reasonable but not strictly required
- `must_not_infer` — edges / variables that a naive LLM might
  invent but would be wrong (confounding, spurious association,
  etc.). Measures hallucination resistance.
- `ambiguities` — known places where the NL has >1 valid reading;
  the correct behavior is `abstain` or `proposal`, not silent pick
- `gold_answerability` — high-level "what kind of follow-up does
  this case need"

## Metrics

The attribution report uses these, computed per-case and aggregated:

- **variable recall** = |extracted ∩ gold| / |gold|
- **edge recall** = |extracted ∩ gold (by `must` severity)| /
  |gold by `must`|
- **critical hallucination rate** = |extracted_edges ∩
  must_not_infer| / |extracted_edges|
- **abstention quality** — on cases with `ambiguities`, did the
  system surface the ambiguity (good) or silently pick one
  reading (bad)?
- **provenance completeness** = |extracted_elements with source
  annotation| / |extracted_elements|

## What's here

- `failure_modes.md` — the failure-mode taxonomy (F1–F9 currently)
- `cases/` — one JSON per case
- `baseline_run.py` — driver that runs each case's narrative +
  question through a given A1 / A5 interface and scores against
  gold. Manual mode: author provides the produced AST directly.
  LLM mode: pending; interface sketch in the file.

## How to grow

- Drop a new JSON in `cases/` matching the schema
- Make sure `failure_modes` references existing codes or add a
  new one in `failure_modes.md` with a rationale
- Keep `gold_edges.severity=must` reserved for edges the user
  would be upset to see missing — overusing `must` inflates
  edge-recall failures
