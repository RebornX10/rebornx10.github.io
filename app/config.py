import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("CONFIG_FILE", ROOT / "config.yaml"))

def _as_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


_ENV_OVERRIDES = {
    "OPENALEX_MAILTO": (("openalex", "mailto"), str),
    "MAX_PAPERS_CAP": (("openalex", "max_papers_cap"), int),
    "HOST": (("server", "host"), str),
    "PORT": (("server", "port"), int),
    "OPEN_BROWSER": (("server", "open_browser"), _as_bool),
    "LOG_LEVEL": (("server", "log_level"), str),
    "WORKERS": (("download", "workers"), int),
    "THREAD_FRACTION": (("download", "thread_fraction"), float),
    "OUTPUT_BASENAME": (("download", "output_basename"), str),
    "RAM_FRACTION": (("download", "ram_fraction"), float),
    "RAM_PER_PAPER_MB": (("download", "ram_per_paper_mb"), float),
    "RAM_GUARD_PCT": (("download", "ram_guard_pct"), float),
    "RAM_TARGET_PCT": (("download", "ram_target_pct"), float),
    "OLLAMA_URL": (("ollama", "url"), str),
    "OLLAMA_MODEL": (("ollama", "model"), str),
    "PARSE_IN_PROCESS": (("download", "parse_in_process"), _as_bool),
    "RERANK": (("retrieval", "rerank"), str),
    "EMBED_MODEL": (("retrieval", "embed_model"), str),
    "RERANK_K": (("retrieval", "rerank_k"), int),
    "MULTI_QUERY": (("retrieval", "multi_query"), _as_bool),
    "VERIFY": (("retrieval", "verify"), _as_bool),
}


def load(path=None):
    with open(path or CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    for env, (keys, cast) in _ENV_OVERRIDES.items():
        if env in os.environ:
            section, key = keys
            data.setdefault(section, {})[key] = cast(os.environ[env])
    return data


CONFIG = load()
