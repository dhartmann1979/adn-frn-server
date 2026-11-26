"""✉️ N8 Mail: password hashes, specification, checks of the root helper, rendered configuration, DNS templates, BIMI, API."""
import json
import shutil
import socket
import struct
import subprocess
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frnadn import mailcfg, mailctl
from frnadn.mailpw import mail_hash, sha512_crypt, verify

H = {"X-N8": "1"}


def test_sha512_crypt_matches_openssl():
    assert sha512_crypt("Hello world!", "saltstringsaltstring", 10000) == \
        "$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v."
    if shutil.which("openssl"):
        for pw in ("geheim", "äöü € long password " * 4):
            out = subprocess.run(["openssl", "passwd", "-6", "-salt", "abcdEFGH", pw], capture_output=True, text=True).stdout.strip()
            assert out == sha512_crypt(pw, "abcdEFGH")
    h = mail_hash("pw-12345678")
    assert h.startswith("{SHA512-CRYPT}$6$rounds=100000$") and verify("pw-12345678", h) and not verify("x", h)
    assert mailctl.HASH_RE.fullmatch(h)


def _db(tmp_path):
    from frnadn.auth import Auth
    from frnadn.db import DB
    db = DB(tmp_path / "t.db")
    a = Auth(db)
    a.set_superadmin("dennis", "geheim-passwort-1")
    chef = [u for u in a.users() if u["username"] == "dennis"][0]
    a.create(chef, "Max.Muster", "max-passwort-12", "user")
    a.create(chef, "abuse", "abuse-passwort-1", "user")
    a.create(chef, "neu", "neu-passwort-123", "user")
    db.x("UPDATE users SET mail_hash='' WHERE username='neu'")
    return db, a


S = {"mail.enabled": True, "mail.domains": "Example.org, example.net, bad_domain", "mail.relay_host": "smtp.provider.de", "mail.relay_port": 465,
     "mail.relay_tls": "tls", "mail.relay_user": "u@example.org", "mail.relay_password": "p:a$s", "mail.quota_mb": 2048, "mail.max_size_mb": 25,
     "mail.dkim_selector": "n8mail", "mail.spam_junk": 6, "mail.spam_reject": 15, "mail.mta_sts": "testing", "mail.bimi": True,
     "mail.dmarc_policy": "quarantine", "mail.relay_spf": "include:_spf.provider.de"}


def test_mailboxes_and_spec(tmp_path):
    db, a = _db(tmp_path)
    assert mailcfg.domains(S) == ["example.org", "example.net"]
    assert mailcfg.cert_names(S) == ["mail.example.org", "mta-sts.example.org", "mail.example.net", "mta-sts.example.net"]
    mb = mailcfg.mailboxes(db, S)
    assert [b["address"] for b in mb["boxes"]] == ["dennis@example.org", "max.muster@example.org", "neu@example.org"]
    assert [x["username"] for x in mb["skipped"]] == ["abuse"]               # role address is reserved
    assert [b["username"] for b in mb["waiting"]] == ["neu"]                  # gets the mailbox at the next login
    le = tmp_path / "letsencrypt" / "config" / "live" / "x"
    le.mkdir(parents=True)
    (le / "fullchain.pem").write_text("c")
    (le / "privkey.pem").write_text("k")
    spec = mailcfg.build_spec(db, S, (str(le / "fullchain.pem"), str(le / "privkey.pem")), tmp_path)
    assert [b["address"] for b in spec["mailboxes"]] == ["dennis@example.org", "max.muster@example.org"]
    assert ["max.muster@example.net", "max.muster@example.org"] in spec["aliases"]
    assert ["postmaster@example.net", "dennis@example.org"] in spec["aliases"]
    sp = mailctl.check_spec(json.loads(json.dumps(spec)), tmp_path)
    main = "\n".join(mailctl.postfix_main(sp))
    assert "relayhost=[smtp.provider.de]:465" in main and "smtp_tls_wrappermode=yes" in main and "smtp_tls_security_level=secure" in main
    assert "smtpd_tls_auth_only=yes" in main and "smtpd_tls_security_level=may" in main
    maps = mailctl.postfix_maps(sp)
    assert maps["relay_passwd"] == ("[smtp.provider.de]:465 u@example.org:p:a$s\n", 0o600)
    assert "max.muster@example.org example.org/max.muster/" in maps["mailboxes"][0]
    for ver in ((2, 3), (2, 4)):
        conf = mailctl.dovecot_conf(sp, ver, v6=False)
        assert "ssl = required" in conf and "port = 0" in conf and "port = 993" in conf and "listen = *\n" in conf
    assert "auth_allow_cleartext = no" in mailctl.dovecot_conf(sp, (2, 4)) and "disable_plaintext_auth = yes" in mailctl.dovecot_conf(sp, (2, 3))
    assert "reject = 15;" in mailctl.rspamd_files(sp)["actions.conf"]


@pytest.mark.parametrize("bad", [
    lambda s: s["relay"].update(password="a b\nrelayhost=evil"),
    lambda s: s["mailboxes"][0].update(hash="{PLAIN}x"),
    lambda s: s["mailboxes"][0].update(address="dennis@evil.org"),
    lambda s: s["aliases"].append(["x@example.org", "nobody@example.org"]),
    lambda s: s.update(selector="n8;rm -rf"),
    lambda s: s["domains"].append({"name": "evil.org\nmydestination", "host": "mail.evil.org"}),
    lambda s: s.update(cert={"fullchain": "/etc/shadow", "privkey": "/etc/shadow"}),
    lambda s: s["webmail"].update(master="root"),
])
def test_mailctl_refuses_bad_spec(tmp_path, bad):
    db, _ = _db(tmp_path)
    spec = json.loads(json.dumps(mailcfg.build_spec(db, S, None, tmp_path)))
    bad(spec)
    with pytest.raises(mailctl.Fail):
        mailctl.check_spec(spec, tmp_path)


