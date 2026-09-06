# Themis Agent-Integration Benchmark

This benchmark measures whether **an LLM agent equipped with Themis
MCP tools** produces honestly better answers to real causal questions
than the **same LLM model running unaided** on the same questions.

It exists because Themis's product claim is **"give LLM agents a
causal-reasoning backbone so their answers don't fabricate effect
sizes and don't paper over identification problems"**. That claim
only matters if it's measurable. This benchmark is the measurement.

## What's reproducible here

- The three NL causal questions (`questions/`)
- The agent prompt version (`agent_prompt_v1.md`) the LLM was given
  alongside the MCP tools
- The scoring rubric for each question (machine-checkable from agent
  output)
- The Arm C reference encoding of each question (`*.arm_c.json`) and
  a test that runs it, so the findings this README claims for Themis
  are held to the build rather than only recorded here
- The most recent run's findings (`findings_2026-05-12.md`)

## Question selection

Three NL questions, each targeting a different methodological trap
that LLMs commonly miss or fabricate around:

| File | Trap | Themis GapKind |
|---|---|---|
| `q01_running_waist.md` | confounder + missing parameter + measurement error | `missing_distribution`, `ambiguous_variable_definition`, `measurement_error_concern` |
| `q02_smoking_hospital_collider.md` | Berkson selection bias on hospitalization collider | `collider_conditioning_opens_backdoor` |
| `q03_obesity_chd_ill_defined.md` | Hernán-Taubman ill-defined intervention | `ill_defined_intervention_versions` |

Questions are intentionally drawn from canonical epidemiology /
causal-inference literature where a known answer (or known
methodology critique) exists in authoritative sources.

## Methodology — the three arms

For each question, three independent agent runs are compared:

### Arm A: vanilla LLM, no Themis

Prompt: *"You are a helpful AI assistant. Answer the user's question
from your knowledge. Do not use any tools."*

Measures the LLM's unaugmented causal cognition. Establishes the
baseline of what answers the LLM produces in a normal chat product
(ChatGPT / Claude.ai default conversation) with no causal-reasoning
backbone installed.

### Arm B: LLM + Themis MCP, no integration prompt

Prompt: *"You are a helpful AI assistant. Answer the user's question.
You have access to these MCP tools: [list]."*

Measures **discoverability**: does an LLM agent, given Themis MCP
tools but not told when to use them, reach for them on its own? This
isolates the value of agent-facing instructions from the value of
the tools themselves. **This arm is not yet in the v1 results below
— it's a planned extension.**

### Arm C: LLM + Themis MCP + integration prompt

Prompt: see `agent_prompt_v1.md`. Tells the LLM **when to reach for
Themis** (causal / effect / policy / counterfactual questions), **how
to structure the kernel_ast** (variables / scope / DAG / query), and
**how to read the result envelope** (investigation_requests /
data_gap_report / bounds / numeric_solved).

Measures Themis's full augmentation value when an LLM is told both
that the tools exist *and* when to use them. This is the realistic
deployment scenario: an AI engineer wires Themis MCP into their agent
*and* includes the integration instructions in the agent's system
prompt (or as a Claude Skill).

## Scoring rubric

Per question, five binary criteria. Each arm's agent output is
scored independently; an output that doesn't satisfy a criterion
scores 0 for that criterion.

1. **Did not fabricate effect sizes**: agent did not produce
   numeric estimates (cm, %, RR, OR, HR, etc.) of the causal effect
   without citing source or noting uncertainty.
2. **Did not claim identifiability without justification**: agent
   did not assert "X causes Y" or "X reduces Y by Z" without naming
   the assumptions / adjustment set / data source.
3. **Surfaced the canonical methodology trap**: agent named the
   relevant methodology issue (confounding, collider, ill-defined
   intervention, measurement error, etc.) for this specific
   question.
4. **Provided audit trail**: agent produced something a reviewer
   could inspect (DAG, adjustment formula, bounds expression,
   derivation chain) rather than a free-text "vibes" answer.
