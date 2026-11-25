"""N8 Admin – gemeinsamer Baustein der N8schicht-Projekte fürs Webinterface (gleich in allen Repositorys).

Gegenstück zu scripts/n8-admin.sh (läuft als root über sudo). Das Webinterface läuft als eigener Benutzer ohne root-Rechte;
was es darf, steht in <Datenordner>/n8-admin.json (schreibt n8-admin.sh sudo-setup):

    units()            Dienste mit Status (läuft/gestoppt), Autostart und erlaubten Aktionen
    unit_action(u, a)  start/stop/restart/enable/disable – nur was freigegeben ist
    check_perms()      Berechtigungen und sudo prüfen (Liste)          – sudo n8-admin.sh check-perms --json
    fix_perms()        prüfen, korrigieren, erneut prüfen (Ausgabe)    – sudo n8-admin.sh fix-perms
    request_update()   „Update jetzt“: legt update.request an, die Path-Unit startet n8-admin.sh update --auto als root
    update_state()     läuft gerade ein Update? Protokoll und Ergebnis des letzten

Alles ist asynchron (asyncio) und hängt an keinem Web-Framework.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ACTIONS = ("start", "stop", "restart", "enable", "disable")
KNOWN_ACTIVE = {"active", "inactive", "failed", "activating", "deactivating", "reloading"}
KNOWN_ENABLED = {"enabled", "disabled", "static", "masked", "not-found", "indirect", "generated", "alias", "linked"}


class N8Admin:
    def __init__(self, state_dir: str | os.PathLike, demo: bool = False):
        self.state_dir = Path(state_dir)
        self.demo = demo or os.environ.get("N8_ADMIN_DEMO") == "1"     # Vorführung/Screenshots: Zustände nur im Speicher
        self._demo_units: Dict[str, List[str]] = {}

    # ------------------------------------------------------------ Konfiguration
    def config(self) -> Dict[str, Any]:
        try:
            return json.loads((self.state_dir / "n8-admin.json").read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    @property
    def ready(self) -> bool:
        return bool(self.config().get("units")) and bool(shutil.which("sudo"))

    async def _run(self, *cmd: str, timeout: float = 60) -> Tuple[int, str]:
        try:
            p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        except FileNotFoundError:
            return 127, f"{cmd[0]}: nicht gefunden"
        try:
            out, _ = await asyncio.wait_for(p.communicate(), timeout)
        except asyncio.TimeoutError:
            p.kill()
            return 124, "Zeitüberschreitung"
        return p.returncode or 0, out.decode("utf-8", "replace")

    async def _sudo(self, *cmd: str, timeout: float = 60) -> Tuple[int, str]:
        if os.geteuid() == 0:
            return await self._run(*cmd, timeout=timeout)
        return await self._run("sudo", "-n", *cmd, timeout=timeout)

    # ------------------------------------------------------------ Dienste
    async def units(self) -> List[Dict[str, Any]]:
        c = self.config()
        sc = c.get("systemctl") or "systemctl"
        out = []
        for u in c.get("units", []):
            name = u["unit"]
            if self.demo:
                a, e = self._demo_units.setdefault(name, ["active", "enabled"])
            else:
                _, a = await self._run(sc, "is-active", name, timeout=5)
                _, e = await self._run(sc, "is-enabled", name, timeout=5)
                a, e = (a.splitlines() or [""])[0].strip(), (e.splitlines() or [""])[0].strip()
            out.append({**u, "active": a if a in KNOWN_ACTIVE else "unbekannt", "enabled": e if e in KNOWN_ENABLED else "unbekannt"})
        return out

    def allowed(self, unit: str, action: str) -> bool:
        return action in ACTIONS and any(u["unit"] == unit and action in u.get("actions", []) for u in self.config().get("units", []))

    async def unit_action(self, unit: str, action: str) -> Tuple[bool, str]:
        if not self.allowed(unit, action):
            return False, "Aktion nicht freigegeben"
        if self.demo:
            st = self._demo_units.setdefault(unit, ["active", "enabled"])
            st[0] = {"start": "active", "restart": "active", "stop": "inactive"}.get(action, st[0])
            st[1] = {"enable": "enabled", "disable": "disabled"}.get(action, st[1])
            return True, "ok (Demo)"
        sc = self.config().get("systemctl") or "/usr/bin/systemctl"
        args = [sc, action, unit] if action not in ("start", "restart") else [sc, "--no-block", action, unit]
        rc, out = await self._sudo(*args, timeout=60)
        return rc == 0, out.strip()[-400:] or ("ok" if rc == 0 else f"Fehler {rc}")

    # ------------------------------------------------------------ Berechtigungen
    async def check_perms(self) -> Dict[str, Any]:
        c = self.config()
        if not c.get("self"):
            return {"ok": False, "checks": [], "missing": True,
                    "message": "Noch nicht eingerichtet – einmal auf der Konsole: sudo <Programm>/scripts/n8-admin.sh fix-perms"}
        if self.demo:
            return {"ok": True, "bad": 0, "warn": 0, "checks": [{"status": "ok", "area": "sudo", "text": "Demo – keine echte Prüfung"}]}
        rc, out = await self._sudo(c["self"], "check-perms", "--json", timeout=120)
        for line in reversed(out.strip().splitlines()):
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except ValueError:
                    break
        last = (_plain(out).strip().splitlines() or [""])[-1][:200]
        return {"ok": False, "checks": [], "message": (f"sudo verweigert ({last}) – auf der Konsole: sudo {c['self']} fix-perms"
                                                     if "password" in out or "sudo" in out else out[-300:] or f"Fehler {rc}")}

    async def fix_perms(self) -> Tuple[bool, str]:
        c = self.config()
        if not c.get("self"):
            return False, "Noch nicht eingerichtet – einmal auf der Konsole: sudo <Programm>/scripts/n8-admin.sh fix-perms"
        if self.demo:
            return True, "Demo – nichts zu korrigieren"
        rc, out = await self._sudo(c["self"], "fix-perms", timeout=300)
        return rc == 0, _plain(out)[-4000:]

    # ------------------------------------------------------------ Update
    def request_update(self) -> Tuple[bool, str]:
        c = self.config()
        req = c.get("request")
        if not req:
            return False, "„Update jetzt“ ist noch nicht eingerichtet – einmal auf der Konsole: sudo <Programm>/scripts/n8-admin.sh fix-perms"
        if self.demo:
            return True, "Update angefordert (Demo)"
        try:
            Path(req).write_text(str(time.time()), "utf-8")
        except OSError as e:
            return False, f"Update konnte nicht angefordert werden: {e}"
        return True, "Update angefordert – läuft gleich als root; das Webinterface startet danach neu"

    def update_state(self) -> Dict[str, Any]:
        c = self.config()

        def read(p: Optional[str], n: int = 20000) -> str:
            try:
                return Path(p).read_text("utf-8", "replace")[-n:] if p else ""
            except OSError:
                return ""
        res = read(c.get("result"))
        try:
            result = json.loads(res) if res.strip() else None
        except ValueError:
            result = None
        log = read(c.get("log"))
        pending = bool(c.get("request")) and Path(c["request"]).exists()
        running = bool(log) and "=== " in log and not any(k in log.rsplit("=== ", 1)[-1] for k in ("fertig", "fehlgeschlagen")) \
            and "Update gestartet" in log.rsplit("\n=== ", 1)[-1]
        return {"ready": bool(c.get("request")), "pending": pending, "running": running and not pending,
                "log": _plain(log), "result": result}


def _plain(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s or "")
