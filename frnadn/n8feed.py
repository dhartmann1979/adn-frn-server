"""N8 Portal-Feed – Live-Zusammenfassung eines N8-Systems für die Portal-Seite des adn-frn-server.

Die Portal-Seite des adn-frn-server holt sich alle 30 Sekunden von HBlink4-FreeRadioID, N8 Crosslink, N8 Hotspot und
N8 Gateway eine kleine Zusammenfassung (Status, Kennzahlen, wer gerade spricht, zuletzt gehört), speichert sie in
SQLite zwischen und zeigt sie als Widgets am Rand. Diese Datei ist in allen N8-Systemen gleich.

Übertragung – Ende-zu-Ende verschlüsselt mit dem Sync-Schlüssel (zusätzlich zu HTTPS; der Schlüssel selbst reist nie):

    jede Anfrage und jede Antwort = b"N8PF1\\n" | salt (16) | nonce (16) | Geheimtext | tag (32)
    enc_key, mac_key = scrypt(Schlüssel, salt, 2^14, 8, 1)   (wie Master & Backup und die N8-Datensicherung)
    Geheimtext = JSON XOR SHAKE-256-Schlüsselstrom · tag = HMAC-SHA-256(mac_key, Kopf | Geheimtext)

    Anfrage  POST /api/n8/feed  {"path", "ts", "id", "data"}  – nur mit gültigem tag, für diesen Pfad, höchstens 5 min alt, einmal
    Antwort  {"id", "ts", "data": Zusammenfassung}             – muss die id der Anfrage tragen

Zusammenfassung (``summary()``):

    {"feed": 1, "system": "hblink4" | "crosslink" | "hotspot" | "gateway", "title", "version", "time",
     "status": "ok" | "warn" | "down", "status_text",
     "kpis":       [{"label", "value"}]                                   – höchstens 4
     "on_air":     [{"call", "name", "where"}]                            – wer gerade spricht
     "last_heard": [{"call", "name", "where", "ts", "duration"}]}         – höchstens 8, neueste zuerst

Keine IP-Adressen, keine Ports, keine Konten – nur, was die öffentliche Live-Seite auch zeigt.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import ssl
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

MAGIC = b"N8PF1\n"
PATH = "/api/n8/feed"
CTYPE = "application/x-n8-feed"
MAX_AGE = 300
MIN_KEY = 24
CHUNK = 1 << 20
SYSTEMS = ("hblink4", "crosslink", "hotspot", "gateway")


class FeedError(Exception):
    """Text is shown to the admin."""


def new_key() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- encryption
def _keys(secret: str, salt: bytes):
    k = hashlib.scrypt(secret.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024)
    return k[:32], k[32:]


def _xor(data: bytes, enc: bytes, nonce: bytes, i: int) -> bytes:
    ks = hashlib.shake_256(enc + nonce + i.to_bytes(8, "big")).digest(len(data))
    return (int.from_bytes(data, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(data), "big")


def seal(obj: Any, key: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(16)
    enc, mac = _keys(key, salt)
    plain = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    ct = b"".join(_xor(plain[o:o + CHUNK], enc, nonce, i) for i, o in enumerate(range(0, len(plain), CHUNK)))
    head = MAGIC + salt + nonce
    return head + ct + hmac.new(mac, head + ct, hashlib.sha256).digest()


def unseal(blob: bytes, key: str) -> Any:
    n = len(MAGIC)
    if not key or not isinstance(blob, (bytes, bytearray)) or len(blob) < n + 64 or blob[:n] != MAGIC:
        raise FeedError("not encrypted with the sync key")
    salt, nonce, ct, tag = blob[n:n + 16], blob[n + 16:n + 32], blob[n + 32:-32], blob[-32:]
    enc, mac = _keys(key, salt)
    if not hmac.compare_digest(tag, hmac.new(mac, blob[:n + 32] + ct, hashlib.sha256).digest()):
        raise FeedError("wrong sync key")
    plain = b"".join(_xor(ct[o:o + CHUNK], enc, nonce, i) for i, o in enumerate(range(0, len(ct), CHUNK)))
    try:
        return json.loads(plain)
    except ValueError:
        raise FeedError("broken message") from None


class Replay:
    """Request ids of the last minutes – a recorded request cannot be sent again."""
    def __init__(self) -> None:
        self.seen: Dict[str, float] = {}

    def check(self, msg: Dict[str, Any]) -> None:
        now = time.time()
        self.seen = {k: t for k, t in self.seen.items() if now - t < 2 * MAX_AGE}
        rid = str(msg.get("id") or "")
        if msg.get("path") != PATH or not rid or abs(now - float(msg.get("ts") or 0)) > MAX_AGE:
            raise FeedError("request expired or for another address – are the clocks right?")
        if rid in self.seen:
            raise FeedError("request already used")
        self.seen[rid] = now


# ---------------------------------------------------------------- the side that answers (HBlink4, Crosslink, Hotspot, Gateway)
def is_local(ip: str) -> bool:
    """LAN or this machine – N8 Hotspot and N8 Gateway answer only there."""
    try:
        a = ipaddress.ip_address((ip or "").split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return a.is_private or a.is_loopback or a.is_link_local


def answer_request(blob: bytes, key: str, replay: Replay, build) -> bytes:
    """Open the request (FeedError if not valid), build the summary with ``build()`` and seal the answer."""
    if not key or len(key) < MIN_KEY:
        raise FeedError("portal feed is off (no sync key set)")
    if len(blob or b"") > 64 * 1024:
        raise FeedError("too large")
    msg = unseal(blob, key)
    if not isinstance(msg, dict):
        raise FeedError("broken message")
    replay.check(msg)
    return seal({"id": msg.get("id"), "ts": time.time(), "data": build()}, key)


def _cut(v: Any, n: int = 60) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()[:n]


def summary(system: str, title: str, version: str, status: str = "ok", status_text: str = "",
            kpis: Optional[List] = None, on_air: Optional[List[Dict[str, Any]]] = None,
            last_heard: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    def person(d: Dict[str, Any], lh: bool) -> Dict[str, Any]:
        out = {"call": _cut(d.get("call"), 20), "name": _cut(d.get("name"), 40), "where": _cut(d.get("where"), 60)}
        if lh:
            try:
                out["ts"] = float(d.get("ts") or 0)
            except (TypeError, ValueError):
                out["ts"] = 0.0
            try:
                out["duration"] = round(float(d.get("duration") or 0), 1)
            except (TypeError, ValueError):
                out["duration"] = 0.0
        return out
    return {"feed": 1, "system": system if system in SYSTEMS else "other", "title": _cut(title, 80), "version": _cut(version, 30),
            "time": time.time(), "status": status if status in ("ok", "warn", "down") else "warn", "status_text": _cut(status_text, 120),
            "kpis": [{"label": _cut(k, 30), "value": _cut(v, 20)} for k, v in (kpis or [])][:4],
            "on_air": [person(x, False) for x in (on_air or [])][:4],
            "last_heard": [person(x, True) for x in (last_heard or [])][:8]}


def midnight(now: Optional[float] = None) -> float:
    lt = time.localtime(now)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def fmt_dur(s: float) -> str:
    s = int(s or 0)
    return f"{s // 3600} h {s % 3600 // 60:02d} min" if s >= 3600 else f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


# ---------------------------------------------------------------- the side that asks (portal of the adn-frn-server)
def fetch(url: str, key: str, timeout: float = 12, agent: str = "n8feed") -> Dict[str, Any]:
    """Ask a system for its summary. Raises FeedError with a readable reason."""
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://[A-Za-z0-9.\-\[\]:]+(/[A-Za-z0-9._~\-/]*)?$", url):
        raise FeedError("address: enter the dashboard address of the system, e.g. https://dmr.example.org")
    if not key:
        raise FeedError("no sync key set")
    rid = secrets.token_hex(16)
    body = seal({"path": PATH, "ts": time.time(), "id": rid, "data": {}}, key)
    req = urllib.request.Request(url + PATH, data=body, method="POST",
                                 headers={"X-N8": "1", "X-Dashboard": "1", "Content-Type": CTYPE, "Accept": CTYPE, "User-Agent": agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            raw = r.read(2 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read(4096) or b"{}")
            msg = msg.get("error") or msg.get("detail") or ""
        except ValueError:
            msg = ""
        if e.code in (401, 403):
            raise FeedError(f"refused: {msg or 'wrong sync key'}") from None
        if e.code in (404, 405):
            raise FeedError("the system does not know the portal feed yet – update it") from None
        raise FeedError(f"HTTP {e.code}{': ' + str(msg) if msg else ''}") from None
    except (urllib.error.URLError, OSError) as e:
        raise FeedError(f"not reachable ({getattr(e, 'reason', e)})") from None
    try:
        out = unseal(raw, key)
    except FeedError:
        raise FeedError("the answer is not encrypted with the sync key (wrong address or key?)") from None
    if not isinstance(out, dict) or out.get("id") != rid or not isinstance(out.get("data"), dict):
        raise FeedError("the answer does not belong to this request")
    return out["data"]
