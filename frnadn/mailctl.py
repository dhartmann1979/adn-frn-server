#!/usr/bin/env python3
"""N8 Mail – root helper of the ADN-FRN-Server (Postfix, Dovecot, Rspamd).

The dashboard runs as an unprivileged user. It writes a specification (``<data>/mail/spec.json``) and calls, through one fixed
sudo rule each::

    sudo -n /usr/bin/python3 -I /opt/adn-frn-server/frnadn/mailctl.py status|apply|install|certs|disable

This file is stdlib only and never imports the dashboard. Everything read from the specification is checked against strict
patterns before it reaches a configuration file, so a compromised dashboard cannot smuggle settings into Postfix or Dovecot.
``apply`` keeps a copy of every file it changes, checks the result with ``postfix check``, ``doveconf -n`` and
``rspamadm configtest`` and puts the old files back when a check fails. Only TLS: IMAPS 993, SMTPS 465, submission 587 with
STARTTLS required, port 25 with STARTTLS (optionally required), the upstream always encrypted. Dovecot 2.3 (Debian 12,
Ubuntu 24.04) and 2.4 (Debian 13) are both supported.

The last line of the output is one JSON object: {"ok": …, "message": …}.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ETC = Path("/etc/n8mail")
SSL = ETC / "ssl"
BACKUPS = ETC / "backups"
PF = Path("/etc/postfix")
PF_MAPS = PF / "n8mail"
DOVE = Path("/etc/dovecot")
DOVE_CONF = DOVE / "conf.d" / "99-n8mail.conf"
DOVE_USERS = DOVE / "n8mail-users"
DOVE_MASTER = DOVE / "n8mail-master"
DOVE_SIEVE = DOVE / "n8mail-spam.sieve"
RSPAMD_LOCAL = Path("/etc/rspamd/local.d")
DKIM_DIR = Path("/var/lib/rspamd/dkim")
VMAIL_USER = "n8vmail"
VMAIL_HOME = Path("/var/mail/n8mail")
PACKAGES = ["postfix", "dovecot-imapd", "dovecot-lmtpd", "dovecot-sieve", "rspamd"]
UNITS = ["postfix", "dovecot", "rspamd"]
RSPAMD_FILES = ["dkim_signing.conf", "actions.conf", "greylist.conf", "milter_headers.conf"]
MILTER = "inet:127.0.0.1:11332"

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
LOCAL_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")
HASH_RE = re.compile(r"^\{SHA512-CRYPT\}\$6\$(rounds=\d{4,9}\$)?[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}$")
SEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
HOST_RE = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
SECRET_RE = re.compile(r"^[^\s:\\]{1,200}$")
PASS_RE = re.compile(r"^[^\s\\]{1,200}$")


class Fail(Exception):
    pass


# ---------------------------------------------------------------- helpers
def say(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: List[str], check: bool = True, inp: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, input=inp, capture_output=True, text=True, env={**os.environ, **(env or {})})
    except FileNotFoundError:
        if check:
            raise Fail(f"{cmd[0]} is missing")
        return 127, f"{cmd[0]} is missing"
    out = (p.stdout or "") + (p.stderr or "")
    if check and p.returncode != 0:
        raise Fail(f"{' '.join(cmd[:3])} failed (exit {p.returncode}): {out.strip()[-1500:]}")
    return p.returncode, out


def which(x: str) -> bool:
    return shutil.which(x) is not None


def data_dir() -> Path:
    unit = Path("/etc/systemd/system/frnadn.service")
    try:
        for line in unit.read_text().splitlines():
            if line.startswith("Environment=FRNADN_DATA="):
                return Path(line.split("=", 2)[2].strip())
    except OSError:
        pass
    return Path("/var/lib/frnadn")


def svc_user() -> str:
    unit = Path("/etc/systemd/system/frnadn.service")
    try:
        for line in unit.read_text().splitlines():
            if line.startswith("User="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "frnadn"


def write(path: Path, text: str, mode: int = 0o644, owner: str = "root", group: str = "root") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".n8tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    shutil.chown(tmp, owner, group)
    tmp.replace(path)


def dovecot_major() -> Tuple[int, int]:
    _, out = run(["dovecot", "--version"], check=False)
    m = re.match(r"(\d+)\.(\d+)", out.strip())
    return (int(m.group(1)), int(m.group(2))) if m else (2, 3)


def installed() -> Dict[str, bool]:
    return {"postfix": which("postconf"), "dovecot": which("doveconf"), "rspamd": which("rspamadm")}


# ---------------------------------------------------------------- the specification
def load_spec(data: Path) -> Dict[str, Any]:
    p = data / "mail" / "spec.json"
    try:
        spec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Fail(f"No mail specification ({p}): {e}")
    return check_spec(spec, data)


def check_spec(spec: Dict[str, Any], data: Path) -> Dict[str, Any]:
    """Every value is checked here – nothing reaches a configuration file unchecked."""
    if spec.get("format") != "n8mail-1":
        raise Fail("Unknown specification format")
    doms = []
    for d in spec.get("domains") or []:
        name, host = str(d.get("name", "")), str(d.get("host", ""))
        if not DOMAIN_RE.fullmatch(name) or host != f"mail.{name}":
            raise Fail(f"Invalid mail domain {name!r}")
        doms.append({"name": name, "host": host})
    if not doms or len(doms) > 50:
        raise Fail("No (or too many) mail domains")
    names = {d["name"] for d in doms}

    def addr(a: Any) -> str:
        a = str(a or "")
        lp, _, dom = a.partition("@")
        if not LOCAL_RE.fullmatch(lp) or dom not in names:
            raise Fail(f"Invalid address {a!r}")
        return a

    boxes = []
    for b in spec.get("mailboxes") or []:
        h = str(b.get("hash", ""))
        if not HASH_RE.fullmatch(h):
            raise Fail("Invalid password hash")
        boxes.append({"address": addr(b.get("address")), "hash": h})
    if len({b["address"] for b in boxes}) != len(boxes):
        raise Fail("Duplicate mailbox")
    box_set = {b["address"] for b in boxes}
    aliases = []
    for a in spec.get("aliases") or []:
        src, dst = addr(a[0]), addr(a[1])
        if dst not in box_set or src in box_set:
            raise Fail(f"Invalid alias {src} → {dst}")
        aliases.append((src, dst))
    senders = []
    for a in spec.get("senders") or []:
        src, dst = addr(a[0]), addr(a[1])
        if dst not in box_set:
            raise Fail(f"Invalid sender {src}")
        senders.append((src, dst))
    relay = spec.get("relay")
    if relay:
        host = str(relay.get("host", "")).lower()
        port = int(relay.get("port", 0))
        tls = relay.get("tls")
        user, pw = str(relay.get("user", "")), str(relay.get("password", ""))
        if not HOST_RE.fullmatch(host) or not 1 <= port <= 65535 or tls not in ("starttls", "tls"):
            raise Fail("Invalid upstream")
        if (user or pw) and not (SECRET_RE.fullmatch(user) and PASS_RE.fullmatch(pw)):
            raise Fail("Upstream user or password contains spaces or forbidden characters")
        relay = {"host": host, "port": port, "tls": tls, "user": user, "password": pw}
    sel = str(spec.get("selector", ""))
    if not SEL_RE.fullmatch(sel):
        raise Fail("Invalid DKIM selector")
    quota = int(spec.get("quota_mb", 0))
    size = int(spec.get("max_size_mb", 0))
    junk, reject = int(spec["spam"]["junk"]), int(spec["spam"]["reject"])
    if not (50 <= quota <= 1048576 and 1 <= size <= 200 and 1 <= junk < reject <= 200):
        raise Fail("Invalid limits")
    cert = spec.get("cert")
    if cert:
        base = (data / "letsencrypt").resolve()
        paths = {}
        for k in ("fullchain", "privkey"):
            p = Path(str(cert.get(k, ""))).resolve()
            if base not in p.parents or not p.is_file():
                raise Fail(f"Certificate file outside {base} or missing: {cert.get(k)}")
            paths[k] = p
        cert = paths
    wm = spec.get("webmail") or {}
    if wm.get("master") != "n8webmail" or not HASH_RE.fullmatch(str(wm.get("hash", ""))):
        raise Fail("Invalid webmail access")
    pm = str(spec.get("postmaster") or "")
    if pm:
        addr(pm)
    return {"domains": doms, "hostname": doms[0]["host"], "mailboxes": boxes, "aliases": aliases, "senders": senders,
            "relay": relay, "inbound_tls": bool(spec.get("inbound_tls")), "quota_mb": quota, "max_size_mb": size,
            "selector": sel, "spam": {"junk": junk, "reject": reject}, "cert": cert, "webmail_hash": wm["hash"],
            "postmaster": pm or (boxes[0]["address"] if boxes else f"postmaster@{doms[0]['name']}")}


# ---------------------------------------------------------------- rendering (pure – tested without root)
def postfix_main(sp: Dict[str, Any]) -> List[str]:
    r = sp["relay"]
    v = [
        f"myhostname={sp['hostname']}", f"myorigin={sp['domains'][0]['name']}", "mydestination=localhost",
        "mynetworks=127.0.0.0/8 [::1]/128", "inet_interfaces=all", "inet_protocols=all",
        f"virtual_mailbox_domains=hash:{PF_MAPS}/domains", f"virtual_mailbox_maps=hash:{PF_MAPS}/mailboxes",
        f"virtual_alias_maps=hash:{PF_MAPS}/aliases", "virtual_transport=lmtp:unix:private/dovecot-lmtp",
        f"smtpd_tls_cert_file={SSL}/fullchain.pem", f"smtpd_tls_key_file={SSL}/privkey.pem",
        f"smtpd_tls_security_level={'encrypt' if sp['inbound_tls'] else 'may'}", "smtpd_tls_auth_only=yes",
        "smtpd_tls_protocols=>=TLSv1.2", "smtpd_tls_mandatory_protocols=>=TLSv1.2", "smtpd_tls_loglevel=1",
        "smtpd_tls_received_header=yes", "tls_preempt_cipherlist=yes",
        "smtpd_sasl_type=dovecot", "smtpd_sasl_path=private/auth", "smtpd_sasl_auth_enable=no",
        "smtpd_helo_required=yes", "disable_vrfy_command=yes", "strict_rfc821_envelopes=yes",
        "smtpd_banner=$myhostname ESMTP",                 # no software/distribution in the greeting
        "smtpd_relay_restrictions=permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination",
        "smtpd_recipient_restrictions=permit_mynetworks,permit_sasl_authenticated,reject_unauth_destination,reject_unlisted_recipient",
        f"smtpd_sender_login_maps=hash:{PF_MAPS}/senders",
        f"message_size_limit={sp['max_size_mb'] * 1024 * 1024}", "mailbox_size_limit=0",
        f"smtpd_milters={MILTER}", f"non_smtpd_milters={MILTER}", "milter_default_action=accept", "milter_protocol=6",
        "smtp_tls_CAfile=/etc/ssl/certs/ca-certificates.crt", "smtp_tls_loglevel=1", "smtp_tls_protocols=>=TLSv1.2",
        "smtp_tls_mandatory_protocols=>=TLSv1.2",
    ]
    if r:
        hp = f"[{r['host']}]:{r['port']}"
        v += [f"relayhost={hp}", "smtp_tls_security_level=secure", "smtp_tls_verify_cert_match=hostname",
              f"smtp_tls_wrappermode={'yes' if r['tls'] == 'tls' else 'no'}",
              f"smtp_sasl_auth_enable={'yes' if r['user'] else 'no'}", f"smtp_sasl_password_maps=hash:{PF_MAPS}/relay_passwd",
              "smtp_sasl_security_options=noanonymous", "smtp_sasl_tls_security_options=noanonymous"]
    else:
        v += ["relayhost=", "smtp_tls_security_level=may", "smtp_tls_wrappermode=no", "smtp_sasl_auth_enable=no"]
    return v


SUBMISSION_OPTS = [
    "smtpd_tls_security_level=encrypt", "smtpd_sasl_auth_enable=yes", "smtpd_tls_auth_only=yes",
    "smtpd_client_restrictions=permit_sasl_authenticated,reject",
    "smtpd_sender_restrictions=reject_sender_login_mismatch",
    "smtpd_relay_restrictions=permit_sasl_authenticated,reject",
    "smtpd_recipient_restrictions=permit_sasl_authenticated,reject",
    "milter_macro_daemon_name=ORIGINATING",
]


def postfix_maps(sp: Dict[str, Any]) -> Dict[str, Tuple[str, int]]:
    hosts = ""
    r = sp["relay"]
    if r and r["user"]:
        hosts = f"[{r['host']}]:{r['port']} {r['user']}:{r['password']}\n"
    return {
        "domains": ("".join(f"{d['name']} OK\n" for d in sp["domains"]), 0o644),
        "mailboxes": ("".join(f"{b['address']} {b['address'].split('@')[1]}/{b['address'].split('@')[0]}/\n" for b in sp["mailboxes"]), 0o644),
        "aliases": ("".join(f"{a} {b}\n" for a, b in sp["aliases"]), 0o644),
        "senders": ("".join(f"{a} {b}\n" for a, b in sp["senders"]), 0o644),
        "relay_passwd": (hosts, 0o600),
    }


def dovecot_users(sp: Dict[str, Any]) -> str:
    return "".join(f"{b['address']}:{b['hash']}::::::\n" for b in sp["mailboxes"])


def sieve_script() -> str:
    return ('# N8 Mail – spam goes to Junk (written by mailctl)\nrequire ["fileinto"];\n'
            'if anyof (header :contains "X-Spam" "Yes", header :contains "X-Spam-Status" "Yes") {\n  fileinto "Junk";\n  stop;\n}\n')


def ipv6() -> bool:
    return Path("/proc/net/if_inet6").exists()


def dovecot_conf(sp: Dict[str, Any], ver: Tuple[int, int], v6: Optional[bool] = None) -> str:
    main = sp["domains"][0]["name"]
    head = "# N8 Mail – written by mailctl.py from the ADN-FRN-Server dashboard. Do not edit: the next „Apply“ overwrites it.\n"
    head += f"listen = {'*, ::' if (ipv6() if v6 is None else v6) else '*'}\n"
    lst = """service lmtp {
  unix_listener /var/spool/postfix/private/dovecot-lmtp {
    mode = 0600
    user = postfix
    group = postfix
  }
}
service auth {
  unix_listener /var/spool/postfix/private/auth {
    mode = 0660
    user = postfix
    group = postfix
  }
}
service imap-login {
  inet_listener imap {
    port = 0
  }
  inet_listener imaps {
    port = 993
    ssl = yes
  }
}
"""
    if ver >= (2, 4):
        return head + f"""ssl = required
