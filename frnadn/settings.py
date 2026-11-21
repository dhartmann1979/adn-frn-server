"""
Settings of dashboard and FRN server, stored in SQLite (table ``settings``).

Everything the Java FRN server needs is generated from here into
server.properties (see frn/javasrv.py). A setting never saved has its default.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .db import DB


class SettingsError(Exception):
    """Message is shown to the user."""


@dataclass(frozen=True)
class Field:
    key: str
    section: str
    label: str
    kind: str                 # text | int | bool | choice | password | longtext
    default: Any
    help: str = ""
    choices: Sequence[Tuple[Any, str]] = ()
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: str = ""


SECTIONS: List[Tuple[str, str, str]] = [
    ("server", "🛰️ FRN server", "Address, port and timeouts – written to server.properties"),
    ("sysman", "🌐 SystemManager", "Registration at sysman.freeradionetwork.de or stand-alone"),
    ("owner", "👤 Operator", "Server owner (gets OWNER rights in every room)"),
    ("dashboard", "🖥️ Dashboard", "Title, public view and what visitors see"),
    ("data", "🗄️ Data", "How long talks and logins are kept"),
    ("https", "🔒 HTTPS & web", "Automatic HTTPS certificates with Let’s Encrypt (requires public DNS and ports 80/443)"),
]

FIELDS: List[Field] = [
    # FRN server (server.properties)
    Field("frn.address", "server", "Server address (server_addr)", "text", "",
          "Hostname or public IP of this server, e.g. frn.die-n8schicht.de – the SystemManager checks that it is reachable",
          pattern=r"[A-Za-z0-9.\-:\[\]]*"),
    Field("frn.port", "server", "Port (server_port)", "int", 10024, "TCP port for the FRN clients; open it in router and firewall",
          min=1, max=65535),
    Field("frn.default_room", "server", "Default room (default_net)", "text", "",
          "Clients that ask for a room that does not exist land here"),
    Field("frn.backup_host", "server", "Backup server (backup_server_addr)", "text", "", "Sent to the clients: where to go if this server is down"),
    Field("frn.backup_port", "server", "Backup server port", "int", 0, "0 = none", min=0, max=65535),
    Field("frn.client_timeout", "server", "Client timeout (client_sotimeout, ms)", "int", 8000,
          "A client that sends nothing for this long is disconnected", min=2000, max=120000),
    Field("frn.tx_timeout", "server", "Voice timeout (client_txtimeout, ms)", "int", 1000,
          "No voice for this long ends a transmission; 0 = off", min=0, max=10000),
    Field("frn.skip_muted_crosslink", "server", "No voice to muted crosslinks", "bool", True),
    Field("frn.skip_muted_gateway", "server", "No voice to muted gateways", "bool", True),
    Field("frn.skip_muted_pconly", "server", "No voice to muted PC-only clients", "bool", False),
    # SystemManager
    Field("frn.standalone", "sysman", "Stand-alone (without SystemManager)", "bool", False,
          "On: the server runs on its own, passwords come from the own list (FRN accounts). Off: registered at the SystemManager"),
    Field("frn.allow_lan", "sysman", "Allow a LAN address (allowLANAddr)", "bool", False, "Only for stand-alone, e.g. a server for the home network"),
    Field("frn.passwd_list", "sysman", "Use the own password list (stand-alone)", "bool", True,
          "Off: every FRN password is accepted in stand-alone mode"),
    Field("sysman.host", "sysman", "SystemManager (sysman_server_addr)", "text", "sysman.freeradionetwork.de",
          "sysman.freeradionetwork.de = alternative FRN system (DE)", pattern=r"[A-Za-z0-9.\-]+"),
    Field("sysman.email", "sysman", "FRN account e-mail (sysman_auth_emailaddr)", "text", "",
          "E-mail of your FRN user account at the SystemManager"),
    Field("sysman.password", "sysman", "FRN account password (sysman_auth_password)", "password", "",
          "The password of this FRN account (as sent by the SystemManager)"),
    # operator
    Field("frn.owner_email", "owner", "Owner e-mail (server_owner)", "text", "",
          "Only one address; empty = the FRN account e-mail above. OWNER rights in every room"),
    Field("frn.owner_callsign", "owner", "Callsign", "text", "", "Shown on the dashboard"),
    Field("frn.owner_name", "owner", "Name", "text", ""),
    Field("frn.website", "owner", "Website", "text", "", "Sent to the SystemManager and shown on the dashboard"),
    # dashboard
    Field("dashboard.title", "dashboard", "Title", "text", "Auf der NachtSchicht"),
    Field("dashboard.subtitle", "dashboard", "Subtitle", "text", "FRN Server"),
    Field("dashboard.public", "dashboard", "Public view", "bool", True,
          "On: everybody sees rooms and statistics without logging in"),
    Field("dashboard.show_hidden", "dashboard", "Show hidden rooms publicly", "bool", False),
    Field("dashboard.chat", "dashboard", "Room chat", "choice", "admin", "Text messages written in the rooms",
          choices=[("off", "Do not record"), ("admin", "Admins only"), ("users", "Logged-in users"), ("public", "Everybody")]),
    Field("dashboard.session_hours", "dashboard", "Login valid for (hours)", "int", 12, min=1, max=720),
    # data
    Field("data.talk_days", "data", "Keep single talks (days)", "int", 400,
          "Daily totals are kept for ever, they are small", min=7, max=3650),
    Field("data.visit_days", "data", "Keep logins (days)", "int", 180, min=7, max=3650),
    Field("data.chat_days", "data", "Keep chat messages (days)", "int", 30, min=1, max=3650),
    # HTTPS – applied by the dashboard process on its next restart
    Field("https.enabled", "https", "Enable HTTPS with Let's Encrypt", "bool", False,
          "Needs a public DNS name pointing to this server and inbound TCP ports 80 and 443. Save, then restart frnadn."),
    Field("https.domain", "https", "Public domain", "text", "",
          "Example: dashboard.example.org. Do not enter http:// or a path.", pattern=r"(?=.{4,253}$)([A-Za-z0-9-]{1,63}\\.)+[A-Za-z]{2,63}"),
    Field("https.email", "https", "Certificate e-mail", "text", "",
          "Let's Encrypt expiry and important certificate notices."),
    Field("https.staging", "https", "Use test certificates (staging)", "bool", False,
          "For testing only; browsers do not trust staging certificates."),
    Field("https.http_port", "https", "HTTP challenge / redirect port", "int", 80,
          "Public TCP port used by HTTP-01 challenge and HTTP → HTTPS redirect.", min=1, max=65535),
    Field("https.port", "https", "HTTPS port", "int", 443,
          "Public HTTPS port. Standard is 443.", min=1, max=65535),
]
BY_KEY = {f.key: f for f in FIELDS}


def validate(f: Field, raw: Any) -> Any:
    k = f.kind
    if k == "bool":
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "on", "yes", "ja")
        return bool(raw)
    if k == "int":
        try:
            v = int(str(raw).strip())
        except ValueError:
            raise SettingsError(f"{f.label}: please enter a whole number.")
        if f.min is not None and v < f.min or f.max is not None and v > f.max:
            raise SettingsError(f"{f.label}: allowed {int(f.min)}–{int(f.max)}.")
        return v
    if k == "ports":
        out = []
        for p in re.split(r"[,\s;]+", str(raw if not isinstance(raw, list) else ",".join(map(str, raw))).strip()):
            if not p:
                continue
            if not p.isdigit() or not 1 <= int(p) <= 65535:
                raise SettingsError(f"{f.label}: '{p}' is not a port.")
            out.append(int(p))
        return out
    if k == "choice":
        v = str(raw)
        if v not in [str(c[0]) for c in f.choices]:
            raise SettingsError(f"{f.label}: invalid choice.")
        return v
    v = "" if raw is None else str(raw)
    if k != "longtext":
        v = v.strip()
        if "\n" in v or "\r" in v:
            raise SettingsError(f"{f.label}: one line only.")
    if len(v) > 4000:
        raise SettingsError(f"{f.label}: too long.")
    if f.pattern and not re.fullmatch(f.pattern, v):
        raise SettingsError(f"{f.label}: '{v}' is not valid.")
    if f.key == "frn.owner_callsign":
        v = v.upper()
    if f.key in ("frn.owner_email", "sysman.email", "https.email"):
        v = v.lower()
        if v and not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+", v):
            raise SettingsError(f"{f.label}: not an e-mail address.")
    return v


class Settings:
    def __init__(self, db: DB):
        self.db = db
        self._cache: Optional[Dict[str, Any]] = None

    def all(self) -> Dict[str, Any]:
        if self._cache is None:
            stored = {r["key"]: r["value"] for r in self.db.q("SELECT key, value FROM settings")}
            self._cache = {f.key: (json.loads(stored[f.key]) if f.key in stored else f.default) for f in FIELDS}
        return dict(self._cache)

    def get(self, key: str) -> Any:
        return self.all()[key]

    def meta(self) -> Dict[str, Tuple[float, str]]:
        return {r["key"]: (r["updated_at"], r["updated_by"]) for r in self.db.q("SELECT * FROM settings")}

    def update(self, changes: Dict[str, Any], who: str = "") -> List[Field]:
        """Validate everything first, then store. Returns the fields that changed."""
        current = self.all()
        clean: Dict[str, Any] = {}
        for key, raw in changes.items():
            f = BY_KEY.get(key)
            if not f:
                raise SettingsError(f"Unknown setting: {key}")
            if f.kind == "password" and raw in (None, "••••••••"):
                continue
            clean[key] = validate(f, raw)
        changed = [BY_KEY[k] for k, v in clean.items() if current.get(k) != v]
        now = time.time()
        for f in changed:
            self.db.x("INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?,?,?,?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at, "
                      "updated_by=excluded.updated_by", (f.key, json.dumps(clean[f.key]), now, who))
        self._cache = None
        return changed

    def describe(self) -> List[Dict[str, Any]]:
        values, meta = self.all(), self.meta()
        out = []
        for sid, title, sub in SECTIONS:
            fields = []
            for f in FIELDS:
                if f.section != sid:
                    continue
                v = values[f.key]
                if f.kind == "password":
                    v = "••••••••" if v else ""
                elif f.kind == "ports":
                    v = ", ".join(str(x) for x in v or [])
                ts, by = meta.get(f.key, (None, ""))
                fields.append({"key": f.key, "label": f.label, "kind": f.kind, "value": v, "help": f.help,
                               "choices": [list(c) for c in f.choices], "min": f.min, "max": f.max,
                               "updated_at": ts, "updated_by": by})
            out.append({"id": sid, "title": title, "subtitle": sub, "fields": fields})
        return out
