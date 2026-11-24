"""API tokens for the HobbyRadioPortal: what a token may and may not do."""
from fastapi.testclient import TestClient

from tests.test_api import H, client, login  # noqa: F401  (fixture)


def _token(c):
    login(c)
    t = c.post("/api/admin/api-tokens", json={"name": "HobbyRadioPortal"}, headers=H).json()["token"]
    c.post("/api/auth/logout", headers=H)
    c.cookies.clear()
    assert t["token"].startswith("frn_") and t["hint"] == t["token"][-4:]
    return {"Authorization": "Bearer " + t["token"], "X-N8": "1", "X-Portal-User": "dirk<x>"}


def test_token_allowed_paths(client):
    T = _token(client)
    assert client.get("/api/admin/settings", headers=T).status_code == 200
    r = client.get("/api/admin/rooms", headers=T).json()
    rid = r["rooms"][1]["id"]
    assert client.patch(f"/api/admin/rooms/{rid}", json={"values": {"tot": 120}}, headers=T).status_code == 200
    r = client.post("/api/admin/settings", json={"changes": {"dashboard.title": "Portal-Test"}}, headers=T).json()
    assert r["changed"] == ["dashboard.title"]
    assert client.get("/api/admin/acl", headers=T).status_code == 200
    log = client.get("/api/admin/audit", headers=T).json()["entries"]
    assert any(e["username"] == "api:HobbyRadioPortal (dirkx)" and e["action"] == "settings_changed" for e in log)


def test_token_forbidden(client):
    T = _token(client)
    for p in ("/api/admin/users", "/api/admin/sessions", "/api/admin/accounts", "/api/admin/api-tokens", "/api/admin/system",
              "/api/admin/updates", "/api/admin/logs"):
        assert client.get(p, headers=T).status_code in (401, 403), p
    assert client.post("/api/admin/api-tokens", json={"name": "x2"}, headers=T).status_code in (401, 403)
    assert client.post("/api/admin/settings", json={"changes": {"https.enabled": True}}, headers=T).status_code == 403
    assert client.post("/api/auth/password", json={"old": "a", "new": "b"}, headers=T).status_code in (401, 403)
    assert client.get("/api/admin/settings", headers={"Authorization": "Bearer frn_wrong"}).status_code == 401
    T2 = dict(T)
    T2.pop("X-N8")
    assert client.post("/api/admin/settings", json={"changes": {}}, headers=T2).status_code == 403


def test_revoke(client):
    T = _token(client)
    login(client)
    tid = client.get("/api/admin/api-tokens").json()["tokens"][0]["id"]
    assert client.delete(f"/api/admin/api-tokens/{tid}", headers=H).json()["ok"]
    client.cookies.clear()
    assert client.get("/api/admin/settings", headers=T).status_code == 401