def test_dns_templates_and_zone():
    t = mailcfg.dns_templates(S, {"dkim": {"example.org": "MIIBIjANBg"}}, "https://frn.example.org", {"v4": ["192.0.2.5"], "v6": ["2001:db8::5"]})
    r = {(x["type"], x["name"]): x["value"] for x in t[0]["records"]}
    assert r[("MX", "example.org")] == "mail.example.org."
    assert r[("TXT", "example.org")] == "v=spf1 mx include:_spf.provider.de -all"
    assert r[("TXT", "n8mail._domainkey.example.org")] == "v=DKIM1; k=rsa; p=MIIBIjANBg"
    assert r[("TXT", "_dmarc.example.org")].startswith("v=DMARC1; p=quarantine;")
    assert r[("TXT", "default._bimi.example.org")].startswith("v=BIMI1; l=https://frn.example.org/.well-known/bimi/example.org.svg")
    assert r[("AAAA", "mail.example.org")] == "2001:db8::5" and ("TXT", "_mta-sts.example.org") in r
    z = mailcfg.zone_text(t[0])
    assert 'example.org.\t3600\tIN\tMX\t10 mail.example.org.' in z and "; PTR 192.0.2.5" in z


def test_bimi_svg():
    good = mailcfg.bimi_default("Auf der NachtSchicht", "#ff2dd1")
    assert mailcfg.bimi_check(good) == []
    assert mailcfg.bimi_check(good.replace("<title>", "<script>alert(1)</script><title>"))
    assert mailcfg.bimi_check('<svg xmlns="http://www.w3.org/2000/svg"><image href="http://x"/></svg>')


def test_dns_client_parses_answers(monkeypatch):
    """A tiny DNS server on localhost answers TXT and MX – the parser must read both (with name compression)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))

    def answer():
        for _ in range(2):
            q, addr = srv.recvfrom(512)
            qid, qt = q[:2], struct.unpack(">H", q[-4:-2])[0]
            hdr = qid + struct.pack(">HHHHH", 0x8180, 1, 1, 0, 0)
            rr = b"\xc0\x0c" + struct.pack(">HHI", qt, 1, 60)
            data = (b"\x09v=spf1 mx" + b"\x05 -all") if qt == 16 else struct.pack(">H", 10) + b"\x04mail\xc0\x0c"
            srv.sendto(hdr + q[12:] + rr + struct.pack(">H", len(data)) + data, addr)
    th = threading.Thread(target=answer, daemon=True)
    th.start()
    monkeypatch.setattr(mailcfg, "_nameservers", lambda: ["127.0.0.1"])
    monkeypatch.setattr(mailcfg, "DNS_PORT", srv.getsockname()[1])
    assert mailcfg.dns_query("example.org", "TXT") == ["v=spf1 mx -all"]
    assert mailcfg.dns_query("example.org", "MX") == ["10 mail.example.org."]
    srv.close()


@pytest.fixture
def client(app_mod):
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        yield c


def test_mail_api(client):
    assert client.get("/api/admin/mail").status_code in (401, 403)
    r = client.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers=H)
    assert r.status_code == 200
    assert client.get("/api/info").json()["mail"] is None
    assert client.get("/api/mail/me").status_code == 404
    assert client.post("/api/admin/mail/settings", json={"changes": {"https.domain": "x.org"}}, headers=H).status_code == 400
    r = client.post("/api/admin/mail/settings", json={"changes": {"mail.enabled": True, "mail.domains": "example.org", "mail.bimi": True,
                                                                  "mail.mta_sts": "testing"}}, headers=H)
    assert r.json()["ok"]
    assert client.get("/api/info").json()["mail"] == {"webmail": True, "address": "chef@example.org"}
    v = client.get("/api/admin/mail").json()
    assert v["domains"] == ["example.org"] and v["boxes"][0]["address"] == "chef@example.org" and "hash" not in v["boxes"][0]
    assert client.get("/api/admin/mail/dns").json()["templates"][0]["domain"] == "example.org"
    svg = client.get("/.well-known/bimi/example.org.svg")
    assert svg.status_code == 200 and "tiny-ps" in svg.text and svg.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/.well-known/bimi/other.org.svg").status_code == 404
    assert "mode: testing" in client.get("/.well-known/mta-sts.txt", headers={"host": "mta-sts.example.org"}).text
    assert client.get("/.well-known/mta-sts.txt", headers={"host": "example.org"}).status_code == 404
    bad = client.post("/api/admin/mail/bimi", json={"svg": "<svg><script>x</script></svg>"}, headers=H)
    assert bad.status_code == 400
    assert client.post("/api/admin/mail/bimi", json={"generate": True, "text": "N8"}, headers=H).json()["ok"]
    # every login gives users from before 2.25 their mailbox hash
    client.A.ctx.db.x("UPDATE users SET mail_hash=''")
    client.post("/api/auth/login", json={"username": "chef", "password": "chef-passwort-1"}, headers=H)
    h = client.A.ctx.db.q("SELECT mail_hash FROM users WHERE username='chef'")[0]["mail_hash"]
    assert verify("chef-passwort-1", h)
