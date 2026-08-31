"""Tests for the NL→AST→reply LLM bridge.

Anthropic SDK calls are stubbed via monkeypatch — no real API calls
in CI. The tests pin parsing and stage attribution; live API behavior
is the user's responsibility to verify when they paste a key.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from themis import language
from themis.web import llm_bridge
from themis.web.app import app
from themis.web.bridge_words import Bridge


client = TestClient(app)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _trivial_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause",
                       "from": _atom("x"), "to": _atom("y")}},
        ],
    }


def _make_message(text: str):
    """Mimic anthropic.types.Message.content = [TextBlock(...)]."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block])


# ============================================ unit: JSON extractor


def test_extract_json_handles_bare_object():
    text = '{"version": "0.1", "x": 1}'
    out = llm_bridge._extract_first_json_object(text)
    assert out == {"version": "0.1", "x": 1}


def test_extract_json_handles_fenced_block():
    text = 'here it is:\n```json\n{"a": 1}\n```'
    out = llm_bridge._extract_first_json_object(text)
    assert out == {"a": 1}


def test_extract_json_handles_leading_paragraph():
    text = "Here is the kernel_ast:\n{\"version\": \"0.1\"}"
    out = llm_bridge._extract_first_json_object(text)
    assert out == {"version": "0.1"}


def test_extract_json_rejects_unbalanced():
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge._extract_first_json_object("{not balanced")
    assert caught.value.species is Bridge.THE_JSON_NEVER_CLOSES


def test_extract_json_rejects_no_object():
    """Read off the species, not out of the sentence.

    Both of these used to be pinned with ``match=`` on ``str(exc)``, which
    is the wording — so the test held the class AND one language of it, and
    the way to make it pass was to keep writing English at the raise site.
    What the caller is entitled to is which of the eleven it was.
    """
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge._extract_first_json_object("just plain text")
    assert caught.value.species is Bridge.THE_REPLY_CARRIES_NO_JSON
    # And the occasion travels beside it, so a surface can say what was
    # there instead of JSON without the raise site having worded it.
    assert caught.value.said["reply"] == "just plain text"


def test_a_bridge_refusal_reads_the_same_thing_in_either_language():
    """The point of the species, measured rather than asserted about.

    One raise, two renderings, and the facts identical in both — which is
    what a sentence welded to its site cannot do, and the reason these were
    counted as debt rather than excused as internal.
    """
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge._extract_first_json_object("just plain text")
    exc = caught.value
    said = {
        lang: language.assemble(exc.species.words, exc.said, exc.words, lang)
        for lang in ("zh", "en")
    }
    assert said["zh"] != said["en"]
    assert all("just plain text" in text for text in said.values())


# ============================================ unit: client / key


def test_client_defaults_to_proxy(monkeypatch):
    """With no key set, the client points at the local proxy — the
    construction itself never raises, even when the proxy isn't running
    (connection errors surface later, on messages.create)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client_obj = llm_bridge._client(api_key=None)
    assert client_obj is not None
    assert "127.0.0.1:7777" in str(client_obj.base_url)


def test_client_uses_explicit_api_key(monkeypatch):
    """When an explicit ``sk-ant-api...`` key is given, talk to
    api.anthropic.com directly (no proxy hop)."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Importing themis.web.app (for the FastAPI test client) setdefault's
    # ANTHROPIC_BASE_URL to the proxy process-wide; clear it so the SDK's real
    # default (api.anthropic.com) applies on the explicit-key direct path.
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client_obj = llm_bridge._client(api_key="sk-ant-api-explicit")
    assert client_obj is not None
    assert "api.anthropic.com" in str(client_obj.base_url)


# ============================================ ask() pipeline (mocked)


