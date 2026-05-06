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

from themis.web import llm_bridge
from themis.web.app import app


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
    with pytest.raises(llm_bridge.LLMBridgeError, match="unbalanced|no JSON"):
        llm_bridge._extract_first_json_object("{not balanced")


def test_extract_json_rejects_no_object():
    with pytest.raises(llm_bridge.LLMBridgeError, match="no JSON"):
        llm_bridge._extract_first_json_object("just plain text")


# ============================================ unit: client / key


def test_client_raises_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(llm_bridge.LLMBridgeError, match="API key"):
        llm_bridge._client(api_key=None)


def test_client_uses_explicit_key_over_env(monkeypatch):
    """Explicit api_key argument wins over env var."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from_env")
    # _client constructs an Anthropic instance — we can't easily probe
    # its key from outside, so just confirm no exception when explicit
    # key is given.
    c = llm_bridge._client(api_key="explicit_key")
    assert c is not None


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

    with pytest.raises(llm_bridge.LLMBridgeError, match="LLM refused"):
        llm_bridge.ask("某个上帝存在吗")


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
    assert "no JSON" in body["message"] or "parse" in body["message"]


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


def test_api_ask_missing_key_returns_400(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/ask", json={"nl": "x"})
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "nl_to_kernel_ast"
    assert "API key" in body["message"]
