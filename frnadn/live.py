"""
Live state for the dashboard, fed by frn/logwatch.py from the logs of the Java FRN
server: who is in which room, who talks, what was heard. Changes are written to
SQLite and pushed to the browsers via ``notify``.
"""
from __future__ import annotations

import asyncio
import collections
import time
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional

from .db import DB
from . import clientsw

LAST_HEARD = 60
EVENTS = 800


def day_of(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


class Live:
    def __init__(self, db: DB, notify: Callable[[Dict[str, Any]], Any], on_talk_end: Callable[[], Any] = lambda: None):
        self.db = db
        self.notify = notify
        self.on_talk_end = on_talk_end
        self.server = None                     # LogWatch, set by the app
        self.chat_mode = "admin"
        self.state: Dict[str, Any] = {"running": False}
        self.last_heard: Deque[Dict[str, Any]] = collections.deque(maxlen=LAST_HEARD)
        self.events: Deque[Dict[str, Any]] = collections.deque(maxlen=EVENTS)
        self._visit: Dict[int, int] = {}       # id(client) -> visits.id
        self._pending: set = set()
        self._flush: Optional[asyncio.TimerHandle] = None
        self._sample_max: Dict[str, int] = {}
        self._slot: Optional[int] = None
        st = {r["callsign"]: r for r in self.db.q("SELECT callsign, descr, client FROM stations")}
        for r in reversed(self.db.q("SELECT * FROM talks WHERE end_ts IS NOT NULL ORDER BY ts DESC LIMIT ?", (LAST_HEARD,))):
            s = st.get(r["callsign"])
            self.last_heard.appendleft({"id": r["id"], "ts": r["ts"], "room": r["net"], "callsign": r["callsign"], "name": r["name"],
                                        "band": r["band"], "country": r["country"], "city": r["city"], "duration": r["duration"],
                                        "sw": clientsw.detect(r["band"], s["descr"] if s else "", r["name"], s["client"] if s else None)})
        # visits left open by a crash or restart are closed
        self.db.x("UPDATE visits SET logout_ts = login_ts WHERE logout_ts IS NULL")

    # ------------------------------------------------------------ helpers
    def _touch(self, room: str) -> None:
        self._pending.add(room)
        if self._flush is None:
            try:
                self._flush = asyncio.get_running_loop().call_later(0.25, self._send)
            except RuntimeError:
                self._send()

    def _send(self) -> None:
        self._flush = None
        rooms, self._pending = self._pending, set()
        for r in rooms:
            self.notify({"type": "room", "room": r})

    def _event(self, kind: str, text: str, room: str = "") -> None:
        e = {"ts": time.time(), "kind": kind, "text": text, "room": room}
        self.events.append(e)
        self.notify({"type": "log", "entry": e})

    def _station(self, c, room: str, ts: float) -> None:
        if c.is_parrot or not c.callsign:
            return
        self.db.x("INSERT INTO stations (callsign, cid, name, band, country, city, descr, client, first_ts, last_ts, last_net) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(callsign) DO UPDATE SET cid=excluded.cid, "
                  "name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE name END, band=excluded.band, "
                  "country=CASE WHEN excluded.country<>'' THEN excluded.country ELSE country END, "
                  "city=CASE WHEN excluded.city<>'' THEN excluded.city ELSE city END, descr=excluded.descr, "
                  "client=excluded.client, last_ts=MAX(last_ts, excluded.last_ts), last_net=excluded.last_net",
                  (c.callsign, c.cid, c.name, c.band, c.country, c.city, c.descr, c.client, ts, ts, room))

    # ------------------------------------------------------------ sink of the FRN server
    def server_state(self, state: Dict[str, Any]) -> None:
        self.state = state
        self.notify({"type": "server", "server": state})
        self.notify({"type": "rooms"})

    def joined(self, room: str, c) -> None:
        if c.is_parrot:
            self._touch(room)
            return
        now = time.time()
        cur = self.db.x("INSERT INTO visits (login_ts, net, cid, callsign, name, email, peer, band, country, city) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (now, room, c.cid, c.callsign, c.name, c.email, c.peer, c.band, c.country, c.city))
        self._visit[id(c)] = cur.lastrowid
        self._station(c, room, now)
        self._touch(room)
        self.notify({"type": "visit", "entry": {"ts": now, "room": room, "callsign": c.callsign, "name": c.name, "action": "login"}})
        self._event("login", f"{c.callsign} ({c.name}) joined {room} · {c.access} · {c.email} · {c.peer}", room)

    def left(self, room: str, c, reason: str) -> None:
        if c.is_parrot:
            self._touch(room)
            return
        now = time.time()
        vid = self._visit.pop(id(c), None)
        if vid:
            self.db.x("UPDATE visits SET logout_ts=? WHERE id=?", (now, vid))
        self._touch(room)
        self.notify({"type": "visit", "entry": {"ts": now, "room": room, "callsign": c.callsign, "name": c.name, "action": "logout"}})
        self._event("logout", f"{c.callsign} left {room} ({reason})", room)

    def enrich(self, room: str, c) -> None:
        """Details of a client that was known from the client list only (e-mail, address, type)."""
        if c.is_parrot:
            return
        vid = self._visit.get(id(c))
        if vid:
            self.db.x("UPDATE visits SET email=?, peer=?, band=? WHERE id=?", (c.email, c.peer, c.band, vid))
        self._station(c, room, time.time())
        self._event("login", f"{c.callsign} ({c.name}) in {room} · {c.access} · {c.email} · {c.peer}", room)

    def updated(self, room: str) -> None:
        self._touch(room)

    def denied(self, info: Dict[str, Any], reason: str, peer: str) -> None:
        self._event("denied", f"{info.get('callsign') or '?'} ({info.get('email')}) refused for {info.get('room') or '-'}: {reason} · {peer}",
                    info.get("room") or "")

    def frn_errorlog(self, text: str) -> None:
        """Reason from the public FRN error log of freeradionetwork.de (refused logins at the SystemManager)."""
        self._event("frnlog", text)

    def config_changed(self, text: str) -> None:
        self._event("config", text)

    def talk_start(self, room: str, c, ts: float) -> int:
        cur = self.db.x("INSERT INTO talks (ts, net, cid, callsign, name, band, country, city) VALUES (?,?,?,?,?,?,?,?)",
                        (ts, room, c.cid, c.callsign, c.name, c.band, c.country, c.city))
        self._touch(room)
        return cur.lastrowid

    def talk_end(self, room: str, c, start: float, end: float, duration: float, tid: Optional[int]) -> None:
        if not tid:
            self._touch(room)
            return
        dur = round(duration, 1)
        if c.is_parrot or dur < 0.3:
            self.db.x("DELETE FROM talks WHERE id=?", (tid,))       # the parrot and key-ups are no talks
            self._touch(room)
            return
        self.db.tx([("UPDATE talks SET end_ts=?, duration=? WHERE id=?", (end, dur, tid)),
                    ("INSERT INTO talk_daily (day, net, callsign, talks, seconds) VALUES (?,?,?,1,?) ON CONFLICT(day, net, callsign) "
                     "DO UPDATE SET talks=talks+1, seconds=seconds+excluded.seconds", (day_of(start), room, c.callsign, dur))])
        self._station(c, room, end)
        entry = {"id": tid, "ts": start, "room": room, "callsign": c.callsign, "name": c.name, "band": c.band,
                 "country": c.country, "city": c.city, "duration": dur,
                 "sw": clientsw.detect(c.band, c.descr, c.name, c.client, c.is_parrot)}
        self.last_heard.appendleft(entry)
        self._touch(room)
        self.notify({"type": "heard", "entry": entry})
        self.on_talk_end()

    def chat(self, room: str, c, text: str, private: bool) -> None:
        if self.chat_mode == "off":
            return
        ts = time.time()
        cur = self.db.x("INSERT INTO chat (ts, net, cid, callsign, text, private) VALUES (?,?,?,?,?,?)",
                        (ts, room, c.cid, c.callsign, text[:1000], 1 if private else 0))
        self.notify({"type": "chat", "entry": {"id": cur.lastrowid, "ts": ts, "net": room, "callsign": c.callsign,
                                               "text": text[:1000], "private": private}})

    # ------------------------------------------------------------ views
    def room(self, name: str, admin: bool = False) -> Optional[Dict[str, Any]]:
        srv = self.server
        r = srv.rooms.get(name) if srv else None
        if r is None:
            return None
        talker = r.talker
        clients = []
        for c in sorted(r.clients, key=lambda c: (not c.is_parrot, c.joined)):
            d = c.public()
            d["talking"] = c is talker
            if admin:
                d.update(email=c.email, peer=c.peer)
            clients.append(d)
        cfg = r.cfg
        return {"name": r.name, "id": r.id, "hidden": bool(cfg.get("hidden")), "parrot": bool(cfg.get("parrot") or r.id == 0),
                "access_on": False, "tot": cfg.get("tot") or 0, "clients": clients,
                "talking": ({**talker.public(), "start": r.talk_start} if talker else None)}

    def rooms(self, see_hidden: bool, admin: bool = False) -> List[Dict[str, Any]]:
        if not self.server:
            return []
        out = []
        for name, r in self.server.rooms.items():
            if r.cfg.get("hidden") and not see_hidden:
                continue
            v = self.room(name, admin)
            if v:
                out.append(v)
        return out

    def hidden_rooms(self) -> set:
        return {n for n, r in self.server.rooms.items() if r.cfg.get("hidden")} if self.server else set()

    def online(self) -> int:
        return sum(1 for r in self.server.rooms.values() for c in r.clients if not c.is_parrot) if self.server else 0

    def snapshot(self, see_hidden: bool, admin: bool) -> Dict[str, Any]:
        hidden = set() if see_hidden else self.hidden_rooms()
        lh = [e for e in self.last_heard if e["room"] not in hidden]
        cond = f" AND net NOT IN ({','.join('?' * len(hidden))})" if hidden else ""
        h = sorted(hidden)
        ev = self.db.q("SELECT * FROM (SELECT login_ts AS ts, 'login' AS action, net AS room, callsign, name FROM visits WHERE 1=1" + cond +
                       " UNION ALL SELECT logout_ts AS ts, 'logout' AS action, net AS room, callsign, name FROM visits "
                       "WHERE logout_ts IS NOT NULL AND logout_ts > login_ts" + cond + ") ORDER BY ts DESC LIMIT 25", h + h)
        return {"rooms": self.rooms(see_hidden, admin), "last_heard": lh[:40], "server": self.server.state() if self.server else self.state,
                "visits": [dict(r) for r in ev]}

    def sample(self) -> None:
        """Every minute: highest number of stations per room, written every 5 minutes."""
        if not self.server:
            return
        now = time.time()
        for name, r in self.server.rooms.items():
            self._sample_max[name] = max(self._sample_max.get(name, 0), sum(1 for c in r.clients if not c.is_parrot))
        slot = int(now // 300) * 300
        if self._slot is None:
            self._slot = slot
        if slot != self._slot:
            self.db.many("INSERT OR REPLACE INTO samples (ts, net, clients) VALUES (?,?,?)",
                         [(self._slot, n, c) for n, c in self._sample_max.items()])
            total = sum(self._sample_max.values())
            self.db.x("INSERT INTO online_daily (day, peak, peak_ts) VALUES (?,?,?) ON CONFLICT(day) DO UPDATE SET "
                      "peak_ts=CASE WHEN excluded.peak>peak THEN excluded.peak_ts ELSE peak_ts END, peak=MAX(peak, excluded.peak)",
                      (day_of(self._slot), total, self._slot))
            self._sample_max = {}
            self._slot = slot
