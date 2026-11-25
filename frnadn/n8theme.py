"""
N8 Theme 2 – profiles and validation of the shared dashboard theme
(HBlink4-FreeRadioID, ADN FRN Server, N8-HotSpot; same file in all three, see n8-theme.js).

A theme is a dict; colours may be empty (= from the profile):
  preset, accent, accent2, background, glow1, glow2, glow3, text, panel,
  glow (0–150), glass (0–100), blur (bool), radius (0–28), font (N8 Theme 2.1)
"""
from __future__ import annotations

import re
from typing import Any, Dict

PRESETS: Dict[str, str] = {
    "n8": "N8 Night", "ocean": "Ocean", "aurora": "Aurora", "ember": "Ember",
    "violet": "Violet", "graphite": "Graphite", "daylight": "Daylight",
}
COLOR_KEYS = ("accent", "accent2", "background", "glow1", "glow2", "glow3", "text", "panel")
DEFAULT: Dict[str, Any] = {"preset": "n8", **{k: "" for k in COLOR_KEYS}, "glow": 100, "glass": 50, "blur": True, "radius": 22,
                           "font": "plex"}
# technical, well readable fonts, self-hosted next to n8-theme.js in fonts/ (see n8-theme.js)
FONTS: Dict[str, str] = {"plex": "IBM Plex Sans", "inter": "Inter", "barlow": "Barlow", "exo2": "Exo 2", "rajdhani": "Rajdhani",
                         "system": "System"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
# Profiles of older versions -> nearest N8 profile
LEGACY = {"midnight": "n8", "forest": "aurora", "sunset": "ember", "light": "daylight"}


class ThemeError(ValueError):
    """Message is shown to the user."""


def _num(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


def normalize(value: Any, strict: bool = False) -> Dict[str, Any]:
    """Validated theme. strict=True raises ThemeError on bad colours instead of dropping them."""
    if not isinstance(value, dict):
        value = {}
    preset = str(value.get("preset") or "n8")
    preset = LEGACY.get(preset, preset)
    if preset not in PRESETS:
        if strict:
            raise ThemeError("Unknown colour profile.")
        preset = "n8"
    out: Dict[str, Any] = {"preset": preset}
    for k in COLOR_KEYS:
        raw = str(value.get(k) or "").strip()
        if raw and not HEX.fullmatch(raw):
            if strict:
                raise ThemeError(f"{k}: colour must look like #12abef.")
            raw = ""
        out[k] = raw.lower()
    out["glow"] = _num(value.get("glow"), 0, 150, DEFAULT["glow"])
    out["glass"] = _num(value.get("glass"), 0, 100, DEFAULT["glass"])
    b = value.get("blur", True)
    out["blur"] = not (b is False or str(b).lower() in ("0", "false", "off", "no"))
    out["radius"] = _num(value.get("radius"), 0, 28, DEFAULT["radius"])
    out["font"] = value.get("font") if value.get("font") in FONTS else DEFAULT["font"]
    return out
