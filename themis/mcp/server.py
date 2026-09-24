"""FastMCP server exposing Themis kernel + prompts (slice A1(b)).

Tools (JSON in / JSON out — same contract as the kernel itself, with one
difference in what comes back; see "What a result hands over" below):

- ``themis_run(program)`` → wraps :func:`themis.run`
- ``themis_apply_patch_and_run(program, patches)`` → wraps :func:`themis.apply_patch_and_run`
- ``themis_result(result_id, pointer, start)`` → a part of a result this server holds, under the same budget
- ``themis_guide(doc, section, start)`` → the prompts and schemas below, a section at a time
- ``themis_audit(program, result)`` → wraps :func:`themis.audit`; every re-check that applies to this artifact, one row each. Prefer it over picking a ``themis_verify_*`` by hand, and pass ``result_id`` rather than a result this server handed out
- ``themis_verify(program, result)`` → wraps :func:`themis.verify`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_data_gap_report(result)`` → wraps :func:`themis.verify_data_gap_report`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_bounds_results(program, result)`` → wraps :func:`themis.verify_bounds_results`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_markov_blanket(result)`` → borrow-list #4, wraps :func:`themis.verify_markov_blanket`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_lagged_discovery(result)`` → wraps :func:`themis.verify_lagged_discovery`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_latent_lagged_discovery(result)`` → wraps :func:`themis.verify_latent_lagged_discovery`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_notears_fit(result)`` → wraps :func:`themis.verify_notears_fit`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_selection_recovery_numeric(result)`` → §S9.1 numeric end, wraps :func:`themis.verify_selection_recovery_numeric`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_missing_data_numeric(result)`` → §S9.2 numeric end, wraps :func:`themis.verify_missing_data_numeric`; returns ``{"ok": bool, "error": str?}``
- ``themis_estimate(program, csv_path, options=None, reference_csv_path=None)`` → wraps :func:`themis.estimate`; loads CSV(s) from disk (reference = external unbiased sample for selection-bias recovery)
- ``themis_discover(csv_path, ...)`` → wraps :mod:`themis.estimation.discovery` (Phase 8.1); skeleton from CSV
- ``themis_markov_blanket(csv_path, target, ...)`` → borrow-list #4, wraps :func:`themis.estimation.discovery.markov_blanket`; local Markov-blanket screen from CSV
- ``themis_discover_lagged_graph(csv_path, time, ...)`` → wraps :func:`themis.estimation.lagged_discovery.discover_lagged_graph`; PCMCI lagged graph from a time series or panel CSV, assuming every common cause was recorded
- ``themis_discover_latent_lagged_graph(csv_path, time, ...)`` → wraps :func:`themis.estimation.latent_lagged_discovery.discover_latent_lagged_graph`; the same graph WITHOUT that assumption, so an edge can come back as "shares something unrecorded" or as "one of the two, and this data cannot say"
- ``themis_discover_notears(csv_path, ...)`` → NOTEARS weighted DAG from CSV, with the certificate and the per-edge scale diagnostic ``themis_discover`` has no room for
- ``themis_report(program, csv_path=None, run_verify=True, lang=None)`` →
  deterministic analyze → (verify) → one Markdown report per query in the
  reader's language (no LLM, no API key)
- ``themis_submit_verdict(verdict, question, ...)`` → Fix 2A (v0.1.5):
  schema-validated yes/no/needs_more_info commitment channel. Removes
  token-level reliability risk when downstream consumers (benchmark
  scoring, agent pipelines, audit logs) need a binary verdict.
- ``themis_list_resources()`` → returns the resource URI catalog

Resources (read by the client to drive NL↔JSON):

- ``themis://prompts/nl_to_kernel_ast.md`` — A1 input bridge
- ``themis://prompts/response_rendering.md`` — output bridge
- ``themis://prompts/narrative_to_variables.md`` — A5 upstream framer
- ``themis://prompts/narrative_to_edges.md`` — A2 edge proposer
- ``themis://prompts/reply_to_framing_patch.md`` — F1 follow-up patcher
- ``themis://prompts/gap_to_action.md`` — Phase 11.1 agent-loop decision table
- ``themis://prompts/kb_lookup.md`` — Phase 11.2 structured KB query/result
- ``themis://schemas/kernel_ast.schema.json`` — input schema
- ``themis://schemas/query_result.schema.json`` — output schema
- ``themis://schemas/derivation.schema.json`` — embedded reasoning chain schema
- ``themis://schemas/kb_query.schema.json`` — Phase 11.2 KB adapter input
- ``themis://schemas/kb_result.schema.json`` — Phase 11.2 KB adapter output

The server does NOT call any LLM. The client (e.g. Claude Code) reads
the prompts, converts NL ↔ JSON, and calls the tools.

What a result hands over. A kernel envelope is a record written for the
verifier, and its size is set by the question: in the first real test an
attribution question with four candidate causes came back at 205,402
characters, Claude Code moved it to a file, and the agent read it only
because it had a shell. So every tool that produces a result keeps the
whole of it here, under an id, runs the audits that apply to it, and
hands back :func:`themis.output.bounded_view.view` of it — the record
with whatever does not fit folded into markers that ``themis_result``
follows. The answer itself is never folded. The prompts and schemas are
served the same way by ``themis_guide``, since the two an agent needs
first are each larger than a client accepts at once.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import themis
from themis.output import bounded_view

from .guide import Guide


REPO_ROOT = Path(__file__).resolve().parents[2]
# Schemas + prompts now live inside the package so they ship with the
# wheel. PACKAGE_ROOT resolves to .../themis/ in both git-clone and
# pip-installed modes. REPO_ROOT is still used for CSV path resolution
# (themis_estimate's csv_path argument is interpreted relative to where
# the MCP server was launched, which is the project root).
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"
SCHEMAS = {
    "kernel_ast.schema.json": SCHEMAS_DIR / "kernel_ast.schema.json",
    "query_result.schema.json": SCHEMAS_DIR / "query_result.schema.json",
    "derivation.schema.json": SCHEMAS_DIR / "derivation.schema.json",
    # Phase 11.2 — KB adapter contract: clients implement adapters that
    # speak this query/result shape, then translate via
    # themis.kb.translator into apply_patch_and_run patches.
    "kb_query.schema.json": SCHEMAS_DIR / "kb_query.schema.json",
    "kb_result.schema.json": SCHEMAS_DIR / "kb_result.schema.json",
}
PROMPT_FILES = (
    "nl_to_kernel_ast.md",
    "response_rendering.md",
    "narrative_to_variables.md",
    "narrative_to_edges.md",
    "reply_to_framing_patch.md",
    # Phase 11.1 — closes the agent loop by telling the LLM what to do
    # when data_gap_report is non-empty (next-action decision table +
    # autonomous-fetch vs ask-user heuristics + loop termination rules).
    "gap_to_action.md",
    # Phase 11.2 — teaches the orchestrator to use structured KBQuery /
    # KBResult instead of free-form WebSearch strings, and to route
    # results through themis.kb.translator helpers.
    "kb_lookup.md",
)


#: What the server tells an agent when it connects, before any tool is
#: called. Short on purpose: it is always in the agent's context, and what
#: it says is where to find the rest.
ORIENTATION = """\
Themis checks causal claims. You translate a question into a kernel program \
(a causal graph plus a query); Themis runs it and every answer comes with \
independent re-checks and a list of the data or assumptions it still lacks. \
Themis itself calls no model.

