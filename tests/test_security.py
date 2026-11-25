"""Hardening (N8 security), N8 Admin (update, permissions, sudo, services) and N8 Kit files."""
import asyncio
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from frnadn import n8_security

ROOT = Path(__file__).resolve().parent.parent


def test_api_docs_off(app_mod):
    with TestClient(app_mod.app) as c:
        for p in ("/docs", "/redoc", "/openapi.json"):
            r = c.get(p)
            assert r.status_code != 200 or "swagger" not in r.text.lower() and '"paths"' not in r.text, p


def test_security_headers(app_mod):
    with TestClient(app_mod.app) as c:
        h = c.get("/api/info").headers
        csp = h["content-security-policy"]
        for part in ("default-src 'self'", "object-src 'none'", "base-uri 'self'", "frame-ancestors 'self'", "form-action 'self'"):
            assert part in csp
        assert "camera=()" in h["permissions-policy"]
        assert h["x-frame-options"] == "SAMEORIGIN" and h["x-content-type-options"] == "nosniff"
        assert "strict-transport-security" not in h and "server" not in h
        assert "max-age" in c.get("/api/info", headers={"X-Forwarded-Proto": "https"}).headers["strict-transport-security"]


def test_uvicorn_without_server_header(app_mod):
    srv = app_mod._Server.make(app_mod.app, host="127.0.0.1", port=1)
    assert srv.config.server_header is False
    assert n8_security.UVICORN_KWARGS == {"server_header": False}


def test_n8_admin_wired():
    """Update, Rechte-Check und sudo laufen über scripts/n8-admin.sh – ohne den alten update guard."""
    unit = (ROOT / "systemd" / "frnadn.service").read_text()
    assert "n8-update-guard" not in unit
    upd = (ROOT / "scripts" / "update.sh").read_text()
    assert 'n8-admin.sh" update' in upd
    conf = (ROOT / "scripts" / "n8-admin.conf").read_text()
    assert "N8_ID=frnadn" in conf and "frn-server.service" in conf
    for f in ("n8-admin.sh", "update.sh", "install.sh"):
        assert subprocess.run(["bash", "-n", str(ROOT / "scripts" / f)]).returncode == 0
    assert 'n8-admin.sh" fix-perms' in (ROOT / "scripts" / "install.sh").read_text()


def test_services_and_perms_api(app_mod, tmp_path):
    import json
    data = app_mod.DATA
    (data / "n8-admin.json").write_text(json.dumps({"self": "/x/n8-admin.sh", "systemctl": "/bin/systemctl", "request": str(data / "update.request"),
        "log": str(data / "update.log"), "result": str(data / "update.result"),
        "units": [{"unit": "frnadn.service", "label": "Dashboard", "actions": ["start", "stop", "restart", "enable", "disable"]}]}))
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        assert c.get("/api/admin/services").status_code in (401, 403)
        assert c.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers={"X-N8": "1"}).status_code == 200
        d = c.get("/api/admin/services").json()
        assert d["units"][0]["unit"] == "frnadn.service" and d["units"][0]["active"] == "active"      # Demo
        r = c.post("/api/admin/services/frnadn.service/stop", headers={"X-N8": "1"}).json()
        assert r["ok"] and r["units"][0]["active"] == "inactive"
        assert c.post("/api/admin/services/sshd.service/stop", headers={"X-N8": "1"}).status_code == 400
        assert c.post("/api/admin/services/frnadn.service/mask", headers={"X-N8": "1"}).status_code == 400
        assert c.get("/api/admin/perms").json()["ok"]
        assert c.get("/api/admin/update-log").json()["ready"]
        # Keep-Alive: von Hand gestoppt → Halt-Marke, Einstellungen, Health nur lokal
        assert (data / "keepalive.hold" / "frnadn.service").exists()
        k = c.post("/api/admin/keepalive", json={"heartbeat_url": "https://hc-ping.com/a-1"}, headers={"X-N8": "1"}).json()
        assert k["conf"]["heartbeat_url"] == "https://hc-ping.com/a-1"
        assert c.post("/api/admin/keepalive", json={"heartbeat_url": "https://x/`id`"}, headers={"X-N8": "1"}).status_code == 400
        assert c.get("/api/n8/health").status_code == 403
        # Abstürze (N8 Kit 1.3): Liste, Protokoll, gelesen
        d = c.get("/api/admin/crashes").json()
        assert d["items"] and d["unacked"] == len(d["items"])
        assert c.get("/api/admin/crashes/" + d["items"][0]["id"]).json()["log"]
        assert c.get("/api/admin/crashes/..%2Fx").status_code == 404
        assert c.post("/api/admin/crashes/ack", json={"all": True}, headers={"X-N8": "1"}).json()["unacked"] == 0
        assert c.post("/api/admin/crashes/delete", json={"all": True}, headers={"X-N8": "1"}).json()["total"] == 0
    conf = (ROOT / "scripts" / "n8-admin.conf").read_text()
    assert "N8_KA_CHECKS=" in conf and "frn-server.service|tcp|" in conf


def test_kit_files_loaded():
    html = (ROOT / "static" / "index.html").read_text()
    for f in ("/static/n8-kit.css", "/static/n8-kit.js", "/static/i18n-app.js", 'id="updateBanner"'):
        assert f in html
    assert "'Last heard': 'Zuletzt gehört'" in (ROOT / "static" / "i18n-app.js").read_text()
