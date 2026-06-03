import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("CONFIG_FILE", ROOT / "config.yaml"))

def _as_bool(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


_ENV_OVERRIDES = {
    "OPENALEX_MAILTO": (("openalex", "mailto"), str),
    "HOST": (("server", "host"), str),
    "PORT": (("server", "port"), int),
    "OPEN_BROWSER": (("server", "open_browser"), _as_bool),
    "WORKERS": (("download", "workers"), int),
    "OUTPUT_BASENAME": (("download", "output_basename"), str),
    "OLLAMA_URL": (("ollama", "url"), str),
    "OLLAMA_MODEL": (("ollama", "model"), str),
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
