"""Backup and restore of adn-frn-server."""
import json
import sqlite3
import tarfile

import pytest

from frnadn import backup as bk, n8mig


def _install(tmp_path):
    data = tmp_path / "data"
    home = data / "frn"
    (home / "acl").mkdir(parents=True)
    (home / "logs").mkdir()
    (home / "server.properties").write_text("server_port=10024\n")
    (home / "acl" / "AdminList01.xml").write_text("<xml/>")
    (home / "logs" / "server.log").write_text("log must not be in the backup")
    (data / "branding").mkdir()
    (data / "branding" / "logo.png").write_bytes(b"\x89PNG")
    (data / "letsencrypt").mkdir()
    (data / "letsencrypt" / "key.pem").write_text("secret, not in the backup")
    con = sqlite3.connect(str(data / "frnadn.db"))
    con.executescript("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT); CREATE TABLE rooms(id INTEGER);"
                      "CREATE TABLE users(id INTEGER); CREATE TABLE sessions(id INTEGER);"
                      "INSERT INTO settings VALUES('dashboard.title','\"Auf der NachtSchicht\"'); INSERT INTO rooms VALUES(1),(2);"
                      "INSERT INTO users VALUES(1); INSERT INTO sessions VALUES(7);")
    con.commit()
    con.close()
    return data, home


def test_create_check_apply_roundtrip(tmp_path):
    data, home = _install(tmp_path)
    with pytest.raises(bk.BackupError):
        bk.create(data, home, "short", "boss")
    p = bk.create(data, home, "lang-genug-123", "boss")
    assert p.parent == data / "backups" and p.read_bytes().startswith(n8mig.MAGIC)
    assert bk.listing(data / "backups")[0]["name"] == p.name
    with pytest.raises(bk.BackupError, match="Wrong password"):
        bk.open_backup(p, "falsches-passwort", tmp_path / "x.tar")
    m = bk.open_backup(p, "lang-genug-123", tmp_path / "x.tar")
    assert m["format"] == bk.FORMAT and m["title"] == "Auf der NachtSchicht" and m["counts"]["rooms"] == 2
    with tarfile.open(tmp_path / "x.tar") as t:
        names = t.getnames()
    assert "frn/server.properties" in names and "data/branding/logo.png" in names and "data/frnadn.db" in names
    assert not any("logs" in n or "letsencrypt" in n or "backups" in n for n in names)
    # change the installation, then restore
    (home / "server.properties").write_text("server_port=1\n")
    sqlite3.connect(str(data / "frnadn.db")).executescript("DELETE FROM rooms;")
    res = bk.apply(tmp_path / "x.tar", data, home)
    assert (home / "server.properties").read_text() == "server_port=10024\n"
    con = sqlite3.connect(str(data / "frnadn.db"))
    assert con.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0          # everybody logs in again
    assert (home / "logs" / "server.log").exists()                                   # logs stay
    assert (tmp_path / "data" / res["kept"].split("/")[-1] / "frn" / "server.properties").read_text() == "server_port=1\n"


def test_unsafe_archive_rejected(tmp_path):
    import io
    t = tmp_path / "evil.tar"
    with tarfile.open(t, "w:gz") as tar:
        for name, data in (("manifest.json", json.dumps({"format": bk.FORMAT}).encode()), ("data/frnadn.db", b"x"), ("../etc/passwd", b"x")):
            ti = tarfile.TarInfo(name); ti.size = len(data); tar.addfile(ti, io.BytesIO(data))
    with pytest.raises(bk.BackupError, match="Unsafe"):
        bk.check_tar(t)


def test_pending_restore_at_start(tmp_path):
    data, home = _install(tmp_path)
    p = bk.create(data, home, "lang-genug-123", "boss")
    bk.open_backup(p, "lang-genug-123", data / bk.PENDING)
    (home / "server.properties").write_text("changed\n")
    res = bk.apply_pending(data, home)
    assert res["ok"] and not (data / bk.PENDING).exists()
    assert json.loads((data / bk.DONE).read_text())["ok"]
    assert (home / "server.properties").read_text() == "server_port=10024\n"
    assert bk.apply_pending(data, home) is None
