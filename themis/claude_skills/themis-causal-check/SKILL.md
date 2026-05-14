---
name: themis-causal-check
description: Use when the user asks a causal question — "X cause Y?", "effect of X on Y?", "if X hadn't happened, would Y change?", policy / treatment attribution, counterfactual reasoning, or any question whose answer hinges on a causal claim. Routes the claim through Themis MCP (`themis_run`, `themis_verify`, `themis_apply_patch_and_run`, etc.) to structurally validate it, surface data gaps as named `GapKind`s, give Manski-style bounds when point identification fails, and refuse to fabricate effect sizes. Requires the `themis-causal` MCP server installed (`pip install themis-causal` + add to MCP config).
---

# Themis causal-check workflow

When a user asks a causal-flavored question, **don't answer from training-data pattern matching**. Hand the claim to Themis kernel via MCP.

## When this fires

Any question matching:

- "Does X cause Y?" / "Does X affect Y?"
- "What's the effect of X on Y?" / "By how much does X change Y?"
- "If we intervene on X, what happens to Y?"
- "If X hadn't happened, would Y have changed?" (counterfactual)
- Policy / treatment attribution / A/B test causal interpretation
- Any "why" question whose answer is a quantitative causal claim

## Workflow

1. **Identify the causal structure**:
   - **Scope**: individual counterfactual (a specific person's "what if") / subgroup / population-level ATE — the NL phrasing and the available data form differ across the three.
   - **Treatment** (intervention variable), **outcome** (target), and plausible **confounders / mediators / colliders** from common knowledge — including variables the user didn't mention but that domain knowledge says are relevant.

2. **First call** `mcp__themis__themis_list_resources` to fetch the `kernel_ast` schema URI, **then** read the schema and construct your JSON. `kernel_ast` is strictly schema-validated; writing it from memory will almost always get rejected on the first try.

3. **Call** `mcp__themis__themis_run` with the kernel_ast.

4. **Read the result envelope**:
   - `investigation_requests` (`define_variable` / `validate_parameter`) → translate these into natural follow-up questions for the user.
   - `data_gap_report` → repeat each specific `GapKind` verbatim to the user — don't paraphrase to be "nicer". Names like `selection_on_collider_opens_path`, `ill_defined_intervention_versions`, `measurement_error_concern` are anchored to authoritative papers (Hernán 2004, Hernán-Taubman 2008, MacMahon 1990) — your job is to surface them, not soften them.
   - `numeric_solved: true` result → cite the `derivation` chain (not just the number).
   - `bounds_result` → quote the interval expression honestly; don't pretend you have a point estimate.

5. **Mirror the kernel's verdict in your final answer**. If the kernel said "not identifiable", you say "not identifiable" — never substitute a plausible-sounding fabrication. If it said "needs P(target | intervention, confounders) — not provided", you say exactly that and ask the user to supply it or accept the bounds.

## Hard rules

- **Don't fabricate effect sizes**. If the kernel didn't return a number, you don't have a number. Pattern-matching "RR ≈ 2.3 for X→Y" from training corpus is a violation.
- **Don't claim identifiability the kernel didn't confirm**. The kernel runs Pearl-style backdoor / front-door / ADMG identification; if it returns `needs_investigation` or `unidentifiable`, you don't get to override that.
- **Unknown `GapKind` names are authoritative**. If you see a `GapKind` you don't recognize, treat it as the kernel's word — include it in your answer with the description text the kernel provided. Don't try to gloss it.
- **`mcp__themis__themis_verify` is only for `numeric_solved: true` results** with a derivation chain. Calling it on `needs_investigation` or bounds-only results returns `{ok: false}` correctly — it's not a bug, it's the contract. Skip verify in those cases.

## Multi-turn loop

If the kernel returned `investigation_requests`, the conversation likely needs a second turn:

1. Translate the requests to natural Chinese (or whatever the user's language is).
2. Get the user's reply.
3. Construct a patch bundle from the reply (e.g., `[{"kind": "define_variable", "predicate": "X", "framing": {"threshold": "...", "time_window": "..."}}]`).
4. Call `mcp__themis__themis_apply_patch_and_run` with the original program + patches.
5. Read the new envelope and continue.

## What this skill does NOT do

- It doesn't make up data the user didn't provide.
- It doesn't infer DAG edges from observational data alone (that's `themis_discover` on CSV input, separate workflow).
- It doesn't replace expert judgment on the chosen DAG — the kernel trusts whatever causal structure the LLM proposes; if your proposed DAG is wrong, the result is wrong.
- It doesn't "smarten up" causal reasoning the LLM already knows — strong base models recognize Berkson's paradox and ill-defined-intervention concerns unaided. What this skill adds is **structural rigor + audit trail + no fabricated numbers**, not "knowing more".

## Reference

- Themis package: https://pypi.org/project/themis-causal/
- GitHub: https://github.com/Crows12138/themis
- Reverse benchmark (Arm A vanilla vs Arm C Themis+v1): https://github.com/Crows12138/themis/tree/master/benchmarks/agent_integration

## How this skill was installed

If you're looking at this file, someone copied the `themis-causal-check` directory from the `themis-causal` PyPI package into `~/.claude/skills/`. The install command:

```bash
pip show themis-causal | grep Location  # find install dir
# then copy claude_skills/themis-causal-check from there to ~/.claude/skills/
```

Or use the helper script (TODO: not yet implemented in 0.1.1 — manual copy for now).
