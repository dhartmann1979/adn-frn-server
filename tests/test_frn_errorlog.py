"""Public FRN error log (log.freeradionetwork.de): parse, match to this server, report."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from frnadn import frn_errorlog as el

H = {"X-N8": "1"}
NOW = time.strftime("%Y-%m-%d %H:%M:%S")
SAMPLE = json.dumps({"log": "\n".join([
    "2026-11-25 09:43:35 ERROR - Server [frn-backup.auf-der-nachtschicht.de:10024], DE, Request SC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !",
    "2026-11-25 09:43:39 ERROR - Client [N8XLINK, Crosslink], DE/DE, Request CC - wrong FRN password - Hint: Perform an FRN password request and use the assigned FRN password !",
    f"{NOW} ERROR - Server [frn.auf-der-nachtschicht.de:10024], DE, Request SC - multiple connections at the same time with the same connection data are not permitted",
    "2026-11-25 09:50:01 ERROR - Server [uhf3radionet.ddns.net:10024], GR, Request SC - not listening on specified port - Hint: Check the firewall settings and port forwarding settings, if applicable !",
])})


def test_parse_match_summary():
    e = el.parse(SAMPLE)
    assert len(e) == 4 and e[0]["kind"] == "Server" and e[0]["id"] == "frn-backup.auf-der-nachtschicht.de:10024"
    assert e[0]["message"] == "wrong FRN password" and "request a password" in e[0]["hint"]
    assert "Multiple connection" in e[2]["hint"] and "port forwarding" in e[3]["hint"]
    mine = el.relevant(e, ["DL1ABC"], ["frn.auf-der-nachtschicht.de"])
    assert [m["id"] for m in mine] == ["frn.auf-der-nachtschicht.de:10024"]
    assert el.summarize(el.relevant(e, ["n8xlink"], []))[0]["count"] == 1


@pytest.fixture
def client(app_mod, monkeypatch):
    async def fake(timeout=8, force=False):
        el._cache["t"] = time.time()
        return el.parse(SAMPLE), ""
    monkeypatch.setattr(el, "fetch", fake)
    app_mod.ctx.settings.update({"frn.address": "frn.auf-der-nachtschicht.de", "frn.owner_callsign": "DO1ABC"}, "test")
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        yield c


def test_endpoint(client):
    assert client.get("/api/admin/frn-errorlog").status_code in (401, 403)
    assert client.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers=H).status_code == 200
    d = client.get("/api/admin/frn-errorlog").json()
    assert d["ok"] and d["page"].endswith("error_log.php") and d["scope"]["servers"] == ["frn.auf-der-nachtschicht.de"]
    assert [g["id"] for g in d["mine"]] == ["frn.auf-der-nachtschicht.de:10024"] and d["mine"][0]["hint"]
    assert "uhf3radionet.ddns.net:10024" in [g["id"] for g in d["others"]]


def test_watch_reports_once(client):
    A = client.A
    A._ERRLOG_SEEN.clear()
    asyncio.run(A.errorlog_watch())
    ev = [e for e in A.ctx.live.events if e["kind"] == "frnlog"]
    assert len(ev) == 1 and "server frn.auf-der-nachtschicht.de:10024 – multiple connections" in ev[0]["text"]
    asyncio.run(A.errorlog_watch())
    assert len([e for e in A.ctx.live.events if e["kind"] == "frnlog"]) == 1


def test_portal_may_read():
    from frnadn.app import _token_path_ok
    assert _token_path_ok("/api/admin/frn-errorlog")
