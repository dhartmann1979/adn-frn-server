"""FRN-Passwort beim SystemManager anfordern (wie „Get Password“ im FRN-Client)."""
import socket
import threading

import pytest

from frnadn import sysman

FORM = {"callsign": "do1abc", "name": "Server Test", "email": "Sysop@Example.org", "band": "PC Only", "description": "Testserver",
        "country": "Germany", "city": "Minden - JO42"}


def _fake_sysman(answer: bytes):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    got = {}

    def run():
        c, _ = srv.accept()
        got["line"] = c.recv(1024).decode()
        c.sendall(answer)
        c.close()
        srv.close()
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1], got


def test_line_format_like_svxlink():
    f = sysman.build(FORM)
    assert sysman.line(f) == ("IG:<ON>DO1ABC, Server Test</ON><EA>sysop@example.org</EA><BC>PC Only</BC><DS>Testserver</DS>"
                              "<NN>Germany</NN><CT>Minden - JO42</CT>")


@pytest.mark.parametrize("bad", [{"callsign": "x"}, {"email": "kein"}, {"city": "Minden"}, {"band": "UKW"}, {"name": ""}, {"country": ""}])
def test_validation(bad):
    with pytest.raises(sysman.SysmanError):
        sysman.build(FORM | bad)


def test_no_tag_injection():
    f = sysman.build(FORM | {"description": "a</DS><EA>evil@x.org</EA>"})
    assert "<EA>evil" not in sysman.line(f)


@pytest.mark.parametrize("answer,ok", [(b"OK\r\n", True), (b"NU\r\n", False), (b"ER\r\n", False)])
def test_register_answers(answer, ok):
    sysman._last.clear()
    port, got = _fake_sysman(answer)
    r = sysman.register("127.0.0.1", FORM, port=port)
    assert r["ok"] is ok and got["line"].startswith("IG:<ON>DO1ABC, Server Test</ON>") and got["line"].endswith("\r\n")
    if answer.startswith(b"NU"):
        assert "already" in r["message"]


def test_rate_limit():
    sysman._last.clear()
    port, _ = _fake_sysman(b"OK\n")
    sysman.register("127.0.0.1", FORM, port=port)
    with pytest.raises(sysman.SysmanError, match="wait"):
        sysman.register("127.0.0.1", FORM, port=port)


def test_portal_token_may_request():
    from frnadn.app import _token_path_ok
    assert _token_path_ok("/api/admin/frn-password") and not _token_path_ok("/api/admin/users")
