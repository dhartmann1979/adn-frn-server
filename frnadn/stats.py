"""
Statistics with a small cache.

* Up to 30 days the single talks are summed (indexed by time).
* 90 days and one year come from ``talk_daily`` (one row per day, room and
  station) – that stays fast however many talks there are.
* Results are cached. A new talk makes the cache stale, but a range is
  computed again at most every few seconds (short ranges) or every minute
  (long ranges); without new talks the cache is kept for a minute.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .db import DB
from . import clientsw

RANGES = ("today", "24h", "7d", "30d", "90d", "1y")
TOP_ROOMS = 5


def _start(rng: str, now: float) -> Tuple[float, str]:
    d = datetime.fromtimestamp(now)
    if rng == "today":
        return d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp(), "hour"
    if rng == "24h":
        return (d.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)).timestamp(), "hour"
    days = {"7d": 7, "30d": 30, "90d": 90}.get(rng)
    if days:
        return (d.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)).timestamp(), "day"
    first = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    m = first.month - 11
    y = first.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return first.replace(year=y, month=m).timestamp(), "month"


def _buckets(start: float, now: float, kind: str) -> List[float]:
    out = []
    d = datetime.fromtimestamp(start)
    while d.timestamp() <= now:
        out.append(d.timestamp())
        if kind == "hour":
            d += timedelta(hours=1)
        elif kind == "day":
            d = (d + timedelta(days=1, hours=2)).replace(hour=0)
        else:
            d = d.replace(year=d.year + (d.month // 12), month=d.month % 12 + 1)
    return out


class Stats:
    def __init__(self, db: DB):
        self.db = db
        self.gen = 0
        self._cache: Dict[str, Tuple[float, int, Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def bump(self) -> None:
        self.gen += 1

    def summary(self, rng: str, hidden: Optional[set] = None) -> Dict[str, Any]:
        key = f"{rng}|{','.join(sorted(hidden or ()))}"
        now = time.time()
        with self._lock:
            c = self._cache.get(key)
            if c:
                age = now - c[0]
                min_age = 60 if rng in ("90d", "1y") else 4
                if (c[1] == self.gen and age < 60) or age < min_age:
                    self.hits += 1
                    return c[2]
        data = self._compute(rng, now, hidden or set())
        with self._lock:
            self.misses += 1
            self._cache[key] = (now, self.gen, data)
            if len(self._cache) > 40:
                for k in sorted(self._cache, key=lambda k: self._cache[k][0])[:10]:
                    self._cache.pop(k, None)
        return data

    # ------------------------------------------------------------ compute
    def _compute(self, rng: str, now: float, hidden: set) -> Dict[str, Any]:
        start, kind = _start(rng, now)
        buckets = _buckets(start, now, kind)
        idx = {b: i for i, b in enumerate(buckets)}
        n = len(buckets)

        def bucket_of(ts: float) -> int:
            d = datetime.fromtimestamp(ts)
            if kind == "hour":
                b = d.replace(minute=0, second=0, microsecond=0)
            elif kind == "day":
                b = d.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                b = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return idx.get(b.timestamp(), -1)

        hide = " AND net NOT IN (%s)" % ",".join("?" * len(hidden)) if hidden else ""
        hargs = list(hidden)
        if kind == "hour" or rng in ("7d", "30d"):
            rows = self.db.q("SELECT ts, net, callsign, name, duration FROM talks WHERE ts >= ? AND end_ts IS NOT NULL" + hide,
                             [start] + hargs)
            recs = [(r["ts"], r["net"], r["callsign"], r["duration"], 1) for r in rows]
            names = {r["callsign"]: r["name"] for r in rows if r["name"]}
        else:
            day0 = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            rows = self.db.q("SELECT day, net, callsign, talks, seconds FROM talk_daily WHERE day >= ?" + hide, [day0] + hargs)
            day_ts: Dict[str, float] = {}
            for r in rows:
                if r["day"] not in day_ts:
                    y, mo, dd = r["day"].split("-")
                    day_ts[r["day"]] = datetime(int(y), int(mo), int(dd), 12).timestamp()
            recs = [(day_ts[r["day"]], r["net"], r["callsign"], r["seconds"], r["talks"]) for r in rows]
            names = {}
        rooms: Dict[str, Dict[str, Any]] = {}
        stations: Dict[str, Dict[str, Any]] = {}
        per_room = {}
        tot_t = tot_d = 0.0
        for ts, net, call, dur, cnt in recs:
            tot_t += cnt
            tot_d += dur
            r = rooms.setdefault(net, {"name": net, "talks": 0, "duration": 0.0, "calls": set()})
            r["talks"] += cnt
            r["duration"] += dur
            if call:
                r["calls"].add(call)
                s = stations.setdefault(call, {"callsign": call, "name": names.get(call, ""), "talks": 0, "duration": 0.0,
                                               "last": 0.0, "rooms": {}})
                s["talks"] += cnt
                s["duration"] += dur
                s["last"] = max(s["last"], ts)
                s["rooms"][net] = s["rooms"].get(net, 0) + dur
            b = bucket_of(ts)
            if b >= 0:
                pr = per_room.setdefault(net, ([0] * n, [0.0] * n))
                pr[0][b] += cnt
                pr[1][b] += dur
        room_list = sorted(({"name": r["name"], "talks": r["talks"], "duration": round(r["duration"], 1),
                             "stations": len(r["calls"]), "share": (r["duration"] / tot_d) if tot_d else 0}
                            for r in rooms.values()), key=lambda r: -r["duration"])
        top = [r["name"] for r in room_list[:TOP_ROOMS]]
        series = [{"room": nm, "talks": per_room[nm][0], "duration": [round(x, 1) for x in per_room[nm][1]]}
                  for nm in top if nm in per_room]
        rest = [nm for nm in per_room if nm not in top]
        if rest:
            series.append({"room": None, "name": f"{len(rest)} more", "talks": [sum(per_room[nm][0][i] for nm in rest) for i in range(n)],
                           "duration": [round(sum(per_room[nm][1][i] for nm in rest), 1) for i in range(n)]})
        st_list = sorted(stations.values(), key=lambda s: -s["duration"])[:20]
        if st_list and not all(s["name"] for s in st_list):
            calls = [s["callsign"] for s in st_list]
            info = {r["callsign"]: r for r in self.db.q(
                f"SELECT callsign, name, country, band FROM stations WHERE callsign IN ({','.join('?' * len(calls))})", calls)}
            for s in st_list:
                r = info.get(s["callsign"])
                if r:
                    s["name"] = s["name"] or r["name"]
                    s["country"], s["band"] = r["country"], r["band"]
        for s in st_list:
            s["duration"] = round(s["duration"], 1)
            s["room"] = max(s["rooms"], key=s["rooms"].get) if s["rooms"] else ""
            s.pop("rooms", None)

        # who is online: samples every 5 minutes (max per bucket of the sum over rooms)
        if rng in ("90d", "1y") and not hidden:
            day0 = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
            srows = [{"ts": r["peak_ts"], "c": r["peak"]} for r in self.db.q("SELECT peak, peak_ts FROM online_daily WHERE day >= ?", (day0,))]
        else:
            srows = self.db.q("SELECT ts, SUM(clients) AS c FROM samples WHERE ts >= ?" + hide + " GROUP BY ts", [start] + hargs)
        online = [0] * n
        peak, peak_ts = 0, None
        for r in srows:
            b = bucket_of(r["ts"])
            if b >= 0:
                online[b] = max(online[b], r["c"])
            if r["c"] > peak:
                peak, peak_ts = r["c"], r["ts"]

        # logins
        v = self.db.q("SELECT COUNT(*) AS n, COUNT(DISTINCT callsign) AS u FROM visits WHERE login_ts >= ?" + hide, [start] + hargs)[0]

        # weekday × hour (only from single talks, up to 30 days back)
        heat = [[0.0] * 24 for _ in range(7)]
        hstart = now - 30 * 86400
        for r in self.db.q("SELECT ts, duration FROM talks WHERE ts >= ? AND end_ts IS NOT NULL" + hide, [hstart] + hargs):
            d = datetime.fromtimestamp(r["ts"])
            heat[d.weekday()][d.hour] += r["duration"]
        return {
            "range": rng, "bucket": kind, "buckets": buckets, "generated": now,
            "totals": {"talks": int(tot_t), "duration": round(tot_d, 1), "stations": len(stations), "rooms": len(rooms),
                       "peak_online": peak, "peak_ts": peak_ts, "logins": v["n"], "visitors": v["u"]},
            "rooms": room_list, "series": series, "stations": st_list, "online": online,
            "heat": [[round(x) for x in row] for row in heat], "heat_days": round((now - hstart) / 86400, 1),
        }

    # ------------------------------------------------------------ station
    def station(self, call: str, hidden: Optional[set] = None) -> Optional[Dict[str, Any]]:
        rows = self.db.q("SELECT * FROM stations WHERE callsign = ?", (call,))
        if not rows:
            return None
        s = dict(rows[0])
        s["sw"] = clientsw.detect(s.get("band"), s.get("descr"), s.get("name"), s.get("client"))
        hide = " AND net NOT IN (%s)" % ",".join("?" * len(hidden)) if hidden else ""
        hargs = list(hidden or ())
        since = time.time() - 30 * 86400
        agg = self.db.q("SELECT COUNT(*) AS n, COALESCE(SUM(duration),0) AS d, MAX(ts) AS last FROM talks "
                        "WHERE callsign=? AND ts>=? AND end_ts IS NOT NULL" + hide, [call, since] + hargs)[0]
        rooms = [dict(r) for r in self.db.q("SELECT net, COUNT(*) AS talks, SUM(duration) AS duration FROM talks "
                                            "WHERE callsign=? AND ts>=? AND end_ts IS NOT NULL" + hide +
                                            " GROUP BY net ORDER BY duration DESC", [call, since] + hargs)]
        recent = [dict(r) for r in self.db.q("SELECT ts, net, duration FROM talks WHERE callsign=? AND end_ts IS NOT NULL" + hide +
                                             " ORDER BY ts DESC LIMIT 15", [call] + hargs)]
        visits = self.db.q("SELECT COUNT(*) AS n, COALESCE(SUM(COALESCE(logout_ts, ?) - login_ts), 0) AS t FROM visits "
                           "WHERE callsign=? AND login_ts>=?" + hide, [time.time(), call, since] + hargs)[0]
        total = self.db.q("SELECT COALESCE(SUM(talks),0) AS n, COALESCE(SUM(seconds),0) AS d FROM talk_daily WHERE callsign=?" + hide,
                          [call] + hargs)[0]
        hours = [0.0] * 24
        for r in self.db.q("SELECT ts, duration FROM talks WHERE callsign=? AND ts>=? AND end_ts IS NOT NULL" + hide, [call, since] + hargs):
            hours[datetime.fromtimestamp(r["ts"]).hour] += r["duration"]
        s.pop("cid", None)
        return {"station": s, "talks_30d": agg["n"], "duration_30d": round(agg["d"], 1), "last_talk": agg["last"],
                "rooms": rooms, "recent": recent, "visits_30d": visits["n"], "online_30d": round(visits["t"]),
                "talks_total": total["n"], "duration_total": round(total["d"], 1), "hours": [round(h) for h in hours]}

    def directory(self, hidden: Optional[set] = None) -> List[Dict[str, Any]]:
        since = time.time() - 30 * 86400
        hide = " AND net NOT IN (%s)" % ",".join("?" * len(hidden)) if hidden else ""
        act = {r["callsign"]: r for r in self.db.q(
            "SELECT callsign, COUNT(*) AS n, SUM(duration) AS d FROM talks WHERE ts>=? AND end_ts IS NOT NULL AND callsign<>''" + hide +
            " GROUP BY callsign", [since] + list(hidden or ()))}
        out = []
        for r in self.db.q("SELECT callsign, name, band, country, city, client, descr, first_ts, last_ts, last_net FROM stations ORDER BY last_ts DESC"):
            if hidden and r["last_net"] in hidden:
                continue
            a = act.get(r["callsign"])
            row = dict(r)
            row["sw"] = clientsw.detect(row["band"], row.pop("descr"), row["name"], row["client"])
            out.append({**row, "talks": a["n"] if a else 0, "duration": round(a["d"], 1) if a else 0})
        return out
