"""🧩 Widgets of the portal page: shown at the side, in an order the admins choose.

Two kinds:

* the own FRN server – „Today“, „Rooms“ and „Connect“ (built in, can be switched off and moved)
* other N8 systems – HBlink4-FreeRadioID, N8 Crosslink, N8 Hotspot and N8 Gateway. The portal asks each of them every
  ``portal.widget_interval`` seconds for a short summary (n8feed.py, encrypted with the sync key of that system) and keeps
  the answer in SQLite (table ``portal_widgets``). Visitors only ever get the cached copy – a slow or switched-off system
  never slows down the portal page. N8 Hotspot and N8 Gateway are asked only in the local network.
"""
from __future__ import annotations

import json
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import n8feed

BUILTIN = {"frn_today": "📊 Today", "frn_rooms": "🎙️ Rooms", "frn_connect": "📻 Connect"}
REMOTE = {"hblink4": "📡 HBlink4 DMR", "crosslink": "🔀 N8 Crosslink", "hotspot": "📶 N8 Hotspot", "gateway": "🛰️ N8 Gateway"}
LOCAL_ONLY = ("hotspot", "gateway")
KINDS = {**BUILTIN, **REMOTE}
STALE = 3                                   # missed answers (× interval) until a widget counts as stale


class WidgetError(Exception):
    """Shown to the admin."""


def ensure_builtin(db) -> None:
    """The three boxes of the own FRN server exist once – the first time in the order of before."""
    have = {r["kind"] for r in db.q("SELECT kind FROM portal_widgets")}
    pos = (db.q("SELECT COALESCE(MAX(position), -1) p FROM portal_widgets")[0]["p"] or 0) + 1 if have else 0
    for kind in BUILTIN:
        if kind not in have:
            db.x("INSERT INTO portal_widgets (kind, title, enabled, position, created_at) VALUES (?,?,?,?,?)",
                 (kind, "", 1, pos, time.time()))
            pos += 1


def _row(r, admin: bool) -> Dict[str, Any]:
    d = dict(r)
    try:
        d["data"] = json.loads(d["data"]) if d["data"] else None
    except ValueError:
        d["data"] = None
    d["builtin"] = d["kind"] in BUILTIN
    d["kind_label"] = KINDS.get(d["kind"], d["kind"])
    d["local_only"] = d["kind"] in LOCAL_ONLY
    d["key_set"] = bool(d.pop("key", ""))
    if not admin:
        for k in ("url", "key_set", "error", "fetched_at", "created_at", "local_only"):
            d.pop(k, None)
    return d


def list_all(db, admin: bool = True) -> List[Dict[str, Any]]:
    return [_row(r, admin) for r in db.q("SELECT * FROM portal_widgets ORDER BY position, id")]


def public(db, interval: int) -> List[Dict[str, Any]]:
    """What the portal page shows: enabled widgets in order; remote ones only with cached data."""
    out = []
    now = time.time()
    for w in list_all(db, admin=False):
        if not w["enabled"]:
            continue
        if not w["builtin"]:
            if not w["data"]:
                continue
            w["stale"] = not w.get("ok_at") or now - float(w["ok_at"]) > max(STALE * interval, 180)
            w["link"] = w["link"] or ""
            lh = w["data"].get("last_heard") or []
            w["data"]["last_heard"] = lh[:max(0, int(w["lh_count"]))] if w["show_lh"] else []
        out.append(w)
    return out


