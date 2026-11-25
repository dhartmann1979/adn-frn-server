"""N8 Crash – gemeinsamer Absturz-Melder der N8schicht-Projekte (Python-Teil, gleich in allen Repositorys).

Gegenstück zu ``scripts/n8-admin.sh crash-hook`` (läuft als root nach JEDEM Ende eines Dienstes, systemd ``ExecStopPost``)
und zum Keep-Alive. Beide schreiben dieselbe Liste ``<Datenordner>/crashes.jsonl`` (eine JSON-Zeile je Befund),
die Einzelheiten stehen in ``<Datenordner>/crash/<id>.log``. Das Webinterface zeigt sie unter System → 💥 Abstürze
und nach der Anmeldung als Hinweisfenster (N8 Kit), bis ein Admin sie als gelesen markiert.

Was die Anwendung selbst beiträgt (der crash-hook allein sieht nur „Dienst beendet, Signal 6“):

* ``crash/fault-<unit>.log`` – faulthandler: Python-Stack ALLER Threads, wenn der Prozess hart stirbt (SIGSEGV in einer
  C-Bibliothek, SIGABRT vom systemd-Watchdog, SIGBUS, SIGFPE, SIGILL). Der crash-hook hängt ihn an den Befund.
* ``crash/last-<unit>.json`` – Hänger-Wächter: Steht die asyncio-Event-Loop länger als ``stall_s`` Sekunden, wird der Stack
  der Loop festgehalten und dem Teil der Anwendung zugeordnet, in dem sie hängt (z. B. „Datenbank ← DMR“).
  Beendet der systemd-Watchdog den Dienst danach, nennt der Befund genau diese Stelle.
* Ausnahmen, die niemand abfängt (Tasks, Threads, Hauptprogramm), und eigene Meldungen über ``note()``
  (z. B. „Verbindungsschleife FRN beendet“, „Vocoder-Prozess mit Signal 11 beendet“).

    watch = CrashWatch(data_dir, app="N8 Crosslink", unit="n8crosslink.service",
                       services=[(r"/frn\\.py$", "FRN"), (r"/dmr/", "DMR")])
    watch.install()                 # im laufenden asyncio-Programm (startet den Hänger-Wächter)
    watch.note("FRN", "Verbindungsschleife beendet", traceback_text, kind="task")

Nur Standardbibliothek – keine Abhängigkeit vom Web-Framework.
"""
from __future__ import annotations

import asyncio
import faulthandler
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import traceback
from typing import Iterable, Optional

log = logging.getLogger("n8crash")

KINDS = {   # Art -> Bezeichnung (gleiche Liste im N8 Kit und in n8-admin.sh)
    "crash": "Absturz", "watchdog": "Watchdog", "oom": "Speicher voll", "exit": "Beendet", "timeout": "Zeitüberschreitung",
    "stall": "Hänger", "task": "Teil abgestürzt", "thread": "Thread abgestürzt", "helper": "Hilfsprozess abgestürzt",
    "keepalive": "Keep-Alive-Neustart", "restart": "Neustart", "intern": "Fehler",
}


def mark_planned(data_dir: str, unit: str, reason: str = "") -> None:
    """Die Anwendung beendet sich gleich ABSICHTLICH selbst (z. B. Neustart-Knopf, der den eigenen Prozess beendet, damit systemd
    ihn neu startet). Der crash-hook von n8-admin.sh sieht dann kein Absturz, sondern einen geplanten Neustart (Marke gilt 3 Minuten)."""
    try:
        d = os.path.join(os.path.abspath(data_dir), "crash")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"planned-{unit or 'app'}"), "w", encoding="utf-8") as f:
            f.write(f"{time.time():.0f} {reason}\n")
    except OSError:
        pass


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


