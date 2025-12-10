"""Speaking Stone Edge package."""

from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Only set missing keys so shell/env vars take precedence.
        if key and key not in os.environ:
            os.environ[key] = value


import os  # noqa: E402  (import after helper definition)

_load_env_file()
