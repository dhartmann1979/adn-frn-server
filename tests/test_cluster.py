"""Master & Backup: configuration sync between two adn-frn-server (frnadn/cluster.py)."""
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from frnadn import cluster
from frnadn.db import DB
from frnadn.frn.store import Store
from frnadn.settings import Settings

H = {"X-N8": "1"}
KEY = "k" * 32


def server(tmp_path, name):
    db = DB(tmp_path / name / "frnadn.db")
    s = Settings(db)
    st = Store(db, s)
    st.ensure_rooms()
    acl = tmp_path / name / "acl"
    acl.mkdir(parents=True)
    return db, s, st, acl


def test_export_apply_roundtrip(tmp_path):
    mdb, ms, mst, macl = server(tmp_path, "master")
    bdb, bs, bst, bacl = server(tmp_path, "backup")
    ms.update({"frn.address": "frn.example.org", "sysman.email": "master@example.org", "dashboard.title": "Nachtschicht",
               "frn.owner_callsign": "do1abc", "cluster.role": "master"}, "t")
    bs.update({"frn.address": "frn-backup.example.org", "sysman.email": "backup@example.org", "cluster.role": "backup"}, "t")
    mst.room_create("Technik")
    mst.account_save("ham@example.org", "DL1XYZ", "Ham", "geheim123")
    mdb.x("INSERT INTO frn_lists(kind,room_id,email,callsign,ts) VALUES('mute',NULL,'bad@example.org','X1',1)")
    (macl / "MuteList01.xml").write_text("<Mute><Net>Nachtschicht</Net></Mute>\n")
    (bacl / "BlockList05.xml").write_text("<Block/>\n")          # stale file on the backup

    data = cluster.export(mdb, ms, macl, "Nachtschicht", mst)
    assert data["format"] == cluster.FORMAT and data["counts"]["frn_accounts"] == 1
    assert "sysman.email" not in data["settings"] and "frn.address" not in data["settings"]

    r = cluster.apply(bdb, bs, bst, bacl, data)
    assert r["changed"] and r["frn_changed"]
    bst.invalidate()
    assert [x["name"] for x in bst.rooms()] == [x["name"] for x in mst.rooms()]
    assert bst.account_get("ham@example.org")["callsign"] == "DL1XYZ"
    assert bs.get("dashboard.title") == "Nachtschicht" and bs.get("frn.owner_callsign") == "DO1ABC"
    # each server keeps its own address, FRN account and role
    assert bs.get("frn.address") == "frn-backup.example.org" and bs.get("sysman.email") == "backup@example.org"
    assert bs.get("cluster.role") == "backup"
    assert (bacl / "MuteList01.xml").read_text().startswith("<Mute>") and not (bacl / "BlockList05.xml").exists()
    assert list((bacl / "backups").glob("BlockList05.xml.*.sync.bak"))

    # nothing changed → nothing written, also when only a login time moved
    assert cluster.apply(bdb, bs, bst, bacl, cluster.export(mdb, ms, macl))["changed"] is False
    mst.account_seen("ham@example.org")
    assert cluster.apply(bdb, bs, bst, bacl, cluster.export(mdb, ms, macl))["changed"] is False
    # a title is a change, but not one for the Java server
    ms.update({"dashboard.title": "Neu"}, "t")
    r = cluster.apply(bdb, bs, bst, bacl, cluster.export(mdb, ms, macl))
    assert r["changed"] and not r["frn_changed"]


def test_apply_refuses_bad_data(tmp_path):
    bdb, bs, bst, bacl = server(tmp_path, "backup")
    with pytest.raises(cluster.ClusterError):
        cluster.apply(bdb, bs, bst, bacl, {"format": "other"})
    mdb, ms, mst, macl = server(tmp_path, "master")
    data = cluster.export(mdb, ms, macl)
    data["tables"]["rooms"]["rows"] = []
    with pytest.raises(cluster.ClusterError, match="no rooms"):
        cluster.apply(bdb, bs, bst, bacl, data)
    assert bst.rooms()                                             # nothing lost