def test_ask_full_pipeline_mocked(monkeypatch):
    """Mock both LLM calls to confirm ask() composes nl_to_kernel_ast,
    themis.run, and render_reply correctly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    program_json = _trivial_program()

    call_count = {"n": 0}

    def fake_messages_create(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: NL → kernel_ast
            import json as _json
            return _make_message(_json.dumps(program_json))
        else:
            # Second call: render reply
            return _make_message("一句话中文回复。")

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=fake_messages_create),
    )
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    out = llm_bridge.ask("我每天跑步会瘦吗")
    assert out["nl"] == "我每天跑步会瘦吗"
    assert out["kernel_ast"] == program_json
    assert "results" in out["envelope"]
    assert out["reply"] == "一句话中文回复。"
    assert call_count["n"] == 2


def test_ask_surfaces_llm_refusal(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: _make_message('{"error": "question is unfalsifiable"}')
        ),
    )
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.ask("某个上帝存在吗")
    assert caught.value.species is Bridge.THE_MODEL_DECLINED_THE_QUESTION
    assert caught.value.said["reason"] == "question is unfalsifiable"


# ============================================ /api/ask endpoint (mocked)


def test_api_ask_happy_path(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    program_json = _trivial_program()

    call_count = {"n": 0}
    def fake_create(**kwargs):
        call_count["n"] += 1
        import json as _json
        if call_count["n"] == 1:
            return _make_message(_json.dumps(program_json))
        return _make_message("回复：x 导致 y。")

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=fake_create),
    )
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    r = client.post("/api/ask", json={"nl": "x 导致 y 吗"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["nl"] == "x 导致 y 吗"
    assert body["kernel_ast"] == program_json
    assert body["reply"].startswith("回复")
    assert "results" in body["envelope"]


def test_api_ask_attributes_stage_on_failure(monkeypatch):
    """When the LLM emits invalid JSON, the API response carries the
    stage tag so the UI can render 'failed at NL→AST stage'."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: _make_message("not even close to JSON")
        ),
    )
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    r = client.post("/api/ask", json={"nl": "anything"})
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "nl_to_kernel_ast"
    # The reader's sentence is the SPECIES' now, in every language, and the
    # stage is what did not happen rather than what went wrong. It used to
    # be the stage's here with the bridge's own English underneath as the
    # diagnostic — which is one sentence for eleven ways of failing, and
    # the eleventh distinguished from the first only in a channel the
    # reader is not handed.
    assert body["words"] == dict(Bridge.THE_REPLY_CARRIES_NO_JSON.words)
    assert body["slots"]["reply"] == "not even close to JSON"


def test_api_ask_attributes_themis_run_failure(monkeypatch):
    """When LLM emits malformed kernel_ast, themis.run rejects — UI
    sees stage=themis_run plus the broken kernel_ast for debugging."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    fake_client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **kw: _make_message('{"version": "0.1"}')  # missing domain
        ),
    )
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    r = client.post("/api/ask", json={"nl": "anything"})
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "themis_run"
    assert body["kernel_ast"] == {"version": "0.1"}


def test_api_ask_transport_failure_blamed_on_nl_stage(monkeypatch):
    """A transport failure during the LLM call (proxy unreachable) is
    attributed to the nl_to_kernel_ast stage — not themis_run — so the UI
    can render where it broke. Mock the client so the test is deterministic
    and never opens a real socket: an earlier env-based version pointed at a
    closed port, which fast-refused in isolation but hung under full-suite
    connection-pool / ephemeral-port pressure."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def boom(**kw):
        raise ConnectionError("proxy unreachable")

    fake_client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: fake_client)

    r = client.post("/api/ask", json={"nl": "x"})
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "nl_to_kernel_ast"


# ============================================ propose_theta_priors (data-scarcity)


