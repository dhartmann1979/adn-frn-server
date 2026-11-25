"""Request an FRN password from the SystemManager (like "Get Password" in the FRN client).

The SystemManager listens on TCP 10025 for registrations. One line goes out, one line comes back
(same format as SvxLink's frn-register):

    IG:<ON>Callsign, Name</ON><EA>e-mail</EA><BC>band/channel</BC><DS>description</DS><NN>country</NN><CT>city - part</CT>
    → OK   the password is e-mailed to the address
    → NU   an account with this name already exists (the password went out back then)

Every server needs its own FRN account: two servers with the same e-mail/password are refused by the SystemManager
("the same credentials are already online on another server").
"""
import re
import socket
import time
from typing import Any, Dict

PORT = 10025
TIMEOUT = 30.0
BAND_RE = re.compile(r"^(PC Only|Crosslink|[0-9]+\.[0-9]+ ?(AM|FM|DIG)( (CTC[0-9.]+|DCS[0-9]+|DSC[0-9]+|NONE))?)$")
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")
CALL_RE = re.compile(r"^[A-Z0-9]{3,8}(-\d{1,2})?$")
ANSWERS = {"OK": "Requested – the SystemManager e-mails the password to {email}. Also check the spam folder.",
           "NU": "There is already an FRN account with this callsign and name. Its password was e-mailed when it was created – "
                 "use a different name (e.g. „DO1ABC, Server Test“) for a second server."}
_last: Dict[str, float] = {}


class SysmanError(Exception):
    pass


def _clean(v: Any, limit: int = 60) -> str:
    v = re.sub(r"[<>\r\n\t]", " ", str(v or "")).strip()
    return re.sub(r"\s{2,}", " ", v)[:limit]


def build(d: Dict[str, Any]) -> Dict[str, str]:
    """Check and normalise the form; returns the fields of the request."""
    call = _clean(d.get("callsign"), 12).upper()
    name = _clean(d.get("name"), 40)
    email = _clean(d.get("email"), 120).lower()
    band = _clean(d.get("band") or "PC Only", 40)
    desc = _clean(d.get("description") or "FRN server", 60)
    country = _clean(d.get("country"), 40)
    city = _clean(d.get("city"), 60)
    if not CALL_RE.match(call):
        raise SysmanError("Callsign: 3–8 letters/digits, e.g. DO1ABC.")
    if not name:
        raise SysmanError("Please enter a name (shown in the FRN system together with the callsign).")
    if not EMAIL_RE.match(email):
        raise SysmanError("Please enter a valid e-mail address – the password is sent there.")
    if not BAND_RE.match(band):
        raise SysmanError("Band/channel: „PC Only“, „Crosslink“ or a frequency like 438.950FM CTC71.9.")
    if not country:
        raise SysmanError("Please enter the country (e.g. Germany).")
    if not re.match(r"^.+ - .+$", city):
        raise SysmanError("City in the form „City - part“, e.g. „Minden - JO42“.")
    return {"ON": f"{call}, {name}", "EA": email, "BC": band, "DS": desc, "NN": country, "CT": city}


def line(f: Dict[str, str]) -> str:
    return "IG:" + "".join(f"<{k}>{f[k]}</{k}>" for k in ("ON", "EA", "BC", "DS", "NN", "CT"))


def register(host: str, d: Dict[str, Any], port: int = PORT, wait: float = 60.0) -> Dict[str, Any]:
    """Send the request; at most one per `wait` seconds and host (the SystemManager is shared by everybody)."""
    f = build(d)
    host = (host or "").strip()
    if not re.match(r"^[A-Za-z0-9.\-]+$", host):
        raise SysmanError("No valid SystemManager address in the settings.")
    now = time.time()
    if now - _last.get(host, 0) < wait:
        raise SysmanError(f"Please wait a minute before the next request ({int(wait - (now - _last[host]))} s).")
    _last[host] = now
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as s:
            s.sendall((line(f) + "\r\n").encode("utf-8"))
            s.settimeout(TIMEOUT)
            buf = b""
            while b"\n" not in buf and len(buf) < 512:
                c = s.recv(256)
                if not c:
                    break
                buf += c
    except OSError as e:
        raise SysmanError(f"SystemManager {host}:{port} not reachable ({e}).") from None
    code = buf.decode("utf-8", "replace").strip()
    if not code:
        raise SysmanError("The SystemManager did not answer.")
    msg = ANSWERS.get(code, "The SystemManager answered „{code}“ – the request was not accepted.")
    return {"ok": code == "OK", "code": code, "message": msg.format(email=f["EA"], code=code), "email": f["EA"], "account": f["ON"]}
