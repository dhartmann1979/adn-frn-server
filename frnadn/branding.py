"""Shared branding presets and validation for dashboard themes."""
from __future__ import annotations

import json
import re
from typing import Any, Dict

from . import n8theme

# colours of the profiles before 2.3 (only used to convert saved themes)
_OLD_PALETTES = {
    "midnight": {"accent": "#5ac8fa", "background": "#0b1224", "text": "#f5f7fb"},
    "ocean": {"accent": "#42d9c8", "background": "#071d28", "text": "#effbfa"},
    "forest": {"accent": "#84d98b", "background": "#101e17", "text": "#f2f8ef"},
    "sunset": {"accent": "#ff9f6e", "background": "#24130f", "text": "#fff4ee"},
    "violet": {"accent": "#bf5af2", "background": "#170e29", "text": "#f8f0ff"},
    "light": {"accent": "#0077cc", "background": "#edf3f8", "text": "#162331"},
}

# Colour profiles of N8 Theme 2 (shared with HBlink4-FreeRadioID and N8-HotSpot)
PALETTES: Dict[str, Dict[str, str]] = {k: {"name": v} for k, v in n8theme.PRESETS.items()}
DEFAULT_THEME = dict(n8theme.DEFAULT)
HEX = n8theme.HEX


def normalize_theme(value: Any, strict: bool = True) -> Dict[str, Any]:
    """Validated N8 Theme 2 object. Themes of version 2.2 ({preset, accent, page, panel, text}) are converted:
    page -> background, accent and text stay; the old solid panel colour is dropped (cards are glass now)."""
    if isinstance(value, str):
        value = {"accent": value}
    if not isinstance(value, dict):
        value = {}
    if "page" in value and "background" not in value:
        old_preset = value.get("preset", "")
        legacy = n8theme.LEGACY.get(str(value.get("preset", "")), str(value.get("preset", "n8")))
        value = {"preset": legacy, "accent": value.get("accent", ""), "background": value.get("page", ""),
                 "text": value.get("text", "")}
        # keep only colours that were changed against the old profile; the rest comes from the new profile
        old = _OLD_PALETTES.get(str(old_preset), {})
        value = {k: v for k, v in value.items() if k == "preset" or str(v).lower() != old.get(k, "")}
    try:
        return n8theme.normalize(value, strict=strict)
    except n8theme.ThemeError as e:
        raise ValueError(str(e))


def read_theme(db) -> Dict[str, str]:
    try:
        value = json.loads(db.kv_get("branding-theme", "{}"))
        return normalize_theme(value, strict=False)
    except (ValueError, TypeError, json.JSONDecodeError):
        return dict(DEFAULT_THEME)
