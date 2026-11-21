"""server.properties, the log reader and – if FRN_Server.jar is available – the real Java FRN server."""
import asyncio
import os
import shutil
import time
from pathlib import Path

import pytest

from frnadn.frn import javasrv
from frnadn.frn.logwatch import LogWatch

ROOMS = [{"idx": 0, "name": "Test", "enabled": 1, "owners": "", "show_info": "acl", "tot": 60, "speechpause": 0, "speechpause_msg": "",
          "parrot": 1, "parrot_startstop": 1, "unmute_min": 0, "acl_cl": "", "acl_gw": "", "acl_info": "", "bl_regexp": "",
          "bl_info": "", "tg_params": "", "hidden": 0, "position": 0, "id": 1},
         {"idx": 1, "name": "Nachtschicht Ü", "enabled": 1, "owners": "a@b.de", "show_info": "always", "tot": 180, "speechpause": 3000,
          "speechpause_msg": "Hallo {callsign}", "parrot": 0, "parrot_startstop": 1, "unmute_min": 10, "acl_cl": "none", "acl_gw": "",
          "acl_info": "<b>nein</b>", "bl_regexp": "spam\\d", "bl_info": "", "tg_params": "", "hidden": 0, "position": 1, "id": 2}]
SETTINGS = {"frn.standalone": False, "frn.allow_lan": False, "sysman.host": "sysman.freeradionetwork.de", "sysman.email": "o@x.de",
            "sysman.password": "PW", "frn.address": "frn.example.org", "frn.port": 10024, "frn.owner_email": "", "frn.website": "",
            "frn.backup_host": "", "frn.backup_port": 0, "frn.client_timeout": 8000, "frn.tx_timeout": 1000,
            "frn.skip_muted_crosslink": True, "frn.skip_muted_gateway": True, "frn.skip_muted_pconly": False, "frn.default_room": ""}


def test_properties():
    text = javasrv.build_properties(SETTINGS, ROOMS, Path("/var/lib/frnadn/frn"))
    assert "standalone" not in text
    assert "server_owner=o@x.de" in text                        # = the account e-mail
    assert "default_net=Nachtschicht \\u00dc" in text
    assert "net01=Nachtschicht \\u00dc" in text and "net01_speechpause=3000" in text and "net01_unmute=10" in text
    assert "net01_bl_regexp=spam\\\\d" in text                  # backslash escaped for Java
    assert "net00_parrot_enable=yes" in text and "net01_parrot_enable" not in text
    assert "net01_show_infomessage=always" in text and "net01_acl_cl=none" in text


def test_passwd_xml():
    x = javasrv.build_passwd(True, [{"callsign": "DL1A", "name": "A&B", "email": "a@b.de", "password": "p<w", "disabled": 0}])
    assert "<disabled>false</disabled>" in x and "<OperatorName>DL1A, A&amp;B</OperatorName>" in x and "<Password>p&lt;w</Password>" in x


class Sink:
    def __init__(self):
        self.ev = []

    def __getattr__(self, name):
        def f(*a):
            self.ev.append((name, a))
            return 7 if name == "talk_start" else None
        return f


class FakeStore:
    def rooms(self):
        return ROOMS

    def account_seen(self, email):
        pass


LOG = """2026-11-19 23:01:07,027 INFO  - server listening on port 10071
2026-11-19 23:01:18,252 INFO  - socket connect from ip 203.0.113.5
2026-11-19 23:01:18,257 INFO  - CTRequest [version=2014003, email_address=A@example.org, password=********, operator_name=DL1AAA, Anke, client_type=1, band_channel=438.950 MHz FM, description=Relais, country=Germany, city=Minden, network=Test]
2026-11-19 23:01:18,363 INFO  - {Test [DL1AAA, Anke]}: server response: AL=OK, NT=Test, ID=~bf8d~, MT=
2026-11-19 23:01:18,365 INFO  - {Test [DL1AAA, Anke]}: >>> CLIENT CONNECT <<<
2026-11-19 23:01:45,828 INFO  - {Test [DL1AAA, Anke]}: Voice transmission started.
2026-11-19 23:01:47,939 INFO  - {Test [DL1AAA, Anke]}: Voice transmission stopped. 0m2s110ms
2026-11-19 23:01:48,000 INFO  - {Test [DL1AAA, Anke]}: TMRequest [id=, message=Hallo Runde]
2026-11-19 23:01:51,040 INFO  - {Test [DL1AAA, Anke]}: >>> CLIENT DISCONNECT <<<
2026-11-19 23:02:01,344 INFO  - {Test [N0BAD, X]}: server response: AL=BLOCK, NT=Test, ID=, MT=
2026-11-19 23:02:02,000 ERROR - SysmanConnection: Error -5, not accessible
"""


