"""Webmail of N8 Mail – reads and writes the mailbox of the logged-in dashboard user.

The dashboard logs in to Dovecot (IMAPS on 127.0.0.1:993) as ``<address>*n8webmail`` with its own master secret, so it never
needs (or keeps) the user's password. Sending goes to the local Postfix (127.0.0.1:25, trusted as localhost), which signs with
DKIM and relays through the upstream; a copy is stored in "Sent". The From address is always the user's own address.
"""
from __future__ import annotations

import base64
import email
import email.policy
import html
import imaplib
import re
import smtplib
import ssl
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, make_msgid, parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

IMAP_HOST, IMAP_PORT, SMTP_HOST, SMTP_PORT = "127.0.0.1", 993, "127.0.0.1", 25
SPECIAL = {"\\Sent": "Sent", "\\Drafts": "Drafts", "\\Junk": "Junk", "\\Trash": "Trash"}
FOLDER_RE = re.compile(r"^[^\x00-\x1f\"\\*%]{1,200}$")
MAX_SEND = 20 * 1024 * 1024


class MailboxError(Exception):
    """Message is shown to the user."""


def _ctx() -> ssl.SSLContext:
    c = ssl.create_default_context()
    c.check_hostname = False            # 127.0.0.1 is not on the certificate – the connection never leaves the machine
    c.verify_mode = ssl.CERT_NONE
    return c


def _dec(v: Any) -> str:
    if v is None:
        return ""
    try:
        return str(make_header(decode_header(str(v))))
    except Exception:  # noqa: BLE001
        return str(v)


def _q(folder: str) -> str:
    if not FOLDER_RE.fullmatch(folder or ""):
        raise MailboxError("Invalid folder")
    return '"' + folder + '"'