class CrashWatch:
    def __init__(self, data_dir: str, app: str = "", unit: str = "", services: Iterable = (),
                 stall_s: float = 8.0, project_re: str = "") -> None:
        self.dir = os.path.abspath(data_dir)
        self.cdir = os.path.join(self.dir, "crash")
        self.list = os.path.join(self.dir, "crashes.jsonl")
        self.app = app
        self.unit = unit
        self.services = [(re.compile(rx), label) for rx, label in services]
        self.project_re = re.compile(project_re) if project_re else None
        self.stall_s = float(stall_s)
        # je Dienst eigene Dateien – mehrere Prozesse eines Projekts (z. B. HBlink4 + Dashboard) teilen sich den Datenordner
        sfx = "-" + re.sub(r"[^A-Za-z0-9@._-]", "_", unit) if unit else ""
        self.f_fault, self.f_last, self.f_svcs = f"fault{sfx}.log", f"last{sfx}.json", f"services{sfx}.json"
        self._beat = time.monotonic()
        self._loop_tid: Optional[int] = None
        self._stall: Optional[dict] = None
        self._recent: dict = {}
        self._fault = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ Zuordnung
    def service_of(self, frames_text: str, default: str = "") -> str:
        """Ordnet einen Stack/Traceback (Text) dem Teil der Anwendung zu: innerste passende Stelle zuerst,
        dazu der aufrufende Teil, wenn er ein anderer ist – z. B. „Datenbank ← DMR“."""
        files = re.findall(r'File "([^"]+)"', frames_text)
        hits: list[str] = []
        for f in reversed(files):                      # innerste Stelle zuerst
            for rx, label in self.services:
                if rx.search(f.replace("\\", "/")):
                    if label not in hits:
                        hits.append(label)
                    break
            if len(hits) == 2:
                break
        return " ← ".join(hits) if hits else default

    # ------------------------------------------------------------ Schreiben
    def _mk(self) -> None:
        os.makedirs(self.cdir, exist_ok=True)

    def note(self, service: str, reason: str, detail: str = "", kind: str = "intern", source: str = "app",
             dedup_s: float = 600) -> Optional[str]:
        """Befund festhalten (crashes.jsonl + crash/<id>.log). Gleicher Befund höchstens alle ``dedup_s`` Sekunden."""
        key = (service, kind, reason[:120])
        now = time.time()
        with self._lock:
            last = self._recent.get(key)
            if last and now - last[0] < dedup_s:
                self._recent[key] = (last[0], last[1] + 1)
                return None
            extra = (self._recent.get(key) or (0, 0))[1]
            self._recent[key] = (now, 0)
        cid = new_id()
        try:
            self._mk()
            head = [f"{self.app or 'N8'} – {KINDS.get(kind, kind)}: {service or '?'}", f"Zeit:    {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    f"Dienst:  {self.unit or '-'} (PID {os.getpid()})", f"Teil:    {service or '-'}", f"Ursache: {reason}"]
            if extra:
                head.append(f"(zusätzlich {extra}× derselbe Befund seit dem letzten Eintrag)")
            with open(os.path.join(self.cdir, cid + ".log"), "w", encoding="utf-8") as f:
                f.write("\n".join(head) + "\n\n" + (detail or "").rstrip() + "\n")
            entry = {"id": cid, "time": round(now, 3), "unit": self.unit, "app": self.app, "service": service, "kind": kind,
                     "reason": reason[:400], "source": source, "restarted": kind in ("task", "helper"), "log": cid + ".log"}
            line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
            fd = os.open(self.list, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
            log.error("💥 %s – %s: %s (Protokoll: crash/%s.log)", KINDS.get(kind, kind), service or "?", reason, cid)
            return cid
        except OSError as e:
            log.error("Befund nicht speicherbar (%s): %s – %s", e, service, reason)
            return None

    def note_exc(self, exc: BaseException, reason: str = "", kind: str = "task", service: str = "") -> Optional[str]:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        svc = service or self.service_of(tb, self.app)
        return self.note(svc, reason or f"{type(exc).__name__}: {exc}"[:300], tb, kind=kind)

    def _last(self, data: Optional[dict]) -> None:
        p = os.path.join(self.cdir, self.f_last)
        try:
            self._mk()
            if data is None:
                if os.path.exists(p):
                    os.remove(p)
                return
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, p)
        except OSError:
            pass

    # ------------------------------------------------------------ Einrichten
    def install(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        try:
            self._mk()
        except OSError as e:                      # Datenordner nicht beschreibbar: Wächter läuft, Befunde nur im Log
            log.warning("Absturz-Melder: %s nicht beschreibbar (%s)", self.cdir, e)
        self._faulthandler()
        self._last(None)
        try:   # für den crash-hook (root): ordnet den Python-Stack aus fault.log demselben Teil der Anwendung zu
            with open(os.path.join(self.cdir, self.f_svcs), "w", encoding="utf-8") as f:
                json.dump([[rx.pattern, label] for rx, label in self.services], f, ensure_ascii=False)
        except OSError:
            pass
        loop = loop or asyncio.get_running_loop()
        loop.set_exception_handler(self._loop_exc)
        threading.excepthook = self._thread_exc
        prev = sys.excepthook

        def _main_exc(t, e, tb):  # noqa: ANN001
            try:
                self.note(self.service_of("".join(traceback.format_tb(tb)), self.app), f"{t.__name__}: {e}",
                          "".join(traceback.format_exception(t, e, tb)), kind="crash")
            finally:
                prev(t, e, tb)
        sys.excepthook = _main_exc
        loop.create_task(self._beater())
        threading.Thread(target=self._stall_watch, name="n8-stallwatch", daemon=True).start()

    def _faulthandler(self) -> None:
        p = os.path.join(self.cdir, self.f_fault)
        try:
            if os.path.exists(p) and os.path.getsize(p) > 1_000_000:          # nicht endlos wachsen lassen
                with open(p, "rb") as f:
                    f.seek(-200_000, os.SEEK_END)
                    keep = f.read()
                with open(p, "wb") as f:
                    f.write(keep)
            self._fault = open(p, "a", encoding="utf-8")                       # bleibt offen – faulthandler braucht die Datei
            self._fault.write(f"\n=== {self.app} gestartet {time.strftime('%Y-%m-%d %H:%M:%S')} · PID {os.getpid()} ===\n")
            self._fault.flush()
            faulthandler.enable(file=self._fault, all_threads=True)
        except OSError as e:
            log.warning("faulthandler: %s – Ausgabe nach stderr (Journal)", e)
            faulthandler.enable(all_threads=True)

    def _loop_exc(self, loop: asyncio.AbstractEventLoop, ctx: dict) -> None:
        exc = ctx.get("exception")
        if exc is None or isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
            loop.default_exception_handler(ctx)
            return
        task = ctx.get("task") or ctx.get("future")
        name = getattr(task, "get_name", lambda: "")() if task is not None else ""
        self.note_exc(exc, f"{type(exc).__name__}: {exc}"[:300] + (f" (Task {name})" if name else ""), kind="task")
        log.error("%s", ctx.get("message") or "Ausnahme in asyncio", exc_info=exc)

    def _thread_exc(self, args) -> None:  # noqa: ANN001
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        tb = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        self.note(self.service_of(tb, self.app), f"Thread {name}: {args.exc_type.__name__}: {args.exc_value}"[:300], tb, kind="thread")

    # ------------------------------------------------------------ Hänger-Wächter
    async def _beater(self) -> None:
        self._loop_tid = threading.get_ident()
        while True:
            self._beat = time.monotonic()
            await asyncio.sleep(0.5)

    def _loop_stack(self) -> str:
        fr = sys._current_frames().get(self._loop_tid or -1)          # noqa: SLF001 – genau dafür gedacht
        return "".join(traceback.format_stack(fr)) if fr is not None else "(Stack der Event-Loop nicht lesbar)"

    def _stall_watch(self) -> None:
        while True:
            time.sleep(1.0)
            try:
                lag = time.monotonic() - self._beat
                s = self._stall
                if s is None and lag > self.stall_s:
                    stack = self._loop_stack()
                    svc = self.service_of(stack, self.app)
                    self._stall = {"since": time.time() - lag, "stack": stack, "service": svc, "max": lag, "marks": [8]}
                    log.warning("⏳ Event-Loop steht seit %.0f s – hängt in %s:\n%s", lag, svc, stack)
                    self._write_stall()
                elif s is not None and lag > self.stall_s:
                    s["max"] = lag
                    nxt = s["marks"][-1] * 2
                    if lag >= nxt:                                   # bei 16, 32, 64 s neu festhalten
                        s["marks"].append(nxt)
                        s["stack"] = self._loop_stack()
                        s["service"] = self.service_of(s["stack"], s["service"])
                        self._write_stall()
                elif s is not None:                                  # Loop läuft wieder
                    self._stall = None
                    self._last(None)
                    dur = s["max"]
                    if dur >= 2 * self.stall_s:
                        self.note(s["service"], f"Event-Loop {dur:.0f} s blockiert – Webinterface und Verbindungen standen still",
                                  "Stack der Event-Loop während des Hängers:\n" + s["stack"], kind="stall", dedup_s=300)
            except Exception as e:  # noqa: BLE001 – der Wächter selbst darf nie sterben
                log.debug("Hänger-Wächter: %s", e)

    def _write_stall(self) -> None:
        s = self._stall or {}
        self._last({"time": time.time(), "kind": "stall", "service": s.get("service", ""),
                    "reason": f"Event-Loop steht seit {s.get('max', 0):.0f} s (hängt in {s.get('service') or '?'})",
                    "since": s.get("since"), "detail": s.get("stack", "")})
