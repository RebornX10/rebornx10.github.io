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


def test_chat_sends_keep_alive_and_num_ctx(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse(json_data={"message": {"content": "x"}})

    monkeypatch.setitem(oc._OLLAMA, "keep_alive", "30m")
    monkeypatch.setitem(oc._OLLAMA, "num_ctx", 4096)
    monkeypatch.setattr(oc._SESSION, "post", fake_post)
    oc.chat("Q?", "ctx", "llama3.2")
    assert captured["json"]["keep_alive"] == "30m"
    assert captured["json"]["options"]["num_ctx"] == 4096


def test_extra_includes_num_predict_only_when_set(monkeypatch):
    monkeypatch.setitem(oc._OLLAMA, "num_predict", None)
    assert "num_predict" not in oc._extra().get("options", {})
    monkeypatch.setitem(oc._OLLAMA, "num_predict", 800)
    assert oc._extra()["options"]["num_predict"] == 800


def test_warm_model_loads_with_empty_prompt(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"], captured["json"] = url, json
        return FakeResponse(json_data={"response": ""})

    monkeypatch.setitem(oc._OLLAMA, "keep_alive", "30m")
    monkeypatch.setattr(oc._SESSION, "post", fake_post)
    oc.warm_model("llama3.2")
    assert captured["url"].endswith("/api/generate")
    assert captured["json"]["prompt"] == "" and captured["json"]["model"] == "llama3.2"
    assert captured["json"]["keep_alive"] == "30m"


def test_warm_model_noop_without_model(monkeypatch):
    monkeypatch.setattr(oc, "pick_model", lambda: None)
    called = {"n": 0}
    monkeypatch.setattr(oc._SESSION, "post", lambda *a, **k: called.update(n=called["n"] + 1))
    oc.warm_model()  # no model -> must not hit the network
    assert called["n"] == 0


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
