"""N8 Guard – protection against flooding and password guessing, the same file in every N8 system.

* **Flooding:** every client IP has a budget of requests per minute (token bucket). API calls, page loads and websocket
  connections each have their own limit; over the limit the answer is ``429 Too Many Requests`` with ``Retry-After``.
  At most ``ws_per_ip`` websockets per IP at the same time.
* **Big requests:** a request body larger than ``max_body`` is refused with ``413`` before it is read.
* **Password guessing:** ``Guard.login_allowed(ip, user)`` / ``login_failed`` / ``login_ok`` – after 10 failed logins per IP
  or 5 per IP and user within 15 minutes the login is locked for 15 minutes (``429``), whatever the password.
* **Memory:** at most ``max_ips`` IPs are tracked; the oldest are forgotten first, so the guard itself cannot be flooded.

The client IP is the TCP peer; ``X-Forwarded-For`` is only believed from a reverse proxy on the same machine (127.0.0.1, ::1) –
uvicorn does that already when it runs with ``forwarded_allow_ips="127.0.0.1"``.
Pure ASGI, standard library only.
"""
from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple

VERSION = "1.0.0"


class Bucket:
    __slots__ = ("tokens", "stamp")

    def __init__(self, cap: float) -> None:
        self.tokens, self.stamp = cap, time.monotonic()


class Guard:
    def __init__(self, app: Callable, api_per_min: int = 600, page_per_min: int = 240, auth_per_min: int = 30,
                 ws_per_min: int = 60, ws_per_ip: int = 24, max_body: int = 64 * 1024 * 1024, max_ips: int = 20000,
                 auth_paths: Tuple[str, ...] = ("/api/auth/", "/api/login", "/api/setup"),
                 exempt: Tuple[str, ...] = ("/static/", "/.well-known/acme-challenge/"),
                 trusted: Tuple[str, ...] = ("127.0.0.1", "::1")) -> None:
        self.app = app
        self.limits = {"api": api_per_min, "page": page_per_min, "auth": auth_per_min, "ws": ws_per_min}
        self.ws_per_ip, self.max_body, self.max_ips = ws_per_ip, max_body, max_ips
        self.auth_paths, self.exempt, self.trusted = auth_paths, exempt, trusted
        self.buckets: "OrderedDict[Tuple[str, str], Bucket]" = OrderedDict()
        self.ws_open: Dict[str, int] = {}
        self.blocked = 0
        GUARDS.append(self)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def ip(scope: Dict[str, Any]) -> str:
        c = scope.get("client")
        return c[0] if c else ""

    def _kind(self, scope: Dict[str, Any]) -> Optional[str]:
        path = scope.get("path", "")
        if any(path.startswith(p) for p in self.exempt):
            return None
        if scope["type"] == "websocket":
            return "ws"
        if any(path.startswith(p) for p in self.auth_paths) and scope.get("method") == "POST":
            return "auth"
        return "api" if path.startswith("/api/") else "page"

    def take(self, ip: str, kind: str) -> float:
        """Take one token; returns 0 if allowed, else the seconds until the next token."""
        if not ip or ip in self.trusted:
            return 0.0
        cap = float(self.limits[kind])
        rate = cap / 60.0
        key = (ip, kind)
        b = self.buckets.get(key)
        now = time.monotonic()
        if b is None:
            b = Bucket(cap)
            self.buckets[key] = b
            while len(self.buckets) > self.max_ips:
                self.buckets.popitem(last=False)
        else:
            self.buckets.move_to_end(key)
            b.tokens = min(cap, b.tokens + (now - b.stamp) * rate)
            b.stamp = now
        if b.tokens >= 1:
            b.tokens -= 1
            return 0.0
        self.blocked += 1
        return max(1.0, (1 - b.tokens) / rate)

    # ------------------------------------------------------------ ASGI
    async def __call__(self, scope, receive, send):  # noqa: ANN001
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        ip, kind = self.ip(scope), self._kind(scope)
        if kind is None:
            return await self.app(scope, receive, send)
        wait = self.take(ip, kind)
        if scope["type"] == "websocket":
            if wait or (ip not in self.trusted and self.ws_open.get(ip, 0) >= self.ws_per_ip):
                await send({"type": "websocket.close", "code": 1013})
                return
            self.ws_open[ip] = self.ws_open.get(ip, 0) + 1
            try:
                return await self.app(scope, receive, send)
            finally:
                n = self.ws_open.get(ip, 1) - 1
                if n > 0:
                    self.ws_open[ip] = n
                else:
                    self.ws_open.pop(ip, None)
        if wait:
            return await _reply(send, 429, "Too many requests – please wait a moment.", {"retry-after": str(int(wait + 0.999))})
        for k, v in scope.get("headers") or []:
            if k == b"content-length":
                try:
                    if int(v) > self.max_body:
                        return await _reply(send, 413, "Request too large.")
                except ValueError:
                    return await _reply(send, 400, "Bad Content-Length.")
        return await self.app(scope, receive, send)


async def _reply(send, status: int, msg: str, extra: Optional[Dict[str, str]] = None) -> None:  # noqa: ANN001
    body = json.dumps({"error": msg, "detail": msg}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store")]
    headers += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


GUARDS: List[Guard] = []


# ---------------------------------------------------------------- password guessing
class LoginGuard:
    """Lockout after too many failed logins: 10 per IP or 5 per IP and user name within 15 minutes → 15 minutes locked."""

    def __init__(self, per_ip: int = 10, per_user: int = 5, window: float = 900, max_keys: int = 20000) -> None:
        self.per_ip, self.per_user, self.window, self.max_keys = per_ip, per_user, window, max_keys
        self.fails: "OrderedDict[str, List[float]]" = OrderedDict()

    def _recent(self, key: str) -> List[float]:
        now = time.time()
        lst = [t for t in self.fails.get(key, []) if now - t < self.window]
        if lst:
            self.fails[key] = lst
        else:
            self.fails.pop(key, None)
        return lst

    def allowed(self, ip: str, user: str = "") -> bool:
        if not ip:
            return True
        return len(self._recent("ip:" + ip)) < self.per_ip and len(self._recent(f"u:{ip}|{(user or '').lower()}")) < self.per_user

    def failed(self, ip: str, user: str = "") -> None:
        for key in ("ip:" + ip, f"u:{ip}|{(user or '').lower()}"):
            self.fails.setdefault(key, []).append(time.time())
            self.fails.move_to_end(key)
        while len(self.fails) > self.max_keys:
            self.fails.popitem(last=False)

    def ok(self, ip: str, user: str = "") -> None:
        self.fails.pop(f"u:{ip}|{(user or '').lower()}", None)