class Box:
    def __init__(self, address: str, secret: str):
        self.address = address
        try:
            self.imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=_ctx(), timeout=15)
            self.imap.login(f"{address}*n8webmail", secret)
        except (OSError, imaplib.IMAP4.error) as e:
            raise MailboxError(f"Mailbox not reachable ({e.__class__.__name__}) – is the mail server running?")

    def __enter__(self) -> "Box":
        return self

    def __exit__(self, *a) -> None:
        try:
            self.imap.logout()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ folders
    def folders(self) -> List[Dict[str, Any]]:
        typ, data = self.imap.list()
        out = []
        for raw in data or []:
            line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            m = re.match(r'\((?P<flags>[^)]*)\) "(?P<sep>[^"]*)" (?P<name>.+)$', line)
            if not m:
                continue
            name = m.group("name").strip().strip('"')
            flags = m.group("flags")
            role = "inbox" if name.upper() == "INBOX" else next((v.lower() for k, v in SPECIAL.items() if k in flags), "")
            unseen, total = 0, 0
            try:
                typ, st = self.imap.status(_q(name), "(MESSAGES UNSEEN)")
                s = st[0].decode() if st and st[0] else ""
                total = int((re.search(r"MESSAGES (\d+)", s) or [0, 0])[1])
                unseen = int((re.search(r"UNSEEN (\d+)", s) or [0, 0])[1])
            except Exception:  # noqa: BLE001
                pass
            out.append({"name": name, "role": role, "unseen": unseen, "total": total})
        order = {"inbox": 0, "drafts": 1, "sent": 2, "junk": 3, "trash": 4, "": 5}
        return sorted(out, key=lambda f: (order.get(f["role"], 5), f["name"].lower()))

    def quota(self) -> Optional[Dict[str, int]]:
        try:
            typ, data = self.imap.getquotaroot("INBOX")
            for d in data[1] if len(data) > 1 else []:
                s = d.decode() if isinstance(d, bytes) else str(d)
                m = re.search(r"STORAGE (\d+) (\d+)", s)
                if m:
                    return {"used_kb": int(m.group(1)), "limit_kb": int(m.group(2))}
        except Exception:  # noqa: BLE001
            pass
        return None

    def role_folder(self, role: str) -> str:
        for f in self.folders():
            if f["role"] == role:
                return f["name"]
        return {"sent": "Sent", "trash": "Trash", "drafts": "Drafts", "junk": "Junk"}.get(role, "INBOX")

    # ------------------------------------------------------------ lists
    def list(self, folder: str, page: int = 0, per: int = 40, query: str = "") -> Dict[str, Any]:
        typ, d = self.imap.select(_q(folder), readonly=True)
        if typ != "OK":
            raise MailboxError("Folder not found")
        if query:
            q = query.replace('"', " ").replace("\\", " ")[:100]
            typ, data = self.imap.uid("SEARCH", "CHARSET", "UTF-8", "OR", "OR", "SUBJECT", f'"{q}"', "FROM", f'"{q}"', "TO", f'"{q}"')
        else:
            typ, data = self.imap.uid("SEARCH", None, "ALL")
        uids = [int(x) for x in (data[0] or b"").split()] if typ == "OK" else []
        uids.sort(reverse=True)
        total = len(uids)
        chunk = uids[page * per:(page + 1) * per]
        items: List[Dict[str, Any]] = []
        if chunk:
            typ, data = self.imap.uid("FETCH", ",".join(map(str, chunk)),
                                      "(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
            cur: Dict[str, Any] = {}
            for part in data or []:
                if isinstance(part, tuple):
                    meta = part[0].decode("utf-8", "replace")
                    hdr = email.message_from_bytes(part[1], policy=email.policy.compat32)
                    uid = int((re.search(r"UID (\d+)", meta) or [0, 0])[1])
                    flags = (re.search(r"FLAGS \(([^)]*)\)", meta) or [0, ""])[1]
                    size = int((re.search(r"RFC822\.SIZE (\d+)", meta) or [0, 0])[1])
                    att = bool(re.search(r'"attachment"', meta, re.I))
                    frm = getaddresses([_dec(hdr.get("From"))])
                    to = getaddresses([_dec(hdr.get("To"))])
                    try:
                        ts = parsedate_to_datetime(hdr.get("Date")).timestamp()
                    except Exception:  # noqa: BLE001
                        ts = None
                    cur[uid] = {"uid": uid, "subject": _dec(hdr.get("Subject")) or "(no subject)",
                                "from": {"name": frm[0][0], "address": frm[0][1]} if frm else {"name": "", "address": ""},
                                "to": [a for _, a in to][:3], "date": ts, "seen": "\\Seen" in flags,
                                "flagged": "\\Flagged" in flags, "answered": "\\Answered" in flags, "size": size, "attachment": att}
            items = [cur[u] for u in chunk if u in cur]
        return {"folder": folder, "total": total, "page": page, "per": per, "items": items}

    # ------------------------------------------------------------ one message
    def _fetch(self, folder: str, uid: int, readonly: bool) -> email.message.EmailMessage:
        typ, _ = self.imap.select(_q(folder), readonly=readonly)
        if typ != "OK":
            raise MailboxError("Folder not found")
        typ, data = self.imap.uid("FETCH", str(int(uid)), "(BODY.PEEK[])")
        raw = next((p[1] for p in data or [] if isinstance(p, tuple)), None)
        if not raw:
            raise MailboxError("Message not found")
        return email.message_from_bytes(raw, policy=email.policy.default)

    def message(self, folder: str, uid: int) -> Dict[str, Any]:
        msg = self._fetch(folder, uid, readonly=False)
        self.imap.uid("STORE", str(int(uid)), "+FLAGS", "(\\Seen)")
        text, has_html = "", False
        body = msg.get_body(preferencelist=("plain",))
        if body is not None:
            try:
                text = body.get_content()
            except Exception:  # noqa: BLE001
                text = body.get_payload(decode=True).decode("utf-8", "replace") if body.get_payload(decode=True) else ""
        h = msg.get_body(preferencelist=("html",))
        if h is not None:
            has_html = True
            if not text:
                try:
                    text = _html_to_text(h.get_content())
                except Exception:  # noqa: BLE001
                    text = ""
        atts = []
        for i, part in enumerate(msg.walk()):
            if part.is_multipart():
                continue
            fn = part.get_filename()
            disp = part.get_content_disposition()
            if fn or disp == "attachment":
                payload = part.get_payload(decode=True) or b""
                atts.append({"part": i, "name": _dec(fn) or f"part-{i}", "type": part.get_content_type(), "size": len(payload),
                             "inline": disp == "inline"})
        try:
            ts = parsedate_to_datetime(msg.get("Date")).timestamp()
        except Exception:  # noqa: BLE001
            ts = None
        auth = str(msg.get("Authentication-Results") or "")
        return {"uid": int(uid), "folder": folder, "subject": _dec(msg.get("Subject")), "from": _dec(msg.get("From")),
                "to": _dec(msg.get("To")), "cc": _dec(msg.get("Cc")), "reply_to": _dec(msg.get("Reply-To")), "date": ts,
                "message_id": str(msg.get("Message-ID") or ""), "references": str(msg.get("References") or ""),
                "text": text[:500_000], "html": has_html, "attachments": atts,
                "checks": {k: (re.search(rf"{k}=(\w+)", auth) or [0, ""])[1] for k in ("spf", "dkim", "dmarc")},
                "spam": "yes" in str(msg.get("X-Spam") or "").lower() or str(msg.get("X-Spam-Status") or "").lower().startswith("yes")}

    def html(self, folder: str, uid: int, images: bool) -> str:
        msg = self._fetch(folder, uid, readonly=True)
        h = msg.get_body(preferencelist=("html",))
        if h is None:
            return ""
        doc = h.get_content()
        # inline images (cid:) as data: URLs, links open outside
        cids = {}
        for part in msg.walk():
            cid = str(part.get("Content-ID") or "").strip("<>")
            if cid and part.get_content_maintype() == "image":
                cids[cid] = f"data:{part.get_content_type()};base64," + base64.b64encode(part.get_payload(decode=True) or b"").decode()
        doc = re.sub(r"cid:([^\"'\s>)]+)", lambda m: cids.get(m.group(1), "#"), doc)
        return '<base target="_blank"><meta name="referrer" content="no-referrer">' + doc

    def attachment(self, folder: str, uid: int, part_no: int) -> Tuple[str, bytes]:
        msg = self._fetch(folder, uid, readonly=True)
        for i, part in enumerate(msg.walk()):
            if i == int(part_no) and not part.is_multipart():
                return _dec(part.get_filename()) or f"part-{i}", part.get_payload(decode=True) or b""
        raise MailboxError("Attachment not found")

    # ------------------------------------------------------------ changes
    def flags(self, folder: str, uids: List[int], add: List[str], remove: List[str]) -> None:
        self.imap.select(_q(folder))
        ids = ",".join(str(int(u)) for u in uids)
        allowed = {"seen": "\\Seen", "flagged": "\\Flagged"}
        if add:
            self.imap.uid("STORE", ids, "+FLAGS", "(" + " ".join(allowed[f] for f in add if f in allowed) + ")")
        if remove:
            self.imap.uid("STORE", ids, "-FLAGS", "(" + " ".join(allowed[f] for f in remove if f in allowed) + ")")

    def move(self, folder: str, uids: List[int], to: str) -> None:
        self.imap.select(_q(folder))
        ids = ",".join(str(int(u)) for u in uids)
        typ, _ = self.imap.uid("MOVE", ids, _q(to))
        if typ != "OK":
            self.imap.uid("COPY", ids, _q(to))
            self.imap.uid("STORE", ids, "+FLAGS", "(\\Deleted)")
            self.imap.expunge()

    def delete(self, folder: str, uids: List[int]) -> str:
        trash = self.role_folder("trash")
        if folder == trash:
            self.imap.select(_q(folder))
            self.imap.uid("STORE", ",".join(str(int(u)) for u in uids), "+FLAGS", "(\\Deleted)")
            self.imap.expunge()
            return "deleted"
        self.move(folder, uids, trash)
        return "trash"

    def append(self, folder: str, raw: bytes, flags: str = "(\\Seen)") -> None:
        self.imap.append(_q(folder), flags, imaplib.Time2Internaldate(time.time()), raw)


def _html_to_text(s: str) -> str:
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(s)).strip()


