"""Link menu of the dashboard header (same options as HBlink4-FreeRadioID).

Stored as ``<data>/branding/links.json``:

    {"enabled": true, "label": "🔗 Links", "style": "menu" | "bar",
     "items": [{"icon": "🌐", "site_icon": true, "label": "Website", "url": "https://…", "new_tab": true}, …]}

The older format (a plain list of ``{"label", "url"}``) is still read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

MAX_ITEMS = 20
STYLES = ("menu", "bar")
DEFAULT_ITEMS: List[Dict[str, Any]] = [
    {"icon": "📻", "label": "FreeRadioNetwork", "url": "https://freeradionetwork.de/", "new_tab": True},
    {"icon": "🌐", "label": "ADN FRN Server", "url": "https://github.com/dhartmann1979/adn-frn-server", "new_tab": True},
    {"icon": "🛰️", "label": "HBlink4-FreeRadioID", "url": "https://github.com/dhartmann1979/HBlink4-FreeRadioID", "new_tab": True},
]
DEFAULT: Dict[str, Any] = {"enabled": True, "label": "🔗 Links", "style": "menu", "items": DEFAULT_ITEMS}


def _url_ok(url: str) -> bool:
    """http(s) with a host, mailto:, a page anchor (#tab) or a path on this server (/…)."""
    if not url or len(url) > 500 or any(c in url for c in "\r\n\t "):
        return False
    if url.startswith("#"):
        return len(url) > 1
    if url.startswith("/") and not url.startswith("//"):
        return True
    p = urlsplit(url)
    if p.scheme in ("http", "https"):
        return bool(p.netloc)
    return p.scheme == "mailto" and bool(p.path)


def _flag(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def normalize(payload: Any) -> Dict[str, Any]:
    """Validate the admin form. Accepts the full object or just a list of items. Raises ValueError."""
    if isinstance(payload, list):
        payload = {"items": payload}
    if not isinstance(payload, dict):
        raise ValueError("Invalid link settings.")
    entries = payload.get("items", payload.get("links"))
    if not isinstance(entries, list) or len(entries) > MAX_ITEMS:
        raise ValueError(f"Please provide up to {MAX_ITEMS} links.")
    items = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ValueError("Each link needs a name and an address.")
        label, url = str(raw.get("label", "")).strip(), str(raw.get("url", "")).strip()
        if not label or len(label) > 50 or not _url_ok(url):
            raise ValueError("Name: 1–50 characters. Address: http://, https://, mailto:, #tab or /path.")
        item: Dict[str, Any] = {"label": label, "url": url}
        icon = str(raw.get("icon", "")).strip()
        if icon:
            item["icon"] = icon[:8]
        item["site_icon"] = _flag(raw.get("site_icon"), True)
        item["new_tab"] = _flag(raw.get("new_tab"), True)
        items.append(item)
    style = str(payload.get("style", "menu"))
    if style not in STYLES:
        raise ValueError("Display must be menu or bar.")
    return {"enabled": bool(payload.get("enabled", True)), "label": (str(payload.get("label", "")).strip()[:30] or "🔗 Links"),
            "style": style, "items": items}


def read(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT))
    try:
        return normalize(data)
    except ValueError:
        return json.loads(json.dumps(DEFAULT))


def write(path: Path, cfg: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
