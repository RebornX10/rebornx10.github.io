from __future__ import annotations

import logging
import os
import time

import psutil

from app.config import CONFIG

log = logging.getLogger("system")


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


def available_cpus() -> int:
    """Logical CPU threads available to this process, honouring container limits."""
    # cgroup v2: "<quota> <period>"
    try:
        quota, period = open("/sys/fs/cgroup/cpu.max").read().split()
        if quota != "max" and int(period) > 0:
            n = int(quota) / int(period)
            if n >= 1:
                return int(round(n))
    except (OSError, ValueError):
        pass
    # cgroup v1
    try:
        q = int(open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read())
        p = int(open("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read())
        if q > 0 and p > 0 and q / p >= 1:
            return int(round(q / p))
    except (OSError, ValueError):
        pass
    try:
        return len(os.sched_getaffinity(0))  # respects cpuset/affinity (Linux)
    except AttributeError:
        return os.cpu_count() or 1


def worker_count() -> int:
    """Download/parse workers: explicit config/env value, else ~thread_fraction of CPUs."""
    cfg = CONFIG["download"].get("workers")
    if cfg:
        return int(cfg)
    frac = CONFIG["download"].get("thread_fraction", 0.8)
    return max(1, round(available_cpus() * frac))


def log_resources() -> None:
    """Log the resource calculations (CPU/thread + RAM allocation) at startup."""
    dl = CONFIG["download"]
    cpus = available_cpus()
    cfg_w = dl.get("workers")
    if cfg_w:
        log.info("Threads: %d CPU threads available; workers=%d (explicit override)", cpus, int(cfg_w))
    else:
        frac = dl.get("thread_fraction", 0.8)
        log.info("Threads: %d CPU threads x %.0f%% -> %d workers", cpus, frac * 100, worker_count())

    total, used = _mem_limit_bytes(), _mem_used_bytes()
    log.info("RAM: total=%.2f GB, used=%.2f GB (%.1f%%)",
             total / 1e9, used / 1e9, 100 * used / total if total else 0)
    log.info("RAM cap: %.0f%% of %.2f GB / %.3f MB-per-paper -> %d papers",
             dl.get("ram_fraction", 0.85) * 100, total / 1e9,
             dl.get("ram_per_paper_mb", 0.1), ram_paper_cap())
    log.info("Paper cap: min(ceiling=%d, RAM=%d) -> effective=%d",
             CONFIG["openalex"]["max_papers_cap"], ram_paper_cap(), effective_max_papers())
    log.info("Guards: abort>%.0f%% RAM, suggest target=%.0f%%; max_chars=%d, max_pdf_bytes=%d",
             dl.get("ram_guard_pct", 85), dl.get("ram_target_pct", 80),
             dl.get("max_chars"), dl.get("max_pdf_bytes"))


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
