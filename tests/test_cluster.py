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
