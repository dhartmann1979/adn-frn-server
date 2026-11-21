#!/usr/bin/env python3
"""
Simulated FRN stations for tests and demos: they log in to a FRN server,
change rooms, talk (silent GSM frames) and write chat messages.

    python3 tools/sim_clients.py --host 127.0.0.1 --port 10024 --minutes 10

Only for a test server with password check “open” – the e-mail addresses
are invented.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time

STATIONS = [
    ("DO1QAA", "Anke", "Germany", "Minden", "PC Only"),
    ("DL3QBE", "Bernd", "Germany", "Bielefeld", "PC Only"),
    ("DB0QXN-L", "Relais Weserbergland", "Germany", "Porta Westfalica", "438.950 MHz FM"),
    ("DG2QCK", "Carsten", "Germany", "Hannover", "PC Only"),
    ("DK5QDO", "Doris", "Germany", "Osnabrück", "PC Only"),
    ("OE3QEF", "Ernst", "Austria", "St. Pölten", "PC Only"),
    ("HB9QFG", "Fritz", "Switzerland", "Bern", "PC Only"),
    ("DM4QGH", "Gabi", "Germany", "Leipzig", "PC Only"),
    ("PD1QHJ", "Hans", "Netherlands", "Enschede", "PC Only"),
    ("DO7QJK", "Jana", "Germany", "Herford", "PC Only"),
    ("DL1QKL", "Klaus", "Germany", "Detmold", "446.00625 MHz PMR"),
    ("ON4QLM", "Luc", "Belgium", "Liège", "PC Only"),
    ("DH6QMN", "Maik", "Germany", "Bremen", "PC Only"),
    ("DC9QNP", "Nina", "Germany", "Kassel", "PC Only"),
    ("SP3QPR", "Piotr", "Poland", "Poznań", "PC Only"),
    ("DF8QRS", "Ralf", "Germany", "Paderborn", "PC Only"),
]
CHAT = ["Moin in die Runde!", "Bin gleich QRV.", "73 und gute Nacht", "Wie ist die Modulation?", "Danke für die Runde 👍",
        "Bin kurz QRX", "Gute Verbindung heute", "Wer hört mit?"]


LOCKS: dict = {}


async def station(host, port, call, name, country, city, band, rooms, until, weights):
    email = f"{call.lower().replace('-', '')}@example.invalid"
    await asyncio.sleep(random.uniform(0, 45))         # real clients do not all come at the same moment
    while time.time() < until:
        room = random.choices(rooms, weights=weights)[0]
        w = dt = None
        try:
            r, w = await asyncio.open_connection(host, port)
            w.write(f"CT:<VX>2014003</VX><EA>{email}</EA><PW>x</PW><ON>{call}, {name}</ON><CL>{1 if 'MHz' in band else 2}</CL>"
                    f"<BC>{band}</BC><DS>{'Gateway' if 'MHz' in band else 'Client'}</DS><NN>{country}</NN><CT>{city}</CT>"
                    f"<NT>{room}</NT>\r\n".encode("cp1252", "replace"))      # FRN clients send ANSI
            await w.drain()
            await r.readline(); await r.readline()
            w.write(b"RX0\r\n")

            async def drain():
                while True:
                    try:
                        d = await asyncio.wait_for(r.read(65536), 0.4)
                    except asyncio.TimeoutError:
                        d = b"."
                    if not d:
                        return
                    w.write(b"P\r\n")
            dt = asyncio.ensure_future(drain())
            stay = time.time() + random.uniform(60, 600)
            lock = LOCKS.setdefault(room, asyncio.Lock())
            while time.time() < min(stay, until) and not dt.done():
                await asyncio.sleep(random.uniform(4, 40))
                if random.random() < 0.55:
                    async with lock:                 # one speaker per room, like real FRN clients
                        w.write(b"TX0\r\n")
                        await asyncio.sleep(0.3)
                        for _ in range(int(random.uniform(3, 45) / 0.2)):
                            w.write(b"TX1\r\n" + bytes(325))
                            await w.drain()
                            await asyncio.sleep(0.2)
                        w.write(b"RX0\r\n")
                        await asyncio.sleep(random.uniform(1.5, 4))
                elif random.random() < 0.15:
                    w.write(f"TM:<ID></ID><MS>{random.choice(CHAT)}</MS>\r\n".encode())
        except OSError:
            pass
        finally:
            if dt:
                dt.cancel()
            if w:
                try:                                  # clean goodbye: FIN and read the rest, no RST
                    w.write_eof()
                    while await asyncio.wait_for(r.read(65536), 2):
                        pass
                except Exception:
                    pass
                w.close()
        await asyncio.sleep(random.uniform(5, 60))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10024)
    ap.add_argument("--rooms", default="Nachtschicht,World,Technik,Test")
    ap.add_argument("--stations", type=int, default=12)
    ap.add_argument("--minutes", type=float, default=10)
    a = ap.parse_args()
    rooms = [x.strip() for x in a.rooms.split(",") if x.strip()]
    weights = [6, 3, 1, 2][:len(rooms)] + [1] * max(0, len(rooms) - 4)
    until = time.time() + a.minutes * 60
    await asyncio.gather(*[station(a.host, a.port, *s, rooms, until, weights) for s in STATIONS[:a.stations]])


if __name__ == "__main__":
    asyncio.run(main())