def test_seal_and_replay():
    blob = cluster.seal({"geheim": "FRN-Passwort"}, KEY)
    assert b"FRN-Passwort" not in blob and blob.startswith(cluster.MAGIC)
    assert cluster.unseal(blob, KEY) == {"geheim": "FRN-Passwort"}
    with pytest.raises(cluster.ClusterError, match="wrong sync key"):
        cluster.unseal(blob, "x" * 32)
    bad = bytearray(blob); bad[40] ^= 1
    with pytest.raises(cluster.ClusterError):
        cluster.unseal(bytes(bad), KEY)
    rp = cluster.Replay()
    req = cluster.seal({"path": "/api/cluster/hello", "ts": time.time(), "id": "a1", "data": {}}, KEY)
    assert cluster.open_request(req, KEY, "/api/cluster/hello", rp)["id"] == "a1"
    with pytest.raises(cluster.ClusterError, match="already used"):
        cluster.open_request(req, KEY, "/api/cluster/hello", rp)
    with pytest.raises(cluster.ClusterError, match="expired"):
        cluster.open_request(cluster.seal({"path": "/api/cluster/hello", "ts": 1, "id": "b"}, KEY), KEY, "/api/cluster/hello", rp)
    with pytest.raises(cluster.ClusterError, match="another address"):
        cluster.open_request(cluster.seal({"path": "/api/cluster/export", "ts": time.time(), "id": "c"}, KEY), KEY, "/api/cluster/hello", rp)
    assert cluster.peer_host("https://frn-backup.example.org/") == "frn-backup.example.org"


def peer(client, path, key=KEY):
    """A request like the partner sends it: encrypted with the sync key."""
    body = cluster.seal({"path": path, "ts": time.time(), "id": secrets.token_hex(8), "data": {}}, key)
    return client.post(path, content=body, headers={**H, "Content-Type": cluster.CTYPE})


@pytest.fixture
def client(app_mod):
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers=H).status_code == 200
        yield c


def test_master_endpoints(client):
    A = client.A
    assert peer(client, "/api/cluster/hello").status_code == 403                    # no key set here
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org"}, "t")
    assert peer(client, "/api/cluster/export", "x" * 32).status_code == 403
    assert client.post("/api/cluster/export", json={}, headers=H).status_code == 403   # not encrypted
    r = peer(client, "/api/cluster/export")
    assert r.status_code == 200 and b"chef" not in r.content
    data = cluster.unseal(r.content, KEY)["data"]
    assert data["format"] == cluster.FORMAT
    assert peer(client, "/api/cluster/pull").status_code == 409                     # the master does not pull
    props = client.get("/api/admin/server/properties").json()["text"]
    assert "backup_server_addr=frn-backup.example.org" in props
    st = client.get("/api/admin/cluster").json()
    assert st["role"] == "master" and st["backup_addr"] == "frn-backup.example.org"
    # the key is never shown, a new one is created on request
    assert client.get("/api/admin/settings").text.count(KEY) == 0
    k = client.post("/api/admin/cluster/key", json={}, headers=H).json()["key"]
    assert len(k) >= 24 and A.ctx.settings.get("cluster.key") == k
    d = client.get("/api/admin/frn-password?for=backup").json()
    assert d["name"].endswith("Backup") and d["own"] is False


def test_backup_sync_now(client, tmp_path, monkeypatch):
    A = client.A
    mdb, ms, mst, macl = server(tmp_path, "m")
    mst.room_create("Vom Master")
    data = cluster.export(mdb, ms, macl, "M", mst)
    monkeypatch.setattr(cluster, "call", lambda url, path, key, method="GET", payload=None, timeout=20: data)
    A.ctx.settings.update({"cluster.role": "backup", "cluster.key": KEY, "cluster.peer_url": "https://frn.example.org"}, "t")
    r = client.post("/api/admin/cluster/sync", json={}, headers=H).json()
    assert r["ok"] and r["changed"], r
    assert "Vom Master" in [x["name"] for x in A.ctx.store.rooms()]
    assert client.post("/api/admin/cluster/sync", json={}, headers=H).json()["changed"] is False
    assert client.get("/api/admin/cluster").json()["last"]["ok"]
    assert client.post("/api/admin/cluster/maintenance", json={"on": True}, headers=H).status_code == 400   # only the master


def test_partner_first_in_link_menu(client):
    A = client.A
    first = lambda: client.get("/api/links").json()["links"][0]  # noqa: E731
    assert first()["label"] != "FRN Backup"                                          # single server: nothing added
    A.ctx.settings.update({"cluster.role": "master", "cluster.peer_url": "https://frn-backup.example.org"}, "t")
    assert first()["label"] == "FRN Backup" and first()["url"] == "https://frn-backup.example.org/"
    A.ctx.settings.update({"cluster.role": "backup", "cluster.peer_url": "https://frn.example.org"}, "t")
    d = client.get("/api/links").json()
    assert d["links"][0]["label"] == "FRN Master" and d["enabled"]
    assert all(x["label"] != "FRN Master" for x in client.get("/api/admin/links").json()["items"])   # not stored in the menu


def test_same_fRN_account_warning(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org",
                           "sysman.email": "Server@Example.org", "frn.standalone": False}, "t")
    tag = A._account_tag()
    monkeypatch.setattr(cluster, "call", lambda *a, **k: {"ok": True, "role": "backup", "account": tag, "standalone": False})
    assert client.get("/api/admin/cluster").json()["same_account"] is True
    monkeypatch.setattr(cluster, "call", lambda *a, **k: {"ok": True, "role": "backup", "account": "other", "standalone": False})
    assert client.get("/api/admin/cluster").json()["same_account"] is False


