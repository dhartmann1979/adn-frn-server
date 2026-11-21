#!/usr/bin/env python3
"""
Fills a dashboard database with invented history (talks, logins, online
samples) for demos and screenshots. Never use it on a real installation.

    FRNADN_DATA=/tmp/demo python3 tools/seed_demo.py --days 60
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from frnadn.db import DB                          # noqa: E402
from sim_clients import CHAT, STATIONS            # noqa: E402



def client_id(email: str) -> str:
    return "demo-" + hashlib.sha1(email.lower().encode()).hexdigest()[:16]


ROOMS = [("Nachtschicht", 6.0), ("World", 2.5), ("Technik", 1.2), ("Test", 0.5)]


def hour_weight(h: int, wd: int) -> float:
    base = 0.15 + 0.85 * max(0.0, math.sin((h - 5) / 24 * 2 * math.pi - 0.6)) ** 2
    if 19 <= h <= 23:
        base *= 2.2
    if h < 6:
        base *= 0.35 if h > 1 else 0.8
    return base * (1.3 if wd >= 5 else 1.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    db = DB(Path(os.environ.get("FRNADN_DATA", "data")) / "frnadn.db")
    now = time.time()
    start = now - a.days * 86400
    talks, daily, visits, samples, chat = [], {}, [], [], []
    favourite = {s[0]: rnd.choices([r for r, _ in ROOMS], weights=[w for _, w in ROOMS])[0] for s in STATIONS}
    activity = {s[0]: rnd.uniform(0.3, 1.6) for s in STATIONS}
    t = start
    while t < now - 600:
        d = datetime.fromtimestamp(t)
        w = hour_weight(d.hour, d.weekday())
        # talks in this 5 minute slot
        for room, rw in ROOMS:
            n = sum(1 for _ in range(6) if rnd.random() < 0.09 * w * rw / 2)
            for _ in range(n):
                st = rnd.choices(STATIONS, weights=[activity[s[0]] * (4 if favourite[s[0]] == room else 1) for s in STATIONS])[0]
                ts = t + rnd.uniform(0, 300)
                dur = round(max(1.0, rnd.lognormvariate(2.6, 0.75)), 1)
                talks.append((ts, ts + dur, room, client_id(st[0].lower() + "@example.invalid"), st[0], st[1], st[4], st[2], st[3], dur))
                key = (datetime.fromtimestamp(ts).strftime("%Y-%m-%d"), room, st[0])
                c = daily.setdefault(key, [0, 0.0])
                c[0] += 1
                c[1] += dur
            samples.append((int(t // 300) * 300, room, int(round(w * rw * 1.4 + rnd.uniform(0, 2)))))
        # logins
        if rnd.random() < 0.35 * w:
            st = rnd.choice(STATIONS)
            dur = rnd.uniform(300, 7200)
            visits.append((t, min(t + dur, now - 60), favourite[st[0]], client_id(st[0].lower() + "@example.invalid"), st[0], st[1],
                           st[0].lower().replace("-", "") + "@example.invalid", f"198.51.100.{rnd.randint(2, 250)}:{rnd.randint(20000, 60000)}",
                           st[4], st[2], st[3]))
        if rnd.random() < 0.02 * w:
            st = rnd.choice(STATIONS)
            chat.append((t + 30, favourite[st[0]], client_id(st[0].lower() + "@example.invalid"), st[0], rnd.choice(CHAT)))
        t += 300
    db.many("INSERT INTO talks (ts, end_ts, net, cid, callsign, name, band, country, city, duration) VALUES (?,?,?,?,?,?,?,?,?,?)", talks)
    db.many("INSERT INTO talk_daily (day, net, callsign, talks, seconds) VALUES (?,?,?,?,?) ON CONFLICT(day, net, callsign) DO UPDATE SET "
            "talks=talks+excluded.talks, seconds=seconds+excluded.seconds", [(k[0], k[1], k[2], v[0], round(v[1], 1)) for k, v in daily.items()])
    db.many("INSERT INTO visits (login_ts, logout_ts, net, cid, callsign, name, email, peer, band, country, city) VALUES (?,?,?,?,?,?,?,?,?,?,?)", visits)
    db.many("INSERT OR REPLACE INTO samples (ts, net, clients) VALUES (?,?,?)", samples)
    db.many("INSERT INTO chat (ts, net, cid, callsign, text) VALUES (?,?,?,?,?)", chat)
    db.x("INSERT OR REPLACE INTO online_daily (day, peak, peak_ts) SELECT day, c, ts FROM (SELECT date(ts, 'unixepoch', 'localtime') AS day, ts, "
         "SUM(clients) AS c, ROW_NUMBER() OVER (PARTITION BY date(ts, 'unixepoch', 'localtime') ORDER BY SUM(clients) DESC) AS rn "
         "FROM samples GROUP BY ts) WHERE rn = 1")
    for s in STATIONS:
        db.x("INSERT INTO stations (callsign, cid, name, band, country, city, descr, client, first_ts, last_ts, last_net) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
             "ON CONFLICT(callsign) DO NOTHING", (s[0], client_id(s[0].lower() + "@example.invalid"), s[1], s[4], s[2], s[3],
                                                  "Gateway" if "MHz" in s[4] else "Client", 1 if "MHz" in s[4] else 0, start, now - rnd.uniform(600, 86400 * 3),
                                                  favourite[s[0]]))
    print(f"{len(talks)} talks, {len(visits)} logins, {len(samples)} samples, {len(chat)} chat messages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
