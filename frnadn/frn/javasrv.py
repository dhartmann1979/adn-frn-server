"""
The Java FRN server of freeradionetwork.de (FRN_Server.jar, Dirk Rasmussen).

frn_adn keeps every setting in SQLite and writes only the files the server needs:

  <home>/server.properties   server and rooms (net00 … net63)
  <home>/log4j.xml           logging: server.log and server_clients.log, read by logwatch.py
  <home>/acl/FRNPasswd.xml   own password list for stand-alone mode

The server runs as its own systemd service (frn-server.service) and is started,
stopped and restarted from the admin portal. For tests and development it can
also run as a child process of this program (FRNADN_FRN_DIRECT=1).
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from ..settings import Settings
from .store import Store

log = logging.getLogger("frnadn.frn")

DOWNLOAD = "https://freeradionetwork.de/assets/files/FRN_Server.zip"
RELEASENOTES = "https://freeradionetwork.de/assets/files/FRN_Server_releasenotes.txt"
SERVICE = "frn-server.service"
VERSION_RE = re.compile(r"Release V\s*([\d.]+)\s*\(Build\s*([\d.]+)\)")

LOG4J = """<?xml version="1.0" encoding="UTF-8" ?>
<!DOCTYPE log4j:configuration SYSTEM "log4j.dtd">
<!-- written by frn_adn – changes are overwritten; frn_adn reads server.log and server_clients.log -->
<log4j:configuration xmlns:log4j="http://jakarta.apache.org/log4j/">
  <appender name="CONSOLE" class="org.apache.log4j.ConsoleAppender">
    <param name="Target" value="System.out"/>
    <param name="Encoding" value="UTF-8"/>
    <param name="Threshold" value="warn"/>
    <layout class="org.apache.log4j.PatternLayout">
      <param name="ConversionPattern" value="%-5p - %m%n"/>
    </layout>
  </appender>
  <appender name="LOGFILE" class="de.bevis.frn.log4j.DailyLimitedRollingFileAppender">
    <param name="Encoding" value="UTF-8"/>
    <param name="File" value="./logs/server.log"/>
    <param name="DatePattern" value="'_'yyyy-MM-dd-HH'.log'"/>
    <param name="MaxBackupFiles" value="48"/>
    <param name="Threshold" value="trace"/>
    <layout class="org.apache.log4j.PatternLayout">
      <param name="ConversionPattern" value="%d{yyyy-MM-dd HH:mm:ss,SSS} %-5p - %m%n"/>
    </layout>
  </appender>
  <appender name="ASYNC" class="org.apache.log4j.AsyncAppender">
    <param name="BufferSize" value="500"/>
    <param name="Blocking" value="false"/>
    <param name="LocationInfo" value="false"/>
    <param name="Threshold" value="trace"/>
    <appender-ref ref="LOGFILE"/>
  </appender>
  <appender name="LOGFILE2" class="de.bevis.frn.log4j.DailyLimitedRollingFileAppender">
    <param name="Encoding" value="UTF-8"/>
    <param name="File" value="./logs/server_clients.log"/>
    <param name="DatePattern" value="'_'yyyy-MM-dd'.log'"/>
    <param name="MaxBackupFiles" value="7"/>
    <param name="Threshold" value="trace"/>
    <layout class="org.apache.log4j.PatternLayout">
      <param name="ConversionPattern" value="%d{yyyy-MM-dd HH:mm:ss,SSS} - %m%n"/>
    </layout>
  </appender>
  <category name="Logger2" additivity="false">
    <priority value="debug"/>
    <appender-ref ref="LOGFILE2"/>
  </category>
  <root>
    <priority value="info"/>
    <appender-ref ref="CONSOLE"/>
    <appender-ref ref="ASYNC"/>
  </root>
