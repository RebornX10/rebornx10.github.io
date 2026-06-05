from __future__ import annotations

import time

import psutil

from app.config import CONFIG


def _cgroup_value(paths):
    for p in paths:
        try:
            v = open(p).read().strip()
        except OSError:
            continue
        if v and v != "max":
            try:
                n = int(v)
            except ValueError:
                continue
            if 0 < n < (1 << 62):
                return n
    return None


def _mem_limit_bytes() -> int:
    limit = _cgroup_value([
        "/sys/fs/cgroup/memory.max",
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",
    ])
    total = psutil.virtual_memory().total
    return min(limit, total) if limit else total


def _mem_used_bytes() -> int:
    used = _cgroup_value([
        "/sys/fs/cgroup/memory.current",
        "/sys/fs/cgroup/memory/memory.usage_in_bytes",
    ])
    return used if used is not None else psutil.virtual_memory().used


def ram_paper_cap() -> int:
    dl = CONFIG["download"]
    per_paper = max(0.05, dl.get("ram_per_paper_mb", 4)) * 1024 * 1024
    frac = dl.get("ram_fraction", 0.4)
    return max(50, int(_mem_limit_bytes() * frac / per_paper))


def effective_max_papers() -> int:
    return min(CONFIG["openalex"]["max_papers_cap"], ram_paper_cap())


def papers_for_target(done: int, baseline_used: int,
                      target_pct: float = 80.0, peak_factor: float = 2.0) -> int:
    """Estimate how many papers keep peak RAM <= target_pct, using the memory
    actually consumed so far (`done` papers since `baseline_used`). The save step
    roughly duplicates the corpus text, hence `peak_factor`. Falls back to the
    static cap when there's no measurement yet."""
    total = _mem_limit_bytes()
    grown = max(0, _mem_used_bytes() - baseline_used)
    if done <= 0 or grown <= 0:
        return effective_max_papers()
    per_paper = grown / done
    budget = total * (target_pct / 100.0) - baseline_used
    if budget <= 0:
        return max(1, done // 2)
    return max(1, int(budget / (per_paper * peak_factor)))


_net = {"t": None, "bytes": None}


def metrics() -> dict:
    cpu = psutil.cpu_percent(interval=None)
    total = _mem_limit_bytes()
    used = _mem_used_bytes()
    ram_pct = round(100 * used / total, 1) if total else 0.0

    recv = psutil.net_io_counters().bytes_recv
    now = time.monotonic()
    kbps = 0.0
    if _net["t"] is not None and now > _net["t"]:
        kbps = max(0.0, (recv - _net["bytes"]) / (now - _net["t"]) / 1024)
    _net["t"], _net["bytes"] = now, recv

    return {
        "cpu": round(cpu, 1),
        "ram": ram_pct,
        "ram_used_mb": round(used / 1024 / 1024),
        "ram_total_mb": round(total / 1024 / 1024),
        "net_kbps": round(kbps, 1),
    }