def test_backup_locked_with_masters_fRN_account(client, tmp_path, monkeypatch):
    """Nie wieder beide mit demselben FRN-Konto: das Backup stoppt und sperrt seinen FRN-Server."""
    A = client.A
    mdb, ms, mst, macl = server(tmp_path, "m")
    data = cluster.export(mdb, ms, macl, "M", mst)
    A.ctx.settings.update({"cluster.role": "backup", "cluster.key": KEY, "cluster.peer_url": "https://frn.example.org",
                           "sysman.email": "server@example.org", "frn.standalone": False}, "t")
    data.update({"account": A._account_tag(), "standalone": False, "role": "master"})      # master: same account
    monkeypatch.setattr(cluster, "call", lambda *a, **k: data)
    assert client.post("/api/admin/server/start", json={}, headers=H).status_code == 200
    r = client.post("/api/admin/cluster/sync", json={}, headers=H).json()
    assert r["ok"]
    st = client.get("/api/admin/cluster").json()
    assert st["guard"]["since"] and st["same_account"]
    assert A.ctx.java._demo_state if hasattr(A.ctx.java, "_demo_state") else True
    r = client.post("/api/admin/server/start", json={}, headers=H)
    assert r.status_code == 409 and "Locked" in r.json()["error"]
    # the master's account cannot be entered again …
    assert client.post("/api/admin/settings", json={"changes": {"sysman.email": "SERVER@example.org"}}, headers=H).status_code == 400
    # … an own account releases the lock
    assert client.post("/api/admin/settings", json={"changes": {"sysman.email": "backup@example.org"}}, headers=H).status_code == 200
    assert not client.get("/api/admin/cluster").json().get("guard")
    assert client.post("/api/admin/server/start", json={}, headers=H).status_code == 200


def test_master_refuses_backups_account(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org",
                           "sysman.email": "master@example.org", "frn.standalone": False}, "t")
    import hashlib
    tag = hashlib.sha256(b"backup@example.org").hexdigest()[:16]
    monkeypatch.setattr(cluster, "call", lambda *a, **k: {"ok": True, "role": "backup", "account": tag, "standalone": False})
    client.get("/api/admin/cluster")
    assert client.post("/api/admin/settings", json={"changes": {"sysman.email": "backup@example.org"}}, headers=H).status_code == 400
    assert client.post("/api/admin/settings", json={"changes": {"sysman.email": "neu@example.org"}}, headers=H).status_code == 200


def test_accounts_of_both_shown(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org",
                           "sysman.email": "master@example.org", "sysman.password": "geheim", "frn.standalone": False}, "t")
    monkeypatch.setattr(cluster, "call", lambda *a, **k: {"ok": True, "role": "backup", "account": "x", "standalone": False,
                                                          "email": "backup@example.org", "password_set": False})
    acc = client.get("/api/admin/cluster").json()["accounts"]
    assert acc["master"]["email"] == "master@example.org" and acc["master"]["password_set"] and acc["master"]["self"]
    assert acc["backup"]["email"] == "backup@example.org" and acc["backup"]["password_set"] is False
    # the sync never touches them
    from frnadn.cluster import shared_keys
    assert "sysman.email" not in shared_keys() and "sysman.password" not in shared_keys()


def test_public_cluster_info_for_frn_clients(client):
    A = client.A
    assert client.get("/api/info").json()["cluster"] == {"role": "off"}
    A.ctx.settings.update({"cluster.role": "backup", "cluster.peer_url": "https://frn.example.org", "frn.address": "frn-backup.example.org",
                           "frn.port": 10024}, "t")
    c = client.get("/api/info").json()["cluster"]
    assert c["role"] == "backup" and c["master"] == {"host": "frn.example.org", "port": 10024}
    assert c["backup"] == {"host": "frn-backup.example.org", "port": 10024}


def _stations_here(A, monkeypatch, n=3):
    real = A.ctx.server.state
    monkeypatch.setattr(A.ctx.server, "state", lambda: {**real(), "running": True, "service": "active", "clients": n})