ssl_server_cert_file = {SSL}/fullchain.pem
ssl_server_key_file = {SSL}/privkey.pem
ssl_min_protocol = TLSv1.2
auth_allow_cleartext = no
auth_mechanisms = plain login
auth_username_format = %{{user | lower}}
auth_default_domain = {main}
auth_master_user_separator = *
mail_driver = maildir
mail_home = {VMAIL_HOME}/%{{user | domain}}/%{{user | username}}
mail_path = ~/Maildir
mail_inbox_path =
mail_uid = {VMAIL_USER}
mail_gid = {VMAIL_USER}
passdb n8master {{
  driver = passwd-file
  master = yes
  passwd_file_path = {DOVE_MASTER}
  default_password_scheme = SHA512-CRYPT
}}
passdb n8users {{
  driver = passwd-file
  passwd_file_path = {DOVE_USERS}
  default_password_scheme = SHA512-CRYPT
}}
userdb n8users {{
  driver = passwd-file
  passwd_file_path = {DOVE_USERS}
}}
{lst}mail_plugins {{
  quota = yes
}}
quota "User quota" {{
  storage_size = {sp['quota_mb']}M
}}
protocol imap {{
  mail_plugins {{
    imap_quota = yes
  }}
}}
protocol lmtp {{
  auth_username_format = %{{user | lower}}
  postmaster_address = {sp['postmaster']}
  mail_plugins {{
    sieve = yes
  }}
}}
sieve_script n8spam {{
  type = after
  driver = file
  path = {DOVE_SIEVE}
}}
namespace inbox {{
  mailbox Drafts {{
    auto = subscribe
  }}
  mailbox Junk {{
    auto = subscribe
  }}
  mailbox Trash {{
    auto = subscribe
  }}
  mailbox Sent {{
    auto = subscribe
  }}
}}
"""
    return head + f"""protocols = imap lmtp
