"""🧩 Portal widgets: own FRN boxes, live data of other N8 systems over the portal feed (widgets.py, n8feed.py)."""
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from frnadn import n8feed, widgets

H = {"X-N8": "1"}
KEY = "w" * 32


@pytest.fixture
def client(app_mod):
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers=H).status_code == 200
        yield c


def fake_system(summary, key=KEY):
    """A system that answers like HBlink4 / Crosslink / Hotspot: the real encryption, without network."""
    replay = n8feed.Replay()

    def fetch(url, k, timeout=12, agent=""):
        rid = secrets.token_hex(8)
        req = n8feed.seal({"path": n8feed.PATH, "ts": time.time(), "id": rid, "data": {}}, k)
        try:
            ans = n8feed.answer_request(req, key, replay, lambda: summary)
        except n8feed.FeedError as e:
            raise n8feed.FeedError(f"refused: {e}")
        out = n8feed.unseal(ans, k)
        assert out["id"] == rid
        return out["data"]
    return fetch


def test_builtin_widgets_and_order(client):
    w = client.get("/api/admin/portal/widgets").json()["widgets"]
    assert [x["kind"] for x in w] == ["frn_today", "frn_rooms", "frn_connect"]
    assert client.delete(f"/api/admin/portal/widgets/{w[0]['id']}", headers=H).status_code == 400   # only switched off
    ids = [w[2]["id"], w[0]["id"], w[1]["id"]]
    assert client.post("/api/admin/portal/widgets/order", json={"ids": ids}, headers=H).status_code == 200
    assert [x["kind"] for x in client.get("/api/portal").json()["widgets"]] == ["frn_connect", "frn_today", "frn_rooms"]
    client.post("/api/admin/portal/widgets", json={"id": w[1]["id"], "enabled": False}, headers=H)
    assert "frn_rooms" not in [x["kind"] for x in client.get("/api/portal").json()["widgets"]]


def test_remote_widget_fetch_cache_and_public(client, monkeypatch):
    s = n8feed.summary("hblink4", "DMR Die N8schicht", "1.19.0", "ok", "", [("Repeaters & hotspots", 7), ("Calls today", 42)],
                       [{"call": "DL1ABC", "name": "Hans", "where": "TG 2623"}],
                       [{"call": f"DO{i}XX", "name": "", "where": "TG 262", "ts": time.time() - i * 60, "duration": 3} for i in range(8)])
    monkeypatch.setattr(n8feed, "fetch", fake_system(s))
    # validation
    assert client.post("/api/admin/portal/widgets", json={"kind": "hblink4", "url": "ftp://x", "key": KEY}, headers=H).status_code == 400
    assert client.post("/api/admin/portal/widgets", json={"kind": "hblink4", "url": "https://dmr.example.org", "key": "kurz"}, headers=H).status_code == 400
    r = client.post("/api/admin/portal/widgets", json={"kind": "hblink4", "url": "https://dmr.example.org", "key": KEY, "lh_count": 3,
                                                       "link": "https://dmr.example.org"}, headers=H).json()
    assert r["widget"]["test"]["ok"] and r["widget"]["key_set"] and "key" not in r["widget"]
    pub = client.get("/api/portal").json()["widgets"][-1]
    assert pub["kind"] == "hblink4" and pub["data"]["kpis"][0] == {"label": "Repeaters & hotspots", "value": "7"}
    assert len(pub["data"]["last_heard"]) == 3 and not pub["stale"] and "url" not in pub and "key" not in str(pub)
    # the key is never shown again; saving without key keeps it
    wid = r["widget"]["id"]
    assert client.post("/api/admin/portal/widgets", json={"id": wid, "url": "https://dmr.example.org", "key": "", "title": "DMR"}, headers=H).status_code == 200
    assert KEY not in client.get("/api/admin/portal/widgets").text
    # wrong key on the system: error kept, old data stays in the cache
    monkeypatch.setattr(n8feed, "fetch", fake_system(s, key="z" * 32))
    t = client.post(f"/api/admin/portal/widgets/{wid}/test", json={}, headers=H).json()
    assert not t["ok"] and "wrong sync key" in t["error"]
    w = [x for x in client.get("/api/admin/portal/widgets").json()["widgets"] if x["id"] == wid][0]
    assert w["error"] and w["data"]["title"] == "DMR Die N8schicht"
    assert client.delete(f"/api/admin/portal/widgets/{wid}", headers=H).status_code == 200


def test_hotspot_only_in_the_lan(client):
    r = client.post("/api/admin/portal/widgets", json={"kind": "hotspot", "url": "http://8.8.8.8", "key": KEY}, headers=H)
    assert r.status_code == 400 and "local network" in r.json()["error"]
    with pytest.raises(widgets.WidgetError):
        widgets.check_url("http://8.8.4.4:8080", "gateway")
    assert widgets.check_url("http://192.168.79.150/", "hotspot") == "http://192.168.79.150"
    assert widgets.check_url("https://dmr.example.org", "hblink4")


def test_summary_is_clean():
    s = n8feed.summary("crosslink", "X" * 200, "1.0", "weird", "", [(f"k{i}", i) for i in range(9)], [], [{"call": "A", "ts": "x"}])
    assert len(s["title"]) == 80 and s["status"] == "warn" and len(s["kpis"]) == 4 and s["last_heard"][0]["ts"] == 0.0
