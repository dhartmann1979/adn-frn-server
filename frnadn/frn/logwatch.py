"""
Live state of the Java FRN server, read from its two log files:

  logs/server.log           logins (CTRequest with e-mail and type), CONNECT/DISCONNECT,
                            voice start/stop with duration, text messages, errors
  logs/server_clients.log   "Logger2": the complete client list of a room after every change
                            (<net>, <rid>, <on>, <bc>, <cty>, <ctry>, <dscr>, <st>, <mt>, <spk>)

server_clients.log was added by the author of the Java server exactly for this purpose
(own client list displays). server.log brings the details that list does not have.
Both files are written by our own log4j.xml (see javasrv.py) and rotate; the reader
follows the rotation.
"""
from __future__ import annotations

import asyncio
import collections
import html
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

log = logging.getLogger("frnadn.frn")

LINE_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3})\s+(?:(\w+)\s+)?-\s(.*)$")
CLIENT_RE = re.compile(r"^\{(.*?) \[(.*)\]\}: (.*)$")
CT_KEYS = ("version", "email_address", "password", "operator_name", "client_type", "band_channel", "description", "country",
           "city", "network")
CT_RE = re.compile(r"(\w+)=(.*?)(?=, (?:%s)=|$)" % "|".join(CT_KEYS))
RESP_RE = re.compile(r"server response: AL=(\w+), NT=(.*?), ID=(.*?), MT=")
STOP_RE = re.compile(r"Voice transmission stopped\.\s*(?:(\d+)m)?(?:(\d+)s)?(?:(\d+)ms)?")
TM_RE = re.compile(r"TMRequest \[id=(.*?), message=(.*)\]$")
L2_RE = re.compile(r"<net>(.*?)</net><rid>(\d+)</rid><on>(.*?)</on><bc>(.*?)</bc><cty>(.*?)</cty><ctry>(.*?)</ctry>"
                   r"<dscr>(.*?)</dscr><st>(.*?)</st><mt>(.*?)</mt><spk>(.*?)</spk>")
SYSMAN_ERRORS = {
    "4": "SystemManager: wrong credentials – check the FRN account e-mail and password",
    "5": "SystemManager: this server is not reachable from the internet – check server address, port forwarding and firewall",
    "6": "SystemManager: server version too old – install the update",
    "7": "SystemManager: access denied",
    "8": "SystemManager: this address and port are already used by another FRN server",
    "9": "SystemManager: the same credentials are already online on another server",
}
STATUS = {"qrv": 0, "qrl": 1, "qrt": 2}
CL_CROSSLINK, CL_GATEWAY, CL_PCONLY = 0, 1, 2


def fix_text(s: str) -> str:
    """Clients that send UTF-8 where the server expects Latin-1 show up as "MÃ¼nchen": repair that."""
    if "Ã" in s or "Â" in s:
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


def parse_ts(date: str, ms: str) -> float:
    try:
        return datetime.strptime(date, "%Y-%m-%d %H:%M:%S").timestamp() + int(ms) / 1000
    except ValueError:
        return time.time()


def split_on(on: str) -> Tuple[str, str]:
    call, _, name = (on or "").partition(",")
    return call.strip().upper(), name.strip()


def type_of_band(band: str) -> int:
    b = (band or "").strip().lower()
    if b in ("pc only", "pc-only", "pconly", "parrot", ""):
        return CL_PCONLY
    if b.startswith("crosslink"):
        return CL_CROSSLINK
    return CL_GATEWAY


@dataclass(eq=False)
class LClient:
    on: str
    callsign: str = ""
    name: str = ""
    email: str = ""
    cid: str = ""
    client: int = CL_PCONLY
    band: str = ""
    descr: str = ""
    country: str = ""
    city: str = ""
    peer: str = ""
    access: str = "OK"
    muted: bool = False
    status: int = 0
    joined: float = field(default_factory=time.time)
    is_parrot: bool = False

    def public(self) -> Dict[str, Any]:
        return {"callsign": self.callsign, "name": self.name, "client": self.client, "band": self.band, "descr": self.descr,
                "country": self.country, "city": self.city, "cid": self.cid or self.on, "status": self.status, "muted": self.muted,
                "since": self.joined, "access": self.access, "parrot": self.is_parrot}


