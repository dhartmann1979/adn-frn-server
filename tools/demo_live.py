#!/usr/bin/env python3
"""
Demo stations for screenshots and trying things out – without a Java server.

Writes the same log lines the Java FRN server writes (logs/server.log and
logs/server_clients.log) into the FRN home of a demo installation; frn_adn reads
them as usual. Crosslinks to DMR, SvxLink, EchoLink, Zello and so on show their
client software avatars, owners and admins their badges.

    FRNADN_DATA=/tmp/demo python3 tools/demo_live.py            # stations log in, one talks
    FRNADN_DATA=/tmp/demo python3 tools/demo_live.py --quiet    # nobody talks

Never use it on a real installation: it writes into the server's log files.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path

#        room            callsign  name       band / channel                 description          city            country        type AL
STATIONS = [
    ("Nachtschicht", "DB0NAC", "Relais Minden", "DMR TG 2623 Crosslink",   "Brandmeister TG 2623", "Minden",       "Germany",     0, "OWNER"),
    ("Nachtschicht", "DL1ABC", "Bernd",         "PC Only",                  "",                    "Bielefeld",    "Germany",     2, "ADMIN"),
    ("Nachtschicht", "DO5ALF", "Andi",          "PC Only",                  "",                    "Porta Westfalica", "Germany", 2, "OK"),
    ("Nachtschicht", "DB0SVX", "SvxLink Weser", "438.725 MHz FM",           "SvxLink Repeater",    "Hameln",       "Germany",     1, "OK"),
    ("Nachtschicht", "OE3XZL", "Zello Gateway", "Zello Kanal N8schicht",    "Zello Bridge",        "Wien",         "Austria",     0, "OK"),
    ("Nachtschicht", "PD1QHJ", "Hans",          "PC Only",                  "",                    "Enschede",     "Netherlands", 2, "OK"),
    ("World",        "W1ECH",  "EchoLink Node", "EchoLink *ECHO-NET*",      "EchoLink Conference", "Boston",       "United States", 0, "OK"),
    ("World",        "HB9QFG", "Fritz",         "145.2875 MHz FM",          "Gateway Bern",        "Bern",         "Switzerland", 1, "OK"),
    ("World",        "G4YSF",  "Fusion Link",   "YSF Reflector UK",         "C4FM Wires-X",        "Leeds",        "United Kingdom", 0, "ADMIN"),
    ("Test",         "DG2QCK", "Carsten",       "PC Only",                  "",                    "Hannover",     "Germany",     2, "OK"),
    ("Test",         "DM0STA", "D-STAR Link",   "XLX262 D",                 "D-STAR Reflector",    "Berlin",       "Germany",     0, "OK"),
]


def stamp(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") + ",%03d" % int((t % 1) * 1000)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="nobody is on air")
    a = ap.parse_args()
    data = Path(os.environ.get("FRNADN_DATA", Path(__file__).resolve().parent.parent / "data"))
    logs = Path(os.environ.get("FRNADN_FRN_HOME", data / "frn")) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    now = time.time() - 600
    main_lines = [f"{stamp(now)} INFO  - Java FRN_Server V 2.0 Build [2020.11.08] (demo)",
                  f"{stamp(now)} INFO  - server started at {stamp(now)}",
                  f"{stamp(now)} INFO  - server listening on port 10024",
                  f"{stamp(now)} INFO  - Operating"]
    rooms = {}
    for i, (room, call, name, band, descr, city, country, ctype, al) in enumerate(STATIONS):
        t = now + 30 * i
        on = f"{call}, {name}"
        main_lines += [
            f"{stamp(t)} INFO  - socket connect from ip 203.0.113.{10 + i}",
            f"{stamp(t)} INFO  - CTRequest [version=2014003, email_address={call.lower()}@example.org, password=********, "
            f"operator_name={on}, client_type={ctype}, band_channel={band}, description={descr}, country={country}, "
            f"city={city}, network={room}]",
            f"{stamp(t + .1)} INFO  - {{{room} [{on}]}}: server response: AL={al}, NT={room}, ID=~d{i:03x}~, MT=",
            f"{stamp(t + .2)} INFO  - {{{room} [{on}]}}: >>> CLIENT CONNECT <<<"]
        rooms.setdefault(room, []).append((on, band, city, country, descr))
    if not a.quiet:
        main_lines.append(f"{stamp(time.time() - 12)} INFO  - {{Nachtschicht [DB0NAC, Relais Minden]}}: Voice transmission started.")
    with open(logs / "server.log", "a", encoding="utf-8") as f:
        f.write("\n".join(main_lines) + "\n")
    t = time.time() - 5
    lines = []
    for rid, (room, members) in enumerate(rooms.items(), 100):
        for on, band, city, country, descr in members:
            lines.append(f"{stamp(t)} - <net>{room}</net><rid>{rid}</rid><on>{on}</on><bc>{band}</bc><cty>{city}</cty>"
                         f"<ctry>{country}</ctry><dscr>{descr}</dscr><st>qrv</st><mt>0</mt><spk>0</spk>")
    with open(logs / "server_clients.log", "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(STATIONS)} demo stations written to {logs}")


if __name__ == "__main__":
    main()
