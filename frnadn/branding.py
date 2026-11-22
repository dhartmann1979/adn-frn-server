"""Shared branding presets and validation for dashboard themes."""
from __future__ import annotations

import json
import re
from typing import Any, Dict

PALETTES: Dict[str, Dict[str, str]] = {
    "midnight": {"name": "Midnight", "accent": "#5ac8fa", "page": "#0b1224", "panel": "#1c2740", "text": "#f5f7fb"},
    "ocean": {"name": "Ocean", "accent": "#42d9c8", "page": "#071d28", "panel": "#12333c", "text": "#effbfa"},
    "forest": {"name": "Forest", "accent": "#84d98b", "page": "#101e17", "panel": "#243b2a", "text": "#f2f8ef"},
    "sunset": {"name": "Sunset", "accent": "#ff9f6e", "page": "#24130f", "panel": "#3a211a", "text": "#fff4ee"},
    "violet": {"name": "Violet", "accent": "#bf5af2", "page": "#170e29", "panel": "#2a1a3d", "text": "#f8f0ff"},
    "light": {"name": "Light", "accent": "#0077cc", "page": "#edf3f8", "panel": "#ffffff", "text": "#162331"},
}
DEFAULT_THEME = {"preset": "midnight", **{k: v for k, v in PALETTES["midnight"].items() if k != "name"}}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_theme(value: Any) -> Dict[str, str]:
    """Validate a theme object. A legacy hex string is treated as an accent override."""
    if isinstance(value, str):
        value = {"preset": "midnight", "accent": value}
    if not isinstance(value, dict):
        value = {}
    preset = str(value.get("preset", "midnight"))
    if preset not in PALETTES:
        raise ValueError("Choose a known color preset.")
    clean = {"preset": preset}
    for key in ("accent", "page", "panel", "text"):
        raw = str(value.get(key, PALETTES[preset][key]))
        if not HEX.fullmatch(raw):
            raise ValueError(f"Invalid theme color: {key}.")
        clean[key] = raw.lower()
    return clean


def read_theme(db) -> Dict[str, str]:
    try:
        value = json.loads(db.kv_get("branding-theme", "{}"))
        return normalize_theme(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return dict(DEFAULT_THEME)
