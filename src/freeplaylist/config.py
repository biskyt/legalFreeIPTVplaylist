"""Loading the YAML files in config/ and the JSON state kept between runs."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def load(name: str, config_dir: Path = CONFIG_DIR):
    """config/<name>.yaml, or an empty dict when the file is empty."""
    with open(config_dir / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