def test_logwatch_main(tmp_path):
    sink = Sink()
    w = LogWatch(FakeStore(), sink, tmp_path, None)
    w.feed_main(LOG.splitlines())
    names = [e[0] for e in sink.ev]
    assert names.count("joined") == 1 and "talk_start" in names and "chat" in names and "left" in names and "denied" in names
    joined = next(e for e in sink.ev if e[0] == "joined")[1][1]
    assert (joined.callsign, joined.name, joined.email, joined.peer, joined.client, joined.cid) == \
        ("DL1AAA", "Anke", "a@example.org", "203.0.113.5", 1, "~bf8d~")
    end = next(e for e in sink.ev if e[0] == "talk_end")[1]
    assert end[4] == pytest.approx(2.11) and end[5] == 7
    assert w.listen == ["10071"] and "not reachable" in w.error


def test_logwatch_client_list(tmp_path):
    sink = Sink()
    w = LogWatch(FakeStore(), sink, tmp_path, None)
    w.feed_clients(["2026-11-19 23:01:18,365 - <net>Test</net><rid>1</rid><on>DL2BBB, Bernd</on><bc>PC Only</bc><cty>Minden</cty>"
                    "<ctry>Germany</ctry><dscr>x</dscr><st>qrv</st><mt>1</mt><spk>0</spk>"])
    c = w.rooms["Test"].clients[0]
    assert c.callsign == "DL2BBB" and c.muted and c.client == 2
    w.feed_main(["2026-11-19 23:01:18,366 INFO  - {Test [DL2BBB, Bernd]}: >>> CLIENT CONNECT <<<"])
    assert len(w.rooms["Test"].clients) == 1 and [e[0] for e in sink.ev].count("joined") == 1
    w.feed_clients(["2026-11-19 23:01:30,000 - <net>Test</net><rid>2</rid><on>null</on><bc>null</bc><cty>null</cty><ctry>null</ctry>"
                    "<dscr>null</dscr><st>null</st><mt>null</mt><spk>null</spk>"])
    assert w.rooms["Test"].clients == []


JAR = Path(os.environ.get("FRN_TEST_JAR", "/opt/frn-server/FRN_Server.jar"))


@pytest.mark.skipif(not JAR.exists() or not shutil.which("java"), reason="FRN_Server.jar or java not available")
def test_real_java_server(app_mod, monkeypatch):
    """Stand-alone Java server as a child process; frn_adn follows its logs."""
    from tests.frnclient import TestClient
    A = app_mod
    A.ctx.java.jar, A.ctx.java.direct, A.ctx.java.demo = JAR, True, False
    port = A.ctx.settings.get("frn.port")

    async def main():
        await A._startup()                     # starts the Java server (direct mode)
        try:
            for _ in range(60):
                await asyncio.sleep(0.5)
                if A.ctx.server.listen:
                    break
            log = (A.FRN_HOME / "logs" / "server.log")
            assert A.ctx.server.listen == [str(port)], log.read_text()[-3000:] if log.exists() else "no server.log"
            a = TestClient(port, "a@example.org", "DL1AAA", "Nachtschicht")
            assert (await a.connect())["AL"] == "OK"
            await a.send("TX0")                # the Java server answers TX0 at once with DT_DO_TX
            await asyncio.sleep(0.5)
            await asyncio.wait_for(a.r.read(65536), 2)
            for i in range(15):
                await a.send("TX1", bytes([i]) * 325)
                await asyncio.sleep(0.05)
            await a.send("RX0")
            await asyncio.sleep(3)
            room = A.ctx.server.rooms["Nachtschicht"]
            assert [c.callsign for c in room.clients] == ["DL1AAA"] and room.clients[0].email == "a@example.org"
            assert A.ctx.db.q("SELECT callsign FROM talks WHERE net='Nachtschicht'")[0]["callsign"] == "DL1AAA"
            a.close()
            await asyncio.sleep(2)
            assert room.clients == []
        finally:
            await A._shutdown()
    asyncio.run(main())
    time.sleep(0.5)
