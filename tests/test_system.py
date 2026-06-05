from app import system
from app.config import CONFIG


def test_ram_paper_cap_positive():
    assert system.ram_paper_cap() >= 50


def test_effective_cap_within_bounds():
    cap = system.effective_max_papers()
    assert 1 <= cap <= CONFIG["openalex"]["max_papers_cap"]


def test_mem_limit_positive():
    assert system._mem_limit_bytes() > 0


def test_metrics_keys_and_types():
    m = system.metrics()
    for k in ("cpu", "ram", "net_kbps", "ram_used_mb", "ram_total_mb"):
        assert k in m
    assert m["ram_total_mb"] > 0
    assert m["cpu"] >= 0
