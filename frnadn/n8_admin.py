"""N8 Admin – gemeinsamer Baustein der N8schicht-Projekte fürs Webinterface (gleich in allen Repositorys).

Gegenstück zu scripts/n8-admin.sh (läuft als root über sudo). Das Webinterface läuft als eigener Benutzer ohne root-Rechte;
was es darf, steht in <Datenordner>/n8-admin.json (schreibt n8-admin.sh sudo-setup):

    units()            Dienste mit Status (läuft/gestoppt), Autostart und erlaubten Aktionen
    unit_action(u, a)  start/stop/restart/enable/disable – nur was freigegeben ist
    check_perms()      Berechtigungen und sudo prüfen (Liste)          – sudo n8-admin.sh check-perms --json
    fix_perms()        prüfen, korrigieren, erneut prüfen (Ausgabe)    – sudo n8-admin.sh fix-perms
    request_update()   „Update jetzt“: legt update.request an, die Path-Unit startet n8-admin.sh update --auto als root
    update_state()     läuft gerade ein Update? Protokoll und Ergebnis des letzten
    keepalive()        Keep-Alive: Zustand der Prüfungen, Internet, Heartbeat, Protokoll und Einstellungen
    keepalive_set(d)   Einstellungen (an/aus, Neustart nach Internet-Ausfall, Heartbeat-Adressen, Pause) – n8-admin.sh liest sie nur
    crashes()          Abstürze, Hänger und Neustarts aller Dienste (n8-admin.sh crash-hook, Keep-Alive, n8_crash.CrashWatch)
    crash_log(id)      vollständiges Protokoll eines Befunds (Journal, Python-Stack, Ursache)
    crash_ack(ids|all) als gelesen markieren – danach erscheint das Hinweisfenster nach der Anmeldung nicht mehr

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
        self._hold(unit, action)
        if self.demo:
            st = self._demo_units.setdefault(unit, ["active", "enabled"])
            st[0] = {"start": "active", "restart": "active", "stop": "inactive"}.get(action, st[0])
            st[1] = {"enable": "enabled", "disable": "disabled"}.get(action, st[1])
            return True, "ok (Demo)"
        sc = self.config().get("systemctl") or "/usr/bin/systemctl"
        args = [sc, action, unit] if action not in ("start", "restart") else [sc, "--no-block", action, unit]
        rc, out = await self._sudo(*args, timeout=60)
        return rc == 0, out.strip()[-400:] or ("ok" if rc == 0 else f"Fehler {rc}")

    def _hold(self, unit: str, action: str) -> None:
        """Von Hand gestoppt → Keep-Alive startet den Dienst nicht wieder, bis er hier gestartet wird."""
        d = self.state_dir / "keepalive.hold"
        try:
            if action == "stop":
                d.mkdir(exist_ok=True)
                (d / unit).write_text(str(time.time()), "utf-8")
            elif action in ("start", "restart"):
                (d / unit).unlink(missing_ok=True)
        except OSError:
            pass

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


    # ------------------------------------------------------------ Keep-Alive
    KA_KEYS = ("enabled", "net_restart", "heartbeat_url", "heartbeat_fail_url", "paused_until")

    def keepalive_conf(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"enabled": True, "net_restart": True, "heartbeat_url": "", "heartbeat_fail_url": "", "paused_until": 0}
        try:
            for line in (self.state_dir / "keepalive.conf").read_text("utf-8").splitlines():
                k, _, v = line.partition("=")
                if k in ("enabled", "net_restart"):
                    out[k] = v.strip() != "0"
                elif k == "paused_until":
                    out[k] = int(v) if v.strip().isdigit() else 0
                elif k in self.KA_KEYS:
                    out[k] = v.strip()
        except OSError:
            pass
        return out

    def keepalive_set(self, d: Dict[str, Any]) -> Dict[str, Any]:
        import re
        c = self.keepalive_conf()
        for k in ("enabled", "net_restart"):
            if k in d:
                c[k] = bool(d[k])
        for k in ("heartbeat_url", "heartbeat_fail_url"):
            if k in d:
                v = str(d[k] or "").strip()
                if v and not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#@!&+,;=%-]{3,400}", v):
                    raise ValueError("Heartbeat-Adresse: nur http(s)://… ohne Leerzeichen und Sonderzeichen wie $ ` Anführungszeichen")
                c[k] = v
        if "pause_minutes" in d:
            m = max(0, min(int(d["pause_minutes"] or 0), 24 * 60))
            c["paused_until"] = int(time.time() + m * 60) if m else 0
        lines = [f"{k}={int(c[k]) if isinstance(c[k], bool) else c[k]}" for k in self.KA_KEYS]
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_dir / "keepalive.conf.tmp"
        tmp.write_text("\n".join(lines) + "\n", "utf-8")
        os.replace(tmp, self.state_dir / "keepalive.conf")
        return c

    def keepalive(self) -> Dict[str, Any]:
        def read(name: str, n: int = 30000) -> str:
            try:
                return (self.state_dir / name).read_text("utf-8", "replace")[-n:]
            except OSError:
                return ""
        try:
            st = json.loads(read("keepalive.json") or "{}")
        except ValueError:
            st = {}
        if self.demo and not st:
            now = int(time.time())
            st = {"time": now - 20, "mode": "an", "net": 1, "net_down_since": 0, "heartbeat": "ok", "restarted": 0, "fails_needed": 3, "max_hour": 4,
                  "checks": [{"unit": u["unit"], "label": u.get("label", u["unit"]), "state": "ok", "active": "active", "why": "", "fails": 0,
                              "restarts": 1 if i == 0 else 0, "last_restart": now - 5400 if i == 0 else 0}
                             for i, u in enumerate(self.config().get("units", [])) if not u["unit"].endswith(".path")]}
        log = _plain(read("keepalive.log", 12000))
        if self.demo and not log:
            log = ("2026-11-25 03:12:40 🌐 Internet weg (keine Antwort von 1.1.1.1:443 9.9.9.9:443 github.com:443)\n"
                   "2026-11-25 03:16:41 🌐 Internet wieder da (nach 241 s Ausfall)\n"
                   "2026-11-25 03:16:41 ↻ Dienst nach dem Internet-Ausfall neu gestartet (Demo)\n")
        age = time.time() - float(st.get("time") or 0)
        return {**st, "stale": bool(st) and age > 180, "age": int(age) if st else None, "conf": self.keepalive_conf(),
                "log": "\n".join(log.splitlines()[-80:]), "ready": bool(st) or self.demo}

    # ------------------------------------------------------------ Abstürze (2.0)
    # <Datenordner>/crashes.jsonl schreiben: n8-admin.sh crash-hook (systemd ExecStopPost, als root), der Keep-Alive und die
    # Anwendung selbst (n8_crash.CrashWatch). Einzelheiten: crash/<id>.log. Gelesen-Markierung: crash/ack.json (nur hier).
    def _crash_entries(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            raw = (self.state_dir / "crashes.jsonl").read_text("utf-8", "replace").splitlines()[-1000:]
        except OSError:
            raw = []
        for line in raw:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and isinstance(e.get("id"), str) and _CRASH_ID.fullmatch(e["id"]):
                out.append(e)
        if self.demo and not out:
            now = time.time()
            unit = next((u["unit"] for u in self.config().get("units", []) if u["unit"].endswith(".service")), "demo.service")
            out = [{"id": "20261125-031240-d001", "time": now - 26 * 3600, "unit": unit, "service": "Datenbank ← Live-Daten", "kind": "watchdog",
                    "reason": "systemd-Watchdog: keine Rückmeldung mehr – der Prozess hing und wurde beendet (SIGABRT) – Event-Loop stand 61 s",
                    "source": "systemd", "restarted": True},
                   {"id": "20261125-093012-d002", "time": now - 5 * 3600, "unit": unit, "service": unit.split(".")[0], "kind": "keepalive",
                    "reason": "Keep-Alive: Weboberfläche – keine Antwort (seit 3 min) – neu gestartet", "source": "keepalive", "restarted": True},
                   {"id": "20261125-151512-d003", "time": now - 600, "unit": unit, "service": "Live-Daten", "kind": "task",
                    "reason": "ConnectionResetError: [Errno 104] Connection reset by peer (Task live)", "source": "app", "restarted": True}]
        return out

    def _crash_ack(self) -> Dict[str, Any]:
        try:
            a = json.loads((self.state_dir / "crash" / "ack.json").read_text("utf-8"))
            return {"until": float(a.get("until") or 0), "ids": [str(i) for i in a.get("ids", [])][-500:]}
        except (OSError, ValueError, AttributeError, TypeError):
            return {"until": 0.0, "ids": []}

    def crashes(self, limit: int = 200) -> Dict[str, Any]:
        """Befunde (neueste zuerst), Zahl der ungelesenen und welche Dienste der Absturz-Wächter überwacht."""
        ack = self._crash_ack()
        items = []
        for e in reversed(self._crash_entries()):
            e["new"] = float(e.get("time") or 0) > ack["until"] and e["id"] not in ack["ids"]
            items.append(e)
        try:
            watch = json.loads((self.state_dir / "crashwatch.json").read_text("utf-8"))
        except (OSError, ValueError):
            watch = {}
        if self.demo and not watch:
            watch = {"units": [{"unit": u["unit"], "label": u.get("label", u["unit"]), "restart": "always"}
                               for u in self.config().get("units", []) if u["unit"].endswith(".service")]}
        week = time.time() - 7 * 86400
        by_svc: Dict[str, int] = {}
        for e in items:
            if float(e.get("time") or 0) >= week:
                by_svc[e.get("service") or e.get("unit") or "?"] = by_svc.get(e.get("service") or e.get("unit") or "?", 0) + 1
        return {"items": items[:limit], "total": len(items), "unacked": sum(1 for e in items if e["new"]),
                "week": by_svc, "watch": watch, "ready": bool(watch) or self.demo}

    def crash_log(self, cid: str) -> Optional[str]:
        if not _CRASH_ID.fullmatch(cid or ""):
            return None
        if self.demo:
            return "Demo – hier steht das vollständige Protokoll des Befunds (Journal, Python-Stack, Ursache)."
        try:
            return _plain((self.state_dir / "crash" / f"{cid}.log").read_text("utf-8", "replace")[-200000:])
        except OSError:
            return None

    def crash_ack(self, ids: Optional[List[str]] = None, all_: bool = False) -> Dict[str, Any]:
        """Als gelesen markieren: alle (bis jetzt) oder einzelne Befunde."""
        a = self._crash_ack()
        if all_:
            newest = max((float(e.get("time") or 0) for e in self._crash_entries()), default=0.0)
            a = {"until": max(time.time(), newest), "ids": []}
        else:
            a["ids"] = (a["ids"] + [i for i in (ids or []) if _CRASH_ID.fullmatch(str(i))])[-500:]
        d = self.state_dir / "crash"
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "ack.json.tmp"
        tmp.write_text(json.dumps(a), "utf-8")
        os.replace(tmp, d / "ack.json")
        return self.crashes()


import re as _re  # noqa: E402
_CRASH_ID = _re.compile(r"[0-9]{8}-[0-9]{6}-[0-9a-z]{2,12}")


def _plain(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s or "")
