from app import system
from app.config import CONFIG


def test_ram_paper_cap_positive():
    assert system.ram_paper_cap() >= 50


def test_effective_cap_within_bounds():
    cap = system.effective_max_papers()
    assert 1 <= cap <= CONFIG["openalex"]["max_papers_cap"]


def test_mem_limit_positive():
    assert system._mem_limit_bytes() > 0


def test_papers_for_target_fallback():
    # no measurement yet -> falls back to the static cap
    assert system.papers_for_target(0, 0) == system.effective_max_papers()


def test_papers_for_target_measured():
    # baseline of 0 means all current usage counts as "grown" -> a finite estimate
    n = system.papers_for_target(done=100, baseline_used=0, target_pct=80)
    assert n >= 1


def test_available_cpus_positive():
    assert system.available_cpus() >= 1


def test_worker_count_explicit(monkeypatch):
    monkeypatch.setitem(system.CONFIG["download"], "workers", 7)
    assert system.worker_count() == 7


def test_worker_count_auto_from_threads(monkeypatch):
    monkeypatch.setitem(system.CONFIG["download"], "workers", None)
    monkeypatch.setitem(system.CONFIG["download"], "thread_fraction", 0.5)
    monkeypatch.setattr(system, "available_cpus", lambda: 10)
    assert system.worker_count() == 5


def test_log_resources_runs():
    system.log_resources()  # must not raise


def test_metrics_keys_and_types():
    m = system.metrics()
    for k in ("cpu", "ram", "net_kbps", "ram_used_mb", "ram_total_mb"):
        assert k in m
    assert m["ram_total_mb"] > 0
    assert m["cpu"] >= 0
