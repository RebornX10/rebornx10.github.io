import app.ollama_client as oc
from tests.conftest import FakeResponse


def test_list_models(monkeypatch):
    monkeypatch.setattr(oc._SESSION, "get",
                        lambda *a, **k: FakeResponse(json_data={"models": [{"name": "llama3.2"}]}))
    assert oc.list_models() == ["llama3.2"]


def test_list_models_handles_error(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(oc._SESSION, "get", boom)
    assert oc.list_models() == []


def test_pick_model_uses_config(monkeypatch):
    monkeypatch.setitem(oc._OLLAMA, "model", "configured")
    assert oc.pick_model() == "configured"


def test_pick_model_first_installed(monkeypatch):
    monkeypatch.setitem(oc._OLLAMA, "model", None)
    monkeypatch.setattr(oc, "list_models", lambda: ["m1", "m2"])
    assert oc.pick_model() == "m1"


def test_pick_model_none(monkeypatch):
    monkeypatch.setitem(oc._OLLAMA, "model", None)
    monkeypatch.setattr(oc, "list_models", lambda: [])
    assert oc.pick_model() is None


def test_chat_returns_answer(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse(json_data={"message": {"content": " answer "}})

    monkeypatch.setattr(oc._SESSION, "post", fake_post)
    out = oc.chat("Q?", "context here", "llama3.2")
    assert out == "answer"
    assert captured["json"]["model"] == "llama3.2"
    assert "context here" in captured["json"]["messages"][0]["content"]


def test_embed_batch(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"], captured["json"] = url, json
        return FakeResponse(json_data={"embeddings": [[1.0, 2.0], [3.0, 4.0]]})

    monkeypatch.setattr(oc._SESSION, "post", fake_post)
    out = oc.embed(["a", "b"], "nomic-embed-text")
    assert out == [[1.0, 2.0], [3.0, 4.0]]
    assert captured["url"].endswith("/api/embed")
    assert captured["json"]["input"] == ["a", "b"]