def _addrs(v: str) -> List[str]:
    out = []
    for name, a in getaddresses([str(v or "")]):
        a = a.strip()
        if not a:
            continue
        if not re.fullmatch(r"[^@\s<>\"(),;:]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", a):
            raise MailboxError(f"Invalid address: {a}")
        out.append(formataddr((name, a)) if name else a)
    return out


def compose(sender: str, sender_name: str, d: Dict[str, Any]) -> Tuple[EmailMessage, List[str]]:
    to, cc, bcc = _addrs(d.get("to")), _addrs(d.get("cc")), _addrs(d.get("bcc"))
    if not to and not cc and not bcc:
        raise MailboxError("Please enter a recipient.")
    if len(to) + len(cc) + len(bcc) > 50:
        raise MailboxError("At most 50 recipients.")
    m = EmailMessage()
    m["From"] = formataddr((sender_name, sender)) if sender_name else sender
    if to:
        m["To"] = ", ".join(to)
    if cc:
        m["Cc"] = ", ".join(cc)
    m["Subject"] = str(d.get("subject") or "")[:300].replace("\n", " ")
    m["Date"] = email.utils.formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain=sender.split("@")[1])
    m["User-Agent"] = "ADN-FRN-Server Webmail"
    irt = str(d.get("in_reply_to") or "")
    if re.fullmatch(r"<[^<>\s]{3,300}>", irt):
        m["In-Reply-To"] = irt
        refs = " ".join(re.findall(r"<[^<>\s]{3,300}>", str(d.get("references") or "")))
        m["References"] = (refs + " " + irt).strip()
    m.set_content(str(d.get("text") or ""))
    total = 0
    for a in d.get("attachments") or []:
        data = base64.b64decode(str(a.get("data") or ""), validate=False)
        total += len(data)
        if total > MAX_SEND:
            raise MailboxError("Attachments larger than 20 MB.")
        ctype = str(a.get("type") or "application/octet-stream")
        main, _, sub = ctype.partition("/")
        if not re.fullmatch(r"[a-z]+", main or "") or not re.fullmatch(r"[a-z0-9.+-]+", sub or ""):
            main, sub = "application", "octet-stream"
        name = re.sub(r"[\r\n\"\\/]", "_", str(a.get("name") or "file"))[:120]
        m.add_attachment(data, maintype=main, subtype=sub, filename=name)
    rcpts = [a for _, a in getaddresses(to + cc + bcc)]
    return m, rcpts


def send(sender: str, msg: EmailMessage, rcpts: List[str]) -> None:
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo("webmail.localhost")
            if s.has_extn("starttls"):
                s.starttls(context=_ctx())
                s.ehlo("webmail.localhost")
            refused = s.send_message(msg, from_addr=sender, to_addrs=rcpts)
            if refused:
                raise MailboxError("Refused: " + ", ".join(refused))
    except smtplib.SMTPException as e:
        raise MailboxError(f"Sending failed: {e}")
    except OSError as e:
        raise MailboxError(f"Mail server not reachable ({e.__class__.__name__})")