</log4j:configuration>
"""


def prop_value(v: Any) -> str:
    """Java properties: one line, backslash escaped, everything outside ASCII as \\uXXXX."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    s = str(v).replace("\\", "\\\\").replace("\r", " ").replace("\n", " ")
    out = []
    for ch in s:
        o = ord(ch)
        if o < 0x20:
            continue
        if o > 0x7e:
            if o > 0xffff:          # outside the BMP: surrogate pair
                o -= 0x10000
                out.append("\\u%04x\\u%04x" % (0xd800 + (o >> 10), 0xdc00 + (o & 0x3ff)))
            else:
                out.append("\\u%04x" % o)
        else:
            out.append(ch)
    s = "".join(out)
    return "\\" + s if s.startswith(" ") else s


def build_properties(s: Dict[str, Any], rooms: List[Dict[str, Any]], home: Path) -> str:
    lines = ["# server.properties – written by frn_adn from its SQLite database.",
             "# Do not edit: change the settings in the admin portal; this file is overwritten.", ""]

    def put(k: str, v: Any) -> None:
        lines.append(f"{k}={prop_value(v)}")

    if s["frn.standalone"]:
        put("standalone", True)
        put("allowLANAddr", bool(s["frn.allow_lan"]))
    put("sysman_server_addr", s["sysman.host"] or "sysman.freeradionetwork.de")
    put("sysman_auth_emailaddr", s["sysman.email"])
    put("sysman_auth_password", s["sysman.password"])
    put("server_addr", s["frn.address"])
    put("server_port", s["frn.port"])
    owner = s["frn.owner_email"] or s["sysman.email"]
    if owner:
        put("server_owner", owner)
    if s["frn.website"]:
        put("website", s["frn.website"])
    if s["frn.backup_host"] and s["frn.backup_port"]:
        put("backup_server_addr", s["frn.backup_host"])
        put("backup_server_port", s["frn.backup_port"])
    put("xmlFilesDir", str(home / "acl"))
    put("client_sotimeout", s["frn.client_timeout"])
    put("client_txtimeout", s["frn.tx_timeout"])
    put("voip_skip_muted_crosslink_clients", bool(s["frn.skip_muted_crosslink"]))
    put("voip_skip_muted_gateway_clients", bool(s["frn.skip_muted_gateway"]))
    put("voip_skip_muted_pconly_clients", bool(s["frn.skip_muted_pconly"]))
    default = s["frn.default_room"] or next((r["name"] for r in rooms if r["enabled"] and r["idx"] != 0), "")
    if default:
        put("default_net", default)
    for r in sorted(rooms, key=lambda r: r["idx"] if r["idx"] is not None else 99):
        if r["idx"] is None:
            continue
        n = "net%02d" % r["idx"]
        lines.append("")
        lines.append(f"# {r['name']}")
        put(n, r["name"])
        if not r["enabled"]:
            put(n + "_enable", False)
        if r["owners"]:
            put(n + "_owner", r["owners"])
        put(n + "_show_infomessage", "always" if r["show_info"] == "always" else "acl")
        put(n + "_tot", r["tot"] or 180)
        if r["speechpause"]:
            put(n + "_speechpause", r["speechpause"])
        if r["speechpause_msg"]:
            put(n + "_speechpause_msg", r["speechpause_msg"])
        if r["idx"] == 0 or r["parrot"]:
            put(n + "_parrot_enable", True)
            put(n + "_parrot_startstop_enable", bool(r["parrot_startstop"]))
        if r["unmute_min"]:
            put(n + "_unmute", r["unmute_min"])
        for col, key in (("acl_cl", "_acl_cl"), ("acl_gw", "_acl_gw"), ("acl_info", "_acl_info"),
                         ("bl_regexp", "_bl_regexp"), ("bl_info", "_bl_info"), ("tg_params", "_tgbot_params")):
            if r.get(col):
                put(n + key, r[col])
    return "\n".join(lines) + "\n"


