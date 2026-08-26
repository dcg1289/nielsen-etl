"""Load project settings from settings.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.yaml"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = path or DEFAULT_SETTINGS_PATH

    with settings_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
