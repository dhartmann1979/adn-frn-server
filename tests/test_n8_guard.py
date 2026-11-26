"""N8 Guard (same file in every N8 system): request budget per IP, websocket limit, body size, login lockout."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
for _m in ("frnadn.n8_guard", "dashboard.n8_guard", "n8crosslink.n8_guard", "n8hotspot.n8_guard"):
    try:
        G = importlib.import_module(_m)
        break
    except ImportError:
        continue


def _scope(path="/api/x", ip="192.0.2.1", kind="http", method="GET", headers=()):
    return {"type": kind, "path": path, "method": method, "client": (ip, 1234), "headers": list(headers)}


def _run(guard, scope):
    sent = []

    async def send(m):
        sent.append(m)

    async def recv():
        return {"type": "http.request"}
    asyncio.run(guard(scope, recv, send))
    return sent


def test_budget_per_ip_and_kind():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["path"])
    g = G.Guard(app, api_per_min=3, page_per_min=2)
    for _ in range(3):
        assert _run(g, _scope()) == []
    r = _run(g, _scope())
    assert r[0]["status"] == 429 and (b"retry-after", b"20") in r[0]["headers"]
    assert _run(g, _scope(path="/static/app.js")) == []               # static files are never limited
    assert _run(g, _scope(ip="192.0.2.2")) == []                      # other IPs unaffected
    assert _run(g, _scope(ip="127.0.0.1")) == []                      # local proxy / keep-alive
    assert len(calls) == 6


def test_body_size_and_websockets():
    async def app(scope, receive, send):
        await asyncio.sleep(0)
    g = G.Guard(app, max_body=100, ws_per_ip=1)
    r = _run(g, _scope(method="POST", headers=[(b"content-length", b"1000")]))
    assert r[0]["status"] == 413
    g.ws_open["192.0.2.5"] = 1                                       # one websocket already open
    r = _run(g, _scope(path="/ws", ip="192.0.2.5", kind="websocket"))
    assert r[0]["type"] == "websocket.close"


def test_login_guard():
    lg = G.LoginGuard(per_ip=10, per_user=5)
    for _ in range(5):
        lg.failed("192.0.2.7", "chef")
    assert not lg.allowed("192.0.2.7", "chef") and lg.allowed("192.0.2.7", "other")
    for i in range(5):
        lg.failed("192.0.2.7", f"u{i}")
    assert not lg.allowed("192.0.2.7", "anyone")                     # changing names from one IP does not help
    assert lg.allowed("192.0.2.8", "chef")


def test_memory_is_bounded():
    g = G.Guard(lambda *a: None, max_ips=100)
    for i in range(1000):
        g.take(f"10.0.{i // 250}.{i % 250}", "api")
    assert len(g.buckets) <= 100