@dataclass(eq=False)
class RoomState:
    name: str
    id: int
    cfg: Dict[str, Any]
    clients: List[LClient] = field(default_factory=list)
    talker: Optional[LClient] = None
    talk_start: float = 0.0
    talk_id: Optional[int] = None

    def find(self, on: str) -> Optional[LClient]:
        return next((c for c in self.clients if c.on == on), None)


class Tail:
    """Follows a log file across rotation (rename + new file) and truncation."""

    def __init__(self, path: Path):
        self.path = path
        self.f = None
        self.ino = None
        self.buf = ""

    def open(self, at_end: bool) -> None:
        try:
            self.f = open(self.path, "r", encoding="utf-8", errors="replace")
            st = os.fstat(self.f.fileno())
            self.ino = st.st_ino
            if at_end:
                self.f.seek(0, os.SEEK_END)
        except FileNotFoundError:
            self.f, self.ino = None, None

    def lines(self) -> List[str]:
        out: List[str] = []
        if self.f is None:
            self.open(False)
            if self.f is None:
                return out
        chunk = self.f.read()
        if chunk:
            self.buf += chunk
        try:
            st = os.stat(self.path)
            if st.st_ino != self.ino or st.st_size < self.f.tell():
                rest = self.f.read()
                if rest:
                    self.buf += rest
                self.f.close()
                self.open(False)
        except FileNotFoundError:
            pass
        if "\n" in self.buf:
            *full, self.buf = self.buf.split("\n")
            out = [x.rstrip("\r") for x in full]
        return out

    def close(self) -> None:
        if self.f:
            self.f.close()
            self.f = None


