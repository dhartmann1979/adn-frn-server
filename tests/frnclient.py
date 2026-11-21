"""A small FRN test client (protocol as documented by freeradionetwork.eu)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import re


def tag(s: str, name: str) -> str:
    m = re.search(f"<{name}>(.*?)</{name}>", s, re.S)
    return m.group(1) if m else ""


class TestClient:
    __test__ = False
    def __init__(self, port: int, email: str, call: str, room: str, password: str = "x", client: int = 2,
                 band: str = "PC Only", host: str = "127.0.0.1"):
        self.port, self.email, self.call, self.room, self.password, self.client, self.band, self.host = \
            port, email, call, room, password, client, band, host
        self.r: Optional[asyncio.StreamReader] = None
        self.w: Optional[asyncio.StreamWriter] = None
        self.login: Dict[str, str] = {}
        self.version = ""

    async def connect(self) -> Dict[str, str]:
        self.r, self.w = await asyncio.open_connection(self.host, self.port)
        self.w.write(f"CT:<VX>2014003</VX><EA>{self.email}</EA><PW>{self.password}</PW><ON>{self.call}, Op</ON><CL>{self.client}</CL>"
                     f"<BC>{self.band}</BC><DS>test</DS><NN>Germany</NN><CT>Minden</CT><NT>{self.room}</NT>\r\n".encode())
        await self.w.drain()
        self.version = (await asyncio.wait_for(self.r.readline(), 5)).decode().strip()
        line = (await asyncio.wait_for(self.r.readline(), 5)).decode()
        self.login = {k: tag(line, k) for k in ("MT", "SV", "AL", "BN", "BP")}
        if self.login["AL"] in ("OK", "ADMIN", "OWNER", "NETOWNER"):
            await self.send("RX0")
        return self.login

    async def send(self, line: str, data: bytes = b"") -> None:
        self.w.write(line.encode() + b"\r\n" + data)
        await self.w.drain()

    async def _lines(self) -> List[str]:
        n = int((await self.r.readline()).decode().strip())
        return [(await self.r.readline()).decode().rstrip("\r\n") for _ in range(n)]

    async def poll(self) -> Tuple[int, Any]:
        """Send P, read one packet: (type, payload)."""
        await self.send("P")
        t = (await asyncio.wait_for(self.r.readexactly(1), 5))[0]
        if t == 0:
            return 0, None
        if t == 1:
            return 1, int.from_bytes(await self.r.readexactly(2), "big")
        if t == 2:
            d = await self.r.readexactly(327)
            return 2, (int.from_bytes(d[:2], "big"), d[2:])
        if t == 3:
            idx = int.from_bytes(await self.r.readexactly(2), "big")
            return 3, (idx, await self._lines())
        return t, await self._lines()

    async def drain(self, limit: int = 50) -> List[Tuple[int, Any]]:
        out = []
        for _ in range(limit):
            p = await self.poll()
            if p[0] == 0:
                break
            out.append(p)
        return out

    async def talk(self, packets: int, gap: float = 0.0) -> bool:
        await self.send("TX0")
        got = await self.drain()
        if not any(t == 1 for t, _ in got):
            return False
        for i in range(packets):
            await self.send("TX1", bytes([i % 256]) * 325)
            if gap:
                await asyncio.sleep(gap)
        await self.send("RX0")
        return True

    def close(self) -> None:
        if self.w:
            self.w.close()


def calls(lines: List[str]) -> List[str]:
    return [tag(x, "ON").split(",")[0] for x in lines]
