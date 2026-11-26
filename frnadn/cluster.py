"""Master & Backup: two FRN servers with the same configuration.

The **master** (e.g. frn.auf-der-nachtschicht.de) is where rooms, access lists, server lists and FRN accounts are edited.
The **backup** (e.g. frn-backup.auf-der-nachtschicht.de) fetches that configuration from the master – on a button press
and every full hour – so the two differ by at most one hour.

Failover itself is done by FRN: every server tells its clients a backup address (``backup_server_addr``); if the server
is gone, the clients connect there by themselves. With a role set, that address defaults to the partner's host.
For maintenance the master can hand over by hand: sync, stop the own FRN server (clients move to the backup), and later
take back: start again, then the backup restarts its FRN server so the stations come back to the master.

What is synced: rooms (with their netNN index), access lists, admin/mute/block lists, the FRN accounts (own password
list) and the ACL files of the Java server, plus the shared settings. Never synced (each server keeps its own): server
address and port, backup address, the FRN account of the server at the SystemManager (every server needs its own),
HTTPS, the dashboard users and this section.

Transport – end-to-end encrypted with the shared sync key (on top of HTTPS; the key itself never travels):

    every request and every answer = b"N8CL1\n" | salt (16) | nonce (16) | ciphertext | tag (32)
    enc_key, mac_key = scrypt(sync key, salt, 2^14, 8, 1) (same primitives as the N8 backup format, n8mig.py)
    ciphertext = JSON XOR SHAKE-256 key stream · tag = HMAC-SHA-256(mac_key, header | ciphertext)

    request  {"path", "ts", "id", "data"}   – accepted only with a valid tag, for this path, at most 5 min old and once
    answer   {"id", "ts", "data"}          – must carry the id of the request (no replay of old answers)

Who does not know the key can neither read the configuration (FRN accounts!) nor send a request.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import __version__, n8mig
from .settings import BY_KEY, FIELDS

FORMAT = "adn-frn-cluster"
SCHEMA = 1
MAGIC = b"N8CL1\n"
CTYPE = "application/x-n8-cluster"
MAX_AGE = 300
MIN_KEY = 24
TABLES = ("rooms", "room_access", "frn_lists", "frn_accounts")          # parents first
LOCAL_KEYS = {"frn.address", "frn.port", "frn.backup_host", "frn.backup_port", "sysman.email", "sysman.password", "portal.domain", "web.hosts"}
OPTIONAL_TABLES = ("news",)       # since 2.24: portal news go to the backup too (an older partner simply has none)
LOCAL_PREFIXES = ("https.", "cluster.", "mail.")
ACL_RE = re.compile(r"(AdminList|MuteList|BlockList|AccessList)\d{2}\.xml")
KV_RE = re.compile(r"acl-file-meta:(AdminList|MuteList|BlockList|AccessList)\d{2}\.xml")
TIMEOUT = 20
VOLATILE = {"frn_accounts": {"last_login"}}     # changes with every login – not a change of the configuration


class ClusterError(Exception):
    """Message is shown to the user."""


def shared_keys() -> List[str]:
    return [f.key for f in FIELDS if f.key not in LOCAL_KEYS and not f.key.startswith(LOCAL_PREFIXES)]


def new_key() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- encryption with the sync key
def seal(obj: Any, key: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(16)
    enc, mac = n8mig._keys(key, salt)
    plain = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    ct = b"".join(n8mig._xor(plain[o:o + n8mig.CHUNK], enc, nonce, i) for i, o in enumerate(range(0, len(plain), n8mig.CHUNK)))
    head = MAGIC + salt + nonce
    return head + ct + hmac.new(mac, head + ct, hashlib.sha256).digest()


def unseal(blob: bytes, key: str) -> Any:
    """Raises ClusterError if the data was not sealed with this key or was changed on the way."""
    n = len(MAGIC)
    if not key or not isinstance(blob, (bytes, bytearray)) or len(blob) < n + 32 + 32 or blob[:n] != MAGIC:
        raise ClusterError("not encrypted with the sync key")
    salt, nonce, ct, tag = blob[n:n + 16], blob[n + 16:n + 32], blob[n + 32:-32], blob[-32:]
    enc, mac = n8mig._keys(key, salt)
    if not hmac.compare_digest(tag, hmac.new(mac, blob[:n + 32] + ct, hashlib.sha256).digest()):
        raise ClusterError("wrong sync key")
    plain = b"".join(n8mig._xor(ct[o:o + n8mig.CHUNK], enc, nonce, i) for i, o in enumerate(range(0, len(ct), n8mig.CHUNK)))
    try:
        return json.loads(plain)
    except ValueError:
        raise ClusterError("broken message") from None


class Replay:
    """Request ids seen in the last minutes – a recorded request cannot be sent again."""
    def __init__(self):
        self.seen: Dict[str, float] = {}

    def check(self, msg: Dict[str, Any], path: str) -> None:
        now = time.time()
        self.seen = {k: t for k, t in self.seen.items() if now - t < 2 * MAX_AGE}
        rid = str(msg.get("id") or "")
        if msg.get("path") != path or not rid or abs(now - float(msg.get("ts") or 0)) > MAX_AGE:
            raise ClusterError("request expired or for another address – are the clocks of both servers right?")
        if rid in self.seen:
            raise ClusterError("request already used")
        self.seen[rid] = now


def open_request(blob: bytes, key: str, path: str, replay: Replay) -> Dict[str, Any]:
    if not key or len(key) < MIN_KEY:
        raise ClusterError("no sync key set on this server")
    msg = unseal(blob, key)
    if not isinstance(msg, dict):
        raise ClusterError("broken message")
    replay.check(msg, path)
    return msg


def answer(msg: Dict[str, Any], data: Any, key: str) -> bytes:
    return seal({"id": msg.get("id"), "ts": time.time(), "data": data}, key)


def peer_host(url: str) -> str:
    try:
        return urlparse(url or "").hostname or ""
    except ValueError:
        return ""


# ---------------------------------------------------------------- export (master) and content hash
def _rows(db, table: str) -> Dict[str, Any]:
    cols = [r[1] for r in db.q(f"PRAGMA table_info({table})")]
    rows = db.q(f"SELECT {', '.join(cols)} FROM {table} ORDER BY rowid")
    return {"columns": cols, "rows": [list(r) for r in rows]}


def _acl_files(acl_dir: Path) -> Dict[str, str]:
    out = {}
    for p in sorted(Path(acl_dir).glob("*.xml")):
        if ACL_RE.fullmatch(p.name):
            out[p.name] = p.read_text(encoding="utf-8", errors="replace")
    return out


def content(db, settings, acl_dir: Path) -> Dict[str, Any]:
    s = settings.all()
    kv = {r["key"]: r["value"] for r in db.q("SELECT key, value FROM kv WHERE key LIKE 'acl-file-meta:%'") if KV_RE.fullmatch(r["key"])}
    return {"settings": {k: s[k] for k in shared_keys()}, "tables": {t: _rows(db, t) for t in TABLES + OPTIONAL_TABLES},
            "kv": kv, "acl_files": _acl_files(acl_dir)}


def digest(c: Dict[str, Any]) -> str:
    """Same configuration → same hash, whatever the column order or version of the other side."""
    norm = {"settings": c.get("settings", {}), "kv": c.get("kv", {}), "acl_files": c.get("acl_files", {}), "tables": {}}
    for t, d in (c.get("tables") or {}).items():
        cols = d.get("columns") or []
        skip = VOLATILE.get(t, set())
        norm["tables"][t] = sorted(json.dumps({k: v for k, v in sorted(zip(cols, r)) if k not in skip}, sort_keys=True, default=str)
                                   for r in d.get("rows") or [])
    return hashlib.sha256(json.dumps(norm, sort_keys=True, default=str).encode()).hexdigest()


def export(db, settings, acl_dir: Path, title: str = "", store=None) -> Dict[str, Any]:
    if store is not None:          # every room gets its netNN index before it goes out
        store.invalidate()
        store.rooms()
    c = content(db, settings, acl_dir)
    counts = {t: len(c["tables"][t]["rows"]) for t in TABLES}
    return {"format": FORMAT, "schema": SCHEMA, "version": __version__, "time": time.time(), "title": title,
            "hash": digest(c), "counts": counts, **c}


# ---------------------------------------------------------------- apply (backup)
def apply(db, settings, store, acl_dir: Path, data: Dict[str, Any], who: str = "sync") -> Dict[str, Any]:
    """Take over the master's configuration. Returns {changed, counts, skipped}."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ClusterError("The partner did not send a configuration of adn-frn-server.")
    if int(data.get("schema") or 0) > SCHEMA:
        raise ClusterError(f"The master is newer (version {data.get('version')}) – update this server first.")
    tables = data.get("tables") or {}
    if any(t not in tables for t in TABLES):
        raise ClusterError("Incomplete configuration from the master.")
    counts = {t: len(tables[t].get("rows") or []) for t in TABLES}
    if counts["rooms"] == 0:
        raise ClusterError("The master sent no rooms – nothing taken over (protection against an empty master).")
    acl_dir = Path(acl_dir)
    local = content(db, settings, acl_dir)
    if digest(local) == digest(data):
        return {"changed": False, "frn_changed": False, "counts": counts, "skipped": []}
    # the Java server reads rooms, lists and accounts only at its start – does it need a restart?
    frn_changed = digest({"tables": {t: local["tables"][t] for t in TABLES}, "acl_files": local["acl_files"]}) != \
        digest({"tables": {t: tables[t] for t in TABLES}, "acl_files": data.get("acl_files") or {}})

    # 1) settings – one by one, an unknown or invalid value of the other version is skipped, not fatal
    skipped = []
    shared = set(shared_keys())
    for k, v in (data.get("settings") or {}).items():
        if k not in shared or k not in BY_KEY:
            continue
        try:
            settings.update({k: v}, who)
        except Exception:     # noqa: BLE001 – SettingsError and odd values of another version
            skipped.append(k)

    # 2) tables in one transaction (children are removed with the rooms – ON DELETE CASCADE)
    st: List[tuple] = [("DELETE FROM room_access", ()), ("DELETE FROM frn_lists", ()), ("DELETE FROM rooms", ()),
                       ("DELETE FROM frn_accounts", ())]
    opt = [t for t in OPTIONAL_TABLES if isinstance(tables.get(t), dict)]
    st += [(f"DELETE FROM {t}", ()) for t in opt]
    for t in TABLES + tuple(opt):
        mine = [r[1] for r in db.q(f"PRAGMA table_info({t})")]
        src = tables[t].get("columns") or []
        cols = [c for c in src if c in mine]
        idx = [src.index(c) for c in cols]
        sql = f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        for row in tables[t].get("rows") or []:
            st.append((sql, [row[i] for i in idx]))
    # 3) ACL meta of the Java server's files
    st.append(("DELETE FROM kv WHERE key LIKE 'acl-file-meta:%' OR key LIKE 'acl-file-sha:%'", ()))
    files = {n: t for n, t in (data.get("acl_files") or {}).items() if ACL_RE.fullmatch(n) and isinstance(t, str)}
    for k, v in (data.get("kv") or {}).items():
        if KV_RE.fullmatch(k):
            st.append(("INSERT INTO kv(key,value) VALUES(?,?)", (k, str(v))))
    for n, t in files.items():
        st.append(("INSERT INTO kv(key,value) VALUES(?,?)", (f"acl-file-sha:{n}", hashlib.sha256(t.encode("utf-8")).hexdigest())))
    db.tx(st)
    store.invalidate()

    # 4) ACL files – old ones are kept in acl/backups
    acl_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bdir = acl_dir / "backups"
    for p in acl_dir.glob("*.xml"):
        if ACL_RE.fullmatch(p.name) and files.get(p.name) != p.read_text(encoding="utf-8", errors="replace"):
            bdir.mkdir(parents=True, exist_ok=True)
            os.chmod(bdir, 0o700)
            shutil.copy2(p, bdir / f"{p.name}.{stamp}.sync.bak")
            if p.name not in files:
                p.unlink()
    for n, t in files.items():
        tmp = acl_dir / (n + ".tmp")
        tmp.write_text(t, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, acl_dir / n)
    return {"changed": True, "frn_changed": frn_changed, "counts": counts, "skipped": skipped}