class LogWatch:
    """Feeds the dashboard (sink = Live) from the logs of the Java FRN server."""

    def __init__(self, store, sink, home: Path, java):
        self.store = store
        self.sink = sink
        self.home = Path(home)
        self.java = java                       # JavaServer (status, version)
        self.rooms: Dict[str, RoomState] = {}
        self.pending: Dict[str, Dict[str, Any]] = {}        # operator name -> CTRequest details
        self.ips: Deque[str] = collections.deque(maxlen=50)
        self.listen: List[str] = []
        self.started: Optional[float] = None
        self.error = ""
        self.error_ts = 0.0
        self.version = ""
        self.service = "unknown"
        self.restarts = 0
        self._task: Optional[asyncio.Task] = None
        self._tails: List[Tuple[Tail, Any]] = []
        self.reload_rooms()

    # ------------------------------------------------------------ rooms
    def reload_rooms(self) -> None:
        rows = {r["name"]: r for r in self.store.rooms() if r["enabled"]}
        for name in list(self.rooms):
            if name not in rows:
                for c in list(self.rooms[name].clients):
                    self.sink.left(name, c, "room closed")
                del self.rooms[name]
        for name, row in rows.items():
            if name in self.rooms:
                self.rooms[name].cfg = row
                self.rooms[name].id = row["idx"] if row["idx"] is not None else 99
            else:
                self.rooms[name] = RoomState(name, row["idx"] if row["idx"] is not None else 99, row)
        self.rooms = dict(sorted(self.rooms.items(), key=lambda kv: (kv[1].cfg.get("position", 0), kv[1].id)))

    def _room(self, name: str) -> RoomState:
        r = self.rooms.get(name)
        if r is None:                          # a room the server knows but the database not (yet)
            r = self.rooms[name] = RoomState(name, 99, {"name": name, "hidden": 0, "tot": 0, "parrot": 0})
        return r

    # ------------------------------------------------------------ state for the dashboard
    def state(self) -> Dict[str, Any]:
        # SystemManager errors are upstream warnings, not proof that the Java process stopped.
        running = self.service == "active" and bool(self.listen)
        return {"running": running, "service": self.service, "started": self.started, "listen": self.listen,
                "error": self.error, "warning": self.error, "version": self.version, "restarts": self.restarts,
                "clients": sum(1 for r in self.rooms.values() for c in r.clients if not c.is_parrot)}

    def _state_changed(self) -> None:
        self.sink.server_state(self.state())

    async def poll_service(self) -> None:
        try:
            st = await self.java.status()
        except Exception:                      # pragma: no cover
            return
        old = (self.service, self.restarts)
        self.service, self.restarts = st.get("active", "unknown"), st.get("restarts", 0)
        if self.service != "active" and old[0] == "active":
            self._server_gone("server stopped")
        if (self.service, self.restarts) != old:
            self._state_changed()

    def _server_gone(self, reason: str) -> None:
        for r in self.rooms.values():
            if r.talker:
                self._talk_end(r, time.time(), None)
            for c in list(r.clients):
                self.sink.left(r.name, c, reason)
            r.clients.clear()
        self.listen = []

    # ------------------------------------------------------------ start / stop
    async def start(self) -> None:
        logs = self.home / "logs"
        self._seed(logs)
        main, clients = Tail(logs / "server.log"), Tail(logs / "server_clients.log")
        main.open(True)
        clients.open(True)
        self._tails = [(main, self.feed_main), (clients, self.feed_clients)]
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        for t, _ in self._tails:
            t.close()

    async def _loop(self) -> None:
        n = 0
        while True:
            try:
                if n % 33 == 0:
                    await self.poll_service()
                for t, fn in self._tails:
                    lines = t.lines()
                    if lines:
                        fn(lines)
            except Exception:
                log.exception("log watch")
            n += 1
            await asyncio.sleep(0.3)

    def _seed(self, logs: Path) -> None:
        """After a start of the dashboard: the last client list of every room, unless the server restarted since."""
        start_ts = 0.0
        try:
            for line in (logs / "server.log").read_text(encoding="utf-8", errors="replace").splitlines():
                m = LINE_RE.match(line)
                if not m:
                    continue
                msg = m.group(4)
                if msg.startswith("server started at"):
                    start_ts = parse_ts(m.group(1), m.group(2))
                    self.started = start_ts
                    self.error = ""
                self._meta(msg, m.group(3) or "", parse_ts(m.group(1), m.group(2)))
        except FileNotFoundError:
            pass
        last: Dict[str, Tuple[int, float, List[Tuple]]] = {}
        try:
            for line in (logs / "server_clients.log").read_text(encoding="utf-8", errors="replace").splitlines():
                m = LINE_RE.match(line)
                e = L2_RE.search(fix_text(line)) if m else None
                if not e:
                    continue
                ts, rid = parse_ts(m.group(1), m.group(2)), int(e.group(2))
                net = html.unescape(e.group(1))
                cur = last.get(net)
                if cur is None or cur[0] != rid:
                    last[net] = (rid, ts, [])
                last[net][2].append(e.groups())
        except FileNotFoundError:
            pass
        for net, (rid, ts, rows) in last.items():
            if ts + 1 < start_ts:
                continue
            room = self._room(net)
            for g in rows:
                if g[2] == "null":
                    continue
                c = self._client_from_l2(g, ts)
                room.clients.append(c)
                self.sink.joined(room.name, c)

    # ------------------------------------------------------------ server_clients.log
    def _client_from_l2(self, g: Tuple, ts: float) -> LClient:
        on = html.unescape(g[2])
        call, name = split_on(on)
        band = html.unescape(g[3])
        p = self.pending.get(on, {})
        if band == "Parrot":
            call, name = "Parrot", on
        return LClient(on=on, callsign=call, name=name, band=band, city=html.unescape(g[4]), country=html.unescape(g[5]),
                       descr=html.unescape(g[6]), status=STATUS.get(g[7], 0), muted=g[8] == "1", joined=ts,
                       client=p.get("client", type_of_band(band)), email=p.get("email", ""), peer=p.get("peer", ""),
                       is_parrot=band == "Parrot")

    def feed_clients(self, lines: List[str]) -> None:
        groups: Dict[str, Tuple[int, float, List[Tuple]]] = {}
        for line in lines:
            m = LINE_RE.match(line)
            e = L2_RE.search(fix_text(line)) if m else None
            if not e:
                continue
            net, rid, ts = html.unescape(e.group(1)), int(e.group(2)), parse_ts(m.group(1), m.group(2))
            cur = groups.get(net)
            if cur is None or cur[0] != rid:
                groups[net] = (rid, ts, [])
            groups[net][2].append(e.groups())
        for net, (rid, ts, rows) in groups.items():
            room = self._room(net)
            seen = set()
            changed = False
            for g in rows:
                if g[2] == "null":
                    continue
                on = html.unescape(g[2])
                seen.add(on)
                c = room.find(on)
                if c is None:
                    c = self._client_from_l2(g, ts)
                    room.clients.append(c)
                    self.sink.joined(room.name, c)
                    changed = True
                    continue
                muted, status = g[8] == "1", STATUS.get(g[7], c.status)
                if (muted, status) != (c.muted, c.status):
                    c.muted, c.status = muted, status
                    changed = True
            for c in list(room.clients):          # missed a disconnect: gone from the list for a while
                if c.on not in seen and c.joined < ts - 3:
                    self._leave(room, c, "gone")
                    changed = True
            if changed:
                self.sink.updated(room.name)

    # ------------------------------------------------------------ server.log
    def _meta(self, msg: str, level: str, ts: float) -> bool:
        """Server-wide lines. True if the state changed."""
        m = re.match(r"server listening on port (\d+)", msg)
        if m:
            port = m.group(1)
            if port not in self.listen:
                self.listen.append(port)
            return True
        if msg.startswith("server started at"):
            self.started, self.error = ts, ""
            return True
        m = re.search(r"Java FRN_Server V ([\d.]+) Build \[([\d.]+)\]", msg)
        if m:
            self.version = f"{m.group(1)} ({m.group(2)})"
            return True
        m = re.search(r"[Ee]rror\s*-(\d)\b", msg)
        if m and m.group(1) in SYSMAN_ERRORS:
            self.error, self.error_ts = SYSMAN_ERRORS[m.group(1)], ts
            return True
        if level == "ERROR" and ("Sysman" in msg or "sysman" in msg) and "DSS" not in msg:
            self.error, self.error_ts = "SystemManager: " + msg[:200], ts
            return True
        if "Operating" in msg or ("SC request" in msg and "AL=0" in msg):
            if self.error.startswith("SystemManager"):
                self.error = ""
                return True
        return False

    def feed_main(self, lines: List[str]) -> None:
        state_changed = False
        for line in lines:
            m = LINE_RE.match(line)
            if not m:
                continue
            ts, level, msg = parse_ts(m.group(1), m.group(2)), m.group(3) or "", fix_text(m.group(4))
            try:
                if msg.startswith("server started at"):
                    self._server_gone("server restart")
                    self.listen = []
                if self._meta(msg, level, ts):
                    state_changed = True
                    continue
                if msg.startswith("socket connect from ip "):
                    self.ips.append(msg.rsplit(" ", 1)[-1])
                    continue
                if msg.startswith("CTRequest ["):
                    d = dict(CT_RE.findall(msg[len("CTRequest ["):].rstrip("]")))
                    on = d.get("operator_name", "")
                    try:
                        ctype = int(d.get("client_type", "2"))
                    except ValueError:
                        ctype = CL_PCONLY
                    self.pending[on] = {"email": d.get("email_address", "").lower(), "client": ctype,
                                        "band": d.get("band_channel", ""), "descr": d.get("description", ""),
                                        "country": d.get("country", ""), "city": d.get("city", ""), "room": d.get("network", ""),
                                        "peer": self.ips.popleft() if self.ips else "", "ts": ts}
                    if len(self.pending) > 500:
                        for k in list(self.pending)[:100]:
                            self.pending.pop(k, None)
                    continue
                c = CLIENT_RE.match(msg)
                if c:
                    self._client_line(c.group(1), c.group(2), c.group(3), ts)
            except Exception:
                log.exception("log line: %s", line)
        if state_changed:
            self._state_changed()

    def _client_line(self, room_name: str, on: str, rest: str, ts: float) -> None:
        m = RESP_RE.match(rest)
        if m:
            p = self.pending.setdefault(on, {})
            p.update(access=m.group(1), cid=m.group(3).strip(), room=m.group(2) or room_name)
            if m.group(1) in ("WRONG", "BLOCK"):
                call, _ = split_on(on)
                self.sink.denied({"callsign": call, "email": p.get("email", ""), "room": room_name},
                                 "wrong password" if m.group(1) == "WRONG" else "blocked", p.get("peer", ""))
            return
        if rest.startswith(">>> CLIENT CONNECT"):
            room = self._room(room_name)
            p = self.pending.get(on, {})
            c = room.find(on)
            call, name = split_on(on)
            new = c is None
            if new:
                c = LClient(on=on, callsign=call, name=name, joined=ts)
                room.clients.append(c)
            c.email, c.peer, c.cid = p.get("email", c.email), p.get("peer", c.peer), p.get("cid", c.cid)
            c.access, c.client = p.get("access", c.access), p.get("client", c.client)
            c.band = p.get("band") or c.band
            c.descr, c.country, c.city = p.get("descr", c.descr), p.get("country", c.country), p.get("city", c.city)
            c.is_parrot = c.band == "Parrot" or c.email.startswith("parrot@")
            if c.is_parrot:
                c.callsign, c.name = "Parrot", on
            if new:
                self.sink.joined(room.name, c)
            else:
                self.sink.enrich(room.name, c)
            self.sink.updated(room.name)
            if c.email:
                try:
                    self.store.account_seen(c.email)
                except Exception:
                    pass
            return
        if rest.startswith(">>> CLIENT DISCONNECT"):
            room = self.rooms.get(room_name)
            c = room.find(on) if room else None
            if c:
                self._leave(room, c, "disconnected")
            return
        if rest.startswith("Voice transmission started"):
            room = self._room(room_name)
            c = room.find(on)
            if c is None:
                return
            if room.talker:
                self._talk_end(room, ts, None)
            room.talker, room.talk_start = c, ts
            room.talk_id = self.sink.talk_start(room.name, c, ts)
            return
        m = STOP_RE.match(rest)
        if m:
            room = self.rooms.get(room_name)
            if room and room.talker and room.talker.on == on:
                dur = int(m.group(1) or 0) * 60 + int(m.group(2) or 0) + int(m.group(3) or 0) / 1000
                self._talk_end(room, ts, dur)
            return
        m = TM_RE.match(rest)
        if m:
            room = self.rooms.get(room_name)
            c = room.find(on) if room else None
            if c and not m.group(1).strip():
                self.sink.chat(room.name, c, m.group(2), False)
            return
        if re.match(r"(MC|UM|BC|UC|AA|DA|AT|DT|ETX|RTX|ENA|TXR)Request", rest):
            self.sink.config_changed(f"{room_name}: {on} – {rest[:200]}")

    def _leave(self, room: RoomState, c: LClient, reason: str) -> None:
        if room.talker is c:
            self._talk_end(room, time.time(), None)
        if c in room.clients:
            room.clients.remove(c)
        self.sink.left(room.name, c, reason)

    def _talk_end(self, room: RoomState, ts: float, duration: Optional[float]) -> None:
        c, start, tid = room.talker, room.talk_start, room.talk_id
        room.talker, room.talk_id = None, None
        if c is None:
            return
        if duration is None:
            duration = max(0.0, ts - start)
        self.sink.talk_end(room.name, c, start, start + duration, duration, tid)