# ---------------------------------------------------------------- checks
def _host_is_local(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        try:
            return n8feed.is_local(host)
        except ValueError:
            return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(n8feed.is_local(a) for a in addrs)


def check_url(url: str, kind: str) -> str:
    url = (url or "").strip().rstrip("/")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise WidgetError("Address: the dashboard address of the system, e.g. https://dmr.example.org or http://192.168.1.20")
    if kind in LOCAL_ONLY and not _host_is_local(p.hostname):
        raise WidgetError(f"{REMOTE[kind]} is asked only in the local network – enter its LAN address (e.g. http://192.168.1.20).")
    return url


def _link(v: str) -> str:
    v = (v or "").strip()
    if v and not urlparse(v).scheme in ("http", "https"):
        raise WidgetError("Link: an address starting with https:// or http://")
    return v[:300]


def save(db, b: Dict[str, Any]) -> Dict[str, Any]:
    wid = int(b.get("id") or 0)
    old = db.q("SELECT * FROM portal_widgets WHERE id=?", (wid,)) if wid else []
    if wid and not old:
        raise WidgetError("This widget does not exist.")
    kind = old[0]["kind"] if old else str(b.get("kind") or "")
    if kind not in KINDS:
        raise WidgetError("Unknown widget.")
    if not old and kind in BUILTIN:
        raise WidgetError("This widget exists already.")
    title = str(b.get("title") or "").strip()[:80]
    enabled = 1 if b.get("enabled", True) else 0
    show_lh = 1 if b.get("show_lh", True) else 0
    try:
        lh_count = max(0, min(8, int(b.get("lh_count", 5))))
    except (TypeError, ValueError):
        lh_count = 5
    if kind in BUILTIN:
        db.x("UPDATE portal_widgets SET title=?, enabled=? WHERE id=?", (title, enabled, wid))
        return get(db, wid)
    url = check_url(str(b.get("url") or ""), kind)
    key = str(b.get("key") or "")
    if key in ("", "••••••••") and old:
        key = old[0]["key"]
    if len(key) < n8feed.MIN_KEY:
        raise WidgetError(f"Sync key: at least {n8feed.MIN_KEY} characters – “🎲 New key” creates one.")
    link = _link(str(b.get("link") or ""))
    if old:
        changed = (url, key) != (old[0]["url"], old[0]["key"])
        db.x("UPDATE portal_widgets SET title=?, url=?, key=?, link=?, enabled=?, show_lh=?, lh_count=?" +
             (", data='', ok_at=NULL, error=''" if changed else "") + " WHERE id=?",
             (title, url, key, link, enabled, show_lh, lh_count, wid))
        return get(db, wid)
    pos = db.q("SELECT COALESCE(MAX(position), -1) p FROM portal_widgets")[0]["p"] + 1
    cur = db.x("INSERT INTO portal_widgets (kind, title, url, key, link, enabled, position, show_lh, lh_count, created_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)", (kind, title, url, key, link, enabled, pos, show_lh, lh_count, time.time()))
    return get(db, cur.lastrowid)


def get(db, wid: int) -> Optional[Dict[str, Any]]:
    r = db.q("SELECT * FROM portal_widgets WHERE id=?", (wid,))
    return _row(r[0], True) if r else None


def delete(db, wid: int) -> None:
    r = db.q("SELECT kind FROM portal_widgets WHERE id=?", (wid,))
    if not r:
        raise WidgetError("This widget does not exist.")
    if r[0]["kind"] in BUILTIN:
        raise WidgetError("The widgets of the own FRN server cannot be deleted – switch them off.")
    db.x("DELETE FROM portal_widgets WHERE id=?", (wid,))


def order(db, ids: List[int]) -> None:
    have = [r["id"] for r in db.q("SELECT id FROM portal_widgets ORDER BY position, id")]
    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise WidgetError("Invalid order.") from None
    seq = [i for i in ids if i in have] + [i for i in have if i not in ids]
    db.tx([("UPDATE portal_widgets SET position=? WHERE id=?", (n, i)) for n, i in enumerate(seq)])


# ---------------------------------------------------------------- fetching (in a thread)
def fetch_one(db, wid: int, agent: str = "adn-frn-server") -> Dict[str, Any]:
    r = db.q("SELECT * FROM portal_widgets WHERE id=?", (wid,))
    if not r or r[0]["kind"] in BUILTIN:
        raise WidgetError("This widget does not fetch anything.")
    w = r[0]
    now = time.time()
    try:
        if w["kind"] in LOCAL_ONLY:
            check_url(w["url"], w["kind"])      # the address may have changed in the DNS
        data = n8feed.fetch(w["url"], w["key"], 12, agent)
        if data.get("feed") != 1:
            raise n8feed.FeedError("this is not a portal feed of an N8 system")
        db.x("UPDATE portal_widgets SET data=?, fetched_at=?, ok_at=?, error='' WHERE id=?",
             (json.dumps(data, ensure_ascii=False), now, now, wid))
        return {"ok": True, "data": data}
    except (n8feed.FeedError, WidgetError) as e:
        db.x("UPDATE portal_widgets SET fetched_at=?, error=? WHERE id=?", (now, str(e)[:300], wid))
        return {"ok": False, "error": str(e)}


def due(db) -> List[int]:
    return [r["id"] for r in db.q("SELECT id FROM portal_widgets WHERE enabled=1 AND kind NOT IN (%s) AND url!='' AND key!=''"
                                  % ",".join("?" * len(BUILTIN)), tuple(BUILTIN))]

