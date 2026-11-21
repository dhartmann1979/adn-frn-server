import pytest
from fastapi.testclient import TestClient

H = {"X-N8": "1"}


@pytest.fixture
def client(app_mod):
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        yield c


def login(c, user="chef", pw="chef-passwort-1"):
    r = c.post("/api/auth/login", json={"username": user, "password": pw}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_setup_needed_without_superadmin(app_mod):
    with TestClient(app_mod.app) as c:
        assert c.get("/api/info").json()["setup_needed"] is True
        # no factory login exists
        assert c.post("/api/auth/login", json={"username": "admin", "password": "admin"}, headers=H).status_code in (400, 401)


def test_public_endpoints(client):
    i = client.get("/api/info").json()
    assert i["setup_needed"] is False and i["title"] == "Auf der NachtSchicht"
    live = client.get("/api/live").json()
    assert [r["name"] for r in live["rooms"]] == ["Test", "Nachtschicht", "World"]
    assert live["rooms"][0]["id"] == 0 and live["rooms"][0]["parrot"]
    assert client.get("/api/stats?range=7d").status_code == 200


def test_admin_needs_login_and_header(client):
    assert client.get("/api/admin/settings").status_code in (401, 403)
    login(client)
    assert client.post("/api/admin/settings", json={"changes": {}}).status_code == 403   # missing X-N8
    assert client.get("/api/admin/settings").status_code == 200


def test_rooms_crud(client):
    login(client)
    r = client.post("/api/admin/rooms", json={"name": "Technik"}, headers=H).json()
    rid = r["id"]
    assert r["restart_needed"] is True
    r = client.patch(f"/api/admin/rooms/{rid}", json={"values": {"tot": "90", "parrot": True, "owners": "A@example.org",
                                                                 "tg_params": "6000;30000;123:ABC;-100123"}}, headers=H)
    assert r.status_code == 200, r.text
    room = next(x for x in r.json()["rooms"] if x["id"] == rid)
    assert room["tot"] == 90 and room["parrot"] == 1 and room["owners"] == "a@example.org" and room["idx"] == 3
    assert "Technik" in client.A.ctx.server.rooms
    props = client.get("/api/admin/server/properties").json()["text"]
    assert "net03=Technik" in props and "net03_tot=90" in props and "net03_parrot_enable=yes" in props
    assert "net00=Test" in props and "standalone=yes" in props
    assert client.patch(f"/api/admin/rooms/{rid}", json={"values": {"name": "World"}}, headers=H).status_code == 400
    assert client.patch(f"/api/admin/rooms/{rid}", json={"values": {"tg_params": "kaputt"}}, headers=H).status_code == 400
    test = next(x for x in r.json()["rooms"] if x["idx"] == 0)
    assert client.delete(f"/api/admin/rooms/{test['id']}", headers=H).status_code == 400      # net00 stays
    assert client.delete(f"/api/admin/rooms/{rid}", headers=H).status_code == 200
    assert "Technik" not in client.A.ctx.server.rooms


def test_accounts_and_password_file(client):
    login(client)
    assert client.post("/api/admin/accounts", json={"email": "a@example.org", "callsign": "DL1A", "password": "a b"}, headers=H).status_code == 400
    assert client.post("/api/admin/accounts", json={"email": "a@example.org", "callsign": "DL1A", "password": "geheim<1"}, headers=H).status_code == 400
    assert client.post("/api/admin/accounts", json={"email": "a@example.org", "callsign": "dl1a", "name": "Anke",
                                                    "password": "geheim1"}, headers=H).status_code == 200
    acc = client.get("/api/admin/accounts").json()["accounts"]
    assert acc[0]["callsign"] == "DL1A" and "password" not in acc[0]
    xml = (client.A.FRN_HOME / "acl" / "FRNPasswd.xml").read_text()
    assert "<EMailAddress>a@example.org</EMailAddress>" in xml and "<Password>geheim1</Password>" in xml
    assert "<OperatorName>DL1A, Anke</OperatorName>" in xml
    assert client.get("/api/admin/acl").json()["files"] == []


def test_roles(client):
    login(client)
    assert client.post("/api/admin/users", json={"username": "mod", "password": "mod-passwort-1", "role": "admin"}, headers=H).status_code == 200
    assert client.post("/api/admin/users", json={"username": "kurz", "password": "kurz", "role": "user"}, headers=H).status_code == 400
    client.post("/api/auth/logout", json={}, headers=H)
    login(client, "mod", "mod-passwort-1")
    # an admin may not create admins or touch the superadmin
    assert client.post("/api/admin/users", json={"username": "x2", "password": "x2-passwort-1", "role": "admin"}, headers=H).status_code in (400, 403)
    users = client.get("/api/admin/users").json()["users"]
    chef = next(u for u in users if u["username"] == "chef")
    assert chef["role"] == "superadmin"
    assert client.delete(f"/api/admin/users/{chef['id']}", headers=H).status_code in (400, 403)
    assert client.post("/api/admin/power", json={"action": "reboot"}, headers=H).status_code == 403


def test_settings_validation(client):
    login(client)
    assert client.post("/api/admin/settings", json={"changes": {"frn.port": "70000"}}, headers=H).status_code == 400
    r = client.post("/api/admin/settings", json={"changes": {"dashboard.title": "Test"}}, headers=H).json()
    assert r["changed"] == ["dashboard.title"] and r["restart_needed"] is False
    r = client.post("/api/admin/settings", json={"changes": {"frn.standalone": False, "sysman.email": "Me@Example.org",
                                                             "sysman.password": "ABCDEFGH"}}, headers=H).json()
    assert r["restart_needed"] is True
    props = client.get("/api/admin/server/properties").json()["text"]
    assert "standalone" not in props and "sysman_auth_emailaddr=me@example.org" in props
    assert "sysman_auth_password=********" in props                       # masked in the view
    assert "ABCDEFGH" in (client.A.FRN_HOME / "server.properties").read_text()


def test_server_control_demo(client):
    login(client)
    r = client.post("/api/admin/server/restart", json={}, headers=H)
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/api/admin/server/reboot", json={}, headers=H).status_code == 404



def test_dashboard_links_editable_by_admin(client):
    defaults = client.get("/api/links").json()["links"]
    assert defaults and defaults[0]["label"] == "FreeRadioNetwork"
    assert client.get("/api/admin/links").status_code in (401, 403)
    login(client)
    payload = {"links": [{"label": "My FRN page", "url": "https://example.org/frn"},
                         {"label": "GitHub", "url": "https://github.com/"}]}
    saved = client.post("/api/admin/links", json=payload, headers=H)
    assert saved.status_code == 200, saved.text
    assert client.get("/api/links").json()["links"] == payload["links"]
    assert client.post("/api/admin/links", json={"links": [{"label": "bad", "url": "javascript:alert(1)"}]}, headers=H).status_code == 400