ssl = required
ssl_cert = <{SSL}/fullchain.pem
ssl_key = <{SSL}/privkey.pem
ssl_min_protocol = TLSv1.2
ssl_prefer_server_ciphers = yes
disable_plaintext_auth = yes
auth_mechanisms = plain login
auth_username_format = %Lu
auth_default_realm = {main}
auth_master_user_separator = *
mail_location = maildir:~/Maildir
mail_uid = {VMAIL_USER}
mail_gid = {VMAIL_USER}
mail_plugins = $mail_plugins quota
passdb {{
  driver = passwd-file
  master = yes
  pass = yes
  args = scheme=SHA512-CRYPT {DOVE_MASTER}
}}
passdb {{
  driver = passwd-file
  args = scheme=SHA512-CRYPT username_format=%u {DOVE_USERS}
}}
userdb {{
  driver = passwd-file
  args = username_format=%u {DOVE_USERS}
  default_fields = uid={VMAIL_USER} gid={VMAIL_USER} home={VMAIL_HOME}/%d/%n
}}
{lst}protocol imap {{
  mail_plugins = $mail_plugins imap_quota
}}
protocol lmtp {{
  mail_plugins = $mail_plugins sieve
  postmaster_address = {sp['postmaster']}
}}
plugin {{
  quota = maildir:User quota
  quota_rule = *:storage={sp['quota_mb']}M
  quota_grace = 10%%
  sieve_after = {DOVE_SIEVE}
}}
namespace inbox {{
  mailbox Drafts {{
    special_use = \\Drafts
    auto = subscribe
  }}
  mailbox Junk {{
    special_use = \\Junk
    auto = subscribe
  }}
  mailbox Trash {{
    special_use = \\Trash
    auto = subscribe
  }}
  mailbox Sent {{
    special_use = \\Sent
    auto = subscribe
  }}
}}
"""


def rspamd_files(sp: Dict[str, Any]) -> Dict[str, str]:
    h = "# N8 Mail – written by mailctl.py, do not edit\n"
    return {
        "dkim_signing.conf": h + f"""enabled = true;