def _effect_program_missing_data():
    """X→Y with a confounder Z, an effect query, and NO θ supplied —
    structurally identifiable (backdoor {Z}) but blocked on missing
    distributions, so the kernel emits probability skeletons."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }


def _prob_skeleton(pred, val, given):
    return {
        "kind": "probability",
        "target": {"atom": _atom(pred), "value": val},
        "given": [{"atom": _atom(g), "value": v} for g, v in given],
        "value": None,
        "annotations": {"source": "TODO"},
    }


def test_propose_theta_priors_fills_skeletons(monkeypatch):
    """The bridge returns each skeleton with value filled, provenance set to
    'llm_prior', and the model's reason in annotations.source — ready for a
    parameter_fill_bundle."""
    import json as _json
    skeletons = [
        _prob_skeleton("y", True, [("x", True)]),
        _prob_skeleton("x", True, []),
    ]

    def fake_create(**kw):
        return _make_message(_json.dumps({"priors": [
            {"index": 0, "value": 0.7, "reason": "常识：约七成"},
            {"index": 1, "value": 0.3, "reason": "基线约三成"},
        ]}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    out = llm_bridge.propose_theta_priors({"version": "0.1"}, skeletons)
    assert [s["value"] for s in out] == [0.7, 0.3]
    assert all(s["provenance"] == "llm_prior" for s in out)
    assert out[0]["annotations"]["source"] == "常识：约七成"
    # Original target/given structure preserved untouched.
    assert out[0]["target"] == skeletons[0]["target"]


def test_propose_theta_priors_rejects_missing_index(monkeypatch):
    import json as _json
    skeletons = [_prob_skeleton("y", True, []), _prob_skeleton("x", True, [])]

    def fake_create(**kw):  # returns only index 0
        return _make_message(_json.dumps({"priors": [{"index": 0, "value": 0.5, "reason": "r"}]}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.propose_theta_priors({"version": "0.1"}, skeletons)
    assert caught.value.species is Bridge.A_PROBABILITY_GOT_NO_PRIOR
    assert caught.value.said["index"] == "1"


def test_propose_theta_priors_rejects_out_of_range(monkeypatch):
    import json as _json
    skeletons = [_prob_skeleton("y", True, [])]

    def fake_create(**kw):
        return _make_message(_json.dumps({"priors": [{"index": 0, "value": 1.7, "reason": "r"}]}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.propose_theta_priors({"version": "0.1"}, skeletons)
    assert caught.value.species is Bridge.A_PRIOR_IS_NOT_A_PROBABILITY


def test_propose_theta_priors_refuses_a_number_with_no_ground_under_it(
        monkeypatch):
    """A prior with no reason is refused rather than given one here.

    ``annotations.source`` is required non-empty on an ``llm_prior``, and
    the checker's own note says why: an empty one would let a fabricated
    number through with no disclosure. This bridge used to satisfy that by
    writing a constant into the field — which passes the check and
    discloses nothing, so the check was defeated by the layer it was
    guarding against rather than met.
    """
    import json as _json
    skeletons = [_prob_skeleton("y", True, [])]

    def fake_create(**kw):
        return _make_message(_json.dumps({"priors": [
            {"index": 0, "value": 0.5, "reason": "   "}]}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.propose_theta_priors({"version": "0.1"}, skeletons)
    assert caught.value.species is Bridge.A_PRIOR_CAME_WITH_NO_REASON


def test_the_reader_s_language_is_said_once_in_the_request(monkeypatch):
    """The counterexample to the frame's allowance being free.

    A prompt frame owes no second language BECAUSE the reader's is a
    parameter of the request. So the parameter has to arrive: the same call
    made for two readers differs, and it differs in the sentence naming the
    language rather than in the payload — which is what one document
    rendering every language means.
    """
    import json as _json
    seen: list[str] = []

    def fake_create(**kw):
        seen.append(kw["messages"][0]["content"])
        return _make_message(_json.dumps({"priors": [
            {"index": 0, "value": 0.5, "reason": "r"}]}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    for lang in ("zh", "en"):
        llm_bridge.propose_theta_priors(
            {"version": "0.1"}, [_prob_skeleton("y", True, [])], lang=lang)
    assert seen[0] != seen[1]
    for lang, sent in zip(("zh", "en"), seen):
        assert language.endonym(lang) in sent


def test_propose_theta_priors_empty_is_noop():
    assert llm_bridge.propose_theta_priors({"version": "0.1"}, []) == []


# ============================================ /api/assume endpoint (mocked)


def test_api_assume_happy_path(monkeypatch):
    """Data-scarce effect query → AI priors → point estimate + disclosure.
    The LLM is mocked to return a valid prior per index; the kernel does the
    real fill + re-run, so numerically_solved and the disclosure surface are
    the kernel's, not the mock's."""
    import json as _json
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")

    def fake_create(**kw):
        # Over-provide indices; propose_theta_priors reads only those it needs.
        priors = [{"index": i, "value": 0.5, "reason": f"先验 {i}"} for i in range(12)]
        return _make_message(_json.dumps({"priors": priors}))

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    r = client.post("/api/assume", json={"program": _effect_program_missing_data()})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "numerically_solved"
    assert res["numeric_result"]["value"] is not None
    review = res["extensions"]["llm_proposed_review"]
    assert len(review["probabilities"]) >= 1
    assert "summary" not in review  # counted by whoever renders it


def test_api_assume_nothing_to_assume(monkeypatch):
    """A query with no missing distributions (a cause query) → 400
    NothingToAssume, and the LLM is never called."""
    called = {"n": 0}

    def fake_create(**kw):
        called["n"] += 1
        return _make_message("{}")

    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: SimpleNamespace(messages=SimpleNamespace(create=fake_create)))

    r = client.post("/api/assume", json={"program": _trivial_program()})
    assert r.status_code == 400
    assert r.json()["stage"] == "nothing_to_assume"
    assert called["n"] == 0  # short-circuited before any LLM call
