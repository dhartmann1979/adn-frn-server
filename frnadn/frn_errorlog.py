"""Public FRN error log of freeradionetwork.de – for analysing problems.

The FRN SystemManager writes every refused login of clients and servers there (wrong FRN password, multiple
connection, port not reachable …) – exactly the reasons the FRN server itself does not tell. Page: Help → error log on
freeradionetwork.de or PAGE directly. The page loads the latest entries as JSON {"log": "line\\nline…"} from URL.

Line format:
    2026-11-25 09:43:39 ERROR - Client [N8XLINK, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: …
    2026-11-25 09:43:44 ERROR - Server [frn.example.de:10024], DE, Request SC - multiple connections at the same time …
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.request

PAGE = "http://log.freeradionetwork.de:60080/error_log.php"
URL = PAGE + "?action=getLog"
LINE_RE = re.compile(r"^(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (?P<level>\w+) - (?P<kind>Server|Client) \[(?P<who>[^\]]*)\], "
                     r"(?P<country>[^,]*), Request (?P<request>\w+) - (?P<message>.*)$")
# known messages -> explanation and what to do
HINTS = [
    (r"wrong FRN password", "Wrong FRN password – request a password from the SystemManager (📧 Request FRN password) and enter exactly "
                            "the assigned password with the same e-mail and the same callsign/name."),
    (r"multiple connections", "Multiple connection: a connection with the same credentials is already active – is a second instance running "
                              "(old server, second server or a backup server with the same account)? Every FRN server needs its own account."),
    (r"not listening on specified port", "The SystemManager cannot reach the server on this address and port from the internet – check "
                                         "firewall and port forwarding (TCP) and the server address."),
    (r"blocked|banned|locked", "Access blocked – ask the operator of the FRN network."),
    (r"unknown|not registered|no account|not found", "Account unknown at the SystemManager – request a password or check the spelling of "
                                                     "e-mail, callsign and name."),
    (r"version", "Protocol version refused – update the FRN server/client."),
    (r"e-?mail", "E-mail address refused – use exactly the address of the FRN password."),
]
_cache: dict = {"t": 0.0, "entries": [], "error": ""}
CACHE_S = 60


def hint_for(message: str) -> str:
    for rx, text in HINTS:
        if re.search(rx, message, re.I):
            return text
    return ""


def parse(text: str) -> list[dict]:
    """Raw text or JSON answer -> entries (newest last)."""
    try:
        text = json.loads(text).get("log", "")
    except (ValueError, AttributeError):
        pass
    out = []
    for line in str(text).splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        e = m.groupdict()
        parts = [p.strip() for p in e["who"].split(",", 1)]
        e["id"] = parts[0]                                   # client: callsign, server: host:port
        e["name"] = parts[1] if len(parts) > 1 else ""
        e["message"], _, hint_en = e["message"].partition(" - Hint: ")
        e["message"] = e["message"].strip()
        e["hint_en"] = hint_en.strip(" !")
        e["hint"] = hint_for(e["message"])
        try:
            e["time"] = time.mktime(time.strptime(e["ts"], "%Y-%m-%d %H:%M:%S"))   # time of the log (CET like the SystemManager)
        except ValueError:
            e["time"] = 0
        out.append(e)
    return out


def _get(timeout: float) -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": "adn-frn-server (error analysis)", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 – fixed URL
        return r.read(1_000_000).decode("utf-8", "replace")


async def fetch(timeout: float = 8, force: bool = False) -> tuple[list[dict], str]:
    """Entries (cached CACHE_S seconds) and an error text if the log cannot be reached."""
    if not force and time.time() - _cache["t"] < CACHE_S:
        return _cache["entries"], _cache["error"]
    try:
        entries, err = parse(await asyncio.to_thread(_get, timeout)), ""
    except Exception as e:  # noqa: BLE001 – network errors are a finding, not a crash
        entries, err = _cache["entries"], f"FRN error log not reachable ({e.__class__.__name__}: {str(e)[:80]})"
    _cache.update(t=time.time(), entries=entries, error=err)
    return entries, err


def _host(s: str) -> str:
    return s.strip().lower().rstrip(".").split(":")[0]


def relevant(entries: list[dict], callsigns=(), hosts=()) -> list[dict]:
    """Entries concerning us: own client callsigns and own server addresses."""
    cs = {c.strip().upper() for c in callsigns if c and c.strip()}
    hs = {_host(h) for h in hosts if h and h.strip()}
    out = []
    for e in entries:
        if e["kind"] == "Client" and e["id"].upper() in cs:
            out.append({**e, "match": "client"})
        elif e["kind"] == "Server" and _host(e["id"]) in hs:
            out.append({**e, "match": "server"})
    return out


def summarize(entries: list[dict]) -> list[dict]:
    """Merge equal messages: per (kind, sender, message) count, first and last time."""
    groups: dict = {}
    for e in entries:
        k = (e["kind"], e["id"], e["message"])
        g = groups.setdefault(k, {**e, "count": 0, "first": e["ts"]})
        g["count"] += 1
        g["ts"], g["time"] = e["ts"], e["time"]
    return sorted(groups.values(), key=lambda g: g["time"], reverse=True)