allow_username_mismatch = true;
allow_hdrfrom_mismatch = false;
sign_authenticated = true;
sign_local = true;
use_domain = "header";
use_esld = false;
selector = "{sp['selector']}";
path = "{DKIM_DIR}/$domain.$selector.key";
""",
        "actions.conf": h + f"reject = {sp['spam']['reject']};\nadd_header = {sp['spam']['junk']};\ngreylist = null;\n",
        "greylist.conf": h + "enabled = false;\n",
        "milter_headers.conf": h + 'use = ["x-spam-status", "authentication-results"];\nauthenticated_headers = ["authentication-results"];\n',
    }


# ---------------------------------------------------------------- actions
def backup(stamp: str, files: List[Path]) -> Path:
    d = BACKUPS / stamp
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(BACKUPS, 0o700)
    for f in files:
        if f.exists():
            dst = d / str(f).lstrip("/").replace("/", "__")
            shutil.copy2(f, dst)
    (d / "files.json").write_text(json.dumps([str(f) for f in files]))
    keep = sorted(BACKUPS.iterdir())
    for old in keep[:-10]:
        shutil.rmtree(old, ignore_errors=True)
    return d


def restore(d: Path) -> None:
    files = json.loads((d / "files.json").read_text())
    for f in map(Path, files):
        src = d / str(f).lstrip("/").replace("/", "__")
        if src.exists():
            shutil.copy2(src, f)
        elif f.exists() and str(f).startswith((str(PF_MAPS), str(DOVE_CONF), str(RSPAMD_LOCAL), str(DOVE_USERS), str(DOVE_MASTER))):
            f.unlink()


def ensure_vmail() -> None:
    import pwd
    try:
        pwd.getpwnam(VMAIL_USER)
    except KeyError:
        run(["useradd", "--system", "--home-dir", str(VMAIL_HOME), "--no-create-home", "--shell", "/usr/sbin/nologin",
             "--user-group", VMAIL_USER])
    VMAIL_HOME.mkdir(parents=True, exist_ok=True)
    shutil.chown(VMAIL_HOME, VMAIL_USER, VMAIL_USER)
    os.chmod(VMAIL_HOME, 0o750)


def dkim_keys(sp: Dict[str, Any]) -> Dict[str, str]:
    """One 2048-bit RSA key per domain (made once, kept). Returns {domain: public key base64}."""
    DKIM_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.chown(DKIM_DIR, "_rspamd", "_rspamd")
    except (LookupError, OSError):
        pass
    os.chmod(DKIM_DIR, 0o750)
    out = {}
    for d in sp["domains"]:
        key = DKIM_DIR / f"{d['name']}.{sp['selector']}.key"
        if not key.exists():
            run(["openssl", "genrsa", "-out", str(key), "2048"])
            say(f"DKIM key made for {d['name']} (selector {sp['selector']})")
        try:
            shutil.chown(key, "_rspamd", "_rspamd")
        except (LookupError, OSError):
            pass
        os.chmod(key, 0o640)
        _, pem = run(["openssl", "rsa", "-in", str(key), "-pubout", "-outform", "PEM"])
        b64 = "".join(l for l in pem.splitlines() if l and not l.startswith("-----") and "writing" not in l.lower())
        base64.b64decode(b64)
        out[d["name"]] = b64
    return out


def copy_certs(sp: Dict[str, Any]) -> bool:
    if not sp.get("cert"):
        return False
    SSL.mkdir(parents=True, exist_ok=True)
    os.chmod(SSL, 0o750)
    for k in ("fullchain", "privkey"):
        dst = SSL / f"{k}.pem"
        data = Path(sp["cert"][k]).read_bytes()
        if not dst.exists() or dst.read_bytes() != data:
            tmp = dst.with_suffix(".n8tmp")
            tmp.write_bytes(data)
            os.chmod(tmp, 0o600 if k == "privkey" else 0o644)
            tmp.replace(dst)
    return True


def cert_info() -> Dict[str, Any]:
    f = SSL / "fullchain.pem"
    if not f.exists():
        return {}
    rc, out = run(["openssl", "x509", "-in", str(f), "-noout", "-enddate", "-ext", "subjectAltName"], check=False)
    end = re.search(r"notAfter=(.+)", out)
    names = re.findall(r"DNS:([^,\s]+)", out)
    info: Dict[str, Any] = {"names": names}
    if end:
        try:
            ts = time.mktime(time.strptime(end.group(1).strip(), "%b %d %H:%M:%S %Y %Z"))
            info.update(expires=end.group(1).strip(), days=int((ts - time.time()) // 86400))
        except ValueError:
            info["expires"] = end.group(1).strip()
    return info


def dovecot_auth_system(off: bool) -> None:
    """Without this, system users (PAM) could log in to IMAP – N8 Mail only knows its own mailboxes."""
    f = DOVE / "conf.d" / "10-auth.conf"
    try:
        t = f.read_text()
    except OSError:
        return
    if off:
        t2 = re.sub(r"(?m)^(\s*)!include auth-system\.conf\.ext", r"\1#!include auth-system.conf.ext  # off: N8 Mail", t)
    else:
        t2 = t.replace("#!include auth-system.conf.ext  # off: N8 Mail", "!include auth-system.conf.ext")
    if t2 != t:
        f.write_text(t2)


def master_cf(sp: Dict[str, Any]) -> None:
    """587 (STARTTLS required) and 465 (TLS from the start) for mail programs."""
    _, cur = run(["postconf", "-M"], check=False)
    for line in cur.splitlines():
        name = line.split()[0] if line.split() else ""
        if name in ("submission/inet", "submissions/inet", "smtps/inet"):
            run(["postconf", "-MX", name], check=False)
    for port, wrap in (("587", False), ("465", True)):
        run(["postconf", "-M", f"{port}/inet={port} inet n - y - - smtpd"])
        opts = [f"syslog_name=postfix/{'submissions' if wrap else 'submission'}"] + SUBMISSION_OPTS
        if wrap:
            opts.append("smtpd_tls_wrappermode=yes")
        for o in opts:
            run(["postconf", "-P", f"{port}/inet/{o}"])


def checks(ver: Tuple[int, int]) -> List[str]:
    problems = []
    rc, out = run(["postfix", "check"], check=False)
    if rc != 0 or re.search(r"fatal|error", out, re.I):
        problems.append("postfix check: " + out.strip()[-1200:])
    rc, out = run(["doveconf", "-n"], check=False)
    if rc != 0:
        problems.append("doveconf: " + out.strip()[-1200:])
    if which("rspamadm"):
        rc, out = run(["rspamadm", "configtest"], check=False)
        if rc != 0:
            problems.append("rspamadm configtest: " + out.strip()[-1200:])
    return problems


def reload_units(start: bool = True) -> List[str]:
    notes = []
    for u in UNITS:
        rc, _ = run(["systemctl", "is-active", "--quiet", u], check=False)
        if rc == 0:
            rc2, out = run(["systemctl", "reload-or-restart", u], check=False)
        elif start:
            rc2, out = run(["systemctl", "enable", "--now", u], check=False)
        else:
            continue
        if rc2 != 0:
            notes.append(f"{u}: {out.strip()[-300:]}")
    return notes


def status(data: Path) -> Dict[str, Any]:
    inst = installed()
    st: Dict[str, Any] = {"time": time.time(), "installed": all(inst.values()), "packages": inst, "services": {}, "versions": {}}
    for u in UNITS:
        rc, out = run(["systemctl", "is-active", u], check=False)
        word = (out.strip().split() or [""])[0]
        st["services"][u] = word if word in ("active", "inactive", "failed", "activating", "deactivating", "reloading") else "unknown"
    if inst["postfix"]:
        st["versions"]["postfix"] = run(["postconf", "-h", "mail_version"], check=False)[1].strip()
        rc, out = run(["postqueue", "-j"], check=False)
        st["queue"] = len([l for l in out.splitlines() if l.startswith("{")]) if rc == 0 else None
    if inst["dovecot"]:
        st["versions"]["dovecot"] = run(["dovecot", "--version"], check=False)[1].strip().split(" ")[0]
    if inst["rspamd"]:
        st["versions"]["rspamd"] = (re.findall(r"[\d.]+", run(["rspamd", "--version"], check=False)[1]) or [""])[0]
    st["cert"] = cert_info()
    st["configured"] = DOVE_CONF.exists()
    try:
        old = json.loads((data / "mail" / "state.json").read_text())
        st["dkim"] = old.get("dkim", {})
        st["last_apply"] = old.get("last_apply")
    except (OSError, ValueError):
        st["dkim"] = {}
    if st["configured"] and DKIM_DIR.exists():
        for key in DKIM_DIR.glob("*.key"):
            dom = key.name.rsplit(".", 2)[0]
            if dom not in st["dkim"]:
                rc, pem = run(["openssl", "rsa", "-in", str(key), "-pubout"], check=False)
                if rc == 0:
                    st["dkim"][dom] = "".join(l for l in pem.splitlines() if l and not l.startswith("-----") and "writing" not in l.lower())
    try:
        out = run(["du", "-sk", str(VMAIL_HOME)], check=False)[1].split()
        st["storage_kb"] = int(out[0]) if out and out[0].isdigit() else None
    except (OSError, ValueError):
        st["storage_kb"] = None
    return st


def save_state(data: Path, st: Dict[str, Any]) -> None:
    d = data / "mail"
    d.mkdir(parents=True, exist_ok=True)
    user = svc_user()
    try:
        shutil.chown(d, user, user)
    except (LookupError, OSError):
        pass
    write(d / "state.json", json.dumps(st, indent=1), 0o600, user, user)


def apply(data: Path, certs_only: bool = False) -> Dict[str, Any]:
    inst = installed()
    if not all(inst.values()):
        raise Fail("The mail server is not installed yet – „Install mail server“ first.")
    sp = load_spec(data)
    ver = dovecot_major()
    if certs_only:
        if not copy_certs(sp):
            raise Fail("No certificate yet")
        notes = reload_units(start=False)
        return {"ok": not notes, "message": "Certificate taken over" + (": " + "; ".join(notes) if notes else ".")}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    files = [PF / "main.cf", PF / "master.cf", DOVE_CONF, DOVE_USERS, DOVE_MASTER, DOVE / "conf.d" / "10-auth.conf", DOVE_SIEVE,
             *[PF_MAPS / n for n in ("domains", "mailboxes", "aliases", "senders", "relay_passwd")],
             *[RSPAMD_LOCAL / n for n in RSPAMD_FILES]]
    first = not (BACKUPS / "original").exists()
    bdir = backup(stamp, files)
    if first:                                     # the state before N8 Mail – „Switch off“ goes back to it
        shutil.copytree(bdir, BACKUPS / "original")
    say(f"Backup of the old configuration: {bdir}")
    try:
        ensure_vmail()
        if not copy_certs(sp):
            raise Fail("No Let's Encrypt certificate for the mail names yet – switch HTTPS on under 🌐 Netz, Ports & Domains "
                       "and wait until the certificate holds mail.<domain>.")
        dkim = dkim_keys(sp)
        PF_MAPS.mkdir(parents=True, exist_ok=True)
        for name, (text, mode) in postfix_maps(sp).items():
            write(PF_MAPS / name, text, mode)
            run(["postmap", f"hash:{PF_MAPS / name}"])
            if mode == 0o600:
                os.chmod(PF_MAPS / f"{name}.db", 0o600)
        for kv in postfix_main(sp):
            run(["postconf", "-e", kv])
        master_cf(sp)
        write(DOVE_USERS, dovecot_users(sp), 0o640, "root", "dovecot")
        # the default domain is appended to every login name – the master user is listed with and without it
        write(DOVE_MASTER, f"n8webmail:{sp['webmail_hash']}::::::\nn8webmail@{sp['domains'][0]['name']}:{sp['webmail_hash']}::::::\n",
              0o640, "root", "dovecot")
        write(DOVE_SIEVE, sieve_script())
        run(["sievec", str(DOVE_SIEVE)], check=False)
        dovecot_auth_system(True)
        write(DOVE_CONF, dovecot_conf(sp, ver))
        RSPAMD_LOCAL.mkdir(parents=True, exist_ok=True)
        for name, text in rspamd_files(sp).items():
            write(RSPAMD_LOCAL / name, text)
        problems = checks(ver)
        if problems:
            raise Fail("Check failed – old configuration restored:\n" + "\n".join(problems))
    except Exception as e:
        restore(bdir)
        for name in ("domains", "mailboxes", "aliases", "senders", "relay_passwd"):
            if (PF_MAPS / name).exists():
                run(["postmap", f"hash:{PF_MAPS / name}"], check=False)
        raise Fail(str(e))
    notes = reload_units(start=True)
    st = status(data)
    st["dkim"] = dkim
    st["last_apply"] = {"time": time.time(), "ok": not notes, "mailboxes": len(sp["mailboxes"]), "domains": [d["name"] for d in sp["domains"]],
                        "notes": notes}
    save_state(data, st)
    msg = f"Mail server configured: {len(sp['domains'])} domain(s), {len(sp['mailboxes'])} mailbox(es), Dovecot {ver[0]}.{ver[1]}."
    if notes:
        msg += " Services: " + "; ".join(notes)
    return {"ok": not notes, "message": msg}


def install(data: Path) -> Dict[str, Any]:
    if all(installed().values()):
        say("Mail packages already installed.")
    else:
        if not which("apt-get"):
            raise Fail("apt-get is missing – install postfix, dovecot-imapd, dovecot-lmtpd, dovecot-sieve and rspamd by hand.")
        host = "localhost"
        try:
            sp = load_spec(data)
            host = sp["hostname"]
        except Fail:
            pass
        run(["debconf-set-selections"], inp=f"postfix postfix/main_mailer_type select Internet Site\npostfix postfix/mailname string {host}\n",
            check=False)
        env = {"DEBIAN_FRONTEND": "noninteractive"}
        say("apt-get update …")
        run(["apt-get", "update", "-qq"], check=False, env=env)
        say("Installing " + " ".join(PACKAGES) + " …")
        run(["apt-get", "install", "-y", "-q", "--no-install-recommends", "-o", "DPkg::Lock::Timeout=120", *PACKAGES], env=env)
    ensure_vmail()
    try:
        load_spec(data)
    except Fail as e:
        st = status(data)
        save_state(data, st)
        return {"ok": True, "message": f"Mail server installed. Next: mail domains and „Apply“ ({e})."}
    return apply(data)


def disable(data: Path) -> Dict[str, Any]:
    orig = BACKUPS / "original"
    for u in ("dovecot", "rspamd"):
        run(["systemctl", "disable", "--now", u], check=False)
    if orig.exists():
        restore(orig)
    for f in [DOVE_CONF, DOVE_USERS, DOVE_MASTER]:
        if f.exists():
            f.unlink()
    dovecot_auth_system(False)
    run(["systemctl", "reload-or-restart", "postfix"], check=False)
    st = status(data)
    save_state(data, st)
    return {"ok": True, "message": "Mail server switched off – Postfix has its configuration from before N8 Mail. Mailboxes stay in "
                                   f"{VMAIL_HOME}, DKIM keys in {DKIM_DIR}."}


def main(argv: List[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("status", "apply", "install", "certs", "disable"):
        print(json.dumps({"ok": False, "message": "usage: mailctl.py status|apply|install|certs|disable"}))
        return 2
    if os.geteuid() != 0:
        print(json.dumps({"ok": False, "message": "mailctl must run as root (sudo)"}))
        return 1
    os.umask(0o022)
    data = data_dir()
    act = argv[1]
    try:
        if act == "status":
            st = status(data)
            save_state(data, st)
            res = {"ok": True, "message": "", "status": st}
        elif act == "apply":
            res = apply(data)
        elif act == "certs":
            res = apply(data, certs_only=True)
        elif act == "install":
            res = install(data)
        else:
            res = disable(data)
    except Fail as e:
        res = {"ok": False, "message": str(e)}
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "message": f"{type(e).__name__}: {e}"}
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