# ---------------------------------------------------------------- talking to the partner
def call(url: str, path: str, key: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None,
         timeout: float = TIMEOUT) -> Dict[str, Any]:
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://[A-Za-z0-9.\-\[\]:]+$", url):
        raise ClusterError("Partner address: enter the dashboard address of the other server, e.g. https://frn-backup.example.org")
    if not key:
        raise ClusterError("No sync key set.")
    rid = secrets.token_hex(16)
    body = seal({"path": path, "ts": time.time(), "id": rid, "data": payload or {}}, key)
    req = urllib.request.Request(url + path, data=body, method="POST",
                                 headers={"X-N8": "1", "Content-Type": CTYPE, "Accept": CTYPE,
                                          "User-Agent": f"adn-frn-server/{__version__} (cluster)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            raw = r.read(64 * 1024 * 1024)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read(4096) or b"{}").get("error") or ""
        except ValueError:
            msg = ""
        if e.code in (401, 403):
            raise ClusterError(f"The partner refused: {msg or 'wrong sync key'} – the key must be the same on both servers.") from None
        if e.code in (404, 405):
            raise ClusterError("The partner does not know Master & Backup yet – update it to the same version.") from None
        raise ClusterError(f"Partner answered HTTP {e.code}{': ' + msg if msg else ''}.") from None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ClusterError(f"Partner {urlparse(url).hostname} not reachable ({reason}).") from None
    try:
        out = unseal(raw, key)
    except ClusterError:
        raise ClusterError("The answer of the partner is not encrypted with the sync key (wrong address or key?).") from None
    if not isinstance(out, dict) or out.get("id") != rid:
        raise ClusterError("The answer of the partner does not belong to this request.")
    return out.get("data") or {}


def next_full_hour(now: Optional[float] = None) -> float:
    now = time.time() if now is None else now
    return (int(now // 3600) + 1) * 3600