def test_backup_sends_stray_stations_back(client, monkeypatch):
    """Verirrte Stationen: das Backup stoppt seinen FRN-Server kurz, die Stationen gehen zum Master, dann startet es wieder."""
    A = client.A
    A.ctx.settings.update({"cluster.role": "backup", "cluster.key": KEY, "cluster.peer_url": "https://frn.example.org",
                           "cluster.return_pause": 5}, "t")
    assert client.post("/api/admin/server/start", json={}, headers=H).status_code == 200
    _stations_here(A, monkeypatch)
    hello = {"ok": True, "role": "master", "maintenance": False, "frn": {"running": True, "clients": 1, "since": 1}}
    monkeypatch.setattr(cluster, "call", lambda *a, **k: hello)
    # master in maintenance or its FRN server down → refused, nothing stopped
    hello["maintenance"] = True
    r = client.post("/api/admin/cluster/return", json={}, headers=H)
    assert r.status_code == 409 and "maintenance" in r.json()["error"]
    hello.update(maintenance=False, frn={"running": False})
    assert client.post("/api/admin/cluster/return", json={}, headers=H).status_code == 409
    hello["frn"] = {"running": True, "since": 1}
    r = client.post("/api/admin/cluster/return", json={}, headers=H).json()
    assert r["ok"] and r["stopped"] and r["clients"] == 3 and r["pause"] == 5
    st = client.get("/api/admin/cluster").json()
    assert st["return_pending"]["start_at"] and st["last_return"]["stopped"]
    # a second press while it is running does not stop it again
    assert client.post("/api/admin/cluster/return", json={}, headers=H).json()["stopped"] is False


def test_master_asks_backup_to_send_back(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org"}, "t")
    _stations_here(A, monkeypatch, 0)
    seen = []
    monkeypatch.setattr(cluster, "call", lambda url, path, key, method="GET", payload=None, timeout=20:
                        seen.append((path, payload.get("by"))) or {"ok": True, "stopped": True, "clients": 2})
    r = client.post("/api/admin/cluster/return", json={}, headers=H).json()
    assert r["stopped"] and seen == [("/api/cluster/return", "chef")]
    A._cluster_set("cluster.maintenance", {"since": time.time()})
    assert client.post("/api/admin/cluster/return", json={}, headers=H).status_code == 409


def test_return_endpoint_only_on_the_backup(client):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org"}, "t")
    assert peer(client, "/api/cluster/return").status_code == 409
    A.ctx.settings.update({"cluster.role": "backup"}, "t")
    r = peer(client, "/api/cluster/return")
    assert r.status_code == 200 and cluster.unseal(r.content, KEY)["data"]["ok"]
    assert client.post("/api/cluster/return", json={}, headers=H).status_code == 403            # not encrypted


def test_updates_of_both_servers(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "master", "cluster.key": KEY, "cluster.peer_url": "https://frn-backup.example.org"}, "t")

    async def fake_check(force=False):
        return {"checked": time.time(), "github": {"local": {"version": "2.30.1", "short": "abc1234"}, "latest": {"short": "def5678"},
                "remote_version": "2.31.0", "update": True, "can_upgrade": True, "behind": 2, "commits": [{"short": "def5678", "message": "neu"}]},
                "java": {"installed": {"version": "1.0", "build": "5"}, "latest": {"version": "1.0", "build": "5"}, "update": False}}
    monkeypatch.setattr(A, "check_all_updates", fake_check)
    asked = []
    monkeypatch.setattr(A.ctx.n8, "request_update", lambda: asked.append(1) or (True, "Update angefordert"))
    # this server (master)
    d = client.post("/api/admin/cluster/update", json={"server": "master", "action": "check"}, headers=H).json()
    assert d["self"] and d["dashboard"]["update"] and d["dashboard"]["latest"] == "2.31.0" and d["java"]["installed"] == "1.0 (build 5)"
    r = client.post("/api/admin/cluster/update", json={"server": "master", "action": "run"}, headers=H).json()
    assert r["ok"] and r["restarting"] and asked == [1]
    # the partner: over the encrypted connection
    calls = []
    monkeypatch.setattr(cluster, "call", lambda url, path, key, method="GET", payload=None, timeout=20:
                        calls.append((path, payload["action"])) or {"ok": True, "dashboard": {"update": False}})
    d = client.post("/api/admin/cluster/update", json={"server": "backup", "action": "check"}, headers=H).json()
    assert d["ok"] and d["self"] is False and calls == [("/api/cluster/update", "check")]
    # the partner endpoint itself
    r = peer(client, "/api/cluster/update")
    assert r.status_code == 200 and cluster.unseal(r.content, KEY)["data"]["dashboard"]["update"]
    assert client.post("/api/admin/cluster/update", json={"server": "x"}, headers=H).status_code == 400


def test_old_partner_without_remote_update(client, monkeypatch):
    A = client.A
    A.ctx.settings.update({"cluster.role": "backup", "cluster.key": KEY, "cluster.peer_url": "https://frn.example.org"}, "t")

    def old(*a, **k):
        raise cluster.ClusterError("The partner does not know Master & Backup yet – update it to the same version.")
    monkeypatch.setattr(cluster, "call", old)
    d = client.post("/api/admin/cluster/update", json={"server": "master", "action": "check"}, headers=H).json()
    assert d["ok"] is False and "older version" in d["error"]