Read the documents a section at a time: themis_guide() lists them, \
themis_guide(doc) gives a document's sections, themis_guide(doc, section) \
one section. Read the sections of nl_to_kernel_ast.md your question needs \
before writing a program, and the relevant sections of response_rendering.md \
before writing the answer up.

Results stay on the server. themis_run and the other tools that produce a \
result return result_id and a view that fits a fixed size, with the audits \
that apply already run (audits: one list per query). The answer itself — \
status, value or interval, tier, the assumption ledger — is never left out. \
Anything that did not fit is replaced in place by \
{"omitted": {"pointer": ..., "chars": ...}}: it exists, and \
themis_result(result_id, pointer) fetches it (for a list, pass the marker's \
"from" as start). Fetch a part before saying anything about it. Pass \
result_id to themis_audit instead of copying a result back.\
"""

#: How many results a server keeps. A result is the size of its question,
#: and a session that runs a hundred programs should not hold them all.
HELD = 64

#: The two keys a handed-over result carries that the artifact did not.
HANDED_OVER = ("result_id", "audits")


class _Kept:
    """What this server has handed out, by the id it was handed out under.

    Held for as long as the process runs — over stdio that is one process
    per client — and only the most recent :data:`HELD`, oldest dropped
    first. The ids are short and counted because an agent copies them back.
    """

    def __init__(self) -> None:
        self._by_id: dict[str, tuple[dict, Any]] = {}
        self._count = 0

    def put(self, doc: dict, program: Any) -> str:
        self._count += 1
        rid = f"r{self._count}"
        doc["result_id"] = rid
        self._by_id[rid] = (doc, program)
        while len(self._by_id) > HELD:
            self._by_id.pop(next(iter(self._by_id)))
        return rid

    def get(self, rid: str) -> tuple[dict, Any]:
        if rid not in self._by_id:
            held = ", ".join(self._by_id) or "none"
            raise ValueError(
                f"no result {rid!r} in this server session (it holds: "
                f"{held}). A result lives as long as the server process and "
                f"the most recent {HELD} are kept; run the program again.")
        return self._by_id[rid]


def _as_artifact(obj: Any) -> Any:
    """An artifact this server handed out, without the two keys it added.

    So that one passed back as it came is checked as what the kernel
    produced; everything else in it is left exactly as the caller sent it,
    so an edited artifact is still refused.
    """
    if isinstance(obj, dict) and "result_id" in obj:
        return {k: v for k, v in obj.items() if k not in HANDED_OVER}
    return obj


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_server(budget: int | None = None):
    """Construct and return the configured FastMCP server.

    Kept as a function (not module-level instantiation) so tests can
    spin up an isolated instance without side effects.

    ``budget`` is how many characters any one reply may run to;
    ``THEMIS_MCP_BUDGET`` sets it for a deployment.
    """
    from mcp.server.fastmcp import FastMCP

    if budget is None:
        budget = int(os.environ.get("THEMIS_MCP_BUDGET",
                                    bounded_view.DEFAULT_BUDGET))
    app = FastMCP("themis", instructions=ORIENTATION)
    kept = _Kept()
    guide = Guide({name: PROMPTS_DIR / name for name in PROMPT_FILES},
                  SCHEMAS, budget)

    def _audits(artifact: dict, program: Any) -> Any:
        results = artifact.get("results")
        try:
            if isinstance(results, list):
                source = (artifact.get("program")
                          or artifact.get("merged_program") or program)
                return [themis.audit(source, r) for r in results]
            return [themis.audit(program, artifact)]
        except Exception as exc:  # a malformed call, not a verdict
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _hand_over(artifact: dict, program: Any = None, *,
                   audit: bool = True) -> str:
        """Keep the whole of ``artifact`` here; hand back a view that fits."""
        clash = [k for k in HANDED_OVER if k in artifact]
        if clash:
            raise ValueError(f"an artifact already carries {clash}, which "
                             f"this server adds to what it hands over")
        doc: dict = {"result_id": ""}
        if audit:
            doc["audits"] = _audits(artifact, program)
        doc.update(artifact)
        kept.put(doc, program)
        return _compact(bounded_view.view(doc, budget))

    # ============================================ tools

    @app.tool(structured_output=False)
    def themis_run(program: dict | str) -> str:
        """Run the Themis kernel on a kernel_ast program.

        ``program``: either a ``dict`` matching ``kernel_ast.schema.json``
        or a JSON string. Returns the ``themis.run`` envelope
        (``{"results": [...], "program": {...}}``) as a view that fits,
        with ``result_id`` and ``audits`` (the re-checks that apply, one
        list per query, already run). A part that did not fit is a marker
        ``{"omitted": {"pointer", "chars", ...}}``; ``themis_result``
        fetches it. The answer itself is never folded.
        """
        return _hand_over(themis.run(program), program)

    @app.tool(structured_output=False)
    def themis_apply_patch_and_run(
        program: dict | str, patches: list[dict] | dict,
    ) -> str:
        """Apply framing/parameter patches and re-run.

        Multi-turn closed loop (slice A3): the client gathers user
        replies as patch bundles, applies them to the original program,
        and gets a refreshed result envelope back — handed over the way
        ``themis_run`` hands one over.
        """
        return _hand_over(themis.apply_patch_and_run(program, patches),
                          program)

    @app.tool(structured_output=False)
    def themis_result(result_id: str, pointer: str = "",
                      start: int = 0) -> str:
        """A part of a result this server handed out, under the same budget.

        ``pointer`` is the JSON Pointer a marker gave (``""`` for the whole
        result). ``start`` resumes a list or a long string: pass a list
        marker's ``from``, or a string part's ``next``. What comes back is
        ``{"pointer", "from"?, "value", "next"?}``, and ``value`` may hold
        markers of its own.
        """
        doc, _ = kept.get(result_id)
        return _compact(bounded_view.part(doc, pointer, start, budget))

    @app.tool(structured_output=False)
    def themis_guide(doc: str | None = None, section: str | None = None,
                     start: int = 0) -> str:
        """The prompts and schemas that say how to drive Themis, in parts.

        No arguments: the documents. ``doc`` alone: its sections, by the
        name to pass as ``section``. ``doc`` and ``section``: that section,
        or — when it is too large to hand over whole — its own opening text
        and the names of its subsections. A long passage with no
        subsections comes in slices: pass ``next`` back as ``start``. For
        a schema a section is a definition, or a JSON Pointer from a
        marker inside one.
        """
        if doc is None:
            return _compact(guide.documents())
        if section is None:
            return _compact(guide.contents(doc))
        return _compact(guide.section(doc, section, start))

    @app.tool()
    def themis_audit(program: dict | str | None = None,
                     result: dict | None = None,
                     result_id: str | None = None) -> dict:
        """Run every independent re-check that applies to this artifact.

        Prefer this over picking a ``themis_verify_*`` tool by hand. The
        individual tools below are each one audit among many, and several
        of them audit a standalone artifact rather than a query_result
        envelope — handed the wrong one they refuse with the same error
        they use for an artifact that failed its audit, so a caller
        choosing by hand can report a result as unverified over an audit
        that was never about it.

        For a result this server handed out, pass its ``result_id``: the
        audits run on the record kept here, one list per query, and nothing
        has to be copied back. ``program`` and ``result`` are for an
        artifact that came from somewhere else.

        Returns ``{"audits": [{"audit", "words", "ok", "refusal"}, ...]}``
        (a list of those lists for ``result_id``), or
        ``{"error": "<message>"}`` when the call itself is malformed.
        """
        try:
            if result_id is not None:
                doc, source = kept.get(result_id)
                return {"audits": _audits(_as_artifact(doc), source)}
            if result is None:
                raise ValueError("pass result_id, or a result to audit")
            return {"audits": themis.audit(program, _as_artifact(result))}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify(program: dict | str, result: dict) -> dict:
        """Independently re-verify a claimed result against the program.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "<message>"}`` on failure (rather than
        raising — MCP transport-friendly).
        """
        try:
            themis.verify(program, result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_data_gap_report(result: dict) -> dict:
        """Independently audit a result's data_gap_report.

        This is intentionally separate from ``themis_verify``: some
        diagnostic outputs have no query derivation to audit, but their
        T10 data-gap report is still independently checkable.
        """
        try:
            themis.verify_data_gap_report(result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_bounds_results(
        program: dict | str, result: dict,
    ) -> dict:
        """Independently audit a result's bounds_results.

        Parallel to ``themis_verify_data_gap_report``: bounds typically
        attach when point identification fails (status=needs_investigation)
        and no derivation chain exists, so ``themis_verify`` rejects them
        for missing derivation. This tool dispatches by
        bounds_results.method to the per-method verifiers
        (manski_natural / manski_tamer_monotonicity / balke_pearl_iv).
        """
        try:
            themis.verify_bounds_results(program, result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_markov_blanket(result: dict) -> dict:
        """Independently audit a Markov-blanket result (borrow-list #4).

        Parallel to ``themis_verify_bounds_results``: the artifact is a
        standalone Markov-blanket dict (from ``themis_markov_blanket``), not a
        query_result envelope, so ``themis_verify`` does not apply. Re-checks
        the completeness + minimality definition on the returned set by
        recomputing every conditional-independence test from the recorded
        correlation matrix with an independent Fisher-Z reimplementation —
        rejecting a fabricated / trimmed blanket or a tampered test.
        """
        try:
            themis.verify_markov_blanket(_as_artifact(result))
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_lagged_discovery(result: dict) -> dict:
        """Independently audit a lagged-discovery result.

        Parallel to ``themis_verify_markov_blanket``: the artifact is a
        standalone ``lagged_discovery`` dict (from
        ``themis_discover_lagged_graph``), not a query_result envelope, so
        ``themis_verify`` does not apply. Recomputes both stages from the
        recorded correlation matrix with an independent Fisher-Z
        reimplementation — whether each parent set is the fixpoint it claims,
        and whether each MCI test really conditioned on the driver's own
        parents as well as the target's, which is the half that would vanish
        without trace if a producer dropped it.
        """
        try:
            themis.verify_lagged_discovery(_as_artifact(result))
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_latent_lagged_discovery(result: dict) -> dict:
        """Independently audit a lagged graph learned WITHOUT assuming that
        every common cause was recorded.

        Parallel to ``themis_verify_lagged_discovery``, with one more claim to
        hold the artifact to. The screen is re-checked as a fixpoint, the
        subset search behind every pair's verdict is re-run from the recorded
        correlation matrix, and then every endpoint mark is re-derived with a
        second transcription of the orientation rules. That last one is what
        this audit is for: a mark saying "causes" that the rules do not
        produce is a causal claim made out of nothing, which is exactly what
        the assumption this method drops used to produce.
        """
        try:
            themis.verify_latent_lagged_discovery(_as_artifact(result))
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool(structured_output=False)
    def themis_estimate(
        program: dict | str,
        csv_path: str,
        options: dict | None = None,
        reference_csv_path: str | None = None,
    ) -> str:
        """Run Phase 7 numeric estimation on a CSV-backed dataset.

        ``csv_path`` is loaded with pandas. ``options`` are forwarded as
        kwargs to :func:`themis.estimate` (e.g. ``{"random_state": 42}``).
        ``reference_csv_path`` (optional) is the external *unbiased* sample
        needed to recover a causal effect under selection bias (§S9.1); it is
        loaded and passed as ``reference_data=`` and used ONLY when a result
        carries a ``selection_recovery`` block. Returns the estimate envelope
        (point / CI / method / assumptions / sensitivity_analysis if binary
        outcome), handed over the way ``themis_run`` hands one over.
        """
        import pandas as pd

        def _load(p: str):
            path = Path(p)
            if not path.is_absolute():
                path = (REPO_ROOT / p).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
            return pd.read_csv(path)

        df = _load(csv_path)
        opts = dict(options or {})
        if reference_csv_path is not None:
            opts["reference_data"] = _load(reference_csv_path)
        return _hand_over(themis.estimate(program, df, **opts), program)

    @app.tool()
    def themis_verify_selection_recovery_numeric(result: dict) -> dict:
        """Independently audit a selection-backdoor recovered ATE (§S9.1).

        The artifact is a query_result whose ``numeric_estimate`` was produced
        by the selection-backdoor recovery estimator
        (``selection_backdoor_recovery``). Re-runs the Bareinboim-Pearl
        Theorem-3.5 recovery formula from the recorded sufficient statistics
        (per-stratum biased counts + external unbiased weight tables) as a
        second, standalone transcription and checks the ATE, the two arms, and
        the weight-table normalisation — rejecting a forged point or tampered
        stratum. A result carrying no such numeric_estimate is a no-op.
        """
        try:
            themis.verify_selection_recovery_numeric(result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_missing_data_numeric(result: dict) -> dict:
        """Independently audit a recovered-from-missing-data ATE (§S9.2).

        The artifact is a query_result whose ``numeric_estimate`` was produced
        by the missing-data recovery estimator
        (``missing_data_recovery_gformula``). Re-runs the Mohan-Pearl-Tian
        g-formula Σ_z (E[Y|1,z]−E[Y|0,z])·P(z) from the recorded per-stratum
        sufficient statistics (the {n, y_sum} conditionals + {z, count} marginal
        tables for the recovered estimate and the naive listwise foil) as a
        second, standalone transcription and checks the reported point, the
        marginal normalisation, and that no contributing stratum was dropped —
        rejecting a forged point or a tampered stratum. A result carrying no
        such numeric_estimate is a no-op.
        """
        try:
            themis.verify_missing_data_numeric(result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool(structured_output=False)
    def themis_report(
        program: dict | str,
        csv_path: str | None = None,
        options: dict | None = None,
        run_verify: bool = True,
        lang: str | None = None,
    ) -> str:
        """Run (or estimate on data) + optionally verify + render one
        human-readable Markdown analysis report per query.

        The deterministic, end-to-end "analyze → verify → report" surface:
        unlike the LLM render bridge it needs no API key, and unlike a
        generic causal report it foregrounds Themis's differentiators —
        the answer first, then the verification status and the
        assumptions / data gaps.

        ``program``: kernel_ast dict or JSON string. ``csv_path``: if
        given, run numeric estimation on the CSV; otherwise a structural
        run. ``options``: forwarded to ``themis.estimate`` when csv_path
        is set. ``run_verify``: run every re-check that applies to each
        result and stamp the report ✓/✗ per check — a re-check is a
        separate re-derivation; the report assembler never re-runs
        reasoning itself.

        ``lang``: which language the reports are written in — one of
        ``themis.language.Lang``, defaulting to
        ``themis.language.DEFAULT``. This tool is the one place a report
        reaches a reader whose language nothing here can observe: the
        browser has the reader in front of it and asks, and a library
        caller passes ``lang=`` to the assembler, but an agent on the
        other end of this door knows which language its user is reading
        and had no way to say so. An unanswerable tag is refused by name
        rather than rendered half-way.

        Which re-checks apply is asked of ``themis.audit`` rather than
        decided here. Gating on a derivation instead meant this tool
        stamped nothing on any envelope answered by an interval or by a
        recovery estimator, though each of those has a registered auditor
        that recomputes its answer.

        Returns ``{"reports": [markdown, ...], "statuses": [...]}`` with a
        ``result_id``; a report too long to hand over whole is a marker that
        ``themis_result`` reads in slices.
        """
        from themis.output.analysis_report import build_analysis_report

        reader = themis.language.answered(
            themis.language.DEFAULT if lang is None else lang)

        if csv_path is not None:
            import pandas as pd

            path = Path(csv_path)
            if not path.is_absolute():
                path = (REPO_ROOT / csv_path).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
            df = pd.read_csv(path)
            env = themis.estimate(program, df, **(options or {}))
        else:
            env = themis.run(program)

        # Both entry points this tool uses echo the validated AST back
        # under "program" — ``themis.estimate`` because it returns the
        # envelope ``themis.run`` built. ("merged_program" is
        # ``apply_patch_and_run``'s key, and nothing here calls it.) The
        # fall-back is therefore only ever the caller's own argument.
        prog_source = env.get("program") or program
        # That argument, unlike the echo, may still be an unparsed JSON
        # string: ``audit`` parses one itself, whereas the report
        # assembler reads fields off a mapping and so is handed one only
        # when we have one.
        prog_dict = prog_source if isinstance(prog_source, dict) else None
        reports: list[str] = []
        statuses: list[str] = []
        for result in env.get("results", []):
            audited = themis.audit(prog_source, result) if run_verify else None
            reports.append(
                build_analysis_report(result, program=prog_dict,
                                      audited=audited, lang=reader)
            )
            statuses.append(result.get("status"))
        return _hand_over({"reports": reports, "statuses": statuses},
                          audit=False)

    @app.tool(structured_output=False)
    def themis_discover(
        csv_path: str,
        bool_predicates: list[str] | None = None,
        algorithm: str = "auto",
        alpha: float = 0.05,
        random_state: int = 42,
        query: dict | None = None,
        n_bootstrap: int = 0,
    ) -> str:
        """Run causal discovery (PC / FCI / GES / GRaSP / LiNGAM / NOTEARS)
        on a CSV-backed dataset and return a kernel_ast suggestion the agent
        can review, edit, then feed to ``themis_run``.

        Each emitted ``cause`` / ``bidirected`` edge carries
        ``annotations.source = "discovery:<algo>"`` so downstream the
        gap report flags them as algorithmic (not domain knowledge),
        and the orchestrator can ask the user to review the suggested
        graph before committing to identification.

        ``algorithm``: ``"pc"`` / ``"fci"`` / ``"ges"`` / ``"grasp"`` /
        ``"lingam"`` / ``"notears"`` / ``"auto"``. Use
        ``themis_discover_notears`` rather than this tool for NOTEARS unless
        the edges are all you want: this one returns a suggestion, and the
        certificate and the per-edge scale diagnostic do not fit inside one.
        ``auto`` runs a deterministic, reproducible selector
        over measured data properties (continuous + non-Gaussian + large
        N → LiNGAM; all-categorical → PC with a chi-square test; else PC
        with Fisher-Z) — the chosen algorithm, the CI test / score
        function, and the rationale are all recorded under
        ``extensions.discovery_metadata`` so the choice is auditable.
        ``bool_predicates``: column names to declare as bool domain
        (others must be filled in by the agent before themis_run will
        accept the suggestion).
        ``query``: optional pre-built query statement to embed.
        ``n_bootstrap``: if ``>0``, re-run the resolved algorithm on that
        many row-resamples and attach a per-edge stability score in
        ``[0, 1]`` as ``annotations.confidence`` — an unstable edge
        (low fraction) is a likely artefact worth reviewing. Costs one
        extra discovery run per resample; ``0`` (default) skips it.
        """
        import pandas as pd

        from themis.estimation.discovery import (
            as_algorithm_name,
            discover_graph,
            discovery_to_kernel_ast,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        # ``algorithm`` arrives over the wire as free-form text; the
        # discovery registry is keyed by a closed vocabulary, and
        # ``as_algorithm_name`` is where the one becomes the other.
        result = discover_graph(
            df, algorithm=as_algorithm_name(algorithm), alpha=alpha,
            random_state=random_state, n_bootstrap=n_bootstrap,
        )
        # A suggestion is a program to review, not an artifact any audit
        # is about, so it is handed over unaudited.
        return _hand_over(discovery_to_kernel_ast(
            result,
            bool_predicates=tuple(bool_predicates or ()),
            query=query,
        ), audit=False)

    @app.tool(structured_output=False)
    def themis_markov_blanket(
        csv_path: str,
        target: str,
        alpha: float = 0.05,
        columns: list[str] | None = None,
    ) -> str:
        """Find the Markov blanket of ``target`` in a continuous CSV dataset
        (borrow-list #4) and return a result the agent can review and audit
        with ``themis_verify_markov_blanket``.

        The Markov blanket is the minimal set of variables that shields the
        target from everything else — its parents, children, and children's
        other parents. It is a **local screening** primitive: it narrows dozens
        of columns to the handful locally relevant to the target for building a
        DAG. It is NOT an adjustment set — the blanket includes children and
        spouses, which must not be conditioned on when estimating the target's
        effect. A human still directs the local edges.

        Dispatches on data type: all-continuous → Fisher-Z (correlation matrix
        is the sufficient statistic); all-discrete (integer-coded / bool) →
        chi-square (joint contingency counts are the sufficient statistic).
        Either way the statistic is recorded so
        ``themis_verify_markov_blanket`` can independently recompute every test.
        Columns that mix continuous and discrete types raise an error (a mixed
        CI test is not implemented). ``columns`` optionally restricts the
        candidate pool; ``alpha`` is the CI-test significance level.
        """
        import pandas as pd

        from themis.estimation.discovery import (
            markov_blanket,
            markov_blanket_to_dict,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        result = markov_blanket(
            df, target,
            alpha=alpha,
            columns=tuple(columns) if columns else None,
        )
        return _hand_over(markov_blanket_to_dict(result))

    @app.tool(structured_output=False)
    def themis_discover_lagged_graph(
        csv_path: str,
        time: str,
        unit: str | None = None,
        columns: list[str] | None = None,
        max_lag: int = 3,
        alpha: float = 0.05,
    ) -> str:
        """Learn the LAGGED causal graph of a time series and return a result
        the agent can review and audit with
        ``themis_verify_lagged_discovery``.

        PCMCI (Runge et al. 2019): for each series, find its lagged parents,
        then test each candidate link conditioning on the target's parents AND
        the driver's own parents shifted back by the lag. That second half is
        what makes the p-value trustworthy when the series are autocorrelated,
        which is the usual case and the usual source of spurious links.

        ``time`` names the integer step column — a lag is a number of steps
        and only you know what one step is, so convert a date upstream.
        ``unit`` optionally names a panel identifier, and lags never cross
        from one unit into another. ``max_lag`` is the deepest link looked
        for, which is an assumption about the system: a link at a longer lag
        reaches the answer the way an unmeasured confounder does.

        Lagged links only. A contemporaneous link is neither sought nor
        represented, and where contemporaneous causation exists this can put a
        spurious lagged link in its place — so the result is a suggestion to
        review, like every discovery output, and the returned kernel_ast
        carries each edge as a time-indexed ``cause`` statement for you to
        accept, edit, or reject.
        """
        import pandas as pd

        from themis.estimation.lagged_discovery import (
            discover_lagged_graph,
            lagged_discovery_to_dict,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        result = discover_lagged_graph(
            df, time=time, unit=unit,
            columns=tuple(columns) if columns else None,
            max_lag=max_lag, alpha=alpha,
        )
        return _hand_over(lagged_discovery_to_dict(result))

    @app.tool(structured_output=False)
    def themis_discover_latent_lagged_graph(
        csv_path: str,
        time: str,
        unit: str | None = None,
        columns: list[str] | None = None,
        max_lag: int = 3,
        alpha: float = 0.05,
    ) -> str:
        """Learn the LAGGED graph of a time series without assuming that every
        common cause is in the data, and return a result the agent can review
        and audit with ``themis_verify_latent_lagged_discovery``.

        Use this rather than ``themis_discover_lagged_graph`` whenever an
        unrecorded driver is plausible — which is most observational series.
        That tool assumes causal sufficiency, and the assumption is not free:
        measured on 4000 steps at alpha=0.01, with a latent AR(1) driving two
        recorded series that have no link between them, it returns two lagged
        causes at p=0 and p=1.3e-15.

        What comes back per edge is one of three answers, and the third is an
        answer: ``tail`` says the driver is a cause, ``arrow`` says the two
        share something unrecorded and the driver is NOT a cause, and
        ``circle`` says it is one of those and this data does not settle
        which. Every mark that is not a circle names the triple that put it
        there.

        Same arguments, same scope, as the sufficiency-assuming tool: ``time``
        names the integer step column, ``unit`` optionally names a panel
        identifier and lags never cross between units, ``max_lag`` is the
        deepest link looked for. Lagged links only — which here is also what
        makes every edge time-ordered and therefore what the orientations rest
        on. The returned kernel_ast carries a settled cause as a time-indexed
        ``cause`` statement, a settled confounding as ``bidirected``, and an
        unsettled edge as an ambiguity for you to resolve rather than as
        either.
        """
        import pandas as pd

        from themis.estimation.latent_lagged_discovery import (
            discover_latent_lagged_graph,
            latent_lagged_discovery_to_dict,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        result = discover_latent_lagged_graph(
            df, time=time, unit=unit,
            columns=tuple(columns) if columns else None,
            max_lag=max_lag, alpha=alpha,
        )
        return _hand_over(latent_lagged_discovery_to_dict(result))

    @app.tool(structured_output=False)
    def themis_discover_notears(
        csv_path: str,
        columns: list[str] | None = None,
        l1: float = 0.1,
        threshold: float = 0.3,
    ) -> str:
        """Learn a weighted DAG by continuous optimisation (NOTEARS, Zheng et
        al. 2018) and return a result the agent can review and audit with
        ``themis_verify_notears_fit``.

        Separate from ``themis_discover`` because what comes back is a
        different kind of thing. That tool returns a kernel_ast suggestion —
        edges for a human to accept or reject. This returns a claim: at these
        weights, with this Gram matrix, the acyclicity residual is that, the
        objective is that, and the first-order residual is that, every one of
        them recomputable by something that never ran the solver.

        Two things travel with it that a bare edge list would not say. The
        certificate does NOT certify global optimality — the problem is not
        convex, and the residual says only that the returned point is nearly
        stationary. And the scale diagnostic says, PER EDGE, which edges
        survived re-running on standardised data: this family of methods is
        known to exploit the marginal variances (Reisach et al. 2021), so an
        edge that does not survive is one the units it was recorded in may
        have decided.

        ``l1`` is the sparsity penalty and ``threshold`` the absolute weight
        below which an entry is not reported as an edge — the two knobs, both
        recorded in the artifact, because the same weights read at a different
        threshold are a different graph.
        """
        import pandas as pd

        from themis.estimation.discovery import (
            discover_graph,
            notears_fit_to_dict,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        result = discover_graph(
            df, algorithm="notears",
            columns=tuple(columns) if columns else None,
            l1=l1, threshold=threshold,
        )
        return _hand_over(notears_fit_to_dict(result))

    @app.tool()
    def themis_verify_notears_fit(result: dict) -> dict:
        """Independently audit a NOTEARS fit.

        Parallel to ``themis_verify_markov_blanket``: the artifact is a
        standalone ``notears_fit`` dict (from ``themis_discover_notears``),
        not a query_result envelope, so ``themis_verify`` does not apply.
        A local optimum cannot be replayed step for step, so this does not
        re-run the solver — the objective and its gradient depend on the data
        only through the Gram matrix, which makes a d×d matrix a sufficient
        statistic for the whole problem, and every number the artifact asserts
        about its own solution is recomputed from it with a second
        transcription of the matrix exponential.
        """
        try:
            themis.verify_notears_fit(_as_artifact(result))
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_submit_verdict(
        verdict: str,
        question: str,
        justification: str | None = None,
        kernel_query_id: str | None = None,
    ) -> dict:
        """v0.1.5 Fix 2A — commit a binary verdict through a typed channel.

        Use AFTER ``themis_run`` when the user's question expects a
        binary answer (e.g. "does X cause Y?", "is the effect positive?",
        "if X hadn't happened, would Y differ?"). The verdict travels in
        a schema-validated tool argument, not in free text, so a
        token-level decoding artifact at the end of your reply cannot
        corrupt the answer downstream consumers (benchmark scoring,
        agent pipelines, audit logs) actually read.

        ``verdict`` must be one of ``"yes"`` / ``"no"`` /
        ``"needs_more_info"``. Any other value is rejected — there is
        no "almost yes" or "probably no" channel; if the kernel didn't
        give you enough to commit, return ``needs_more_info`` and use
        the free-text reply to explain what's missing.

        ``question``: the original NL question, copied verbatim (or
        first ~200 chars) so a downstream auditor can match the verdict
        to the asked thing without re-reading the full transcript.

        ``justification``: optional NL explanation, primarily for the
        audit trail. The user-facing explanation belongs in your reply,
        not here.

        ``kernel_query_id``: optional ``query_id`` from a prior
        ``themis_run`` result whose evidence backs this verdict. Lets
        downstream consumers cross-reference the typed answer to the
        structural / numeric evidence.

        For open-ended / numeric / "what is the effect" questions, do
        NOT call this tool — there is no binary verdict to commit.
        Reply in natural language directly.

        Returns an acknowledgment echoing the committed verdict. The
        MCP transcript itself is the persistent record.
        """
        allowed = ("yes", "no", "needs_more_info")
        if verdict not in allowed:
            raise ValueError(
                f"verdict must be one of {list(allowed)}, got {verdict!r}"
            )
        return {
            "ok": True,
            "verdict": verdict,
            "question_excerpt": (question or "")[:200],
            "justification": justification,
            "kernel_query_id": kernel_query_id,
        }

    @app.tool()
    def themis_list_resources() -> dict:
        """Catalog of available MCP resource URIs.

        Useful for clients that want to discover prompts/schemas
        without parsing the resource list themselves.
        """
        return {
            "prompts": [f"themis://prompts/{name}" for name in PROMPT_FILES],
            "schemas": [f"themis://schemas/{name}" for name in SCHEMAS],
        }

    # ============================================ resources

    def _make_text_reader(path: Path):
        def reader() -> str:
            return path.read_text(encoding="utf-8")
        return reader

    def _make_json_reader(path: Path):
        def reader() -> str:
            # Re-serialize through json to validate well-formedness.
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2)
        return reader

    for name in PROMPT_FILES:
        path = PROMPTS_DIR / name
        if not path.is_file():
            continue
        app.resource(
            f"themis://prompts/{name}",
            name=name,
            mime_type="text/markdown",
        )(_make_text_reader(path))

    for name, path in SCHEMAS.items():
        if not path.is_file():
            continue
        app.resource(
            f"themis://schemas/{name}",
            name=name,
            mime_type="application/json",
        )(_make_json_reader(path))

    return app


def main() -> None:
    """CLI entry point — runs the server over stdio (default MCP transport)."""
    app = build_server()
    app.run()


if __name__ == "__main__":
    main()
