"""HobbyRadioPortal on the same server (since 2.11.0): no token – direct calls from this machine count as the portal."""
import pytest
from fastapi.testclient import TestClient

from tests.test_api import H, client, login  # noqa: F401  (fixture)

P = {"X-HobbyRadioPortal": "1", "X-N8": "1", "X-Portal-User": "dirk<x>"}


@pytest.fixture()
def local(app_mod):
    """Client that connects like the portal: from 127.0.0.1 to http://127.0.0.1:PORT/."""
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app, base_url="http://127.0.0.1:8090", client=("127.0.0.1", 50000)) as c:
        yield c


def test_portal_allowed_paths(local):
    assert local.get("/api/admin/settings", headers=P).status_code == 200
    r = local.get("/api/admin/rooms", headers=P).json()
    rid = r["rooms"][1]["id"]
    assert local.patch(f"/api/admin/rooms/{rid}", json={"values": {"tot": 120}}, headers=P).status_code == 200
    r = local.post("/api/admin/settings", json={"changes": {"dashboard.title": "Portal-Test"}}, headers=P).json()
    assert r["changed"] == ["dashboard.title"]
    assert local.get("/api/admin/acl", headers=P).status_code == 200
    log = local.get("/api/admin/audit", headers=P).json()["entries"]
    assert any(e["username"] == "portal (dirkx)" and e["action"] == "settings_changed" for e in log)


def test_portal_forbidden_paths(local):
    for p in ("/api/admin/users", "/api/admin/sessions", "/api/admin/accounts", "/api/admin/system", "/api/admin/updates", "/api/admin/logs"):
        assert local.get(p, headers=P).status_code in (401, 403), p
    assert local.post("/api/admin/settings", json={"changes": {"https.enabled": True}}, headers=P).status_code == 403
    assert local.post("/api/auth/password", json={"old": "a", "new": "b"}, headers=P).status_code in (401, 403)
    assert local.get("/api/admin/api-tokens", headers=P).status_code == 404          # gibt es nicht mehr


@pytest.mark.parametrize("extra", [{"X-Forwarded-For": "203.0.113.9"}, {"X-Real-IP": "203.0.113.9"}, {"Forwarded": "for=203.0.113.9"},
                                   {"Via": "1.1 nginx"}, {"Host": "frn.example.org"}])
def test_proxied_requests_are_never_the_portal(local, extra):
    """nginx/Caddy also connect from 127.0.0.1 – any proxy header (or a public Host) means: not the portal."""
    assert local.get("/api/admin/settings", headers={**P, **extra}).status_code == 401


def test_only_with_marker_and_from_loopback(local, client):
    assert local.get("/api/admin/settings", headers={"X-N8": "1"}).status_code == 401              # ohne Portal-Kennung
    assert client.get("/api/admin/settings", headers=P).status_code == 401                         # anderer Rechner
    p2 = dict(P)
    p2.pop("X-N8")
    assert local.post("/api/admin/settings", json={"changes": {}}, headers=p2).status_code == 403  # CSRF-Kopf bleibt Pflicht


def test_switch_off(local, monkeypatch, app_mod):
    monkeypatch.setattr(app_mod, "PORTAL_LOCAL", False)
    assert local.get("/api/admin/settings", headers=P).status_code == 401


def test_cli_for_the_portal_installer(tmp_path, monkeypatch, capsys):
    """HobbyRadioPortal-Installer: eigenes HTTPS aus (nginx des Portals übernimmt 80/443) – ein Token braucht es nicht mehr."""
    import json, sys
    monkeypatch.setenv("FRNADN_DATA", str(tmp_path))
    from frnadn import __main__ as m
    c = m._ctx()
    c.settings.update({"https.enabled": True, "https.domain": "frn.example.org", "https.email": "a@example.org"}, "test")
    monkeypatch.setattr(sys, "argv", ["frnadn", "behind-proxy"])
    assert m.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["https_was"] and out["domain"] == "frn.example.org"
    assert m._ctx().settings.get("https.enabled") is False
