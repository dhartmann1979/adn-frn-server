"""E-mail on the ADN-FRN-Server – the dashboard side.

* Every dashboard user has a mailbox ``<username>@<main domain>`` (and the same name at every further mail domain), the same
  password as in the dashboard (Dovecot gets it as SHA512-CRYPT, see mailpw.py).
* Postfix (SMTP), Dovecot (IMAP, LMTP) and Rspamd (spam, DKIM signing, SPF/DKIM/DMARC checks) run on this machine. The
  dashboard never writes system files itself: it writes a *specification* (``<data>/mail/spec.json``) and asks the root helper
  ``mailctl.py`` (sudo, fixed arguments) to check it and turn it into the configuration of the three services.
* Only TLS: IMAPS 993, SMTPS 465 and submission 587 with STARTTLS required; port 25 offers STARTTLS (or requires it);
  the upstream is always reached encrypted. The certificate is the dashboard's Let's Encrypt certificate, which also holds
  ``mail.<domain>`` (and ``mta-sts.<domain>``) of every mail domain.
* DNS templates for MX, A/AAAA, SPF, DKIM, DMARC, BIMI, MTA-STS, TLS-RPT and the autoconfig SRV records, with a live check.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import random
import re
import secrets
import socket
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
LOCAL_RE = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,62}[a-z0-9])?$")
WEBMAIL_MASTER = "n8webmail"
ROLE_ALIASES = ("postmaster", "abuse", "hostmaster", "dmarc", "tls-reports")
MAILCTL_TIMEOUT = 900


class MailError(Exception):
    """Message is shown to the admin."""


# ---------------------------------------------------------------- names
def domains(s: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for d in re.split(r"[,\s;]+", str(s.get("mail.domains") or "").lower()):
        d = d.strip().rstrip(".")
        if d and DOMAIN_RE.fullmatch(d) and d not in out:
            out.append(d)
    return out


# second-level public suffixes (the common ones) – foo.example.co.uk → example.co.uk
_SLD = {"co.uk", "org.uk", "me.uk", "ac.uk", "gov.uk", "ltd.uk", "plc.uk", "net.uk", "com.au", "net.au", "org.au", "co.nz", "org.nz",
        "co.at", "or.at", "co.jp", "ne.jp", "or.jp", "com.br", "net.br", "co.za", "com.pl", "net.pl", "org.pl", "com.tr", "co.il",
        "com.cn", "com.mx", "co.in", "co.kr", "com.ar", "com.es", "com.pt", "com.gr", "com.ua", "co.id", "com.sg", "com.my", "com.hk", "com.tw"}


def base_domain(host: str) -> str:
    """news.example.org → example.org; www.example.co.uk → example.co.uk; mail.x.de → x.de."""
    labels = str(host or "").strip().lower().rstrip(".").split(".")
    if len(labels) < 2:
        return ""
    n = 3 if ".".join(labels[-2:]) in _SLD and len(labels) >= 3 else 2
    d = ".".join(labels[-n:])
    return d if DOMAIN_RE.fullmatch(d) else ""


def auto_domains(hosts: List[str], current: List[str], skip: List[str]) -> List[str]:
    """Mail domains after adding the base domains of all web domains (keeps the order, the main domain stays first)."""
    out = list(current)
    for h in hosts:
        b = base_domain(h)
        if b and b not in out and b not in skip:
            out.append(b)
    return out


def resolve(name: str) -> set:
    try:
        return {a[4][0] for a in socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)}
    except OSError:
        return set()


def dns_ready(name: str, mine: set) -> bool:
    """Does the name point to this server? (Only then Let's Encrypt can check it – a name without DNS would stop the whole certificate.)"""
    return bool(resolve(name) & mine)


def host_of(domain: str) -> str:
    return f"mail.{domain}"


def cert_names(s: Dict[str, Any]) -> List[str]:
    """Names the mail server needs on the Let's Encrypt certificate (added to the dashboard's certificate)."""
    if not s.get("mail.enabled"):
        return []
    out = []
    for d in domains(s):
        out.append(host_of(d))
        if s.get("mail.mta_sts", "off") != "off":
            out.append(f"mta-sts.{d}")
    return out


def local_part(username: str) -> Optional[str]:
    lp = str(username or "").strip().lower()
    return lp if LOCAL_RE.fullmatch(lp) and ".." not in lp else None


def mailboxes(db, s: Dict[str, Any]) -> Dict[str, Any]:
    """Every dashboard user → mailbox. Returns {boxes: [...], skipped: [...], waiting: [...]}."""
    doms = domains(s)
    boxes, skipped, waiting = [], [], []
    rows = db.q("SELECT id, username, display_name, role, disabled, mail_hash FROM users ORDER BY username COLLATE NOCASE")
    for r in rows:
        lp = local_part(r["username"])
        info = {"username": r["username"], "display_name": r["display_name"], "role": r["role"], "disabled": bool(r["disabled"])}
        if not lp:
            skipped.append({**info, "reason": "Username is not usable as an e-mail address (letters, digits, . _ - only)"})
            continue
        if lp in ROLE_ALIASES:
            skipped.append({**info, "reason": f"{lp}@ is reserved for the role addresses"})
            continue
        addr = f"{lp}@{doms[0]}" if doms else ""
        box = {**info, "local": lp, "address": addr, "aliases": [f"{lp}@{d}" for d in doms[1:]], "ready": bool(r["mail_hash"]),
               "hash": r["mail_hash"]}
        if not r["mail_hash"]:
            waiting.append(box)
        boxes.append(box)
    return {"boxes": boxes, "skipped": skipped, "waiting": waiting}


def postmaster_box(db, s: Dict[str, Any], boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    want = str(s.get("mail.postmaster") or "").strip().lower()
    active = [b for b in boxes if not b["disabled"]]
    for b in active:
        if want and b["username"].lower() == want:
            return b
    for b in active:
        if b["role"] == "superadmin":
            return b
    return active[0] if active else None


# ---------------------------------------------------------------- files of the dashboard
def mail_dir(data: Path) -> Path:
    d = Path(data) / "mail"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def webmail_secret(db) -> str:
    v = db.kv_get("mail.webmail_secret")
    if not v:
        v = secrets.token_urlsafe(32)
        db.kv_set("mail.webmail_secret", v)
    return v


def read_state(data: Path) -> Dict[str, Any]:
    try:
        return json.loads((Path(data) / "mail" / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_spec(db, s: Dict[str, Any], cert: Optional[Tuple[str, str]], data: Path) -> Dict[str, Any]:
    """Everything mailctl needs – plain data, checked again by mailctl before anything is written."""
    from .mailpw import mail_hash
    doms = domains(s)
    if not doms:
        raise MailError("Enter at least one mail domain first.")
    mb = mailboxes(db, s)
    boxes = [b for b in mb["boxes"] if not b["disabled"] and b["hash"]]
    pm = postmaster_box(db, s, boxes)
    aliases: List[List[str]] = []
    for b in boxes:
        aliases += [[a, b["address"]] for a in b["aliases"]]
    if pm:
        for d in doms:
            for role in ROLE_ALIASES:
                aliases.append([f"{role}@{d}", pm["address"]])
    relay = None
    if s.get("mail.relay_host"):
        relay = {"host": s["mail.relay_host"].strip().lower(), "port": int(s.get("mail.relay_port") or 587),
                 "tls": s.get("mail.relay_tls") or "starttls", "user": s.get("mail.relay_user") or "",
                 "password": s.get("mail.relay_password") or ""}
    ws = webmail_secret(db)
    return {
        "format": "n8mail-1", "generated": time.time(),
        "hostname": host_of(doms[0]), "domains": [{"name": d, "host": host_of(d)} for d in doms],
        "mailboxes": [{"address": b["address"], "hash": b["hash"]} for b in boxes],
        "aliases": aliases,
        "senders": [[b["address"], b["address"]] for b in boxes] + [[a, b["address"]] for b in boxes for a in b["aliases"]],
        "postmaster": pm["address"] if pm else "",
        "relay": relay,
        "inbound_tls": bool(s.get("mail.inbound_tls")),
        "quota_mb": int(s.get("mail.quota_mb") or 2048), "max_size_mb": int(s.get("mail.max_size_mb") or 25),
        "selector": s.get("mail.dkim_selector") or "n8mail",
        "spam": {"junk": int(s.get("mail.spam_junk") or 6), "reject": int(s.get("mail.spam_reject") or 15)},
        "cert": {"fullchain": cert[0], "privkey": cert[1]} if cert else None,
        "webmail": {"master": WEBMAIL_MASTER, "hash": mail_hash(ws)},
    }


def write_spec(data: Path, spec: Dict[str, Any]) -> Path:
    p = mail_dir(data) / "spec.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(spec, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(p)
    return p


# ---------------------------------------------------------------- the root helper
def mailctl_cmd(app_dir: Path, action: str) -> List[str]:
    if action not in ("status", "apply", "install", "disable", "certs"):
        raise MailError("unknown action")
    return ["sudo", "-n", "/usr/bin/python3", "-I", str(Path(app_dir) / "frnadn" / "mailctl.py"), action]


async def run_mailctl(app_dir: Path, action: str) -> Dict[str, Any]:
    """Run ``mailctl.py <action>`` as root. Returns {ok, message, log}."""
    cmd = mailctl_cmd(app_dir, action)
    try:
        p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                 stdin=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(p.communicate(), MAILCTL_TIMEOUT)
    except FileNotFoundError:
        return {"ok": False, "message": "sudo is missing.", "log": ""}
    except asyncio.TimeoutError:
        return {"ok": False, "message": f"mailctl {action}: no answer after {MAILCTL_TIMEOUT // 60} minutes.", "log": ""}
    text = out.decode("utf-8", "replace")
    last = {}
    for line in reversed(text.strip().splitlines()):
        if line.startswith("{"):
            try:
                last = json.loads(line)
                break
            except ValueError:
                pass
    if p.returncode != 0 and not last:
        hint = " – the sudo rule is missing: Admin → System → Permissions & sudo → Fix" if "password is required" in text or "a terminal" in text else ""
        return {"ok": False, "message": f"mailctl {action} failed{hint}.", "log": text[-6000:]}
    return {"ok": bool(last.get("ok", p.returncode == 0)), "message": last.get("message", ""), "log": text[-6000:], **{k: v for k, v in last.items() if k not in ("ok", "message")}}


# ---------------------------------------------------------------- DNS templates
def _ips() -> Dict[str, List[str]]:
    """Public addresses of this machine as far as we can see (the admin can still adjust the template)."""
    v4, v6 = set(), set()
    for fam, target in ((socket.AF_INET, ("1.1.1.1", 53)), (socket.AF_INET6, ("2606:4700:4700::1111", 53))):
        try:
            with socket.socket(fam, socket.SOCK_DGRAM) as so:
                so.connect(target)
                ip = so.getsockname()[0]
                if ipaddress.ip_address(ip).is_global:
                    (v4 if fam == socket.AF_INET else v6).add(ip)
        except OSError:
            pass
    return {"v4": sorted(v4), "v6": sorted(v6)}


def dkim_record(pub_b64: str) -> str:
    return f"v=DKIM1; k=rsa; p={pub_b64}"


def dmarc_record(s: Dict[str, Any], d: str, main: str) -> str:
    pol = s.get("mail.dmarc_policy") or "quarantine"
    al = s.get("mail.dmarc_alignment") or "r"
    rua = s.get("mail.dmarc_rua") or f"dmarc@{main}"
    parts = [f"v=DMARC1", f"p={pol}", f"sp={pol}", f"adkim={al}", f"aspf={al}", f"rua=mailto:{rua}", "fo=1", "pct=100"]
    return "; ".join(parts)


def bimi_url(base: str, d: str) -> str:
    return f"{base}/.well-known/bimi/{d}.svg"


def dns_templates(s: Dict[str, Any], state: Dict[str, Any], web_base: str, ips: Optional[Dict[str, List[str]]] = None) -> List[Dict[str, Any]]:
    """Records per mail domain. web_base = https://<dashboard domain> (BIMI logo and MTA-STS policy live there)."""
    doms = domains(s)
    if not doms:
        return []
    ips = ips if ips is not None else _ips()
    main = doms[0]
    sel = s.get("mail.dkim_selector") or "n8mail"
    keys = (state.get("dkim") or {})
    spf_extra = (s.get("mail.relay_spf") or "").strip()
    out = []
    for d in doms:
        host = host_of(d)
        recs: List[Dict[str, Any]] = []
        add = lambda t, n, v, why, need=True, prio=None: recs.append(  # noqa: E731
            {"type": t, "name": n, "value": v, "why": why, "required": need, **({"priority": prio} if prio is not None else {})})
        for ip in ips.get("v4", []) or ["<IPv4 of this server>"]:
            add("A", host, ip, "Address of the mail server")
        for ip in ips.get("v6", []):
            add("AAAA", host, ip, "IPv6 address of the mail server")
        add("MX", d, f"{host}.", "Mail for the domain goes to this server", prio=10)
        spf = "v=spf1 mx" + (f" {spf_extra}" if spf_extra else "") + " -all"
        add("TXT", d, spf, "SPF: who may send for the domain (this server" + (" and the upstream" if spf_extra else "") + ")")
        k = keys.get(d)
        add("TXT", f"{sel}._domainkey.{d}", dkim_record(k) if k else "(appears after „Apply“ – the key is made on the server)",
            "DKIM: the public key of the signature")
        add("TXT", f"_dmarc.{d}", dmarc_record(s, d, main), "DMARC: policy and reports")
        if s.get("mail.bimi"):
            v = f"v=BIMI1; l={bimi_url(web_base, d)}" + (f"; a={s['mail.bimi_vmc']}" if s.get("mail.bimi_vmc") else "; a=")
            add("TXT", f"default._bimi.{d}", v, "BIMI: logo next to your mails (needs DMARC quarantine/reject)", need=False)
        if s.get("mail.mta_sts", "off") != "off":
            add("TXT", f"_mta-sts.{d}", f"v=STSv1; id={sts_id(s)}", "MTA-STS: deliver only encrypted", need=False)
            for ip in ips.get("v4", []) or ["<IPv4 of this server>"]:
                add("A", f"mta-sts.{d}", ip, "MTA-STS policy (https://mta-sts.…/.well-known/mta-sts.txt)", need=False)
            add("TXT", f"_smtp._tls.{d}", f"v=TLSRPTv1; rua=mailto:tls-reports@{main}", "TLS-RPT: reports about TLS problems", need=False)
        add("SRV", f"_imaps._tcp.{d}", f"0 1 993 {host}.", "Mail programs find IMAP by themselves", need=False)
        add("SRV", f"_submissions._tcp.{d}", f"0 1 465 {host}.", "Mail programs find SMTP by themselves", need=False)
        add("SRV", f"_imap._tcp.{d}", "0 0 0 .", "No unencrypted IMAP", need=False)
        add("SRV", f"_submission._tcp.{d}", f"0 1 587 {host}.", "SMTP with STARTTLS", need=False)
        add("PTR", (ips.get("v4") or ["<IPv4>"])[0], f"{host_of(main)}.", "Reverse DNS at the hosting provider – very important against spam filters", need=True)
        out.append({"domain": d, "host": host, "records": recs})
    return out


def zone_text(tpl: Dict[str, Any]) -> str:
    """One domain as a BIND zone snippet (the PTR goes to the hosting provider)."""
    lines = [f"; {tpl['domain']} – N8 Mail ({time.strftime('%Y-%m-%d')})"]
    for r in tpl["records"]:
        if r["type"] == "PTR":
            lines.append(f"; PTR {r['name']} -> {r['value']}  (set at your hosting provider)")
            continue
        v = r["value"]
        if r["type"] == "TXT":
            chunks = [v[i:i + 250] for i in range(0, len(v), 250)] or [""]
            v = " ".join(f'"{c}"' for c in chunks)
        elif r["type"] == "MX":
            v = f"{r.get('priority', 10)} {v}"
        lines.append(f"{r['name']}.\t3600\tIN\t{r['type']}\t{v}")
    return "\n".join(lines) + "\n"


def sts_id(s: Dict[str, Any]) -> str:
    """Changes whenever the policy changes – senders then fetch it again."""
    import hashlib
    raw = f"{s.get('mail.mta_sts')}|{','.join(domains(s))}"
    return "n8" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def mta_sts_policy(s: Dict[str, Any], d: str) -> str:
    mode = s.get("mail.mta_sts") or "testing"
    return f"version: STSv1\nmode: {mode}\nmx: {host_of(d)}\nmax_age: {604800 if mode == 'enforce' else 86400}\n"


# ---------------------------------------------------------------- BIMI logo (SVG Tiny PS)
_BAD_SVG = re.compile(r"<\s*(script|foreignObject|image|iframe|object|embed|a|animate|set|style)\b|\son\w+\s*=|javascript:|xlink:href\s*=\s*[\"'](?!#)|href\s*=\s*[\"'](?!#)|<!ENTITY|<!DOCTYPE",
                      re.I)


def bimi_check(svg: str) -> List[str]:
    """Problems of an uploaded logo for BIMI (SVG Tiny Portable/Secure). Empty list = fine."""
    p = []
    if len(svg.encode("utf-8")) > 32 * 1024:
        p.append("larger than 32 KB")
    if not re.search(r"<svg\b", svg):
        p.append("no <svg> element")
    if not re.search(r'baseProfile\s*=\s*["\']tiny-ps["\']', svg):
        p.append('baseProfile="tiny-ps" is missing')
    if not re.search(r'version\s*=\s*["\']1\.2["\']', svg):
        p.append('version="1.2" is missing')
    if not re.search(r"<title\b[^>]*>[^<]+</title>", svg):
        p.append("<title> is missing")
    if re.search(r'\s(x|y)\s*=\s*["\'][^"\']+["\']', svg[:svg.find(">") + 1] if "<svg" in svg else ""):
        p.append("x/y on the <svg> element are not allowed")
    if _BAD_SVG.search(svg):
        p.append("forbidden content (script, image, link, style or entity)")
    return p


def bimi_default(title: str, accent: str = "#5ac8fa", text: str = "") -> str:
    """A square logo that meets SVG Tiny PS: coloured background, moon-and-antenna sign and initials."""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent or ""):
        accent = "#5ac8fa"
    letters = text or "".join(w[0] for w in re.findall(r"[A-Za-zÄÖÜäöü0-9]+", title or "N8"))[:3].upper() or "N8"
    letters = re.sub(r"[^A-Z0-9ÄÖÜ]", "", letters)[:3] or "N8"
    t = re.sub(r"[<>&\"']", "", title or "N8")[:60]
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" version="1.2" baseProfile="tiny-ps" viewBox="0 0 512 512">
<title>{t}</title>
<rect width="512" height="512" fill="#0b1224"/>
<circle cx="256" cy="256" r="228" fill="{accent}"/>
<circle cx="256" cy="256" r="200" fill="#0b1224"/>
<path d="M296 96a134 134 0 1 0 118 196a106 106 0 1 1-118-196z" fill="{accent}"/>
<text x="236" y="300" font-family="Arial, Helvetica, sans-serif" font-size="96" font-weight="700" text-anchor="middle" fill="#ffffff">{letters}</text>
</svg>
'''


# ---------------------------------------------------------------- a tiny DNS client (for the live check, no extra package)
def _nameservers() -> List[str]:
    out = []
    try:
        for line in Path("/etc/resolv.conf").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                out.append(parts[1])
    except OSError:
        pass
    return out or ["1.1.1.1", "9.9.9.9"]


DNS_PORT = 53
QTYPES = {"A": 1, "MX": 15, "TXT": 16, "AAAA": 28, "SRV": 33, "PTR": 12}


def _qname(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode("idna") for p in name.rstrip(".").split(".")) + b"\0"


def _name(msg: bytes, off: int) -> Tuple[str, int]:
    labels, jumped, end = [], False, off
    for _ in range(64):
        ln = msg[off]
        if ln == 0:
            off += 1
            break
        if ln & 0xC0 == 0xC0:
            ptr = ((ln & 0x3F) << 8) | msg[off + 1]
            if not jumped:
                end = off + 2
            jumped, off = True, ptr
            continue
        labels.append(msg[off + 1:off + 1 + ln].decode("ascii", "replace"))
        off += 1 + ln
    return ".".join(labels), (end if jumped else off)


def dns_query(name: str, qtype: str, timeout: float = 3.0) -> List[str]:
    if qtype == "PTR":
        name = ipaddress.ip_address(name).reverse_pointer
    qt = QTYPES[qtype]
    qid = random.randint(0, 65535)
    pkt = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + _qname(name) + struct.pack(">HH", qt, 1)
    for ns in _nameservers()[:3]:
        try:
            fam = socket.AF_INET6 if ":" in ns else socket.AF_INET
            with socket.socket(fam, socket.SOCK_DGRAM) as so:
                so.settimeout(timeout)
                so.sendto(pkt, (ns, DNS_PORT))
                msg, _ = so.recvfrom(4096)
            if msg[2] & 0x02:   # truncated → TCP
                with socket.create_connection((ns, DNS_PORT), timeout) as so:
                    so.sendall(struct.pack(">H", len(pkt)) + pkt)
                    ln = struct.unpack(">H", so.recv(2))[0]
                    msg = b""
                    while len(msg) < ln:
                        chunk = so.recv(ln - len(msg))
                        if not chunk:
                            break
                        msg += chunk
            rid, flags, qd, an = struct.unpack(">HHHH", msg[:8])
            if rid != qid:
                continue
            off = 12
            for _ in range(qd):
                _, off = _name(msg, off)
                off += 4
            out = []
            for _ in range(an):
                _, off = _name(msg, off)
                t, _c, _ttl, rdl = struct.unpack(">HHIH", msg[off:off + 10])
                off += 10
                rd = msg[off:off + rdl]
                if t == qt:
                    if t == 1:
                        out.append(socket.inet_ntop(socket.AF_INET, rd))
                    elif t == 28:
                        out.append(socket.inet_ntop(socket.AF_INET6, rd))
                    elif t == 16:
                        i, s = 0, b""
                        while i < len(rd):
                            ln = rd[i]
                            s += rd[i + 1:i + 1 + ln]
                            i += 1 + ln
                        out.append(s.decode("utf-8", "replace"))
                    elif t == 15:
                        pref = struct.unpack(">H", rd[:2])[0]
                        out.append(f"{pref} {_name(msg, off + 2)[0]}.")
                    elif t == 33:
                        pr, w, port = struct.unpack(">HHH", rd[:6])
                        out.append(f"{pr} {w} {port} {_name(msg, off + 6)[0]}.")
                    elif t == 12:
                        out.append(_name(msg, off)[0] + ".")
                off += rdl
            return out
        except (OSError, struct.error, IndexError, ValueError):
            continue
    return []


def _norm(v: str) -> str:
    return re.sub(r"\s+", " ", v.strip().rstrip(".").lower())


def check_record(r: Dict[str, Any]) -> Dict[str, Any]:
    """Compare one template record with what the DNS says right now."""
    if "<" in r["value"] or r["value"].startswith("("):
        return {"status": "skip", "found": []}
    try:
        found = dns_query(r["name"], r["type"])
    except Exception:  # noqa: BLE001
        found = []
    want = _norm(r["value"] if r["type"] != "MX" else f"{r.get('priority', 10)} {r['value']}")
    if r["type"] == "TXT":
        prefix = r["value"].split(";")[0].split(" ")[0].lower()
        same = [f for f in found if f.lower().startswith(prefix)]
        if any(_norm(f) == want or _norm(f).replace(" ", "") == want.replace(" ", "") for f in same):
            return {"status": "ok", "found": same}
        return {"status": "diff" if same else "missing", "found": same}
    if any(_norm(f) == want for f in found):
        return {"status": "ok", "found": found}
    return {"status": "diff" if found else "missing", "found": found}