def build_passwd(enabled: bool, accounts: List[Dict[str, Any]]) -> str:
    out = ["<PasswdList>", f"  <disabled>{'false' if enabled else 'true'}</disabled>"]
    for a in accounts:
        on = a["callsign"] + (", " + a["name"] if a["name"] else "")
        out += ["  <User>", f"    <OperatorName>{escape(on)}</OperatorName>", f"    <EMailAddress>{escape(a['email'])}</EMailAddress>",
                f"    <Password>{escape(a['password'] or '')}</Password>",
                f"    <disabled>{'true' if a['disabled'] else 'false'}</disabled>", "  </User>"]
    out.append("</PasswdList>")
    return "\n".join(out) + "\n"


def parse_version(text: str) -> Optional[Dict[str, str]]:
    m = VERSION_RE.search(text or "")
    return {"version": m.group(1), "build": m.group(2)} if m else None


def _write(path: Path, text: str, mode: int = 0o640) -> bool:
    """Write only when the content changed. Returns True if it changed."""
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except FileNotFoundError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    return True


class JavaServer:
    def __init__(self, store: Store, settings: Settings, home: Path, jar: Path, demo: bool = False):
        self.store = store
        self.settings = settings
        self.home = Path(home)
        self.jar = Path(jar)
        self.demo = demo
        self.direct = os.environ.get("FRNADN_FRN_DIRECT", "") not in ("", "0")
        self.java = os.environ.get("FRNADN_JAVA", "java")
        self.proc: Optional[asyncio.subprocess.Process] = None
        self.update_info: Dict[str, Any] = {}

    # ------------------------------------------------------------ files
    def write_config(self) -> bool:
        """Write server.properties, log4j.xml and FRNPasswd.xml. True if server.properties or the password list changed."""
        (self.home / "acl").mkdir(parents=True, exist_ok=True)
        (self.home / "logs").mkdir(parents=True, exist_ok=True)
        s = self.settings.all()
        changed = _write(self.home / "server.properties", build_properties(s, self.store.rooms(), self.home), 0o600)
        _write(self.home / "log4j.xml", LOG4J, 0o644)
        pw = build_passwd(bool(s["frn.passwd_list"]), self.store.accounts(with_password=True))
        changed = _write(self.home / "acl" / "FRNPasswd.xml", pw, 0o600) or changed
        return changed

    def properties_text(self) -> str:
        try:
            text = (self.home / "server.properties").read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        return re.sub(r"^(sysman_auth_password\S*=).+$", r"\1********", text, flags=re.M)

    def acl_files(self) -> List[Dict[str, Any]]:
        """Mute, block, admin and access lists the server keeps itself (changed by moderators in the FRN client)."""
        names = {r["idx"]: r["name"] for r in self.store.rooms()}
        out = []
        for p in sorted((self.home / "acl").glob("*.xml")):
            if p.name == "FRNPasswd.xml":
                continue
            m = re.match(r"(AdminList|MuteList|BlockList|AccessList)(\d+)\.xml$", p.name)
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            idx = int(m.group(2)) if m else None
            out.append({"file": p.name, "kind": m.group(1) if m else "", "room": names.get(idx, f"net{idx:02d}" if idx is not None else ""),
                        "mtime": p.stat().st_mtime, "entries": self._entries(text), "text": text[:20000]})
        return out

    @staticmethod
    def _entries(text: str) -> List[Dict[str, str]]:
        """Best effort: every element with an e-mail address and its sibling fields."""
        rows = []
        for block in re.findall(r"<(\w+)>((?:(?!</\1>).)*?@(?:(?!</\1>).)*?)</\1>", text, re.S):
            fields = dict(re.findall(r"<(\w+)>([^<]*)</\1>", block[1]))
            if fields:
                rows.append(fields)
        return rows

    def jar_version(self) -> Optional[Dict[str, str]]:
        for p in (self.jar.parent / "releasenotes.txt", self.jar.parent / "FRN_Server_releasenotes.txt"):
            try:
                v = parse_version(p.read_text(encoding="utf-8-sig", errors="replace")[:400])
                if v:
                    return v
            except OSError:
                continue
        return None

    # ------------------------------------------------------------ process / service
    async def _systemctl(self, *args: str) -> Dict[str, Any]:
        from ..system import _sudo, run
        return await run([*_sudo(), "systemctl", *args, SERVICE], 30)

    async def status(self) -> Dict[str, Any]:
        if self.direct:
            return {"active": "active" if self.proc and self.proc.returncode is None else "inactive", "since": None}
        if self.demo:
            return {"active": "active", "since": None}
        from ..system import run
        r = await run(["systemctl", "show", SERVICE, "-p", "ActiveState", "-p", "ActiveEnterTimestampMonotonic", "-p", "NRestarts"], 10)
        d = dict(line.split("=", 1) for line in r["out"].splitlines() if "=" in line)
        return {"active": d.get("ActiveState", "unknown"), "restarts": int(d.get("NRestarts") or 0)}

    async def control(self, action: str) -> Dict[str, Any]:
        if action not in ("start", "stop", "restart"):
            raise ValueError("unknown action")
        if action in ("start", "restart"):
            self.write_config()
        if self.demo and not self.direct:
            return {"rc": 0, "out": ""}
        if self.direct:
            if action in ("stop", "restart") and self.proc and self.proc.returncode is None:
                self.proc.terminate()
                try:
                    await asyncio.wait_for(self.proc.wait(), 10)
                except asyncio.TimeoutError:
                    self.proc.kill()
            if action in ("start", "restart"):
                self.proc = await asyncio.create_subprocess_exec(
                    self.java, "-jar", str(self.jar), "-sp", "server.properties", "-lp", "log4j.xml", cwd=str(self.home),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            return {"rc": 0, "out": ""}
        return await self._systemctl(action)

    async def stop_child(self) -> None:
        if self.direct and self.proc and self.proc.returncode is None:
            self.proc.terminate()
            try:
                await asyncio.wait_for(self.proc.wait(), 10)
            except asyncio.TimeoutError:
                self.proc.kill()

    # ------------------------------------------------------------ updates from freeradionetwork.de
    async def check_update(self) -> Dict[str, Any]:
        def fetch() -> str:
            req = urllib.request.Request(RELEASENOTES, headers={"User-Agent": "frn_adn"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read(4000).decode("utf-8-sig", "replace")
        try:
            latest = parse_version(await asyncio.to_thread(fetch))
        except Exception as e:                       # network errors are shown, not raised
            return {"ok": False, "error": str(e), "installed": self.jar_version()}
        inst = self.jar_version()
        newer = bool(latest and (not inst or _vt(latest["version"]) > _vt(inst["version"]) or
                                 (latest["version"] == inst["version"] and latest["build"] > inst["build"])))
        self.update_info = {"ok": True, "installed": inst, "latest": latest, "update": newer, "checked": time.time()}
        return self.update_info

    async def install_update(self) -> Dict[str, Any]:
        def fetch() -> bytes:
            req = urllib.request.Request(DOWNLOAD, headers={"User-Agent": "frn_adn"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(64 * 1024 * 1024)
        data = await asyncio.to_thread(fetch)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = {Path(n).name: n for n in z.namelist() if not n.endswith("/")}
            if "FRN_Server.jar" not in names:
                raise ValueError("FRN_Server.jar is missing in the download.")
            self.jar.parent.mkdir(parents=True, exist_ok=True)
            for name in ("FRN_Server.jar", "releasenotes.txt", "properties_doc.pdf"):
                if name in names:
                    tmp = self.jar.parent / (name + ".new")
                    with z.open(names[name]) as src, open(tmp, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.replace(tmp, self.jar.parent / name)
        await self.control("restart")
        return {"ok": True, "installed": self.jar_version()}


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v))