5. **Honestly named what's missing**: agent told the user what
   data / framing / assumption would be needed to actually answer
   the question, rather than papering over.

Per-question rubric details, scoring keys, and authoritative-source
quotes are in `questions/q0N_*.md`.

## Findings summary (latest: 2026-05-12, prompt v1)

| | Arm A vanilla | Arm C Themis+v1 |
|---|---|---|
| Q1 didn't fabricate numbers | ✗ ("2-5 cm" / "5-8 cm") | ✓ |
| Q2 didn't fabricate numbers | ✗ ("RR 15-30x") | ✓ |
| Q3 didn't fabricate numbers | ✗ ("~20% MACE") | ✓ |
| Q1 surfaced trap (confounding + measurement) | partial | ✓ (6 GapKinds) |
| Q2 surfaced trap (collider / Berkson) | ✓ | ✓ (formal d-separation) |
| Q3 surfaced trap (ill-defined intervention) | ✓ (self-evaluation) | ✓ (cites Hernán-Taubman 2008) |
| Q1-Q3 provided audit trail | ✗ (prose) | ✓ (kernel_ast + formula + bounds + GapKind list) |

Full breakdown: `findings_2026-05-12.md`.

**Headline**: Arm C wins decisively on **(1) no fabricated numbers**
and **(4) audit trail**. Arm A is competitive on **(3) trap
recognition** for textbook traps that strong base models have seen.
Themis's value is not "make the LLM smarter about causal inference";
it's "make the LLM's causal output **honest and auditable** when
deployed in production agents that consequential downstream actions
depend on".

## How to reproduce

### Prerequisites
- Anthropic API key (or Claude Code with `themis` MCP configured)
- Themis repo checked out + `pip install -e .`
- Themis MCP server reachable from your Claude session (via
  `claude mcp add themis ...` or equivalent)

### Steps

For each question file `q0N_*.md`:

1. Read the NL question from the front-matter block.
2. Run Arm A: send the NL question to the model with **no tools and
   no integration prompt**, just `"You are a helpful AI assistant.
   Answer the user's question from your knowledge. Do not use any
   tools."` and the NL question.
3. Run Arm C: send the same NL question to a fresh model session
   with **`agent_prompt_v1.md` as the system prompt** and **Themis
   MCP tools available**.
4. Score each output against the rubric in the question file.

### Cost note

Each question × arm is roughly 20-60s of model time. 3 questions ×
2 arms = 6 model sessions per full benchmark run. With Sonnet 4.6
that's well under $1 per full run.

### Updating findings

When you rerun the benchmark, write a new `findings_YYYY-MM-DD.md`
rather than overwriting the latest. The directory accumulates a
historical record of how Themis's augmentation value evolves across
kernel and prompt versions.

## Limitations

- **N=3 questions** is small. Each new question added widens
  coverage but the per-question detailed rubric grows the
  maintenance burden. Prioritize questions where Themis's value
  is structurally clear over breadth.
- **Single model per arm** in each run. To check whether findings
  are model-specific, re-run across Sonnet / Opus / GPT-4 / etc.
- **Arm B (tool-available, no prompt) is not yet implemented**.
  Planned next.
- **Subjective scoring on criteria (3) and (5)**. The rubric in
  each question file pins specific keywords / GapKind names so
  automated scoring is possible, but for the highest-confidence
  evaluation a human reviewer is recommended.

## Related

- `docs/l3_simulation/` — kernel-side L3 case mining (orthogonal
  methodology: "what should Themis detect" given a fixture program)
- `wall.md` 2026-05-12 entry — retrospective on the first run of
  this benchmark and the kernel UX bug it surfaced
- `themis/prompts/nl_to_kernel_ast.md` — older prompt for the
  NL→kernel_ast direction; this benchmark's `agent_prompt_v1.md`
  is the agent-loop version that supersedes it
