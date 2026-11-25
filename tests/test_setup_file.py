"""Einrichtung aus JSON: frnadn apply-setup (install.sh schreibt das JSON aus den Antworten)."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_apply_setup_file_creates_rooms_settings_and_superadmin(tmp_path):
    data = tmp_path / "data"
    setup = {"settings": {"frn.standalone": True, "frn.address": "frn.example.org", "frn.port": 10024, "frn.owner_callsign": "DO1ABC",
                          "dashboard.title": "Testnetz", "dashboard.public": True},
             "test_room": "Test", "rooms": ["Nachtschicht", "World"], "superadmin": {"username": "sysop", "password": "Lang-genug-123"}}
    f = tmp_path / "setup.json"
    f.write_text(json.dumps(setup))
    env = dict(os.environ, FRNADN_DATA=str(data), FRNADN_FRN_HOME=str(data / "frn"), FRNADN_DEMO="0")
    r = subprocess.run([sys.executable, "-m", "frnadn", "apply-setup", str(f)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    con = sqlite3.connect(str(data / "frnadn.db"))
    rooms = [x[0] for x in con.execute("SELECT name FROM rooms ORDER BY 1")]
    assert set(rooms) >= {"Test", "Nachtschicht", "World"}
    vals = {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM settings")}
    assert vals["dashboard.title"] == "Testnetz" and vals["frn.address"] == "frn.example.org"
    assert con.execute("SELECT role FROM users WHERE username='sysop'").fetchone()[0] == "superadmin"
    assert (data / "frn" / "server.properties").is_file()


def test_install_sh_uses_apply_setup():
    s = (ROOT / "scripts" / "install.sh").read_text()
    assert "FRNADN_SETUP_FILE" not in s and "run_app apply-setup /tmp/frnadn-setup.json" in s
    assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / "install.sh")]).returncode == 0
