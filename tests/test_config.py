from app import config


def test_config_has_all_sections():
    for section in ("server", "openalex", "download", "ollama", "retrieval", "theme"):
        assert section in config.CONFIG


def test_load_applies_env_override(monkeypatch, tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "server: {host: 127.0.0.1, port: 8000, open_browser: true}\n"
        "openalex: {mailto: a@b.com, per_page: 200, default_search: null,"
        " default_filters: null, max_papers: 25}\n"
        "download: {workers: 12, paper_deadline_s: 30, max_pdf_bytes: 1, connect_timeout: 5,"
        " read_timeout: 20, max_chars: 10, output_basename: papers}\n"
        "ollama: {url: http://localhost:11434, model: null, request_timeout: 300}\n"
        "retrieval: {top_k: 5, context_budget: 9000}\n"
        "theme: {anthropic_model: x}\n"
    )
    monkeypatch.setenv("WORKERS", "4")
    monkeypatch.setenv("PORT", "9999")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("OPEN_BROWSER", "false")
    monkeypatch.setenv("OUTPUT_BASENAME", "data/papers")
    data = config.load(cfg)
    assert data["download"]["workers"] == 4
    assert data["server"]["port"] == 9999
    assert data["server"]["host"] == "0.0.0.0"
    assert data["server"]["open_browser"] is False
    assert data["download"]["output_basename"] == "data/papers"


def test_load_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKERS", raising=False)
    data = config.load()
    assert isinstance(data["download"]["workers"], int)
