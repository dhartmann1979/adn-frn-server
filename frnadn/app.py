"""
frn_adn – dashboard and admin portal for the Java FRN server of freeradionetwork.de
(FastAPI + asyncio). Settings live in SQLite; server.properties is written from them.

Environment:
  FRNADN_DATA      data directory (SQLite database); default <repo>/data
  FRNADN_FRN_HOME  working directory of the FRN server (server.properties, acl/, logs/);
                   default <data>/frn
  FRNADN_FRN_JAR   FRN_Server.jar, default /opt/frn-server/FRN_Server.jar
  FRNADN_FRN_DIRECT 1 = run the FRN server as a child process instead of frn-server.service
  FRNADN_BIND      web listen address, default 0.0.0.0
  FRNADN_PORT      web port (HTTP), default 8080
  FRNADN_DEMO      1 = demo mode (simulated system values)
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import socket
import shutil
import sys
import time
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import n8_security as _sec
from .n8_admin import N8Admin, own_unit
from . import backup as fbackup
from . import sysman as fsysman
from . import portal as fportal
from . import mailcfg
from . import webmail as fwebmail
from . import cluster, n8feed, widgets as fwidgets
from . import frn_errorlog
from . import __version__, branding as brandstore, clientsw, links as linkstore, siteicons, updater
from .auth import ADMIN_ROLES, Auth, AuthError
from .db import DB
from .frn.acl import ACLStore
from .frn.javasrv import JavaServer, with_peer
from .frn.logwatch import LogWatch
from .frn.store import MAX_ROOMS, ROOM_COLUMNS, Store
from .live import Live
from .settings import Settings, SettingsError
from .stats import RANGES, Stats
from .system import System

log = logging.getLogger("frnadn")
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DATA = Path(os.environ.get("FRNADN_DATA", ROOT / "data"))
DEMO = os.environ.get("FRNADN_DEMO", "") not in ("", "0")
COOKIE = "frnadn_session"
FRN_HOME = Path(os.environ.get("FRNADN_FRN_HOME", DATA / "frn"))
FRN_JAR = Path(os.environ.get("FRNADN_FRN_JAR", "/opt/frn-server/FRN_Server.jar"))
NAME_RE = re.compile(r"[^<>\r\n,]{1,40}")
EMAIL_RE = re.compile(r"[^@\s<>,]+@[^@\s<>,]+")


class Ctx:
    def __init__(self):
        DATA.mkdir(parents=True, exist_ok=True)
        self.db = DB(DATA / "frnadn.db")
        self.auth = Auth(self.db)
        self.settings = Settings(self.db)
        self.store = Store(self.db, self.settings)
        self.acls = ACLStore(self.db, self.store, FRN_HOME)
        self.stats = Stats(self.db)
        self.live = Live(self.db, self.notify, self.stats.bump)
        self.java = JavaServer(self.store, self.settings, FRN_HOME, FRN_JAR, demo=DEMO)
        self.server = LogWatch(self.store, self.live, FRN_HOME, self.java)
        self.live.server = self.server
        self.live.chat_mode = self.settings.get("dashboard.chat")
        self.system = System(demo=DEMO)
        self.n8 = N8Admin(DATA, demo=DEMO)      # Dienste, Berechtigungen, „Update jetzt“ über scripts/n8-admin.sh
        if DEMO and not (DATA / "n8-admin.json").exists():   # Demo: was scripts/n8-admin.sh sudo-setup schreiben würde
            all5 = ["start", "stop", "restart", "enable", "disable"]
            (DATA / "n8-admin.json").write_text(json.dumps({"version": 1, "name": "ADN-FRN-Server", "id": "frnadn", "systemctl": "/usr/bin/systemctl",
                "self": str(ROOT / "scripts" / "n8-admin.sh"), "update_unit": "frnadn-update.service", "request": str(DATA / "update.request"),
                "log": str(DATA / "update.log"), "result": str(DATA / "update.result"), "units": [
                    {"unit": "frnadn.service", "label": "Dashboard (frnadn)", "actions": all5},
                    {"unit": "frn-server.service", "label": "Java-FRN-Server", "actions": all5},
                    {"unit": "frnadn-update.path", "label": "Update-Auslöser („Update jetzt“)", "actions": all5}]}), "utf-8")
        self.sockets: Dict[WebSocket, Dict[str, Any]] = {}
        self.restart_needed = False
        self.dashboard_restart_needed = False
        self.tasks: List[asyncio.Task] = []

    def notify(self, ev: Dict[str, Any]) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.ensure_future(push(ev))

    def see_hidden(self, user) -> bool:
        return bool(user) or bool(self.settings.get("dashboard.show_hidden"))

    def chat_allowed(self, user) -> bool:
        m = self.settings.get("dashboard.chat")
        return m == "public" or (m == "users" and bool(user)) or (m == "admin" and bool(user) and user["role"] in ADMIN_ROLES)

    def hidden_for(self, user) -> set:
        return set() if self.see_hidden(user) else self.live.hidden_rooms()


ctx: Optional[Ctx] = None
_RESTORED: Dict[str, Any] = {}
app = FastAPI(title="frn_adn", **{"docs_url": None, "redoc_url": None, "openapi_url": None, **_sec.FASTAPI_KWARGS})
app.add_middleware(GZipMiddleware, minimum_size=800)
# N8 Guard: request budget per IP (flooding), websocket limit, body size – the same in every N8 system
from .n8_guard import Guard, LoginGuard  # noqa: E402
app.add_middleware(Guard, api_per_min=1200, page_per_min=600, auth_per_min=30, max_body=64 * 1024 * 1024)
LOGIN_GUARD = LoginGuard()


class HTTPError(Exception):
    def __init__(self, status: int, msg: str):
        self.status, self.msg = status, msg


@app.exception_handler(HTTPError)
async def _http_error(request: Request, exc: HTTPError):
    return JSONResponse({"error": exc.msg}, status_code=exc.status)


@app.exception_handler(AuthError)
async def _auth_error(request: Request, exc: AuthError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(SettingsError)
async def _settings_error(request: Request, exc: SettingsError):
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.middleware("http")
async def _mw(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "PATCH", "DELETE") \
            and request.headers.get("x-n8") != "1":
        return JSONResponse({"error": "Missing X-N8 header."}, status_code=403)
    resp = await call_next(request)
    _sec.headers(resp, https=_sec.is_https(request))
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    elif request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "public, max-age=604800, immutable" if request.url.query else "public, max-age=3600"
    return resp


# ---------------------------------------------------------------- helpers
def ip_of(conn) -> str:
    return conn.client.host if conn.client else ""


def user_of(conn) -> Optional[Dict[str, Any]]:
    return ctx.auth.session_user(conn.cookies.get(COOKIE))


def need_human_admin(request: Request) -> Dict[str, Any]:
    return need_admin(request)


def is_admin(u) -> bool:
    return bool(u) and u["role"] in ADMIN_ROLES


def need_view(request: Request):
    u = user_of(request)
    if not u and not ctx.settings.get("dashboard.public"):
        raise HTTPError(401, "Please log in.")
    return u


def need_admin(request: Request) -> Dict[str, Any]:
    u = user_of(request)
    if not u:
        raise HTTPError(401, "Please log in.")
    if not is_admin(u):
        raise HTTPError(403, "Admins only.")
    return u


async def body(request: Request) -> Dict[str, Any]:
    try:
        b = await request.json()
    except Exception:
        raise HTTPError(400, "Invalid request.")
    if not isinstance(b, dict):
        raise HTTPError(400, "Invalid request.")
    return b


async def push(ev: Dict[str, Any]) -> None:
    """Send one event to every browser that may see it."""
    t = ev.get("type")
    room = ev.get("room") if isinstance(ev.get("room"), str) else (ev.get("entry") or {}).get("room") or (ev.get("entry") or {}).get("net")
    hidden = room in ctx.live.hidden_rooms() if room else False
    cache: Dict[Any, Any] = {}
    dead = []
    for ws, meta in list(ctx.sockets.items()):
        if t == "log" and not meta.get("admin"):
            continue
        if hidden and not meta.get("see_hidden"):
            continue
        if t == "chat" and not meta.get("chat"):
            continue
        out = ev
        if t == "room":
            k = ("room", meta.get("admin"))
            if k not in cache:
                cache[k] = ctx.live.room(room, bool(meta.get("admin")))
            if cache[k] is None:
                continue
            out = {"type": "room", "room": cache[k]}
        elif t == "rooms":
            k = ("rooms", meta.get("see_hidden"), meta.get("admin"))
            if k not in cache:
                cache[k] = ctx.live.rooms(bool(meta.get("see_hidden")), bool(meta.get("admin")))
            out = {"type": "rooms", "rooms": cache[k]}
        try:
            await ws.send_json(out)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ctx.sockets.pop(ws, None)


def _cluster_public(s: Dict[str, Any]) -> Dict[str, Any]:
    role = s["cluster.role"]
    if role not in ("master", "backup"):
        return {"role": "off"}
    pb = pushed_backup()                               # the same address the clients get at login
    me = {"host": s["frn.address"] or "", "port": int(s["frn.port"])}
    peer = {"host": pb["host"], "port": pb["port"]} if pb["host"] else None
    return {"role": role, "master": me if role == "master" else peer, "backup": me if role == "backup" else peer,
            "maintenance": bool(_cluster_get("cluster.maintenance")),
            "peer_url": (s["cluster.peer_url"] or "").rstrip("/") + "/" if s["cluster.peer_url"] else ""}   # also in the link menu


def info_for(u) -> Dict[str, Any]:
    s = ctx.settings.all()
    addr = s["frn.address"]
    if addr:
        addr = f"{addr}:{s['frn.port']}"
    return {"title": s["dashboard.title"], "subtitle": s["dashboard.subtitle"], "address": addr, "public": s["dashboard.public"],
            "version": __version__, "demo": DEMO, "chat": ctx.chat_allowed(u), "owner": s["frn.owner_callsign"],
            "website": s["frn.website"], "setup_needed": not ctx.auth.has_superadmin(),
            "role": s["cluster.role"],          # Master & Backup: im Kopfbereich als [Master] / [Backup] / [Standalone]
            # für FRN-Clients wie N8 Crosslink: wer ist Master, wer Backup (die Adresse geht ohnehin als backup_server_addr an
            # jeden FRN-Client) – damit sie nach einem Ausfall von selbst zum Master zurückkehren
            "cluster": _cluster_public(s),
            # ✉️ N8 Mail: webmail tab for every logged-in user
            "mail": ({"webmail": True, "address": _mail_address(u)} if u and s["mail.enabled"] and mailcfg.domains(s) and _mail_address(u) else None),
            # 📰 portal page (news) – the tab in the menu leads there
            "portal": ({"url": next((_url_of(d) for d, t in web_hosts(s) if t == "portal"), "/portal")}
                       if s["portal.enabled"] else None)}


def refresh_sockets() -> None:
    for ws, meta in list(ctx.sockets.items()):
        u = user_of(ws)
        meta.update(see_hidden=ctx.see_hidden(u), chat=ctx.chat_allowed(u), admin=is_admin(u))


# ---------------------------------------------------------------- pages & public API
def _page(name: str) -> Response:
    html = (STATIC / name).read_text(encoding="utf-8").replace("{{V}}", __version__)
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- domains and what they show (2.26)
HOST_TARGETS = [("live", "🎙️ Live dashboard"), ("portal", "📰 Portal (news)")]
_HOST_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def web_hosts(s: Optional[Dict[str, Any]] = None) -> List[Tuple[str, str]]:
    """Every domain of the dashboard with its target ("live" or "portal"); the certificate's main name comes first."""
    s = s or ctx.settings.all()
    out: List[Tuple[str, str]] = []
    for line in str(s.get("web.hosts") or "").splitlines():
        d, _, t = line.strip().partition("=")
        d, t = d.strip().lower().rstrip("."), t.strip()
        if _HOST_RE.fullmatch(d) and t in dict(HOST_TARGETS) and d not in dict(out):
            out.append((d, t))
    main = str(s.get("https.domain") or "").strip().lower()
    pd = str(s.get("portal.domain") or "").strip().lower()
    if pd and pd not in dict(out):                      # before 2.26: one portal domain
        out.append((pd, "portal"))
    if main and main not in dict(out):
        out.insert(0, (main, "live"))
    elif main:
        out.sort(key=lambda x: x[0] != main)
    return out


def _hosts_changes(hosts: List[Tuple[str, str]]) -> Dict[str, Any]:
    first_portal = next((d for d, t in hosts if t == "portal"), "")
    return {"web.hosts": "\n".join(f"{d}={t}" for d, t in hosts), "portal.domain": first_portal}


def host_target(host: str) -> Optional[str]:
    h = (host or "").split(":")[0].strip().lower().rstrip(".")
    return dict(web_hosts()).get(h)


def _url_of(d: str) -> str:
    s = ctx.settings.all()
    if s.get("https.enabled"):
        port = "" if int(s.get("https.port") or 443) == 443 else f":{s['https.port']}"
        return f"https://{d}{port}/"
    return f"http://{d}/"


@app.get("/")
async def index(request: Request):
    # every domain shows what it is set to under 🌐 Netz, Ports & Domains → 🔒 Domains & HTTPS (Live dashboard or 📰 portal)
    if ctx.settings.get("portal.enabled") and host_target(request.headers.get("host", "")) == "portal":
        return _page("portal.html")
    return _page("index.html")


@app.get("/dashboard")
async def dashboard_page():
    return _page("index.html")


@app.get("/portal")
async def portal_page():
    if not ctx.settings.get("portal.enabled"):
        return RedirectResponse("/", status_code=302)
    return _page("portal.html")


@app.get("/news/{nid}")
async def portal_news_page(nid: int):
    if not ctx.settings.get("portal.enabled"):
        return RedirectResponse("/", status_code=302)
    return _page("portal.html")


def _portal_info(request: Request) -> Dict[str, Any]:
    s = ctx.settings.all()
    u = user_of(request)
    live = next((d for d, t in web_hosts(s) if t == "live"), "")
    dash = _url_of(live) if live else "/dashboard"
    if host_target(request.headers.get("host", "")) != "portal":
        dash = "/"
    return {"title": s["portal.title"] or s["dashboard.title"], "subtitle": s["portal.subtitle"] or s["dashboard.subtitle"],
            "intro": s["portal.intro"], "dashboard_url": dash, "address": f"{s['frn.address']}:{s['frn.port']}" if s["frn.address"] else "",
            "website": s["frn.website"], "owner": s["frn.owner_callsign"], "role": s["cluster.role"], "version": __version__,
            "categories": [{"id": c, "label": l} for c, l in fportal.CATEGORIES], "per_page": s["portal.per_page"],
            "user": ({"username": u["username"], "admin": is_admin(u)} if u else None),
            "show_live": bool(s["portal.show_live"]) and (bool(u) or bool(s["dashboard.public"])),
            "show_stats": bool(s["portal.show_stats"]) and (bool(u) or bool(s["dashboard.public"]))}


# ---------------------------------------------------------------- ✉️ N8 Mail (mailcfg.py, mailctl.py, webmail.py)
_mail_task: Optional[asyncio.Task] = None


def _mail_address(u) -> str:
    s = ctx.settings.all()
    doms = mailcfg.domains(s)
    lp = mailcfg.local_part(u["username"]) if u else None
    return f"{lp}@{doms[0]}" if lp and doms and lp not in mailcfg.ROLE_ALIASES else ""


def _web_base() -> str:
    s = ctx.settings.all()
    if s.get("https.domain") and s.get("https.enabled"):
        port = "" if int(s.get("https.port") or 443) == 443 else f":{s['https.port']}"
        return f"https://{s['https.domain']}{port}"
    return f"http://{s.get('frn.address') or '127.0.0.1'}:{_web_port()}"


def _mail_cert() -> Optional[tuple]:
    if _tls_manager is not None and _tls_manager.have_cert():
        return _tls_manager.cert_file, _tls_manager.key_file
    return None


async def _mailctl(action: str) -> Dict[str, Any]:
    if DEMO and action != "status":
        return {"ok": True, "message": f"Demo: mailctl {action} not run."}
    if os.geteuid() == 0:                       # tests/containers as root: no sudo needed
        cmd = [sys.executable, "-I", str(ROOT / "frnadn" / "mailctl.py"), action]
        p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(p.communicate(), mailcfg.MAILCTL_TIMEOUT)
        text = out.decode("utf-8", "replace")
        try:
            last = json.loads(text.strip().splitlines()[-1])
        except (ValueError, IndexError):
            last = {"ok": p.returncode == 0, "message": text[-300:]}
        return {**last, "log": text[-6000:]}
    return await mailcfg.run_mailctl(ROOT, action)


async def _mail_apply(who: str = "") -> Dict[str, Any]:
    s = ctx.settings.all()
    try:
        spec = await asyncio.to_thread(mailcfg.build_spec, ctx.db, s, _mail_cert(), DATA)
    except mailcfg.MailError as e:
        return {"ok": False, "message": str(e)}
    await asyncio.to_thread(mailcfg.write_spec, DATA, spec)
    r = await _mailctl("apply")
    if who:
        ctx.auth.audit("mail_applied" if r.get("ok") else "mail_apply_failed", who, (r.get("message") or "")[:300])
    return r


async def _mail_after_cert(action: str) -> None:
    s = ctx.settings.all()
    if s.get("mail.enabled") and (mailcfg.read_state(DATA).get("configured")):
        r = await (_mail_apply("certificate") if action == "apply" else _mailctl("certs"))
        log.info("N8 Mail nach Zertifikat: %s", r.get("message"))


def _mail_users_changed() -> None:
    """Users or passwords changed → rewrite the mailbox list (debounced, in the background)."""
    global _mail_task
    s = ctx.settings.all()
    if not s.get("mail.enabled") or not mailcfg.read_state(DATA).get("configured"):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def later():
        await asyncio.sleep(3)
        r = await _mail_apply()
        log.info("N8 Mail: Postfächer aktualisiert: %s", r.get("message"))
    if _mail_task and not _mail_task.done():
        _mail_task.cancel()
    _mail_task = loop.create_task(later())


# ---------------------------------------------------------------- ✉️ automatic mail domains and certificates (2.27)
_tls_main = None                       # the running HTTPS server – its certificate is swapped in place
_mail_kick: Optional[asyncio.Event] = None


def _my_ips() -> set:
    """Addresses that mean "this server": its public addresses and what the dashboard's own domain resolves to."""
    ips = set(sum(mailcfg._ips().values(), []))
    main = str(ctx.settings.get("https.domain") or "")
    if main:
        ips |= mailcfg.resolve(main)
    return ips


def _cert_plan() -> Dict[str, Any]:
    """Names for the certificate: all web domains, and every mail name whose DNS already points here."""
    s = ctx.settings.all()
    web = [d for d, _ in web_hosts(s)][1:]
    mine = _my_ips()
    ready, waiting = [], []
    for n in mailcfg.cert_names(s):
        (ready if mailcfg.dns_ready(n, mine) else waiting).append(n)
    return {"extra": web + ready, "waiting": waiting}


async def tls_refresh(reason: str = "") -> bool:
    """Extend (or shrink) the Let's Encrypt certificate to the wanted names – in place, without a restart."""
    cm, main = _tls_manager, _tls_main
    if cm is None:
        return False
    plan = await asyncio.to_thread(_cert_plan)
    ctx.db.kv_set("mail.dns_waiting", json.dumps(plan["waiting"]))
    from .tls import _DOMAIN_RE as _TLS_RE
    want = [d for d in plan["extra"] if _TLS_RE.fullmatch(d) and d != cm.domain]
    if set(want) == set(cm.extra) and not cm.needs_expand():
        return False
    old = list(cm.extra)
    cm.extra = want
    log.info("Zertifikat wird angepasst (%s): %s", reason or "Domains", ", ".join(cm.names()))
    if await cm.obtain():
        if main is not None and main.config.ssl is not None:
            main.config.ssl.load_cert_chain(cm.cert_file, cm.key_file)
        ctx.auth.audit("certificate_extended", "system", ", ".join(cm.names())[:480])
        return True
    cm.extra = old
    log.error("Zertifikat für %s nicht erweitert – DNS und Port 80 prüfen", ", ".join(want))
    return False


async def mail_auto(reason: str = "") -> Dict[str, Any]:
    """Add the base domains of all web domains as mail domains, extend the certificate, give the mail server the result."""
    s = ctx.settings.all()
    out: Dict[str, Any] = {"added": [], "certificate": False, "applied": None}
    if not s.get("mail.enabled"):
        return out
    if s.get("mail.auto_domains"):
        cur = mailcfg.domains(s)
        try:
            skip = json.loads(ctx.db.kv_get("mail.auto_skip") or "[]")
        except ValueError:
            skip = []
        new = mailcfg.auto_domains([d for d, _ in web_hosts(s)], cur, skip)
        if new != cur:
            ctx.settings.update({"mail.domains": ", ".join(new)}, "auto")
            out["added"] = [d for d in new if d not in cur]
            ctx.auth.audit("mail_domains_auto", "system", ", ".join(out["added"]))
            log.info("N8 Mail: Mail-Domains automatisch ergänzt: %s", ", ".join(out["added"]))
    out["certificate"] = await tls_refresh(reason or "Mail-Domains")
    if (out["added"] or out["certificate"]) and mailcfg.read_state(DATA).get("configured"):
        r = await _mail_apply("auto")
        out["applied"] = r.get("message")
    return out


def mail_kick() -> None:
    if _mail_kick is not None:
        _mail_kick.set()


async def mail_auto_loop() -> None:
    """Every 30 minutes (and right after a change): new mail domains, certificate, mail server."""
    global _mail_kick
    _mail_kick = asyncio.Event()
    await asyncio.sleep(20)
    while True:
        try:
            await mail_auto("automatisch")
        except Exception as e:  # noqa: BLE001
            log.warning("N8 Mail automatisch: %s", e)
        try:
            await asyncio.wait_for(_mail_kick.wait(), 1800)
        except asyncio.TimeoutError:
            pass
        _mail_kick.clear()
        await asyncio.sleep(2)


@app.get("/.well-known/bimi/{name}")
async def bimi_logo(name: str):
    s = ctx.settings.all()
    dom = name[:-4] if name.endswith(".svg") else ""
    if not s.get("mail.bimi") or dom not in mailcfg.domains(s):
        raise HTTPError(404, "not found")
    svg = ctx.db.kv_get("mail.bimi_svg") or mailcfg.bimi_default(s.get("dashboard.title") or "N8")
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400",
                                                              "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@app.get("/.well-known/mta-sts.txt")
async def mta_sts(request: Request):
    s = ctx.settings.all()
    host = request.headers.get("host", "").split(":")[0].lower()
    dom = host[len("mta-sts."):] if host.startswith("mta-sts.") else ""
    if s.get("mail.mta_sts", "off") == "off" or dom not in mailcfg.domains(s):
        raise HTTPError(404, "not found")
    return Response(mailcfg.mta_sts_policy(s, dom), media_type="text/plain")


_PTR_CACHE: Dict[str, Any] = {"t": 0.0, "v": []}


def _ptr_check() -> List[Tuple[str, List[str]]]:
    """Reverse DNS of the public addresses of this server (cached 10 minutes)."""
    if time.time() - _PTR_CACHE["t"] > 600:
        out = []
        for ip in mailcfg._ips().get("v4", []):
            try:
                out.append((ip, mailcfg.dns_query(ip, "PTR")))
            except Exception:  # noqa: BLE001
                out.append((ip, []))
        _PTR_CACHE.update(t=time.time(), v=out)
    return _PTR_CACHE["v"]


def _mail_view(s: Dict[str, Any]) -> Dict[str, Any]:
    st = mailcfg.read_state(DATA)
    mb = mailcfg.mailboxes(ctx.db, s)
    names = mailcfg.cert_names(s)
    have = set((st.get("cert") or {}).get("names") or []) or set(_tls_manager.names() if _tls_manager else [])
    warn = []
    if s.get("mail.enabled"):
        if not mailcfg.domains(s):
            warn.append("Noch keine Mail-Domain – unter 🌐 Netz, Ports & Domains → ✉️ Mail-Domains eintragen.")
        if not (s.get("https.enabled") and s.get("https.domain")):
            warn.append("HTTPS mit Let's Encrypt ist aus – der Mailserver braucht das Zertifikat (🔒 Domains & HTTPS).")
        missing = [n for n in names if n not in have]
        if missing and s.get("https.enabled"):
            warn.append("Noch nicht im Zertifikat: " + ", ".join(missing) + " – sobald der DNS-Eintrag auf diesen Server zeigt, "
                        "holt das Dashboard das Zertifikat automatisch (Prüfung alle 30 Minuten oder „🔄 Jetzt prüfen“).")
        if not s.get("mail.relay_host"):
            warn.append("Kein Upstream eingetragen – Mails gehen direkt ins Internet (ausgehend Port 25, viele Anbieter sperren ihn).")
        if mb["waiting"]:
            warn.append(f"{len(mb['waiting'])} Benutzer haben noch kein Mail-Passwort – es entsteht bei der nächsten Anmeldung im Dashboard.")
        if mailcfg.domains(s):
            for ip, ptr in _ptr_check():
                want = mailcfg.host_of(mailcfg.domains(s)[0])
                if want not in [p.rstrip(".") for p in ptr]:
                    warn.append(f"Reverse-DNS (PTR) von {ip} ist {', '.join(p.rstrip('.') for p in ptr) or 'nicht gesetzt'} – beim Hoster auf "
                                f"{want} ändern. Sonst meldet die Gegenstelle „Reverse DNS does not match SMTP Banner“ und Mails landen eher im Spam.")
        if s.get("mail.inbound_tls"):
            warn.append("Port 25 verlangt TLS: Server und Prüftools ohne STARTTLS werden mit „530 Must issue a STARTTLS command first“ "
                        "abgewiesen (RFC 3207 rät bei öffentlichen MX davon ab) – für den Empfang meist besser aus.")
        if s.get("mail.bimi") and s.get("mail.dmarc_policy") == "none":
            warn.append("BIMI braucht DMARC „quarantine“ oder „reject“.")
    boxes = [{k: v for k, v in b.items() if k != "hash"} for b in mb["boxes"]]
    return {"state": st, "boxes": boxes, "skipped": mb["skipped"], "warnings": warn, "domains": mailcfg.domains(s),
            "cert_names": names, "fields": ctx.settings.describe_section("mail"),
            "dns_waiting": json.loads(ctx.db.kv_get("mail.dns_waiting") or "[]"),
            "auto_skip": json.loads(ctx.db.kv_get("mail.auto_skip") or "[]"), "web_base": _web_base(), "demo": DEMO,
            "postmaster": (mailcfg.postmaster_box(ctx.db, s, [b for b in mb["boxes"] if b["hash"]]) or {}).get("address", "")}


@app.get("/api/admin/mail")
async def admin_mail(request: Request):
    need_admin(request)
    return await asyncio.to_thread(_mail_view, ctx.settings.all())


@app.post("/api/admin/mail/settings")
async def admin_mail_settings(request: Request):
    b = await body(request)
    changes = b.get("changes") or {}
    if not isinstance(changes, dict) or any(not str(k).startswith("mail.") for k in changes):
        raise HTTPError(400, "Invalid request.")
    before = mailcfg.domains(ctx.settings.all())
    keys = await _save(request, changes)
    after = mailcfg.domains(ctx.settings.all())
    if before != after:                         # removed by hand → not added again automatically; added again → allowed
        try:
            skip = set(json.loads(ctx.db.kv_get("mail.auto_skip") or "[]"))
        except ValueError:
            skip = set()
        skip = (skip | (set(before) - set(after))) - set(after)
        ctx.db.kv_set("mail.auto_skip", json.dumps(sorted(skip)))
    mail_kick()
    return {"ok": True, "changed": keys, "restart": False,
            "message": "Gespeichert. Mail-Domains, Let's-Encrypt-Zertifikat und Mailserver werden jetzt automatisch angepasst – "
                       "mail.<domain> kommt aufs Zertifikat, sobald sein DNS auf diesen Server zeigt."}


@app.post("/api/admin/mail/auto")
async def admin_mail_auto(request: Request):
    """Run the automatic step now (button „Jetzt prüfen“)."""
    u = need_admin(request)
    r = await mail_auto("von Hand")
    ctx.auth.audit("mail_auto", u["username"], json.dumps(r)[:400], ip_of(request))
    msg = []
    if r["added"]:
        msg.append("Neue Mail-Domains: " + ", ".join(r["added"]))
    msg.append("Zertifikat erweitert." if r["certificate"] else "Zertifikat unverändert.")
    if r["applied"]:
        msg.append(r["applied"])
    waiting = json.loads(ctx.db.kv_get("mail.dns_waiting") or "[]")
    if waiting:
        msg.append("Wartet auf DNS: " + ", ".join(waiting))
    return {"ok": True, "message": " ".join(msg), **r, "view": await asyncio.to_thread(_mail_view, ctx.settings.all())}


@app.post("/api/admin/mail/action")
async def admin_mail_action(request: Request):
    u = need_admin(request)
    b = await body(request)
    act = str(b.get("action") or "")
    if act not in ("status", "apply", "install", "disable"):
        raise HTTPError(400, "Unknown action.")
    if act in ("install", "disable") and u["role"] != "superadmin":
        raise HTTPError(403, "Only the superadmin installs or switches off the mail server.")
    if act == "apply":
        r = await _mail_apply(u["username"])
    elif act == "install":
        if not ctx.settings.get("mail.enabled"):
            ctx.settings.update({"mail.enabled": True}, u["username"])
        try:
            spec = await asyncio.to_thread(mailcfg.build_spec, ctx.db, ctx.settings.all(), _mail_cert(), DATA)
            await asyncio.to_thread(mailcfg.write_spec, DATA, spec)
        except mailcfg.MailError:
            pass
        r = await _mailctl("install")
        ctx.auth.audit("mail_install", u["username"], (r.get("message") or "")[:300], ip_of(request))
    elif act == "disable":
        r = await _mailctl("disable")
        ctx.settings.update({"mail.enabled": False}, u["username"])
        ctx.auth.audit("mail_disabled", u["username"], (r.get("message") or "")[:300], ip_of(request))
    else:
        r = await _mailctl("status")
    return {**r, "view": await asyncio.to_thread(_mail_view, ctx.settings.all())}


@app.get("/api/admin/mail/dns")
async def admin_mail_dns(request: Request, check: bool = False):
    need_admin(request)
    s = ctx.settings.all()
    tpl = await asyncio.to_thread(mailcfg.dns_templates, s, mailcfg.read_state(DATA), _web_base())
    if check:
        async def one(r):
            r["check"] = await asyncio.to_thread(mailcfg.check_record, r)
        await asyncio.gather(*[one(r) for t in tpl for r in t["records"]])
    return {"templates": tpl, "zones": {t["domain"]: mailcfg.zone_text(t) for t in tpl}, "checked": check}


@app.get("/api/admin/mail/bimi")
async def admin_mail_bimi(request: Request):
    need_admin(request)
    s = ctx.settings.all()
    own = ctx.db.kv_get("mail.bimi_svg")
    svg = own or mailcfg.bimi_default(s.get("dashboard.title") or "N8")
    return {"svg": svg, "own": bool(own), "problems": mailcfg.bimi_check(svg),
            "urls": {d: mailcfg.bimi_url(_web_base(), d) for d in mailcfg.domains(s)}}


@app.post("/api/admin/mail/bimi")
async def admin_mail_bimi_save(request: Request):
    u = need_admin(request)
    b = await body(request)
    if b.get("reset"):
        ctx.db.x("DELETE FROM kv WHERE key = 'mail.bimi_svg'")
        return {"ok": True, "message": "Standard-Logo"}
    if b.get("generate"):
        svg = mailcfg.bimi_default(str(b.get("title") or ctx.settings.get("dashboard.title") or "N8"), str(b.get("accent") or ""),
                                   str(b.get("text") or ""))
    else:
        svg = str(b.get("svg") or "")
    problems = mailcfg.bimi_check(svg)
    if problems:
        raise HTTPError(400, "Not usable for BIMI: " + "; ".join(problems))
    ctx.db.kv_set("mail.bimi_svg", svg)
    ctx.auth.audit("mail_bimi", u["username"], "logo saved", ip_of(request))
    return {"ok": True, "message": "BIMI-Logo gespeichert"}


# ---------------------------------------------------------------- ✉️ webmail (every logged-in user)
def _need_mail(request: Request):
    u = user_of(request)
    if not u:
        raise HTTPError(401, "Please log in.")
    s = ctx.settings.all()
    addr = _mail_address(u)
    if not s.get("mail.enabled") or not addr:
        raise HTTPError(404, "No mailbox.")
    return u, addr


async def _box(addr: str, fn, *a):
    def work():
        with fwebmail.Box(addr, mailcfg.webmail_secret(ctx.db)) as b:
            return fn(b, *a)
    try:
        return await asyncio.to_thread(work)
    except fwebmail.MailboxError as e:
        raise HTTPError(400, str(e))


@app.get("/api/mail/me")
async def mail_me(request: Request):
    u, addr = _need_mail(request)
    s = ctx.settings.all()
    out = await _box(addr, lambda b: {"folders": b.folders(), "quota": b.quota()})
    return {"address": addr, "name": u.get("display_name") or u["username"],
            "aliases": [f"{mailcfg.local_part(u['username'])}@{d}" for d in mailcfg.domains(s)[1:]],
            "server": {"host": mailcfg.host_of(mailcfg.domains(s)[0]), "imap": 993, "smtps": 465, "submission": 587}, **out}


@app.get("/api/mail/list")
async def mail_list(request: Request, folder: str = "INBOX", page: int = 0, q: str = ""):
    _, addr = _need_mail(request)
    return await _box(addr, lambda b: b.list(folder, max(0, page), 40, q))


@app.get("/api/mail/msg")
async def mail_msg(request: Request, folder: str, uid: int):
    _, addr = _need_mail(request)
    return await _box(addr, lambda b: b.message(folder, uid))


@app.get("/api/mail/html")
async def mail_html(request: Request, folder: str, uid: int, images: int = 0):
    _, addr = _need_mail(request)
    doc = await _box(addr, lambda b: b.html(folder, uid, bool(images)))
    img = "data: https:" if images else "data:"
    return Response(doc, media_type="text/html; charset=utf-8", headers={
        "Content-Security-Policy": f"default-src 'none'; style-src 'unsafe-inline'; img-src {img}; font-src data:; "
                                   "frame-ancestors 'self'; base-uri 'none'; form-action 'none'; sandbox allow-popups allow-popups-to-escape-sandbox",
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@app.get("/api/mail/att")
async def mail_att(request: Request, folder: str, uid: int, part: int):
    _, addr = _need_mail(request)
    name, data = await _box(addr, lambda b: b.attachment(folder, uid, part))
    from urllib.parse import quote
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"})


_WEBMAIL_SENT: Dict[str, List[float]] = {}


@app.post("/api/mail/send")
async def mail_send(request: Request):
    u, addr = _need_mail(request)
    b = await body(request)
    try:
        msg, rcpts = fwebmail.compose(addr, u.get("display_name") or "", b)
    except (fwebmail.MailboxError, ValueError) as e:
        raise HTTPError(400, str(e))
    # against spam from a taken-over account: at most 200 recipients per user and hour from the webmail
    now = time.time()
    sent = [t for t in _WEBMAIL_SENT.get(addr, []) if now - t < 3600]
    if len(sent) + len(rcpts) > 200:
        raise HTTPError(429, "Sending limit reached (200 recipients per hour) – please try again later.")
    _WEBMAIL_SENT[addr] = sent + [now] * len(rcpts)
    try:
        await asyncio.to_thread(fwebmail.send, addr, msg, rcpts)
    except fwebmail.MailboxError as e:
        raise HTTPError(400, str(e))

    def after(box):
        box.append(box.role_folder("sent"), msg.as_bytes())
        if b.get("reply_folder") and b.get("reply_uid"):
            try:
                box.imap.select(fwebmail._q(str(b["reply_folder"])))
                box.imap.uid("STORE", str(int(b["reply_uid"])), "+FLAGS", "(\\Answered)")
            except Exception:  # noqa: BLE001
                pass
    try:
        await _box(addr, after)
    except HTTPError:
        pass
    return {"ok": True, "message": f"Gesendet an {len(rcpts)} Empfänger"}


@app.post("/api/mail/act")
async def mail_act(request: Request):
    _, addr = _need_mail(request)
    b = await body(request)
    folder, uids, act = str(b.get("folder") or "INBOX"), [int(x) for x in (b.get("uids") or [])][:500], str(b.get("action") or "")
    if not uids:
        raise HTTPError(400, "Nothing selected.")
    if act in ("seen", "unseen", "flag", "unflag"):
        add = {"seen": ["seen"], "flag": ["flagged"]}.get(act, [])
        rem = {"unseen": ["seen"], "unflag": ["flagged"]}.get(act, [])
        await _box(addr, lambda x: x.flags(folder, uids, add, rem))
        return {"ok": True}
    if act == "delete":
        r = await _box(addr, lambda x: x.delete(folder, uids))
        return {"ok": True, "result": r}
    if act in ("move", "spam", "inbox"):
        def mv(x):
            to = str(b.get("to") or "") if act == "move" else (x.role_folder("junk") if act == "spam" else "INBOX")
            x.move(folder, uids, to)
        await _box(addr, mv)
        return {"ok": True}
    raise HTTPError(400, "Unknown action.")


@app.get("/portal/rss.xml")
async def portal_rss(request: Request):
    """RSS 2.0 feed of the published news."""
    if not ctx.settings.get("portal.enabled"):
        raise HTTPError(404, "The portal page is switched off.")
    from email.utils import formatdate
    from xml.sax.saxutils import escape as xesc
    info = _portal_info(request)
    host = re.sub(r"[^A-Za-z0-9.\-:\[\]]", "", request.headers.get("host", "")) or "localhost"
    base = f"{'https' if _sec.is_https(request) else 'http'}://{host}"
    items = (await asyncio.to_thread(fportal.list_public, ctx.db, 0, 30))["news"]
    body_xml = "".join(
        f"<item><title>{xesc(n['title'])}</title><link>{base}/news/{n['id']}</link><guid isPermaLink=\"true\">{base}/news/{n['id']}</guid>"
        f"<pubDate>{formatdate(n['published_at'] or 0, usegmt=True)}</pubDate><category>{xesc(n['category'])}</category>"
        + (f"<enclosure url=\"{base}{xesc(n['image_url'])}\" type=\"image/jpeg\" length=\"0\"/>" if n.get("image_url") else "")
        + f"<description>{xesc(n['teaser'] or n['body'][:500])}</description></item>" for n in items)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{xesc(info["title"])}</title>'
           f"<link>{base}/portal</link><description>{xesc(info['subtitle'] or 'News')}</description>{body_xml}</channel></rss>")
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


@app.get("/api/portal")
async def api_portal(request: Request, offset: int = 0, category: str = ""):
    """Public: portal page – title, welcome text, published news and (if the dashboard is public) a live summary."""
    if not ctx.settings.get("portal.enabled"):
        raise HTTPError(404, "The portal page is switched off.")
    info = _portal_info(request)
    news = await asyncio.to_thread(fportal.list_public, ctx.db, offset, info["per_page"], category)
    out: Dict[str, Any] = {**info, **news}
    if info["show_live"]:
        rooms = ctx.live.rooms(False, False)
        out["live"] = {"online": sum(len([c for c in r["clients"] if not c.get("parrot")]) for r in rooms),
                       "rooms": [{"name": r["name"], "parrot": r["parrot"], "stations": len([c for c in r["clients"] if not c.get("parrot")]),
                                  "talking": ({"callsign": r["talking"].get("callsign"), "name": r["talking"].get("name")} if r["talking"] else None)}
                                 for r in rooms],
                       "running": bool((ctx.server.state() or {}).get("running"))}
    if info["show_stats"]:
        t = (await asyncio.to_thread(ctx.stats.summary, "today", ctx.live.hidden_rooms())).get("totals", {})
        out["today"] = {k: t.get(k) for k in ("talks", "duration", "stations", "peak_online")}
    # 🧩 widgets at the side: order and choice of the admins, live data of other N8 systems from the SQLite cache
    out["widgets"] = await asyncio.to_thread(fwidgets.public, ctx.db, int(ctx.settings.get("portal.widget_interval") or 30))
    out["widgets_side"] = ctx.settings.get("portal.widgets_side")
    return out


@app.get("/api/portal/news/{nid}/image")
async def api_portal_news_image(nid: int, request: Request):
    """Topic image of a news item – published ones for everybody, drafts only for admins."""
    img = await asyncio.to_thread(fportal.get_image, ctx.db, nid, not is_admin(user_of(request)))
    if not img:
        raise HTTPError(404, "No image.")
    return Response(img[1], media_type=img[0], headers={"Cache-Control": "public, max-age=604800",
                                                        "Content-Security-Policy": "default-src 'none'"})


@app.get("/api/portal/news/{nid}")
async def api_portal_news(nid: int, request: Request):
    if not ctx.settings.get("portal.enabled"):
        raise HTTPError(404, "The portal page is switched off.")
    n = await asyncio.to_thread(fportal.get, ctx.db, nid, True)
    if not n:
        raise HTTPError(404, "This news item does not exist.")
    return {**_portal_info(request), "item": n}


# ---------------------------------------------------------------- 📰 Portal (admin): only admins are authors
@app.get("/api/admin/portal")
async def admin_portal(request: Request):
    need_admin(request)
    sec = {"id": "portal", "fields": ctx.settings.describe_section("portal")}
    s = ctx.settings.all()
    pd = [d for d, t in web_hosts(s) if t == "portal"]
    url = _url_of(pd[0]) if pd else "/portal"
    return {"settings": sec, "news": await asyncio.to_thread(fportal.list_all, ctx.db), "url": url,
            "domain": ", ".join(pd), "categories": [{"id": c, "label": l} for c, l in fportal.CATEGORIES]}


@app.post("/api/admin/portal/settings")
async def admin_portal_settings(request: Request):
    b = await body(request)
    changes = b.get("changes") or {}
    if not isinstance(changes, dict) or any(not str(k).startswith("portal.") or k == "portal.domain" for k in changes):
        raise HTTPError(400, "Invalid request.")
    keys = await _save(request, changes)
    await push({"type": "news"})
    return {"ok": True, "changed": keys}


# ---------------------------------------------------------------- 🧩 Portal widgets (widgets.py, n8feed.py)
@app.get("/api/admin/portal/widgets")
async def admin_widgets(request: Request):
    need_admin(request)
    return {"widgets": await asyncio.to_thread(fwidgets.list_all, ctx.db), "kinds": fwidgets.KINDS, "local_only": list(fwidgets.LOCAL_ONLY),
            "interval": ctx.settings.get("portal.widget_interval"), "side": ctx.settings.get("portal.widgets_side")}


@app.post("/api/admin/portal/widgets")
async def admin_widget_save(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        w = await asyncio.to_thread(fwidgets.save, ctx.db, b)
    except fwidgets.WidgetError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("widget_saved", u["username"], f"#{w['id']} {w['kind']} {w['title']}".strip(), ip_of(request))
    if not w["builtin"] and w["enabled"]:
        w = {**w, "test": await asyncio.to_thread(fwidgets.fetch_one, ctx.db, w["id"])}
    await push({"type": "news"})
    return {"ok": True, "widget": w}


@app.post("/api/admin/portal/widgets/order")
async def admin_widget_order(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        await asyncio.to_thread(fwidgets.order, ctx.db, b.get("ids") or [])
    except fwidgets.WidgetError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("widget_order", u["username"], ",".join(str(i) for i in b.get("ids") or [])[:200], ip_of(request))
    await push({"type": "news"})
    return {"ok": True}


@app.post("/api/admin/portal/widgets/key")
async def admin_widget_key(request: Request):
    need_admin(request)
    return {"key": n8feed.new_key()}


@app.post("/api/admin/portal/widgets/{wid}/test")
async def admin_widget_test(wid: int, request: Request):
    need_admin(request)
    try:
        r = await asyncio.to_thread(fwidgets.fetch_one, ctx.db, wid, f"adn-frn-server/{__version__} (portal)")
    except fwidgets.WidgetError as e:
        raise HTTPError(400, str(e))
    await push({"type": "news"})
    return r


@app.delete("/api/admin/portal/widgets/{wid}")
async def admin_widget_delete(wid: int, request: Request):
    u = need_admin(request)
    try:
        await asyncio.to_thread(fwidgets.delete, ctx.db, wid)
    except fwidgets.WidgetError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("widget_deleted", u["username"], f"#{wid}", ip_of(request))
    await push({"type": "news"})
    return {"ok": True}


async def widget_loop() -> None:
    """Every portal.widget_interval seconds: ask the other N8 systems for their live data and cache it in SQLite."""
    await asyncio.sleep(8)
    while True:
        try:
            if ctx.settings.get("portal.enabled"):
                ids = await asyncio.to_thread(fwidgets.due, ctx.db)
                agent = f"adn-frn-server/{__version__} (portal)"
                await asyncio.gather(*(asyncio.to_thread(fwidgets.fetch_one, ctx.db, i, agent) for i in ids), return_exceptions=True)
        except Exception:  # noqa: BLE001 – never stop the dashboard
            log.exception("portal widgets")
        await asyncio.sleep(max(15, int(ctx.settings.get("portal.widget_interval") or 30)))


@app.post("/api/admin/news")
async def admin_news_save(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        n = await asyncio.to_thread(fportal.save, ctx.db, b, u)
    except fportal.PortalError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("news_saved", u["username"], f"#{n['id']} {n['title'][:60]}" + (" (published)" if n["published"] else " (draft)"), ip_of(request))
    await push({"type": "news"})
    return {"ok": True, "item": n}


@app.post("/api/admin/news/{nid}/publish")
async def admin_news_publish(nid: int, request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        n = await asyncio.to_thread(fportal.set_published, ctx.db, nid, bool(b.get("published")), u)
    except fportal.PortalError as e:
        raise HTTPError(404, str(e))
    ctx.auth.audit("news_published" if n["published"] else "news_unpublished", u["username"], f"#{nid} {n['title'][:60]}", ip_of(request))
    await push({"type": "news"})
    return {"ok": True, "item": n}


@app.delete("/api/admin/news/{nid}")
async def admin_news_delete(nid: int, request: Request):
    u = need_admin(request)
    old = await asyncio.to_thread(fportal.get, ctx.db, nid)
    if not old or not await asyncio.to_thread(fportal.delete, ctx.db, nid):
        raise HTTPError(404, "This news item does not exist (any more).")
    ctx.auth.audit("news_deleted", u["username"], f"#{nid} {old['title'][:60]}", ip_of(request))
    await push({"type": "news"})
    return {"ok": True}


_BUILD: Dict[str, Any] = {}


def build_info() -> Dict[str, Any]:
    """Version, commit and date of this installation for the footer (read once)."""
    if not _BUILD:
        v = updater.local_version()
        _BUILD.update(version=v["version"], commit=v["short"], date=v["date"])
    return dict(_BUILD)


@app.get("/api/info")
async def api_info(request: Request):
    u = user_of(request)
    i = info_for(u)
    if not u and not i["public"]:
        return {"title": i["title"], "public": False, "user": None, "login_required": True, "setup_needed": i["setup_needed"]}
    return {**i, "user": u, "build": build_info()}


@app.get("/api/live")
async def api_live(request: Request):
    u = need_view(request)
    return ctx.live.snapshot(ctx.see_hidden(u), is_admin(u))


@app.get("/api/stats")
async def api_stats(request: Request, range: str = "today"):
    u = need_view(request)
    if range not in RANGES:
        raise HTTPError(400, "range must be one of " + ", ".join(RANGES))
    return await asyncio.to_thread(ctx.stats.summary, range, ctx.hidden_for(u))


@app.get("/api/stations")
async def api_stations(request: Request):
    u = need_view(request)
    return {"stations": await asyncio.to_thread(ctx.stats.directory, ctx.hidden_for(u))}


@app.get("/api/station/{call}")
async def api_station(call: str, request: Request):
    u = need_view(request)
    if not re.fullmatch(r"[A-Za-z0-9/._ -]{1,24}", call):
        raise HTTPError(400, "Invalid callsign.")
    d = await asyncio.to_thread(ctx.stats.station, call.upper(), ctx.hidden_for(u))
    if not d:
        raise HTTPError(404, "Not heard on this server yet.")
    d["online"] = [dict(c, room=r["name"]) for r in ctx.live.rooms(ctx.see_hidden(u)) for c in r["clients"] if c["callsign"] == call.upper()]
    return d


@app.get("/api/chat")
async def api_chat(request: Request, limit: int = 100):
    u = need_view(request)
    if not ctx.chat_allowed(u):
        raise HTTPError(403, "The room chat is not shown here.")
    hid = ctx.hidden_for(u)
    rows = ctx.db.q("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 500),))
    return {"entries": [dict(r) for r in rows if r["net"] not in hid]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    u = user_of(ws)
    if not u and not ctx.settings.get("dashboard.public"):
        await ws.close(code=4401)
        return
    await ws.accept()
    ctx.sockets[ws] = {"admin": is_admin(u), "see_hidden": ctx.see_hidden(u), "chat": ctx.chat_allowed(u)}
    try:
        await ws.send_json({"type": "hello", "live": ctx.live.snapshot(ctx.see_hidden(u), is_admin(u))})
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        ctx.sockets.pop(ws, None)


# ---------------------------------------------------------------- auth
@app.post("/api/auth/login")
async def login(request: Request):
    b = await body(request)
    hours = 24 * 30 if b.get("remember") else float(ctx.settings.get("dashboard.session_hours"))
    ip, name = ip_of(request), str(b.get("username", ""))[:64]
    if not LOGIN_GUARD.allowed(ip, name):              # also blocks guessing with changing user names from one IP
        raise HTTPError(429, "Too many failed attempts. Please wait 15 minutes.")
    try:
        r = ctx.auth.login(name, str(b.get("password", "")), ip, request.headers.get("user-agent", ""), hours)
    except AuthError:
        LOGIN_GUARD.failed(ip, name)
        await asyncio.sleep(0.4)
        raise
    LOGIN_GUARD.ok(ip, name)
    resp = JSONResponse({"user": r["user"]})
    resp.set_cookie(COOKIE, r["token"], max_age=r["max_age"] if b.get("remember") else None, httponly=True,
                    samesite="strict", secure=request.url.scheme == "https", path="/")
    return resp


@app.post("/api/auth/logout")
async def logout(request: Request):
    ctx.auth.logout(request.cookies.get(COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


@app.post("/api/auth/password")
async def own_password(request: Request):
    u = user_of(request)
    if not u:
        raise HTTPError(401, "Please log in.")
    b = await body(request)
    return {"user": ctx.auth.change_own(u, str(b.get("old", "")), str(b.get("new", "")), str(b.get("username", "") or ""), ip_of(request))}


# ---------------------------------------------------------------- admin: settings
@app.get("/api/admin/settings")
async def get_settings(request: Request):
    need_admin(request)
    return {"sections": ctx.settings.describe(), "restart_needed": ctx.restart_needed, "server": ctx.server.state(),
            "jar": ctx.java.jar_version(), "jar_path": str(FRN_JAR), "home": str(FRN_HOME)}


def config_changed(u, request: Request, what: str) -> None:
    """Write the files of the FRN server; it uses them after a restart."""
    if ctx.java.write_config():
        ctx.restart_needed = True
    ctx.live.config_changed(f"{u['username']}: {what}")


@app.post("/api/admin/settings")
async def save_settings(request: Request):
    u = need_admin(request)
    b = await body(request)
    changes = b.get("changes") or {}
    if not isinstance(changes, dict):
        raise HTTPError(400, "Invalid request.")
    if "frn.default_room" in changes and changes["frn.default_room"] and \
            changes["frn.default_room"] not in [r["name"] for r in ctx.store.rooms()]:
        raise HTTPError(400, "Default room: this room does not exist.")
    if "sysman.email" in changes and ctx.settings.get("cluster.role") in ("master", "backup"):
        new = str(changes.get("sysman.email") or "").strip().lower()
        tag = hashlib.sha256(new.encode()).hexdigest()[:16] if new else ""
        sa = changes.get("frn.standalone", ctx.settings.get("frn.standalone"))
        if account_conflict(tag, bool(sa) if not isinstance(sa, str) else sa.lower() in ("1", "true", "on", "yes")):
            other = "backup" if ctx.settings.get("cluster.role") == "master" else "master"
            raise HTTPError(400, f"This FRN account is already used by the {other} – every server needs its own FRN account "
                                 f"(📧 FRN password {other.capitalize()} / Backup).")
    changed = ctx.settings.update(changes, u["username"])
    keys = [f.key for f in changed]
    if any(k.startswith("https.") for k in keys):
        ctx.dashboard_restart_needed = True
    if keys:
        ctx.auth.audit("settings_changed", u["username"], ", ".join(k for k in keys), ip_of(request))
        ctx.live.chat_mode = ctx.settings.get("dashboard.chat")
        if any(k.startswith(("frn.", "sysman.", "cluster.")) for k in keys):
            config_changed(u, request, "settings " + ", ".join(keys))
        if any(k in keys for k in ("sysman.email", "frn.standalone", "cluster.role")):
            await account_guard("settings")
        if "cluster.peer_url" in keys or "cluster.role" in keys:
            p = partner_link()
            if p:
                ctx.tasks.append(asyncio.create_task(asyncio.to_thread(siteicons.refresh_many, ctx.db, [p["url"]])))
            await push({"type": "links"})
        refresh_sockets()
        await push({"type": "info"})
        await push({"type": "rooms"})
    return {"changed": keys, "restart_needed": ctx.restart_needed, "dashboard_restart_needed": ctx.dashboard_restart_needed}


# Request an FRN password from the SystemManager ("Get Password" of the FRN client) – e.g. for an own account of this server
@app.get("/api/admin/frn-password")
async def frn_password_defaults(request: Request):
    need_admin(request)
    g = ctx.settings.get
    which = request.query_params.get("for", "")        # Master & Backup: an own FRN account for each server
    tag = {"master": " Master", "backup": " Backup"}.get(which, "")
    title = (g("dashboard.title") or "FRN server")
    return {"host": g("sysman.host") or "sysman.freeradionetwork.de", "callsign": g("frn.owner_callsign") or "",
            "name": ((g("frn.owner_name") or "") + tag).strip(), "email": g("sysman.email") or "", "band": "PC Only",
            "description": (title + (" – Backup" if which == "backup" else ""))[:60], "country": "Germany", "city": "",
            "for": which, "own": which in ("", g("cluster.role"))}


@app.post("/api/admin/frn-password")
async def frn_password_request(request: Request):
    u = need_admin(request)
    b = await body(request)
    host = ctx.settings.get("sysman.host") or "sysman.freeradionetwork.de"
    try:
        r = await asyncio.to_thread(fsysman.register, host, b)
    except fsysman.SysmanError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("frn_password_request", u["username"], f"{r['account']} <{r['email']}> → {r['code']}", ip_of(request))
    if r["ok"] and b.get("use_email") and not ctx.settings.get("sysman.email"):
        ctx.settings.update({"sysman.email": r["email"]}, u["username"])
    return r


# ---------------------------------------------------------------- Master & Backup (cluster.py)
def _cluster_set(key: str, value: Dict[str, Any]) -> None:
    ctx.db.kv_set(key, json.dumps(value, ensure_ascii=False))


def _cluster_get(key: str) -> Dict[str, Any]:
    try:
        return json.loads(ctx.db.kv_get(key) or "{}")
    except ValueError:
        return {}


_cluster_replay = cluster.Replay()


async def _cluster_peer(request: Request, roles) -> Dict[str, Any]:
    """Calls between the two servers: encrypted with the shared sync key (cluster.py), only in the right role."""
    raw = await request.body()
    if len(raw) > 1024 * 1024:
        raise HTTPError(413, "too large")
    try:
        msg = cluster.open_request(raw, ctx.settings.get("cluster.key"), request.url.path, _cluster_replay)
    except cluster.ClusterError as e:
        await asyncio.sleep(1.0)                        # slows down guessing
        raise HTTPError(403, str(e))
    if ctx.settings.get("cluster.role") not in roles:
        raise HTTPError(409, f"this server is {ctx.settings.get('cluster.role')}, not {'/'.join(roles)}")
    _remember_peer(msg.get("data") or {})
    return msg


def _cluster_answer(msg: Dict[str, Any], data: Any) -> Response:
    return Response(cluster.answer(msg, data, ctx.settings.get("cluster.key")), media_type=cluster.CTYPE)


def _account_tag() -> str:
    """Kennung des FRN-Kontos beim SystemManager (Hash der E-Mail) – zum Vergleich mit dem Partner, ohne die Adresse zu zeigen."""
    e = (ctx.settings.get("sysman.email") or "").strip().lower()
    return hashlib.sha256(e.encode()).hexdigest()[:16] if e else ""


def _me() -> Dict[str, Any]:
    """Was jeder Server bei jeder Anfrage/Antwort über sich mitschickt: Kennung seines FRN-Kontos."""
    s = ctx.settings.all()
    return {"account": _account_tag(), "standalone": bool(s["frn.standalone"]), "role": s["cluster.role"],
            # zur Anzeige im Kasten Master & Backup (nur über die verschlüsselte Verbindung, nur für Admins sichtbar)
            "email": s["sysman.email"] or "", "password_set": bool(s["sysman.password"]), "host": s["frn.address"] or "",
            "sysman": s["sysman.host"] or "", "frn_port": int(s["frn.port"] or 0)}


def _remember_peer(d: Dict[str, Any]) -> None:
    if isinstance(d, dict) and "account" in d:
        old = _cluster_get("cluster.peer_account")
        try:
            port = int(d.get("frn_port") or (d.get("frn") or {}).get("port") or old.get("frn_port") or 0)
        except (TypeError, ValueError):
            port = 0
        new = {"tag": str(d.get("account") or ""), "standalone": bool(d.get("standalone")),
               "email": str(d.get("email") or "")[:200], "password_set": bool(d.get("password_set")),
               "host": str(d.get("host") or "")[:200], "role": str(d.get("role") or ""), "frn_port": port, "time": time.time()}
        _cluster_set("cluster.peer_account", new)
        if (old.get("host"), old.get("frn_port")) != (new["host"], new["frn_port"]):
            # the FRN address of the partner is what every client gets at login (BN/BP) – write it, restart when it fits
            try:
                if ctx.java.write_config():
                    ctx.restart_needed = True
            except OSError as e:
                log.error("cannot write the FRN server configuration: %s", e)


def pushed_backup() -> Dict[str, Any]:
    """What the FRN server gives every client at login as its backup server (BN/BP in the login answer)."""
    s = with_peer(ctx.settings)
    if s["frn.backup_host"] and s["frn.backup_port"]:
        return {"host": s["frn.backup_host"], "port": int(s["frn.backup_port"]), "source": "manual"}
    if s["cluster.role"] in ("master", "backup"):
        host = s["cluster.peer_frn_host"] or cluster.peer_host(s["cluster.peer_url"])
        if host:
            return {"host": host, "port": int(s["frn.backup_port"] or s["cluster.peer_frn_port"] or s["frn.port"]),
                    "source": "partner" if s["cluster.peer_frn_host"] else "dashboard"}
    return {"host": "", "port": 0, "source": ""}


def account_conflict(tag: Optional[str] = None, standalone: Optional[bool] = None) -> bool:
    """Master und Backup mit demselben FRN-Konto beim SystemManager? (Dann darf nur der Master sein FRN-Server laufen.)"""
    s = ctx.settings.all()
    if s["cluster.role"] not in ("master", "backup"):
        return False
    tag = _account_tag() if tag is None else tag
    standalone = s["frn.standalone"] if standalone is None else standalone
    p = _cluster_get("cluster.peer_account")
    return bool(tag) and not standalone and bool(p.get("tag")) and not p.get("standalone") and p["tag"] == tag


async def account_guard(where: str) -> None:
    """Backup: hat es dasselbe FRN-Konto wie der Master, wird sein FRN-Server gestoppt und bleibt gesperrt (auch für den
    Keep-Alive), bis ein eigenes Konto eingetragen ist – sonst nimmt er dem Master die Anmeldung beim SystemManager weg.
    Ist das Konto wieder verschieden, gibt die Sperre den FRN-Server frei und startet ihn."""
    guard = _cluster_get("cluster.guard")
    if ctx.settings.get("cluster.role") == "backup" and account_conflict():
        if not guard:
            _cluster_set("cluster.guard", {"since": time.time(), "where": where})
            ctx.auth.audit("cluster_guard", where, "same FRN account as the master – FRN server stopped and locked", "")
            log.warning("Master & Backup: dasselbe FRN-Konto wie der Master – FRN-Server gestoppt und gesperrt (%s)", where)
        st = await ctx.java.status()
        if st.get("active") in ("active", "activating", "reloading"):
            ctx.n8._hold("frn-server.service", "stop")
            await ctx.java.control("stop")
            await ctx.server.poll_service()
    elif guard:
        ctx.db.x("DELETE FROM kv WHERE key='cluster.guard'")
        ctx.auth.audit("cluster_guard", where, "own FRN account – lock released, FRN server started", "")
        if ctx.settings.get("cluster.role") == "backup" or not account_conflict():
            ctx.n8._hold("frn-server.service", "start")
            await ctx.java.control("start")


def _frn_running() -> bool:
    st = ctx.server.state()
    return st["running"] or (DEMO and st["service"] == "active")       # demo: no Java process listens


def _frn_state() -> Dict[str, Any]:
    st = ctx.server.state()
    return {"running": _frn_running(), "clients": st["clients"], "address": ctx.settings.get("frn.address"),
            "port": ctx.settings.get("frn.port"), "since": st.get("started"), "on_air": _on_air(),
            "returning": bool(_cluster_get("cluster.return_pending"))}


def _on_air() -> bool:
    """Is somebody transmitting on this server right now?"""
    try:
        return any(r.talker for r in ctx.server.rooms.values())
    except AttributeError:
        return False


@app.post("/api/cluster/hello")
async def cluster_hello(request: Request):
    msg = await _cluster_peer(request, ("master", "backup"))
    return _cluster_answer(msg, {"ok": True, "role": ctx.settings.get("cluster.role"), "version": __version__,
            "title": ctx.settings.get("dashboard.title"), "frn": _frn_state(), "time": time.time(),
            "maintenance": bool(_cluster_get("cluster.maintenance")), "last": _cluster_get("cluster.last"),
            "callsigns": _online_callsigns(), **_me()})


def _online_callsigns() -> List[str]:
    """Callsigns connected here – for the station window of the partner (only over the encrypted connection)."""
    try:
        return sorted({c.callsign.upper() for r in ctx.server.rooms.values() for c in r.clients if c.callsign})
    except AttributeError:
        return []


@app.get("/api/admin/cluster/where")
async def cluster_where(call: str, request: Request):
    """Station window: is this station on the MAIN (master) or on the BACKUP right now?"""
    need_admin(request)
    s = ctx.settings.all()
    call = call.strip().upper()
    role = s["cluster.role"]
    out: Dict[str, Any] = {"role": role, "here": call in _online_callsigns(), "peer": None, "on": None,
                           "maintenance": bool(_cluster_get("cluster.maintenance")), "error": ""}
    if role in ("master", "backup") and s["cluster.peer_url"] and s["cluster.key"]:
        try:
            h = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/hello", s["cluster.key"], "POST", _me(), 6)
            _remember_peer(h)
            out["peer"] = call in (h.get("callsigns") or [])
            out["maintenance"] = out["maintenance"] or bool(h.get("maintenance"))
            out["peer_frn"] = h.get("frn") or {}
        except cluster.ClusterError as e:
            out["error"] = str(e)
    other = "backup" if role == "master" else "master"
    out["on"] = role if out["here"] else other if out["peer"] else None
    return out


@app.post("/api/cluster/export")
async def cluster_export(request: Request):
    msg = await _cluster_peer(request, ("master",))
    errors = ctx.acls.sync_from_files()                 # moderators may have changed lists in the FRN client
    data = cluster.export(ctx.db, ctx.settings, FRN_HOME / "acl", ctx.settings.get("dashboard.title"), ctx.store)
    _cluster_set("cluster.last_export", {"time": time.time(), "ip": ip_of(request), "hash": data["hash"][:12]})
    data.update(_me())
    if errors:
        data["warnings"] = errors
    return await asyncio.to_thread(_cluster_answer, msg, data)


@app.post("/api/cluster/pull")
async def cluster_pull_remote(request: Request):
    msg = await _cluster_peer(request, ("backup",))
    return _cluster_answer(msg, await cluster_pull("master"))


@app.post("/api/cluster/handback")
async def cluster_handback(request: Request):
    """End of the maintenance on the master: restart the own FRN server – the stations go back to the master
    (it is their backup address here)."""
    msg = await _cluster_peer(request, ("backup",))
    r = await send_back("master (handback)", ip_of(request))
    return _cluster_answer(msg, {"ok": r["ok"], "restarted": r["stopped"], "clients": r["clients"], **r})


@app.post("/api/cluster/return")
async def cluster_return_remote(request: Request):
    """The master asks: send the stations that are here back to it (stop – pause – start)."""
    msg = await _cluster_peer(request, ("backup",))
    d = msg.get("data") or {}
    return _cluster_answer(msg, await send_back(f"master: {str(d.get('by') or '')[:40]}".strip(), ip_of(request)))


@app.post("/api/cluster/update")
async def cluster_update_remote(request: Request):
    """The partner checks or installs the updates of this server (dashboard from GitHub and Java FRN server)."""
    msg = await _cluster_peer(request, ("master", "backup"))
    d = msg.get("data") or {}
    action = str(d.get("action") or "status")
    who = f"partner: {str(d.get('by') or '')[:40]}"
    if action == "run":
        res = await update_run(who, ip_of(request))
    else:
        res = await update_summary(action == "check")
    return _cluster_answer(msg, res)


async def cluster_pull(who: str) -> Dict[str, Any]:
    """Backup: fetch and take over the master's configuration. Restarts the FRN server only if it changed and no
    station is connected – otherwise the restart banner says it is pending."""
    s = ctx.settings.all()
    t0 = time.time()
    res: Dict[str, Any] = {"time": t0, "by": who, "ok": False}
    try:
        data = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/export", s["cluster.key"], "POST", _me(), 60)
        _remember_peer(data)
        await account_guard("sync")
        r = await asyncio.to_thread(cluster.apply, ctx.db, ctx.settings, ctx.store, FRN_HOME / "acl", data, "sync:master")
        res.update(ok=True, changed=r["changed"], counts=r["counts"], skipped=r["skipped"], master=data.get("version"),
                   hash=str(data.get("hash", ""))[:12], warnings=data.get("warnings") or [])
        restart = "none"
        if r["changed"]:
            ctx.store.invalidate()
            ctx.server.reload_rooms()
            ctx.live.chat_mode = ctx.settings.get("dashboard.chat")
            props = ctx.java.write_config()
            if (props or r["frn_changed"]) and _cluster_get("cluster.guard"):
                restart = "locked (same FRN account as the master)"
            elif props or r["frn_changed"]:
                st = {**ctx.server.state(), "running": _frn_running()}
                if st["running"] and st["clients"] == 0:
                    ctx.n8._hold("frn-server.service", "restart")
                    await ctx.java.control("restart")
                    ctx.restart_needed, restart = False, "done"
                elif st["running"]:
                    ctx.restart_needed, restart = True, f"pending ({st['clients']} stations connected)"
                else:
                    restart = "not running"
            refresh_sockets()
            await push({"type": "info"})
            await push({"type": "rooms"})
        res["restart"] = restart
        ctx.auth.audit("cluster_sync", who, ("changed" if r["changed"] else "unchanged") + f" · {r['counts']} · restart {restart}", "")
    except cluster.ClusterError as e:
        res["error"] = str(e)
    except Exception as e:  # noqa: BLE001 – a broken sync must never stop the dashboard
        log.exception("cluster sync")
        res["error"] = f"Sync failed: {e}"
    res["seconds"] = round(time.time() - t0, 1)
    _cluster_set("cluster.last", res)
    if not res["ok"]:
        log.warning("Master & Backup: %s", res.get("error"))
    return res


async def cluster_hourly() -> None:
    """Backup: fetch the configuration at every full hour (a few seconds after it)."""
    while True:
        await asyncio.sleep(max(5.0, cluster.next_full_hour() - time.time() + 7))
        s = ctx.settings.all()
        if s["cluster.role"] == "backup" and s["cluster.hourly"] and s["cluster.peer_url"] and s["cluster.key"]:
            await cluster_pull("hourly")


@app.get("/api/admin/cluster")
async def cluster_status(request: Request):
    need_admin(request)
    s = ctx.settings.all()
    out: Dict[str, Any] = {"role": s["cluster.role"], "peer_url": s["cluster.peer_url"], "key_set": bool(s["cluster.key"]),
                           "hourly": s["cluster.hourly"], "last": _cluster_get("cluster.last"),
                           "last_export": _cluster_get("cluster.last_export"), "maintenance": _cluster_get("cluster.maintenance"),
                           "next": cluster.next_full_hour() if s["cluster.role"] == "backup" and s["cluster.hourly"] else None,
                           "frn": _frn_state(), "backup_addr": s["frn.backup_host"] or cluster.peer_host(s["cluster.peer_url"]), "pushed": pushed_backup(),
                           "peer": None, "last_return": _cluster_get("cluster.last_return"),
                           "return_pending": _cluster_get("cluster.return_pending"), "auto_return": s["cluster.auto_return"],
                           "return_pause": s["cluster.return_pause"]}
    if s["cluster.role"] != "off" and s["cluster.peer_url"] and s["cluster.key"]:
        try:
            out["peer"] = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/hello", s["cluster.key"], "POST", _me(), 8)
        except cluster.ClusterError as e:
            out["peer"] = {"ok": False, "error": str(e)}
        p = out["peer"] or {}
        _remember_peer(p)
        await account_guard("status")
        out["guard"] = _cluster_get("cluster.guard")
        # beide Server mit demselben FRN-Konto: der SystemManager lässt nur einen online (der andere: „wrong credentials“)
        out["same_account"] = account_conflict()
    # FRN-Konten beider Server beim SystemManager (bleiben beim Abgleich unangetastet)
    me, peer = _me(), _cluster_get("cluster.peer_account")
    own = {"email": me["email"], "password_set": me["password_set"], "standalone": me["standalone"], "host": me["host"], "self": True}
    other = {"email": peer.get("email", ""), "password_set": peer.get("password_set"), "standalone": peer.get("standalone"),
             "host": peer.get("host", ""), "time": peer.get("time")} if peer else None
    if s["cluster.role"] == "master":
        out["accounts"] = {"master": own, "backup": other}
    elif s["cluster.role"] == "backup":
        out["accounts"] = {"master": other, "backup": own}
    return out


@app.post("/api/admin/cluster/sync")
async def cluster_sync_now(request: Request):
    u = need_admin(request)
    s = ctx.settings.all()
    if s["cluster.role"] == "backup":
        return await cluster_pull(u["username"])
    if s["cluster.role"] == "master":         # the backup fetches – the master only asks it to
        try:
            r = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/pull", s["cluster.key"], "POST", _me(), 90)
        except cluster.ClusterError as e:
            r = {"ok": False, "error": str(e), "time": time.time()}
        r["via"] = "backup"
        _cluster_set("cluster.last", r)
        ctx.auth.audit("cluster_sync", u["username"], "asked the backup: " + ("ok" if r.get("ok") else r.get("error", "")), ip_of(request))
        return r
    raise HTTPError(400, "Set the role (Master or Backup) first.")


@app.post("/api/admin/cluster/key")
async def cluster_new_key(request: Request):
    u = need_admin(request)
    key = cluster.new_key()
    ctx.settings.update({"cluster.key": key}, u["username"])
    ctx.auth.audit("cluster_key", u["username"], "new sync key", ip_of(request))
    return {"key": key}


@app.post("/api/admin/cluster/maintenance")
async def cluster_maintenance(request: Request):
    """Master: hand over to the backup for maintenance (sync, then stop the own FRN server – the clients move to their
    backup address by themselves) and take back afterwards (start, then the backup sends its stations back)."""
    u = need_admin(request)
    b = await body(request)
    s = ctx.settings.all()
    if s["cluster.role"] != "master":
        raise HTTPError(400, "Only the master hands over to the backup.")
    steps: List[Dict[str, Any]] = []
    call = lambda path, timeout=30: asyncio.to_thread(cluster.call, s["cluster.peer_url"], path, s["cluster.key"],  # noqa: E731
                                                      "POST", _me(), timeout)
    if b.get("on"):
        try:
            r = await call("/api/cluster/pull", 90)
            steps.append({"step": "Configuration synced to the backup", "ok": bool(r.get("ok")), "detail": r.get("error", "")})
            _cluster_set("cluster.last", {**r, "via": "backup"})
            if not r.get("ok"):
                raise HTTPError(409, f"Sync failed – nothing switched: {r.get('error', '')}")
            hello = await call("/api/cluster/hello", 10)
        except cluster.ClusterError as e:
            raise HTTPError(409, f"Backup not reachable – nothing switched: {e}")
        if not (hello.get("frn") or {}).get("running") and not b.get("force"):
            raise HTTPError(409, "The FRN server on the backup is not running – nothing switched.")
        steps.append({"step": "FRN server on the backup is running", "ok": True, "detail": ""})
        clients = ctx.server.state()["clients"]
        ctx.n8._hold("frn-server.service", "stop")      # Keep-Alive: stays stopped
        r = await ctx.java.control("stop")
        if r["rc"] != 0:
            raise HTTPError(500, f"Stopping the FRN server failed: {r['out'].strip()[:200]}")
        steps.append({"step": "FRN server here stopped – the stations switch to the backup", "ok": True, "detail": f"{clients} stations"})
        _cluster_set("cluster.maintenance", {"since": time.time(), "by": u["username"]})
        ctx.auth.audit("cluster_maintenance", u["username"], "handed over to the backup", ip_of(request))
    else:
        ctx.n8._hold("frn-server.service", "start")
        r = await ctx.java.control("start")
        if r["rc"] != 0:
            raise HTTPError(500, f"Starting the FRN server failed: {r['out'].strip()[:200]}")
        for _ in range(30):
            await asyncio.sleep(1)
            await ctx.server.poll_service()
            if _frn_running():
                break
        ok = _frn_running()
        steps.append({"step": "FRN server here started", "ok": ok, "detail": "" if ok else "not running after 30 s"})
        ctx.db.x("DELETE FROM kv WHERE key='cluster.maintenance'")
        if ok and b.get("handback", True):
            try:
                h = await call("/api/cluster/handback", 60)
                steps.append({"step": "Backup sends its stations back", "ok": bool(h.get("ok")),
                              "detail": f"{h.get('clients', 0)} stations" if h.get("restarted") else "no FRN server running there"})
            except cluster.ClusterError as e:
                steps.append({"step": "Backup sends its stations back", "ok": False, "detail": str(e)})
        ctx.auth.audit("cluster_maintenance", u["username"], "taken back from the backup", ip_of(request))
    await ctx.server.poll_service()
    return {"ok": all(x["ok"] for x in steps), "steps": steps, "maintenance": bool(b.get("on"))}


# ---------------------------------------------------------------- Master & Backup: stray stations back to the master
_return_task: Optional[asyncio.Task] = None


async def send_back(who: str, ip: str = "") -> Dict[str, Any]:
    """Backup: send the stations connected here back to the master. The FRN server here stops (the stations go to their
    backup address = the master), stays stopped for ``cluster.return_pause`` seconds and starts again in the background.
    While it is stopped, ``cluster.return_pending`` remembers to start it – also over a restart of the dashboard."""
    global _return_task
    st = ctx.server.state()
    clients = st["clients"]
    pause = int(ctx.settings.get("cluster.return_pause") or 20)
    base = {"ok": True, "stopped": False, "clients": clients, "pause": pause, "time": time.time(), "by": who}
    if _cluster_get("cluster.return_pending"):
        return {**base, "detail": "already sending back – the FRN server starts again shortly"}
    if _cluster_get("cluster.guard"):
        return {**base, "detail": "FRN server here locked (same FRN account as the master)"}
    if not _frn_running():
        return {**base, "detail": "FRN server here not running – no stations here"}
    if clients == 0:
        return {**base, "detail": "no stations here – nothing to send back"}
    ctx.n8._hold("frn-server.service", "stop")
    r = await ctx.java.control("stop")
    if r["rc"] != 0:
        return {**base, "ok": False, "detail": f"stopping the FRN server failed: {r['out'].strip()[:200]}"}
    start_at = time.time() + pause
    _cluster_set("cluster.return_pending", {"since": time.time(), "start_at": start_at, "by": who, "clients": clients})
    _cluster_set("cluster.last_return", {**base, "stopped": True})
    ctx.auth.audit("cluster_return", who, f"{clients} stations sent back to the master · pause {pause} s", ip)
    log.info("Master & Backup: %d Stationen zum Master geschickt (%s), FRN-Server startet in %d s", clients, who, pause)
    await ctx.server.poll_service()
    _return_task = asyncio.ensure_future(_return_restart(start_at))
    return {**base, "stopped": True, "detail": f"FRN server here stopped – starts again in {pause} s"}


async def _return_restart(start_at: float) -> None:
    """Start the FRN server of the backup again after the pause (also called at startup if it was interrupted)."""
    await asyncio.sleep(max(0.0, start_at - time.time()))
    try:
        if not _cluster_get("cluster.guard"):
            ctx.n8._hold("frn-server.service", "start")
            r = await ctx.java.control("start")
            if r["rc"] != 0:
                log.error("Master & Backup: FRN-Server startet nach dem Zurückschicken nicht: %s", r["out"].strip()[:200])
        ctx.restart_needed = False
    finally:
        ctx.db.x("DELETE FROM kv WHERE key='cluster.return_pending'")
        await ctx.server.poll_service()


async def _master_ready(hello: Dict[str, Any], need_since: float = 0) -> Optional[str]:
    """Why the stations should NOT go to the master now – or None."""
    if hello.get("ok") is False:
        return f"master not reachable: {hello.get('error', '')}"
    if hello.get("maintenance"):
        return "the master is in maintenance (handed over to the backup) – take it back there first"
    f = hello.get("frn") or {}
    if not f.get("running"):
        return "the FRN server on the master is not running – the stations would have nowhere to go"
    if need_since and f.get("since") and time.time() - float(f["since"]) < need_since:
        return "the FRN server on the master runs only for a short time"
    return None


@app.post("/api/admin/cluster/return")
async def cluster_return(request: Request):
    """🔁 Force the stations that are on the backup back to the master – from the master or from the backup."""
    u = need_admin(request)
    b = await body(request)
    s = ctx.settings.all()
    call = lambda path, timeout=30: asyncio.to_thread(cluster.call, s["cluster.peer_url"], path, s["cluster.key"],  # noqa: E731
                                                      "POST", {**_me(), "by": u["username"]}, timeout)
    if s["cluster.role"] == "master":
        if _cluster_get("cluster.maintenance"):
            raise HTTPError(409, "Maintenance is on – use “Take back from the backup”, that brings the stations back too.")
        if not _frn_running() and not b.get("force"):
            raise HTTPError(409, "The FRN server here (master) is not running – start it first, otherwise the stations have nowhere to go.")
        try:
            r = await call("/api/cluster/return", 30)
        except cluster.ClusterError as e:
            msg = str(e)
            if "does not know" in msg:
                msg = "The backup does not know this function yet – update it first (⬆️ Updates of both servers)."
            raise HTTPError(409, msg)
    elif s["cluster.role"] == "backup":
        if not b.get("force"):
            try:
                hello = await call("/api/cluster/hello", 10)
            except cluster.ClusterError as e:
                hello = {"ok": False, "error": str(e)}
            why = await _master_ready(hello)
            if why:
                raise HTTPError(409, why[0].upper() + why[1:] + ".")
        r = await send_back(u["username"], ip_of(request))
    else:
        raise HTTPError(400, "Set the role (Master or Backup) first.")
    _cluster_set("cluster.last_return", r)
    return r


async def cluster_auto_return() -> None:
    """Backup with “send stray stations back by themselves”: every 5 minutes, see whether stations are here although the
    master is fine – then send them back. Never while somebody transmits here or the master is in maintenance."""
    while True:
        await asyncio.sleep(300)
        try:
            s = ctx.settings.all()
            if not (s["cluster.role"] == "backup" and s["cluster.auto_return"] and s["cluster.peer_url"] and s["cluster.key"]):
                continue
            st = ctx.server.state()
            if not _frn_running() or st["clients"] == 0 or _on_air() or _cluster_get("cluster.return_pending"):
                continue
            try:
                hello = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/hello", s["cluster.key"], "POST", _me(), 10)
            except cluster.ClusterError:
                continue
            _remember_peer(hello)
            if await _master_ready(hello, need_since=600):
                continue
            _cluster_set("cluster.last_return", await send_back("auto"))
        except Exception:  # noqa: BLE001 – never stop the dashboard
            log.exception("cluster auto return")


# ---------------------------------------------------------------- Master & Backup: updates of both servers
def _commit_list(gh: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"short": c.get("short"), "message": c.get("message"), "date": c.get("date")} for c in (gh.get("commits") or [])[:8]]


async def update_summary(force: bool = False) -> Dict[str, Any]:
    """Short view of check_all_updates() for the box Master & Backup – the same for this server and the partner."""
    d = await check_all_updates(force)
    gh, java = d.get("github") or {}, d.get("java") or {}
    st = ctx.n8.update_state()
    loc, latest = gh.get("local") or {}, gh.get("latest") or {}
    ji, jl = java.get("installed") or {}, java.get("latest") or {}
    return {"ok": True, "role": ctx.settings.get("cluster.role"), "version": __version__, "checked": d.get("checked"),
            "title": ctx.settings.get("dashboard.title"),
            "dashboard": {"installed": loc.get("version") or __version__, "commit": loc.get("short", ""),
                          "latest": gh.get("remote_version") or latest.get("short", ""), "latest_commit": latest.get("short", ""),
                          "update": bool(gh.get("update")), "can": bool(gh.get("can_upgrade")), "behind": gh.get("behind", 0),
                          "commits": _commit_list(gh), "error": gh.get("error", ""), "hint": gh.get("hint", "")},
            "java": {"installed": jv_txt(ji), "latest": jv_txt(jl), "update": bool(java.get("update")), "error": java.get("error", "")},
            "running": bool(st.get("running") or st.get("pending")), "result": st.get("result"), "frn": _frn_state()}


async def update_run(who: str, ip: str = "") -> Dict[str, Any]:
    """Install what is new on this server: the Java FRN server (restarts it) and the dashboard (as root via
    scripts/n8-admin.sh update --auto: fast-forward, packages, permissions, restart, check, otherwise roll back).
    On the master a Java update moves the stations to the backup – they are sent back afterwards."""
    summ = await update_summary(True)
    steps: List[Dict[str, Any]] = []
    if summ["java"]["update"]:
        try:
            r = await ctx.java.install_update()
            steps.append({"step": "Java FRN server updated", "ok": bool(r.get("ok")), "detail": jv_txt(r.get("installed"))})
            ctx.auth.audit("upgrade_java", who, jv_txt(r.get("installed")), ip)
            s = ctx.settings.all()
            if s["cluster.role"] == "master" and s["cluster.peer_url"] and s["cluster.key"] and not _cluster_get("cluster.maintenance"):
                for _ in range(30):
                    await asyncio.sleep(1)
                    await ctx.server.poll_service()
                    if _frn_running():
                        break
                if _frn_running():
                    await asyncio.sleep(5)                 # let the stations land on the backup first
                    try:
                        b = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/return", s["cluster.key"],
                                                    "POST", {**_me(), "by": who}, 30)
                        steps.append({"step": "Backup sends the stations back", "ok": bool(b.get("ok")), "detail": b.get("detail", "")})
                    except cluster.ClusterError as e:
                        steps.append({"step": "Backup sends the stations back", "ok": False, "detail": str(e)})
        except Exception as e:  # noqa: BLE001
            log.exception("java update")
            steps.append({"step": "Java FRN server updated", "ok": False, "detail": str(e)[:200]})
    if summ["dashboard"]["update"]:
        if not summ["dashboard"]["can"]:
            steps.append({"step": "Dashboard update", "ok": False, "detail": summ["dashboard"]["hint"] or summ["dashboard"]["error"]
                          or "cannot be installed from the web interface"})
        else:
            ok, msg = ctx.n8.request_update()
            steps.append({"step": "Dashboard update started – the web interface restarts", "ok": ok, "detail": msg})
            if ok:
                ctx.auth.audit("upgrade_github", who, f"{summ['dashboard']['installed']} → {summ['dashboard']['latest']}", ip)
    if not steps:
        steps.append({"step": "Everything is up to date", "ok": True, "detail": ""})
    return {"ok": all(x["ok"] for x in steps), "steps": steps, "restarting": any("restarts" in x["step"] and x["ok"] for x in steps),
            "version": __version__, "commit": summ["dashboard"]["commit"], "time": time.time()}


def jv_txt(v: Optional[Dict[str, Any]]) -> str:
    return f"{v.get('version', '')} (build {v.get('build')})" if v and v.get("build") else (v or {}).get("version", "")


@app.post("/api/admin/cluster/update")
async def cluster_update(request: Request):
    """⬆️ Updates of both servers from the box Master & Backup: server = master | backup, action = status | check | run."""
    u = need_admin(request)
    b = await body(request)
    s = ctx.settings.all()
    which, action = str(b.get("server") or ""), str(b.get("action") or "status")
    if action not in ("status", "check", "run"):
        raise HTTPError(400, "Unknown action.")
    if s["cluster.role"] not in ("master", "backup"):
        raise HTTPError(400, "Set the role (Master or Backup) first.")
    if which not in ("master", "backup"):
        raise HTTPError(400, "Unknown server.")
    if which == s["cluster.role"]:
        res = await (update_run(u["username"], ip_of(request)) if action == "run" else update_summary(action == "check"))
        res["self"] = True
        return res
    try:
        res = await asyncio.to_thread(cluster.call, s["cluster.peer_url"], "/api/cluster/update", s["cluster.key"], "POST",
                                      {**_me(), "action": action, "by": u["username"]}, 240 if action == "run" else 60)
    except cluster.ClusterError as e:
        msg = str(e)
        if "does not know" in msg:
            msg = ("The partner does not know remote updates yet (older version) – update it once there "
                   "(System → Update) or on its console: sudo ./scripts/update.sh")
        return {"ok": False, "error": msg, "self": False}
    if action == "run":
        ctx.auth.audit("cluster_update", u["username"], f"{which}: " + "; ".join(x.get("step", "") for x in res.get("steps") or []), ip_of(request))
    res["self"] = False
    return res


@app.post("/api/admin/server/{action}")
async def server_control(action: str, request: Request):
    u = need_admin(request)
    if action not in ("start", "stop", "restart"):
        raise HTTPError(404, "Unknown action.")
    if action != "stop" and _cluster_get("cluster.guard"):
        raise HTTPError(409, "Locked: this backup uses the same FRN account as the master. Enter an own FRN account under "
                             "SystemManager first (📧 FRN password Backup).")
    ctx.n8._hold("frn-server.service", action)        # Keep-Alive: von Hand gestoppt bleibt gestoppt
    r = await ctx.java.control(action)
    if r["rc"] != 0:
        raise HTTPError(500, f"systemctl {action} frn-server: {r['out'].strip()[:300] or 'failed'}")
    if action != "stop":
        ctx.restart_needed = False
    ctx.auth.audit("frn_" + action, u["username"], "", ip_of(request))
    await asyncio.sleep(1.5)
    await ctx.server.poll_service()
    return {"ok": True, "server": ctx.server.state()}


@app.get("/api/admin/server/update")
async def server_update_check(request: Request):
    need_admin(request)
    return await ctx.java.check_update()


@app.post("/api/admin/server/update")
async def server_update(request: Request):
    u = need_admin(request)
    try:
        r = await ctx.java.install_update()
    except Exception as e:
        raise HTTPError(500, f"Update failed: {e}")
    ctx.auth.audit("frn_update", u["username"], str((r.get("installed") or {}).get("version")), ip_of(request))
    return r


@app.get("/api/admin/server/properties")
async def server_properties(request: Request):
    need_admin(request)
    ctx.java.write_config()
    return {"text": ctx.java.properties_text(), "path": str(FRN_HOME / "server.properties")}



# ---------------------------------------------------------------- updates and legacy configuration import
GITHUB_REPO = os.environ.get("FRNADN_GITHUB_REPO", updater.DEFAULT_REPO)
GITHUB_BRANCH = os.environ.get("FRNADN_GITHUB_BRANCH", "main")
_update_state: Dict[str, Any] = {"checked": None, "github": None, "java": None}

async def check_all_updates(force: bool = False) -> Dict[str, Any]:
    """Dashboard (GitHub) and Java FRN server. Results are cached for ten minutes unless forced."""
    if not force and _update_state["checked"] and time.time() - _update_state["checked"] < 600:
        return {**_update_state, "result": ctx.n8.update_state()["result"]}
    gh = dict(await asyncio.to_thread(updater.check, GITHUB_REPO, GITHUB_BRANCH, True))
    # installiert wird als root über scripts/n8-admin.sh („Update jetzt“ → update.request → frnadn-update.service)
    ready = ctx.n8.update_state()["ready"]
    gh["can_upgrade"] = bool(gh.get("update") and ready and not str(gh.get("hint", "")).startswith("This dashboard has its own commits"))
    if gh.get("hint", "").startswith("Run once as root") or (gh.get("update") and not ready):
        gh["hint"] = "" if ready else f"Run once as root: sudo {updater.ROOT}/scripts/n8-admin.sh fix-perms (sets up “Update now”, permissions and sudo)."
    java = await ctx.java.check_update()
    _update_state.update(checked=time.time(), github=gh, java=java)
    return {**_update_state, "result": ctx.n8.update_state()["result"]}

def parse_java_properties(raw: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    logical = ""
    for line in raw.splitlines():
        line = line.rstrip()
        if not logical and (not line.strip() or line.lstrip().startswith(("#", "!"))): continue
        logical += line.lstrip() if logical else line
        if logical.endswith("\\"):
            logical = logical[:-1]; continue
        m = re.match(r"^([^:=\s]+)\s*(?:[:=]|\s)\s*(.*)$", logical)
        if m: values[m.group(1)] = m.group(2).strip()
        logical = ""
    return values


LINKS_FILE = DATA / "branding" / "links.json"


def links_payload(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """`links` stays the plain item list (older clients); enabled, label and style are new."""
    links = []
    for item in cfg["items"]:
        row = dict(item)
        key = siteicons.key_for(row["url"]) if row.get("site_icon", True) else None
        if key:
            row["site_icon_url"] = f"/link-icons/{key}"
        links.append(row)
    return {**cfg, "links": links}


def partner_link() -> Optional[Dict[str, Any]]:
    """Master & Backup: der Partner steht über Kreuz automatisch als erster Eintrag im Link-Menü
    (auf dem Master „FRN Backup“, auf dem Backup „FRN Master“)."""
    s = ctx.settings.all()
    url = (s["cluster.peer_url"] or "").rstrip("/")
    if s["cluster.role"] not in ("master", "backup") or not url:
        return None
    label = "FRN Backup" if s["cluster.role"] == "master" else "FRN Master"
    return {"icon": "🔁", "label": label, "url": url + "/", "new_tab": True, "site_icon": True, "auto": "cluster"}


@app.get("/api/links")
async def public_links():
    cfg = linkstore.read(LINKS_FILE)
    p = partner_link()
    if p:
        cfg = {**cfg, "enabled": True, "items": [p] + [x for x in cfg["items"] if x.get("url", "").rstrip("/") != p["url"].rstrip("/")]}
    return links_payload(cfg)


@app.get("/api/admin/links")
async def admin_get_links(request: Request):
    need_admin(request)
    return links_payload(linkstore.read(LINKS_FILE))


@app.post("/api/admin/links")
async def admin_save_links(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        cfg = linkstore.normalize(b if "items" in b or "style" in b or "enabled" in b else b.get("links"))
    except ValueError as e:
        raise HTTPError(400, str(e))
    linkstore.write(LINKS_FILE, cfg)
    await asyncio.to_thread(siteicons.refresh_many, ctx.db,
                            [x["url"] for x in cfg["items"] if x.get("site_icon", True)],
                            bool(b.get("refresh_icons")))
    ctx.auth.audit("links_changed", u["username"], f"{len(cfg['items'])} dashboard links saved ({cfg['style']})", ip_of(request))
    return {"ok": True, **links_payload(cfg)}


@app.get("/api/branding")
async def public_branding():
    return {"theme": brandstore.read_theme(ctx.db), "palettes": brandstore.PALETTES}


@app.get("/branding/logo")
async def branding_logo():
    p = DATA / "branding" / "logo.png"
    return FileResponse(p, media_type="image/png") if p.exists() else FileResponse(STATIC / "adn-icon.svg", media_type="image/svg+xml")


@app.get("/branding/site-icon")
async def branding_site_icon():
    folder = DATA / "branding"
    png, ico = folder / "site-icon.png", folder / "site-icon.ico"
    if png.exists():
        return FileResponse(png, media_type="image/png", headers={"Cache-Control": "no-cache"})
    if ico.exists():
        return FileResponse(ico, media_type="image/x-icon", headers={"Cache-Control": "no-cache"})
    return FileResponse(STATIC / "adn-icon.svg", media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})


@app.post("/api/admin/branding")
async def save_branding(request: Request):
    u = need_admin(request)
    import base64
    b = await body(request)
    folder = DATA / "branding"
    folder.mkdir(parents=True, exist_ok=True)

    def remove(path: Path) -> None:
        try: path.unlink()
        except FileNotFoundError: pass

    def decode_upload(encoded: Any, asset: str) -> Optional[tuple[str, bytes]]:
        if not encoded:
            return None
        try:
            raw = base64.b64decode(str(encoded).split(",", 1)[-1], validate=True)
        except Exception:
            raise HTTPError(400, f"Invalid {asset} upload.")
        if len(raw) > 2_000_000:
            raise HTTPError(400, f"{asset.capitalize()} must be no larger than 2 MB.")
        if asset == "logo" and raw.startswith(bytes.fromhex("89504e470d0a1a0a")):
            name = "logo.png"
        elif asset == "site icon" and raw.startswith(bytes.fromhex("89504e470d0a1a0a")):
            name = "site-icon.png"
        elif asset == "site icon" and raw.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")):
            name = "site-icon.ico"
        else:
            allowed = "PNG" if asset == "logo" else "PNG or ICO"
            raise HTTPError(400, f"Please upload a {allowed} {asset} up to 2 MB.")
        return name, raw

    def save_upload(decoded: Optional[tuple[str, bytes]], asset: str) -> Optional[Path]:
        if not decoded:
            return None
        name, raw = decoded
        path = folder / name
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)
        if asset == "site icon":
            remove(folder / ("site-icon.ico" if name.endswith(".png") else "site-icon.png"))
        return path

    try:
        theme = brandstore.normalize_theme(b.get("theme", brandstore.read_theme(ctx.db)))
    except ValueError as e:
        raise HTTPError(400, str(e))
    # Validate both uploads before replacing either existing asset.
    logo_data = decode_upload(b.get("logo"), "logo")
    site_icon_data = decode_upload(b.get("site_icon"), "site icon")
    logo = save_upload(logo_data, "logo")
    site_icon = save_upload(site_icon_data, "site icon")
    if b.get("reset_logo"):
        remove(folder / "logo.png")
        logo = folder / "logo.png"
    if b.get("reset_site_icon"):
        remove(folder / "site-icon.png")
        remove(folder / "site-icon.ico")
        site_icon = folder / "site-icon.png"
    ctx.db.kv_set("branding-theme", json.dumps(theme))
    ctx.auth.audit("branding_changed", u["username"], "theme, logo or site icon updated", ip_of(request))
    return {"ok": True, "theme": theme, "logo_updated": logo.stat().st_mtime if logo and logo.exists() else None,
            "site_icon_updated": site_icon.stat().st_mtime if site_icon and site_icon.exists() else None}


# ---------------------------------------------------------------- client software avatars
@app.get("/api/client-logos")
async def client_logos_list():
    """Kinds of client software and which of them have an own image (key -> version)."""
    own = {r["key"]: int(r["updated_at"]) for r in ctx.db.q("SELECT key, updated_at FROM client_logos")}
    return {"kinds": [{"key": k, "label": clientsw.LABELS[k], "own": own.get(k)} for k in clientsw.KEYS]}


@app.get("/client-logos/{key}")
async def client_logo(key: str):
    if key not in clientsw.KEYS:
        raise HTTPError(404, "Unknown client software.")
    rows = ctx.db.q("SELECT content_type, data FROM client_logos WHERE key=?", (key,))
    if not rows:
        raise HTTPError(404, "No own image.")
    return Response(bytes(rows[0]["data"]), media_type=rows[0]["content_type"], headers={
        "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})


@app.post("/api/admin/client-logos/{key}")
async def client_logo_upload(key: str, request: Request):
    u = need_admin(request)
    if key not in clientsw.KEYS:
        raise HTTPError(404, "Unknown client software.")
    b = await body(request)
    try:
        raw = base64.b64decode(str(b.get("data") or "").split(",", 1)[-1], validate=True)
    except Exception:
        raise HTTPError(400, "Invalid image.")
    if not raw or len(raw) > 512 * 1024:
        raise HTTPError(400, "The image must be smaller than 512 KB.")
    ctype = siteicons._image_type(raw)          # PNG, ICO, GIF, JPEG, WebP or a harmless SVG
    if not ctype:
        raise HTTPError(400, "Please upload PNG, JPEG, WebP, GIF, ICO or a plain SVG.")
    ctx.db.x("INSERT INTO client_logos (key, content_type, data, updated_at, updated_by) VALUES (?,?,?,?,?) "
             "ON CONFLICT(key) DO UPDATE SET content_type=excluded.content_type, data=excluded.data, "
             "updated_at=excluded.updated_at, updated_by=excluded.updated_by", (key, ctype, raw, time.time(), u["username"]))
    ctx.auth.audit("client_logo", u["username"], f"own image for {key}", ip_of(request))
    await push({"type": "client_logos"})
    return {"ok": True}


@app.delete("/api/admin/client-logos/{key}")
async def client_logo_delete(key: str, request: Request):
    u = need_admin(request)
    ctx.db.x("DELETE FROM client_logos WHERE key=?", (key,))
    ctx.auth.audit("client_logo", u["username"], f"image for {key} removed", ip_of(request))
    await push({"type": "client_logos"})
    return {"ok": True}


@app.get("/link-icons/{key}")
async def cached_link_icon(key: str):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise HTTPError(404, "Site icon not found.")
    icon = siteicons.cached_icon(ctx.db, key)
    if not icon:
        # The public menu can request the image before the startup warm-up finishes.
        # Resolve the key only against configured links, fill the SQLite cache, then serve it.
        cfg = linkstore.read(LINKS_FILE)
        url = next((item["url"] for item in cfg["items"]
                    if item.get("site_icon", True) and siteicons.key_for(item["url"]) == key), None)
        if url:
            await asyncio.to_thread(siteicons.refresh_one, ctx.db, url)
            icon = siteicons.cached_icon(ctx.db, key)
    if not icon:
        raise HTTPError(404, "Site icon not found.")
    return Response(icon["data"], media_type=icon["content_type"], headers={"Cache-Control": "no-cache"})


@app.get("/api/admin/updates")
async def updates_check(request: Request):
    need_admin(request)
    return await check_all_updates()

@app.post("/api/admin/updates/check")
async def updates_force_check(request: Request):
    need_admin(request)
    return await check_all_updates(True)

@app.post("/api/admin/updates/upgrade")
async def updates_upgrade(request: Request):
    u = need_admin(request)
    b = await body(request)
    target = str(b.get("target", "java"))
    if target == "java":
        try:
            result = await ctx.java.install_update()
        except Exception as e:
            log.exception("java update")
            raise HTTPError(500, f"Java-Update fehlgeschlagen: {e}")
    elif target == "github":
        # als root über scripts/n8-admin.sh update --auto: vorspulen, Pakete, Rechte, Neustart, Prüfung, sonst Rückfall
        if not (_update_state.get("github") or {}).get("update"):
            raise HTTPError(400, "Bitte zuerst nach Updates suchen.")
        ok, msg = ctx.n8.request_update()
        if not ok:
            raise HTTPError(400, msg)
        result = {"changed": True, "requested": True, "restarting": True, "message": msg}
    else:
        raise HTTPError(400, "Unknown update target.")
    ctx.auth.audit("upgrade_" + target, u["username"], str({k: v for k, v in result.items() if k not in ("files", "pip")}), ip_of(request))
    return result

@app.post("/api/admin/server/properties/import")
async def import_server_properties(request: Request):
    u = need_admin(request)
    b = await body(request)
    raw = str(b.get("text", ""))
    if not raw.strip() or len(raw) > 1_000_000: raise HTTPError(400, "Please upload a valid server.properties file (max. 1 MB).")
    parsed = parse_java_properties(raw)
    mapping = {"server_addr":"frn.address", "server_port":"frn.port", "sysman_server_addr":"sysman.host",
               "sysman_auth_emailaddr":"sysman.email", "sysman_auth_password":"sysman.password",
               "server_owner":"frn.owner_email", "website":"frn.website", "client_sotimeout":"frn.client_timeout",
               "client_txtimeout":"frn.tx_timeout", "default_net":"frn.default_room",
               "standalone":"frn.standalone", "allowLANAddr":"frn.allow_lan",
               "backup_server_addr":"frn.backup_host", "backup_server_port":"frn.backup_port",
               "voip_skip_muted_crosslink_clients":"frn.skip_muted_crosslink",
               "voip_skip_muted_gateway_clients":"frn.skip_muted_gateway",
               "voip_skip_muted_pconly_clients":"frn.skip_muted_pconly"}
    changes = {}
    known = {field["key"]: field for section in ctx.settings.describe() for field in section["fields"]}
    for prop, key in mapping.items():
        if prop in parsed and key in known:
            val: Any = parsed[prop]
            if known[key].get("kind") == "bool": val = val.lower() in ("yes", "true", "1", "on")
            elif known[key].get("kind") in ("int", "ports"):
                try: val = int(val)
                except ValueError: raise HTTPError(400, f"Invalid number for {prop}.")
            changes[key] = val
    has_room_definitions = any(re.fullmatch(r"net\d{2}", key) and value.strip() for key, value in parsed.items())
    if not changes and not has_room_definitions:
        raise HTTPError(400, "No supported FRN settings or room definitions were found in this file.")
    backup = FRN_HOME / ("server.properties.import-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    FRN_HOME.mkdir(parents=True, exist_ok=True)
    current = FRN_HOME / "server.properties"
    if current.exists(): shutil.copy2(current, backup)
    ctx.settings.update(changes, u["username"])
    imported_rooms = []
    suffixes = {"_enable":"enabled", "_owner":"owners", "_show_infomessage":"show_info", "_tot":"tot",
                "_speechpause":"speechpause", "_speechpause_msg":"speechpause_msg", "_parrot_enable":"parrot",
                "_parrot_startstop_enable":"parrot_startstop", "_unmute":"unmute_min", "_acl_cl":"acl_cl",
                "_acl_gw":"acl_gw", "_acl_info":"acl_info", "_bl_regexp":"bl_regexp", "_bl_info":"bl_info",
                "_tgbot_params":"tg_params"}
    for key, room_name in parsed.items():
        match = re.fullmatch(r"net(\d{2})", key)
        if not match or not room_name.strip(): continue
        idx = int(match.group(1))
        room = ctx.store.room_by_name(room_name.strip())
        if room is None:
            if idx in {r["idx"] for r in ctx.store.rooms() if r["idx"] is not None}:
                continue
            rid = ctx.store.room_create(room_name.strip())
            ctx.db.x("UPDATE rooms SET idx=? WHERE id=?", (idx, rid))
            ctx.store.invalidate()
            room = ctx.store.room_by_name(room_name.strip()) or {"id": rid}
        values = {}
        for suffix, column in suffixes.items():
            prop = key + suffix
            if prop not in parsed: continue
            value = parsed[prop]
            if column in ("enabled", "parrot", "parrot_startstop"): value = 1 if value.lower() in ("yes", "true", "1", "on") else 0
            elif column in ("tot", "speechpause", "unmute_min"):
                try: value = int(value)
                except ValueError: continue
            elif column == "show_info": value = "always" if value.lower() == "always" else "acl"
            values[column] = value
        if values: ctx.store.room_update(room["id"], values)
        imported_rooms.append(room_name.strip())
    ctx.store.invalidate()
    ctx.java.write_config()
    ctx.restart_needed = True
    ctx.auth.audit("properties_import", u["username"], f"{len(changes)} settings; {len(imported_rooms)} rooms; backup={backup if current.exists() else 'none'}", ip_of(request))
    return {"ok": True, "imported": list(changes), "rooms": imported_rooms, "ignored": [k for k in parsed if k not in mapping and not re.fullmatch(r"net\d{2}(?:_[A-Za-z0-9_]+)?", k)], "backup": str(backup) if backup.exists() else None,
            "restart_needed": True}

# ---------------------------------------------------------------- admin: rooms
def _room_values(b: Dict[str, Any]) -> Dict[str, Any]:
    v: Dict[str, Any] = {}
    for k in ROOM_COLUMNS:
        if k not in b:
            continue
        x = b[k]
        if k in ("enabled", "hidden", "parrot", "parrot_startstop"):
            v[k] = 1 if x in (True, 1, "1", "true", "on") else 0
        elif k in ("tot", "speechpause", "unmute_min"):
            try:
                v[k] = max(0, int(x or 0))
            except (TypeError, ValueError):
                raise HTTPError(400, f"{k}: please enter a whole number.")
        elif k == "show_info":
            v[k] = "always" if x == "always" else "acl"
        elif k == "name":
            name = str(x or "").strip()
            if not NAME_RE.fullmatch(name):
                raise HTTPError(400, "Room name: 1–40 characters, no comma and no < >.")
            v[k] = name
        elif k == "bl_regexp":
            try:
                re.compile(str(x or ""))
            except re.error as e:
                raise HTTPError(400, f"Pattern: {e}")
            v[k] = str(x or "")
        elif k == "tg_params":
            t = str(x or "").strip()
            if t and not re.fullmatch(r"\d+;\d+;[^;\s]+;-?\d+", t):
                raise HTTPError(400, "Telegram: min. transmission ms;min. idle ms;bot token;channel ID")
            v[k] = t
        elif k in ("owners", "acl_cl", "acl_gw"):
            items = [e.strip().lower() for e in str(x or "").split(",") if e.strip()]
            for e in items:
                if e != "none" and not EMAIL_RE.fullmatch(e):
                    raise HTTPError(400, f"'{e}' is not an e-mail address.")
            v[k] = ",".join(items)
        else:
            v[k] = str(x or "").replace("\n", " ").replace("\r", " ")[:2000]
    return v


def rooms_payload() -> List[Dict[str, Any]]:
    out = []
    for r in ctx.store.rooms():
        live = ctx.server.rooms.get(r["name"])
        out.append({**r, "online": sum(1 for c in live.clients if not c.is_parrot) if live else 0})
    return out


async def after_rooms(u, request: Request, what: str) -> Dict[str, Any]:
    ctx.store.invalidate()
    ctx.server.reload_rooms()
    ctx.auth.audit("rooms", u["username"], what, ip_of(request))
    config_changed(u, request, what)
    await push({"type": "rooms"})
    return {"ok": True, "rooms": rooms_payload(), "restart_needed": ctx.restart_needed}


@app.get("/api/admin/rooms")
async def rooms_get(request: Request):
    need_admin(request)
    return {"rooms": rooms_payload(), "default_room": ctx.settings.get("frn.default_room"), "restart_needed": ctx.restart_needed}


@app.post("/api/admin/rooms")
async def rooms_create(request: Request):
    u = need_admin(request)
    b = await body(request)
    v = _room_values({"name": b.get("name")})
    if any(r["name"].lower() == v["name"].lower() for r in ctx.store.rooms()):
        raise HTTPError(400, f"Room {v['name']} already exists.")
    if ctx.store.free_index() is None:
        raise HTTPError(400, f"The FRN server has at most {MAX_ROOMS} rooms.")
    extra = {}
    tpl = next((r for r in ctx.store.rooms() if r["id"] == b.get("template")), None)
    if tpl:
        extra = {k: tpl[k] for k in ROOM_COLUMNS if k != "name"}
    rid = ctx.store.room_create(v["name"], None, extra)
    out = await after_rooms(u, request, f"room created: {v['name']}")
    out["id"] = rid
    return out


@app.patch("/api/admin/rooms/{rid}")
async def rooms_update(rid: int, request: Request):
    u = need_admin(request)
    b = await body(request)
    row = next((r for r in ctx.store.rooms() if r["id"] == rid), None)
    if not row:
        raise HTTPError(404, "Unknown room.")
    v = _room_values(b.get("values") or {})
    if "name" in v and v["name"].lower() != row["name"].lower() and any(r["name"].lower() == v["name"].lower() for r in ctx.store.rooms()):
        raise HTTPError(400, f"Room {v['name']} already exists.")
    if row["idx"] == 0:
        v["parrot"] = 1                      # net00 is always the test/parrot room
    ctx.store.room_update(rid, v)
    if "name" in v and ctx.settings.get("frn.default_room") == row["name"]:
        ctx.settings.update({"frn.default_room": v["name"]}, u["username"])
    return await after_rooms(u, request, f"room {row['name']}: " + ", ".join(v))


@app.delete("/api/admin/rooms/{rid}")
async def rooms_delete(rid: int, request: Request):
    u = need_admin(request)
    rows = ctx.store.rooms()
    row = next((r for r in rows if r["id"] == rid), None)
    if not row:
        raise HTTPError(404, "Unknown room.")
    if row["idx"] == 0:
        raise HTTPError(400, "net00 is the test/parrot room of the FRN server; it can be renamed or closed, not deleted.")
    if len(rows) <= 2:
        raise HTTPError(400, "The last room cannot be deleted.")
    ctx.store.room_delete(rid)
    if ctx.settings.get("frn.default_room") == row["name"]:
        ctx.settings.update({"frn.default_room": next(r["name"] for r in rows if r["id"] != rid and r["idx"] != 0)}, u["username"])
    return await after_rooms(u, request, f"room deleted: {row['name']}")


@app.post("/api/admin/rooms/order")
async def rooms_order(request: Request):
    u = need_admin(request)
    b = await body(request)
    ids = [int(x) for x in b.get("ids") or []]
    if sorted(ids) != sorted(r["id"] for r in ctx.store.rooms()):
        raise HTTPError(400, "Invalid order.")
    ctx.store.room_order(ids)
    ctx.auth.audit("rooms", u["username"], "room order", ip_of(request))
    ctx.server.reload_rooms()
    await push({"type": "rooms"})
    return {"ok": True, "rooms": rooms_payload()}


# ---------------------------------------------------------------- admin: lists (kept by the server) and accounts
@app.get("/api/admin/acl")
async def acl_get(request: Request):
    need_admin(request)
    payload = ctx.acls.payload()
    clients = {}
    for room in (ctx.server.rooms or {}).values():
        for client in room.clients:
            if client.is_parrot:
                continue
            key = (client.cid or client.on, client.email)
            clients[key] = {"id": key[0], "email": client.email, "callsign": client.callsign, "name": client.name,
                            "client_type": str(client.client), "band_channel": client.band, "country": client.country, "city": client.city}
    payload["clients"] = sorted(clients.values(), key=lambda c: (c["callsign"].lower(), c["email"].lower()))
    return payload


@app.post("/api/admin/acl")
async def acl_save(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        result = ctx.acls.save(u["username"], b)
    except (ValueError, KeyError) as e:
        raise HTTPError(400, str(e))
    ctx.restart_needed = True
    ctx.auth.audit("acl", u["username"], f"{b.get('action', '')} {b.get('kind', '')}", ip_of(request))
    return {**result, "restart_needed": ctx.restart_needed}


@app.get("/api/admin/accounts")
async def accounts_get(request: Request):
    need_admin(request)
    return {"accounts": ctx.store.accounts(), "standalone": ctx.settings.get("frn.standalone"),
            "enabled": ctx.settings.get("frn.passwd_list")}


@app.post("/api/admin/accounts")
async def accounts_save(request: Request):
    u = need_admin(request)
    b = await body(request)
    email = str(b.get("email", "")).strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise HTTPError(400, "Please enter an e-mail address.")
    pw = str(b.get("password") or "")
    exists = ctx.store.account_get(email)
    if (not exists or pw) and not re.fullmatch(r"[^\s<>&]{4,64}", pw):
        raise HTTPError(400, "FRN password: 4–64 characters, no spaces and no < > &.")
    ctx.store.account_save(email, str(b.get("callsign", ""))[:20], str(b.get("name", ""))[:60], pw or None, bool(b.get("disabled")))
    ctx.auth.audit("frn_account", u["username"], ("changed " if exists else "created ") + email, ip_of(request))
    config_changed(u, request, f"FRN account {email}")
    return {"ok": True, "accounts": ctx.store.accounts(), "restart_needed": ctx.restart_needed}


@app.delete("/api/admin/accounts/{email}")
async def accounts_delete(email: str, request: Request):
    u = need_admin(request)
    ctx.store.account_delete(email)
    ctx.auth.audit("frn_account", u["username"], f"deleted {email}", ip_of(request))
    config_changed(u, request, f"FRN account {email} deleted")
    return {"ok": True, "accounts": ctx.store.accounts(), "restart_needed": ctx.restart_needed}


# ---------------------------------------------------------------- admin: users & sessions
@app.get("/api/admin/users")
async def users(request: Request):
    need_admin(request)
    return {"users": ctx.auth.users()}


@app.post("/api/admin/users")
async def create_user(request: Request):
    u = need_admin(request)
    b = await body(request)
    return {"user": ctx.auth.create(u, str(b.get("username", "")), str(b.get("password", "")), str(b.get("role", "user")),
                                    str(b.get("display_name", "")), ip_of(request))}


@app.patch("/api/admin/users/{uid}")
async def update_user(uid: int, request: Request):
    u = need_admin(request)
    b = await body(request)
    allowed = {k: b[k] for k in ("username", "display_name", "role", "disabled", "password") if k in b}
    return {"user": ctx.auth.update(u, uid, allowed, ip_of(request))}


@app.delete("/api/admin/users/{uid}")
async def delete_user(uid: int, request: Request):
    u = need_admin(request)
    ctx.auth.delete(u, uid, ip_of(request))
    return {"ok": True}


@app.get("/api/admin/sessions")
async def sessions(request: Request):
    need_admin(request)
    return {"sessions": ctx.auth.sessions()}


@app.delete("/api/admin/sessions/{sid}")
async def revoke(sid: str, request: Request):
    u = need_admin(request)
    ctx.auth.revoke(sid)
    ctx.auth.audit("session_revoked", u["username"], sid, ip_of(request))
    return {"ok": True}


@app.get("/api/admin/audit")
async def audit(request: Request):
    need_admin(request)
    return {"entries": ctx.auth.audit_log()}


# ---------------------------------------------------------------- admin: system & logs
@app.get("/api/admin/system")
async def system(request: Request):
    need_admin(request)
    counts = {t: ctx.db.q(f"SELECT COUNT(*) AS n FROM {t}")[0]["n"]
              for t in ("talks", "visits", "stations", "chat", "talk_daily", "rooms", "frn_accounts")}
    first = ctx.db.q("SELECT MIN(ts) AS t FROM talks")[0]["t"]
    db_size = sum(p.stat().st_size for p in DATA.glob("frnadn.db*") if p.exists())
    return {"info": ctx.system.info(), "server": ctx.server.state(), "app_version": __version__, "demo": DEMO,
            "jar": ctx.java.jar_version(), "jar_path": str(FRN_JAR), "frn_home": str(FRN_HOME),
            "counts": counts, "since": first, "db_size": db_size, "data_dir": str(DATA), "online": ctx.live.online(),
            "cache": {"hits": ctx.stats.hits, "misses": ctx.stats.misses}, "sockets": len(ctx.sockets),
            "uptime": time.time() - ctx.system.started, "restart_needed": ctx.restart_needed}


# ---------------------------------------------------------------- backup & restore (superadmin, never with an API token)
def need_superadmin(request: Request) -> Dict[str, Any]:
    u = need_human_admin(request)
    if u["role"] != "superadmin":
        raise HTTPError(403, "Backups contain all access data – superadmin only.")
    return u


BACKUPS = DATA / "backups"
UPLOAD = DATA / "restore-upload.frnbak"
_BK_NAME = re.compile(r"^frn-backup-[A-Za-z0-9._-]+-\d{8}-\d{6}\.frnbak$")


@app.get("/api/admin/backups")
async def backups_list(request: Request):
    need_superadmin(request)
    try:
        last = json.loads((DATA / fbackup.DONE).read_text())
    except (OSError, ValueError):
        last = None
    return {"backups": fbackup.listing(BACKUPS), "last_restore": last, "min_password": fbackup.MIN_PASSWORD,
            "uploaded": UPLOAD.is_file(), "keep": fbackup.KEEP}


@app.post("/api/admin/backups")
async def backups_create(request: Request):
    u = need_superadmin(request)
    b = await body(request)
    try:
        p = await asyncio.to_thread(fbackup.create, DATA, FRN_HOME, str(b.get("password") or ""), u["username"])
    except fbackup.BackupError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("backup_created", u["username"], p.name, ip_of(request))
    return {"name": p.name, "size": p.stat().st_size}


@app.get("/api/admin/backups/{name}")
async def backups_download(name: str, request: Request):
    u = need_superadmin(request)
    p = BACKUPS / name
    if not _BK_NAME.match(name) or not p.is_file():
        raise HTTPError(404, "Backup not found.")
    ctx.auth.audit("backup_downloaded", u["username"], name, ip_of(request))
    return FileResponse(p, media_type="application/octet-stream", filename=name, headers={"Cache-Control": "no-store"})


@app.delete("/api/admin/backups/{name}")
async def backups_delete(name: str, request: Request):
    u = need_superadmin(request)
    p = BACKUPS / name
    if not _BK_NAME.match(name) or not p.is_file():
        raise HTTPError(404, "Backup not found.")
    p.unlink()
    ctx.auth.audit("backup_deleted", u["username"], name, ip_of(request))
    return {"ok": True}


@app.post("/api/admin/restore/upload")
async def restore_upload(request: Request):
    need_superadmin(request)
    size = 0
    tmp = UPLOAD.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        os.chmod(tmp, 0o600)
        async for chunk in request.stream():
            size += len(chunk)
            if size > fbackup.MAX_BYTES:
                f.close()
                tmp.unlink(missing_ok=True)
                raise HTTPError(413, "The file is too large.")
            f.write(chunk)
    with open(tmp, "rb") as f:
        if f.read(7) != fbackup.n8mig.MAGIC:
            tmp.unlink(missing_ok=True)
            raise HTTPError(400, "This is not a backup of adn-frn-server (.frnbak).")
    tmp.replace(UPLOAD)
    return {"ok": True, "size": size}


async def _open_upload(password: str, dest) -> Dict[str, Any]:
    if not UPLOAD.is_file():
        raise HTTPError(400, "Please upload the backup file first.")
    try:
        return await asyncio.to_thread(fbackup.open_backup, UPLOAD, password, dest)
    except fbackup.BackupError as e:
        await asyncio.sleep(1)
        raise HTTPError(400, str(e))


@app.post("/api/admin/restore/check")
async def restore_check(request: Request):
    need_superadmin(request)
    b = await body(request)
    tmp = DATA / "restore-check.tar"
    try:
        manifest = await _open_upload(str(b.get("password") or ""), tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return {"manifest": manifest}


@app.post("/api/admin/restore")
async def restore_apply(request: Request):
    u = need_superadmin(request)
    b = await body(request)
    if b.get("confirmation") != "RESTORE":
        raise HTTPError(400, "Please type RESTORE to confirm.")
    manifest = await _open_upload(str(b.get("password") or ""), DATA / fbackup.PENDING)
    UPLOAD.unlink(missing_ok=True)
    ctx.auth.audit("backup_restore", u["username"], f"{manifest.get('host')} · {manifest.get('version')}", ip_of(request))
    asyncio.get_running_loop().call_later(1.0, os._exit, 3)     # systemd starts us again; the start applies the backup
    return {"ok": True, "manifest": manifest, "relogin": True}


@app.post("/api/admin/restart")
async def restart_app(request: Request):
    """Restart the whole program; systemd starts it again (Restart=always)."""
    u = need_admin(request)
    ctx.auth.audit("app_restart", u["username"], "", ip_of(request))
    from .n8_crash import mark_planned
    mark_planned(str(DATA), "frnadn.service", "Neustart aus dem Adminbereich")   # kein „Absturz“ im Absturz-Wächter
    asyncio.get_running_loop().call_later(0.5, os._exit, 3)
    return {"ok": True}


# ---------------------------------------------------------------- 🌐 Netz, Ports & Domains (N8 Kit 1.4, Vorbild N8 Crosslink)
# HTTPS, Domain und die Web-Ports stehen NUR hier (nicht mehr unter Einstellungen).
_PORT_GROUPS = [
    ("🌐 Webinterface", "Dashboard und Live-Daten. HTTP- und HTTPS-Port gelten nur mit HTTPS (Let's Encrypt prüft immer auf Port 80).", [
        ("web.port", "Web-Port", "in", "TCP", "steht im systemd-Dienst (FRNADN_PORT) – mit HTTPS ist das Dashboard unter dem HTTPS-Port erreichbar"),
        ("https.http_port", "HTTP-Port", "in", "TCP", "Let's-Encrypt-Prüfung und Weiterleitung auf HTTPS"),
        ("https.port", "HTTPS-Port", "in", "TCP", "https:// der Domain (Standard 443)")]),
    ("📻 FRN-Server (Java)", "Hier verbinden sich die FRN-Clients; gilt nach einem Neustart des FRN-Servers.", [
        ("frn.port", "FRN-Port", "in", "TCP", "server_port in server.properties (Standard 10024)"),
        ("frn.backup_port", "Port des Ausweichservers", "out", "TCP", "wird den Clients mitgeteilt · 0 = keiner"),
        ("sysman.port", "SystemManager", "out", "TCP", "Anmeldung des Servers beim SystemManager (Standard 10025)")]),
]


def _web_port() -> int:
    return int(os.environ.get("FRNADN_PORT", "8080") or 8080)


@app.get("/api/admin/ports")
async def admin_ports(request: Request):
    need_admin(request)
    vals = ctx.settings.all()
    groups = []
    for title, help_, rows in _PORT_GROUPS:
        out = []
        for k, lab, d, pr, h in rows:
            if k == "web.port":
                out.append({"key": k, "label": lab, "dir": d, "proto": pr, "help": h, "value": _web_port(), "readonly": True})
            elif k == "sysman.port":
                out.append({"key": k, "label": lab, "dir": d, "proto": pr, "help": h, "value": 10025, "readonly": True})
            elif k in vals:
                out.append({"key": k, "label": lab, "dir": d, "proto": pr, "help": h, "value": vals[k], "min": 0 if k == "frn.backup_port" else 1})
        groups.append({"title": title, "help": help_, "rows": out})
    if vals.get("mail.enabled"):
        groups.append({"title": "✉️ E-Mail (N8 Mail)", "help": "Nur verschlüsselt: IMAP und SMTP für Mailprogramme nur mit TLS, Port 25 mit STARTTLS.",
                       "rows": [{"key": "mail.25", "label": "SMTP (MX)", "dir": "in", "proto": "TCP", "help": "Mail aus dem Internet (STARTTLS)", "value": 25, "readonly": True},
                                {"key": "mail.465", "label": "SMTPS", "dir": "in", "proto": "TCP", "help": "Senden aus Mailprogrammen, TLS von Anfang an", "value": 465, "readonly": True},
                                {"key": "mail.587", "label": "Submission", "dir": "in", "proto": "TCP", "help": "Senden aus Mailprogrammen, STARTTLS Pflicht", "value": 587, "readonly": True},
                                {"key": "mail.993", "label": "IMAPS", "dir": "in", "proto": "TCP", "help": "Lesen in Mailprogrammen (TLS)", "value": 993, "readonly": True},
                                {"key": "mail.up", "label": "Upstream", "dir": "out", "proto": "TCP",
                                 "help": vals.get("mail.relay_host") or "direkt zustellen (ausgehend Port 25)",
                                 "value": vals.get("mail.relay_port") if vals.get("mail.relay_host") else 25, "readonly": True}]})
    note = "Gespeichert, aber noch nicht aktiv – Dashboard bzw. FRN-Server neu starten." if (ctx.dashboard_restart_needed or ctx.restart_needed) else ""
    return {"intro": "Alle Ports des ADN-FRN-Servers an einer Stelle. Eingehend: in Firewall und Router freigeben, wenn das von außen "
                     "erreichbar sein soll. Ausgehend: die Gegenstelle muss erreichbar sein.",
            "groups": groups, "note": note, "restart": {"button": "Dashboard neu starten", "url": "/api/admin/restart"}}


async def _save(request: Request, changes: Dict[str, Any]) -> List[str]:
    u = need_admin(request)
    try:
        changed = ctx.settings.update(changes, u["username"])
    except Exception as e:  # SettingsError
        raise HTTPError(400, str(e))
    keys = [f.key for f in changed]
    if any(k.startswith("https.") for k in keys):
        ctx.dashboard_restart_needed = True
    if keys:
        ctx.auth.audit("settings_changed", u["username"], ", ".join(keys), ip_of(request))
        if any(k.startswith(("frn.", "sysman.")) for k in keys):
            config_changed(u, request, "settings " + ", ".join(keys))
    return keys


@app.post("/api/admin/ports")
async def admin_ports_save(request: Request):
    b = await body(request)
    vals = b.get("values") or {}
    allowed = {"https.http_port", "https.port", "frn.port", "frn.backup_port"}
    cur = ctx.settings.all()
    keys = await _save(request, {k: v for k, v in vals.items() if k in allowed and v != cur.get(k)})
    msg = "Nichts geändert." if not keys else "Gespeichert: " + ", ".join(keys) + "." + \
        (" Der FRN-Server braucht einen Neustart." if any(k.startswith("frn.") for k in keys) else "") + \
        (" Das Dashboard braucht einen Neustart." if any(k.startswith("https.") for k in keys) else "")
    return {"ok": True, "message": msg, "changed": keys}


def _cert_info() -> Optional[Dict[str, Any]]:
    if _tls_manager is None or not _tls_manager.have_cert():
        return None
    try:
        import ssl as _ssl
        from datetime import datetime as _dt
        c = _ssl._ssl._test_decode_cert(str(_tls_manager.cert_file))
        exp = _dt.strptime(c.get("notAfter", ""), "%b %d %H:%M:%S %Y %Z")
        issuer = " ".join(v for part in c.get("issuer", ()) for k, v in part if k in ("organizationName", "commonName"))
        return {"days": (exp - _dt.utcnow()).days, "expires": exp.strftime("%d.%m.%Y"), "issuer": issuer, "staging": "STAGING" in issuer.upper()}
    except Exception:  # noqa: BLE001
        return {"days": None, "expires": "", "issuer": "", "staging": False}


def _dns(name: str) -> List[str]:
    try:
        return sorted({a[4][0] for a in socket.getaddrinfo(name, None)})
    except OSError:
        return []


@app.get("/api/admin/domains")
async def admin_domains(request: Request):
    need_admin(request)
    v = ctx.settings.all()
    on, dom = bool(v.get("https.enabled")), str(v.get("https.domain") or "").strip().lower()
    cert = _cert_info()
    targets = [{"id": i, "label": l} for i, l in HOST_TARGETS]
    sites = []
    for d, t in web_hosts(v):
        pending = bool(_tls_manager and (d not in _tls_manager.names() or _tls_manager.needs_expand()))
        info = ("HTTPS ist aus" if not on else "Zertifikat wird um diese Domain erweitert …" if pending
                else "Hauptname des Zertifikats" if d == dom else "gleiches Zertifikat")
        if t == "portal" and not v.get("portal.enabled"):
            info += " · Portal-Seite ist aus – zeigt das Dashboard"
        sites.append({"domain": d, "label": "🔒 Hauptname" if d == dom else "", "target": t, "targets": targets,
                      "https": on and cert is not None and not pending, "cert": cert if on and not pending else None,
                      "dns": await asyncio.to_thread(_dns, d), "info": info})
    waiting = set(json.loads(ctx.db.kv_get("mail.dns_waiting") or "[]"))
    for mh in mailcfg.cert_names(v):
        pending = bool(_tls_manager and (mh not in _tls_manager.names() or _tls_manager.needs_expand()))
        if mh in waiting:
            sites.append({"domain": mh, "label": "", "target_label": "✉️ Mail" if mh.startswith("mail.") else "✉️ MTA-STS",
                          "https": False, "cert": None, "dns": await asyncio.to_thread(_dns, mh), "remove": False, "renew": False,
                          "info": "wartet auf DNS – kommt automatisch aufs Zertifikat, sobald der Eintrag auf diesen Server zeigt"})
            continue
        sites.append({"domain": mh, "label": "", "target_label": "✉️ Mail" if mh.startswith("mail.") else "✉️ MTA-STS",
                      "https": on and cert is not None and not pending, "cert": cert if on and not pending else None,
                      "dns": await asyncio.to_thread(_dns, mh), "remove": False,
                      "info": ("HTTPS ist aus – der Mailserver braucht das Let's-Encrypt-Zertifikat" if not on else
                               "Zertifikat wird um diese Domain erweitert …" if pending else "gleiches Zertifikat – Postfix und Dovecot nutzen es")})
    hint = "HTTPS ist an, aber es ist keine Domain eingetragen." if on and not dom else \
        ("HTTPS ist eingeschaltet, läuft aber erst nach einem Neustart des Dashboards." if on and _tls_manager is None else "")
    has_live = any(t == "live" for _, t in web_hosts(v))
    add = {"allowed": True, "email": v.get("https.email", ""), "staging": bool(v.get("https.staging")),
           "placeholder": "news.example.org" if dom else "frn.example.org", "targets": targets, "target": "portal" if has_live else "live",
           "button": "Domain eintragen & Zertifikat holen",
           "reason": ("Jede Domain oder Subdomain zeigt, was du unter „Zeigt“ wählst: 🎙️ das Live-Dashboard oder 📰 die Portal-Seite mit den "
                      "News – jederzeit umstellbar. Alle Domains kommen auf ein Let's-Encrypt-Zertifikat; die DNS-Einträge müssen auf diesen "
                      "Server zeigen.")}
    return {"intro": "Eigene Domains und Subdomains mit kostenlosem Zertifikat von Let's Encrypt – je Domain wählbar, ob sie das 🎙️ Live-Dashboard "
                     "oder die 📰 Portal-Seite zeigt. Das Dashboard macht HTTPS selbst (certbot, ohne nginx). Voraussetzung: die Domains "
                     "zeigen per DNS auf diesen Server und der HTTP-Port (Let's Encrypt prüft immer auf 80) und der HTTPS-Port sind aus dem "
                     "Internet erreichbar (siehe 🔌 Ports).",
            "hint": hint, "sites": sites, "renew_auto": True if (on and _tls_manager is not None) else None,
            "options": [{"key": "https.enabled", "label": "HTTPS mit Let's Encrypt", "value": on,
                         "help": "Aus = nur http://IP:Web-Port. Ein- und Ausschalten startet das Dashboard neu."}],
            "add": add}


def _restart_soon(why: str) -> None:
    from .n8_crash import mark_planned
    mark_planned(str(DATA), "frnadn.service", why)
    asyncio.get_running_loop().call_later(1.0, os._exit, 3)


@app.post("/api/admin/domains")
async def admin_domains_add(request: Request):
    b = await body(request)
    dom = str(b.get("domain") or "").strip().lower().rstrip(".")
    if not _HOST_RE.fullmatch(dom):
        raise HTTPError(400, "Keine gültige Domain")
    hosts = web_hosts()
    target = str(b.get("target") or ("portal" if any(t == "live" for _, t in hosts) else "live"))
    if target not in dict(HOST_TARGETS):
        raise HTTPError(400, "Unbekanntes Ziel")
    if dom in dict(hosts) or dom in mailcfg.cert_names(ctx.settings.all()):
        raise HTTPError(400, "Diese Domain ist schon eingetragen.")
    what = "📰 Portal-Seite" if target == "portal" else "🎙️ Live-Dashboard"
    main = str(ctx.settings.get("https.domain") or "").strip().lower()
    if main:                                    # a further domain on the same certificate
        mail_kick()
        await _save(request, {**_hosts_changes(hosts + [(dom, target)]),
                              "https.email": str(b.get("email") or ctx.settings.get("https.email") or "").strip()})
        if ctx.settings.get("https.enabled"):
            if _tls_main is not None:            # 2.27: the certificate is extended in place – no restart
                ctx.tasks.append(asyncio.ensure_future(tls_refresh(f"Domain {dom}")))
                return {"ok": True, "message": f"{dom} zeigt jetzt die {what}. Das Zertifikat wird im laufenden Betrieb erweitert – "
                                               f"in einer Minute unter https://{dom}/ öffnen."}
            _restart_soon("Domain hinzugefügt")
            return {"ok": True, "message": f"{dom} zeigt jetzt die {what}. Das Dashboard startet neu und erweitert das Zertifikat – "
                                           f"in einer Minute unter https://{dom}/ öffnen."}
        return {"ok": True, "message": f"{dom} zeigt jetzt die {what} (HTTPS ist aus: http://{dom}/)."}
    await _save(request, {**_hosts_changes([(dom, target)] + hosts), "https.domain": dom, "https.email": str(b.get("email") or "").strip(),
                          "https.staging": bool(b.get("staging")), "https.enabled": True})
    _restart_soon("HTTPS/Domain geändert")
    return {"ok": True, "message": f"{dom} eingetragen ({what}), HTTPS ist an. Das Dashboard startet neu und holt das Zertifikat – "
                                   f"in einer Minute unter https://{dom}/ öffnen."}


@app.post("/api/admin/domains/{domain}/target")
async def admin_domains_target(domain: str, request: Request):
    b = await body(request)
    d, target = domain.strip().lower(), str(b.get("target") or "")
    if target not in dict(HOST_TARGETS):
        raise HTTPError(400, "Unbekanntes Ziel")
    hosts = web_hosts()
    if d not in dict(hosts):
        raise HTTPError(404, "Diese Domain ist nicht eingetragen.")
    await _save(request, _hosts_changes([(h, target if h == d else t) for h, t in hosts]))
    what = "die 📰 Portal-Seite" if target == "portal" else "das 🎙️ Live-Dashboard"
    note = " (Die Portal-Seite ist aus – bis sie unter 📰 Portal eingeschaltet ist, zeigt die Domain das Dashboard.)" \
        if target == "portal" and not ctx.settings.get("portal.enabled") else ""
    return {"ok": True, "message": f"{d} zeigt jetzt {what} – sofort, ohne Neustart.{note}"}


@app.post("/api/admin/domains/{domain}/renew")
async def admin_domains_renew(domain: str, request: Request):
    need_admin(request)
    if _tls_manager is None:
        raise HTTPError(400, "HTTPS läuft noch nicht – erst einschalten und das Dashboard neu starten.")
    if domain.strip().lower() not in _tls_manager.names():
        _restart_soon("Zertifikat um eine Domain erweitern")
        return {"ok": True, "message": "Die Domain ist noch nicht im laufenden Zertifikat – das Dashboard startet neu und erweitert es."}
    fresh = not _tls_manager.have_cert() or _tls_manager.needs_expand()
    ok = await (_tls_manager.obtain() if fresh else _tls_manager.renew())
    have = _tls_manager.have_cert()
    return {"ok": bool(ok) or have, "message": "Zertifikat geholt bzw. aktuell." if ok or have else
            "certbot ist fehlgeschlagen – zeigt die Domain auf diesen Server und ist Port 80 von außen erreichbar? Einzelheiten im Log."}


@app.delete("/api/admin/domains/{domain}")
async def admin_domains_remove(domain: str, request: Request):
    d = domain.strip().lower()
    hosts = web_hosts()
    if d not in dict(hosts):
        raise HTTPError(404, "Diese Domain ist nicht eingetragen.")
    rest = [(h, t) for h, t in hosts if h != d]
    main = str(ctx.settings.get("https.domain") or "").strip().lower()
    if d != main:
        await _save(request, _hosts_changes(rest))
        if ctx.settings.get("https.enabled"):
            if _tls_main is not None:
                ctx.tasks.append(asyncio.ensure_future(tls_refresh(f"Domain {d} entfernt")))
            else:
                _restart_soon("Domain entfernt")
        return {"ok": True, "message": f"{domain} entfernt." + (" Die Portal-Seite bleibt unter /portal erreichbar." if dict(hosts)[d] == "portal" else "")}
    if rest:                                    # the next domain becomes the certificate's main name
        await _save(request, {**_hosts_changes(rest), "https.domain": rest[0][0]})
        _restart_soon("Hauptdomain entfernt")
        return {"ok": True, "message": f"{domain} entfernt – {rest[0][0]} ist jetzt der Hauptname des Zertifikats. Das Dashboard startet neu."}
    await _save(request, {**_hosts_changes([]), "https.domain": "", "https.enabled": False})
    _restart_soon("HTTPS/Domain geändert")
    return {"ok": True, "message": f"{domain} entfernt, HTTPS ist aus. Das Dashboard startet neu."}


@app.post("/api/admin/domains/options")
async def admin_domains_options(request: Request):
    b = await body(request)
    if "https.enabled" not in b:
        raise HTTPError(400, "unbekannte Option")
    await _save(request, {"https.enabled": bool(b["https.enabled"])})
    _restart_soon("HTTPS ein/aus")
    return {"ok": True, "message": "HTTPS " + ("eingeschaltet" if b["https.enabled"] else "ausgeschaltet") + " – das Dashboard startet neu."}


@app.post("/api/admin/power")
async def power(request: Request):
    u = need_admin(request)
    if u["role"] != "superadmin":
        raise HTTPError(403, "Only the superadmin may reboot the machine.")
    b = await body(request)
    try:
        r = await ctx.system.power(str(b.get("action", "")))
    except ValueError as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit(str(b.get("action")), u["username"], "", ip_of(request))
    return {"ok": r["rc"] == 0}


# ---------------------------------------------------------------- Dienste, Berechtigungen & sudo, Update-Protokoll (scripts/n8-admin.sh)
@app.get("/api/admin/services")
async def services_list(request: Request):
    need_admin(request)
    return {"ready": ctx.n8.ready, "units": await ctx.n8.units()}


@app.post("/api/admin/services/{unit}/{action}")
async def services_action(unit: str, action: str, request: Request):
    u = need_admin(request)
    ok, out = await ctx.n8.unit_action(unit, action)
    ctx.auth.audit("service", u["username"], f"{action} {unit}: {'ok' if ok else out[:120]}", ip_of(request))
    if not ok:
        raise HTTPError(400, out or "failed")
    if unit == "frn-server.service":
        await asyncio.sleep(1.5)
        await ctx.server.poll_service()
    return {"ok": ok, "message": out, "units": await ctx.n8.units(), "self": action in ("restart", "stop") and unit == own_unit()}


@app.get("/api/admin/perms")
async def perms_check(request: Request):
    need_admin(request)
    return await ctx.n8.check_perms()


@app.post("/api/admin/perms/fix")
async def perms_fix(request: Request):
    u = need_admin(request)
    ok, out = await ctx.n8.fix_perms()
    ctx.auth.audit("perms_fix", u["username"], "ok" if ok else "errors remain", ip_of(request))
    return {"ok": ok, "message": out, "check": await ctx.n8.check_perms()}


# Abstürze (N8 Kit 1.3): crash-hook von scripts/n8-admin.sh (auch für den Java-FRN-Server), Keep-Alive und n8_crash.CrashWatch
# schreiben <Datenordner>/crashes.jsonl – gleiche Adressen in allen N8-Systemen
@app.get("/api/admin/crashes")
async def crashes_get(request: Request):
    need_admin(request)
    return await asyncio.to_thread(ctx.n8.crashes)


@app.get("/api/admin/crashes/{cid}")
async def crash_get(cid: str, request: Request):
    need_admin(request)
    txt = await asyncio.to_thread(ctx.n8.crash_log, cid)
    if txt is None:
        raise HTTPError(404, "Befund nicht gefunden")
    return {"id": cid, "log": txt}


@app.post("/api/admin/crashes/ack")
async def crashes_ack(request: Request):
    need_admin(request)
    b = await body(request)
    b = b if isinstance(b, dict) else {}
    ids = b.get("ids") if isinstance(b.get("ids"), list) else []
    return await asyncio.to_thread(ctx.n8.crash_ack, [str(i) for i in ids][:500], bool(b.get("all")))

@app.post("/api/admin/crashes/delete")
async def crashes_delete(request: Request):
    need_admin(request)
    b = await body(request)
    b = b if isinstance(b, dict) else {}
    ids = b.get("ids") if isinstance(b.get("ids"), list) else []
    return await asyncio.to_thread(ctx.n8.crash_delete, [str(i) for i in ids][:500], bool(b.get("all")))


@app.get("/api/admin/keepalive")
async def keepalive_get(request: Request):
    need_admin(request)
    return ctx.n8.keepalive()


@app.post("/api/admin/keepalive")
async def keepalive_set(request: Request):
    u = need_admin(request)
    b = await body(request)
    try:
        c = ctx.n8.keepalive_set(b)
    except (ValueError, TypeError) as e:
        raise HTTPError(400, str(e))
    ctx.auth.audit("keepalive", u["username"], ", ".join(f"{k}={'…' if 'url' in k and v else v}" for k, v in c.items()), ip_of(request))
    return ctx.n8.keepalive()


@app.get("/api/n8/health")
async def n8_health(request: Request):
    """Für den Keep-Alive (scripts/n8-admin.sh): Zustand der Teile – nur direkt von diesem Rechner, nie über einen Proxy."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1") or any(h in request.headers for h in ("x-forwarded-for", "x-real-ip", "forwarded", "via")):
        raise HTTPError(403, "local only")
    st = ctx.server.state()
    ok = DEMO or bool(st.get("running"))
    return {"ok": True, "items": {
        "web": {"ok": True},
        "frn": {"ok": ok, "why": "" if ok else ("FRN-Server " + (st.get("service") or "?") + (" – nimmt keine Verbindungen an" if st.get("service") == "active" else "")
                                                 + (f" ({st['error']})" if st.get("error") else ""))},
        "sysman": {"ok": True, "warning": st.get("error") or ""},
    }}


@app.get("/api/admin/update-log")
async def update_log(request: Request):
    need_admin(request)
    return ctx.n8.update_state()


@app.get("/api/admin/logs")
async def logs(request: Request):
    need_admin(request)
    return {"entries": list(ctx.live.events)}


@app.get("/api/admin/journal")
async def journal(request: Request, lines: int = 300, unit: str = "frnadn"):
    need_admin(request)
    return {"text": await ctx.system.journal(lines, "frn-server" if unit == "frn-server" else "frnadn")}


@app.get("/api/admin/frnlog")
async def frnlog(request: Request, lines: int = 400):
    """The last lines of server.log of the FRN server (passwords are masked by the server itself)."""
    need_admin(request)
    path = FRN_HOME / "logs" / "server.log"
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 400_000))
            text = f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return {"text": f"{path} does not exist yet – has the FRN server been started?"}
    return {"text": "\n".join(text.splitlines()[-min(max(lines, 10), 3000):])}


@app.get("/api/admin/visits")
async def visits(request: Request, limit: int = 200):
    need_admin(request)
    rows = ctx.db.q("SELECT * FROM visits ORDER BY login_ts DESC LIMIT ?", (min(max(limit, 1), 1000),))
    return {"entries": [dict(r) for r in rows]}


# ---------------------------------------------------------------- background
async def hourly_update_check() -> None:
    """One check shortly after start, then at every full hour. Never installs anything by itself."""
    await asyncio.sleep(30)
    while True:
        next_check = (int(time.time() // 3600) + 1) * 3600 + 5
        try: await check_all_updates(True)
        except Exception: log.exception("update check")
        await asyncio.sleep(max(1, next_check - time.time()))


def _seconds_to_local_midnight() -> float:
    now = time.time()
    tomorrow = datetime.fromtimestamp(now).date() + timedelta(days=1)
    midnight = time.mktime((tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, -1, -1, -1))
    return max(1.0, midnight - now)


async def midnight_site_icon_refresh() -> None:
    """Refresh the linked website icons at local midnight."""
    while True:
        await asyncio.sleep(_seconds_to_local_midnight())
        try:
            cfg = linkstore.read(LINKS_FILE)
            urls = [item["url"] for item in cfg["items"] if item.get("site_icon", True)]
            await asyncio.to_thread(siteicons.refresh_many, ctx.db, urls, True)
            log.info("Midnight site icon refresh completed (%s links)", len(urls))
        except Exception:
            log.exception("midnight site icon refresh")

# ---------------------------------------------------------------- public FRN error log (freeradionetwork.de)
_ERRLOG_SEEN: set = set()
if DEMO:   # demo without internet: a typical log with entries about the demo server
    def _demo_errorlog(timeout: float) -> str:
        ago = lambda m: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - m * 60))  # noqa: E731
        hint = " - Hint: Perform an FRN password request and use the assigned FRN password !"
        lines = [f"{ago(50 - i * 5)} ERROR - Server [frn-demo.example.org:10024], DE, Request SC - wrong FRN password{hint}" for i in range(6)]
        lines += [f"{ago(31)} ERROR - Server [frn-demo.example.org:10024], DE, Request SC - multiple connections at the same time "
                  "with the same connection data are not permitted",
                  f"{ago(9)} ERROR - Server [uhf3radionet.ddns.net:10024], GR, Request SC - not listening on specified port - Hint: "
                  "Check the firewall settings and port forwarding settings, if applicable !",
                  f"{ago(2)} ERROR - Client [DL9XYZ, Gateway], DE/DE, Request CC - wrong FRN password{hint}"]
        return json.dumps({"log": "\n".join(lines)})
    frn_errorlog._get = _demo_errorlog


def errorlog_scope() -> Tuple[List[str], List[str]]:
    """Callsigns and server addresses whose entries in the public FRN error log concern this server: the own server
    address, the owner's callsign and stations refused on this server in the last hour."""
    s = ctx.settings.all()
    calls = [s.get("frn.owner_callsign") or ""]
    now = time.time()
    for e in list(ctx.live.events):
        if e.get("kind") == "denied" and e.get("ts", 0) > now - 3600:
            calls.append(str(e.get("text", "")).split(" ", 1)[0])
    # Master & Backup: auch der Partner (dieselben Räume, oft dieselben Probleme – z. B. dasselbe FRN-Konto)
    hosts = [s.get("frn.address") or ""]
    if s.get("cluster.role") in ("master", "backup"):
        hosts.append(s.get("frn.backup_host") or cluster.peer_host(s.get("cluster.peer_url")))
    return [c for c in dict.fromkeys(calls) if c and c != "?"], [h for h in dict.fromkeys(hosts) if h]


async def errorlog_watch() -> None:
    """Look into the public FRN error log and report new entries about this server as event (once per message)."""
    entries, err = await frn_errorlog.fetch(force=True)
    if err:
        return
    calls, hosts = errorlog_scope()
    recent = [e for e in frn_errorlog.relevant(entries, calls, hosts) if e["time"] >= time.time() - 1800]
    for g in frn_errorlog.summarize(recent)[:5]:
        key = (g["kind"], g["id"], g["message"], g["first"])
        if key in _ERRLOG_SEEN:
            continue
        _ERRLOG_SEEN.add(key)
        who = f"client {g['id']}" + (f", {g['name']}" if g["name"] else "") if g["kind"] == "Client" else f"server {g['id']}"
        ctx.live.frn_errorlog(f"FRN error log: {who} – {g['message']}" + (f" ({g['count']}× since {g['first'][11:16]})" if g["count"] > 1 else "")
                              + (f" → {g['hint']}" if g["hint"] else ""))


@app.get("/api/admin/frn-errorlog")
async def frn_errorlog_get(request: Request, force: bool = False):
    """Public FRN error log of freeradionetwork.de – entries about this server (address, owner, refused stations)."""
    need_admin(request)
    calls, hosts = errorlog_scope()
    entries, err = await frn_errorlog.fetch(force=force)
    mine = frn_errorlog.relevant(entries, calls, hosts)
    seen = {(e["ts"], e["kind"], e["id"]) for e in mine}
    return {"ok": not err, "error": err, "page": frn_errorlog.PAGE, "fetched": frn_errorlog._cache["t"], "total": len(entries),
            "span": [entries[0]["ts"], entries[-1]["ts"]] if entries else None, "scope": {"callsigns": calls, "servers": hosts},
            "mine": frn_errorlog.summarize(mine),
            "others": frn_errorlog.summarize([e for e in entries if (e["ts"], e["kind"], e["id"]) not in seen])[:15]}


_ERRLOG_STATE = {"sig": None, "at": 0.0}


async def errorlog_on_problem() -> None:
    """Wie in N8 Crosslink: sobald der FRN-Server ein Problem meldet (Ablehnung durch den SystemManager, Ende, Neustart),
    nach ein paar Sekunden im öffentlichen Fehlerprotokoll nachsehen – dort steht der Grund, den der Server selbst nicht nennt.
    Höchstens einmal pro Minute; der Grund landet im Ereignisprotokoll."""
    st = ctx.server.state()
    sig = (bool(st.get("error")), st.get("error") or "", st.get("restarts") or 0, st.get("service"))
    prev, _ERRLOG_STATE["sig"] = _ERRLOG_STATE["sig"], sig
    if prev is None or sig == prev:
        return
    problem = bool(st.get("error")) or (st.get("restarts") or 0) > (prev[2] or 0) or st.get("service") not in ("active",)
    if problem and time.time() - _ERRLOG_STATE["at"] > 60:
        _ERRLOG_STATE["at"] = time.time()
        await asyncio.sleep(4)                       # der SystemManager schreibt den Eintrag kurz nach der Ablehnung
        await errorlog_watch()


async def background() -> None:
    n = 0
    while True:
        try:
            # public FRN error log: right after a problem of the FRN server, every 2 minutes while the SystemManager reports
            # one, otherwise every 10 minutes – new reasons go to the events (like N8 Crosslink)
            if not DEMO and ctx.settings.get("frn.address") and not ctx.settings.get("frn.standalone"):
                await errorlog_on_problem()
                if n % (24 if ctx.server.error else 120) == 7:
                    await errorlog_watch()
            if n % 12 == 0:
                ctx.live.sample()
            if n % 720 == 5:
                await asyncio.to_thread(cleanup)
        except Exception:
            log.exception("background")
        n += 1
        await asyncio.sleep(5)


def cleanup() -> None:
    s = ctx.settings.all()
    now = time.time()
    ctx.db.x("DELETE FROM talks WHERE ts < ?", (now - s["data.talk_days"] * 86400,))
    ctx.db.x("DELETE FROM visits WHERE login_ts < ?", (now - s["data.visit_days"] * 86400,))
    ctx.db.x("DELETE FROM chat WHERE ts < ?", (now - s["data.chat_days"] * 86400,))
    ctx.db.x("DELETE FROM samples WHERE ts < ?", (now - 400 * 86400,))
    ctx.db.x("PRAGMA optimize")


async def _startup() -> None:
    global ctx
    if ctx is None:
        ctx = Ctx()
    ctx.auth.on_mail_change = _mail_users_changed      # ✉️ new users / passwords → mailbox list of the mail server
    ctx.store.ensure_rooms()
    fwidgets.ensure_builtin(ctx.db)                     # 🧩 the three boxes of the own FRN server on the portal page
    if not ctx.db.kv_get("migr.client_timeout_300k"):   # 2.32.0: new default 5 min instead of 8 s
        stored = ctx.db.q("SELECT value FROM settings WHERE key='frn.client_timeout'")
        if stored and str(stored[0]["value"]).strip() in ("8000", "8000.0"):
            ctx.settings.update({"frn.client_timeout": 300000}, "update 2.32.0")
            log.info("Client-Zeitlimit: alter Standard 8000 ms → neuer Standard 300000 ms")
        ctx.db.kv_set("migr.client_timeout_300k", "1")
    for error in ctx.acls.sync_from_files():
        log.warning("ACL import: %s", error)
    configured_links = linkstore.read(LINKS_FILE)
    ctx.tasks.append(asyncio.create_task(asyncio.to_thread(
        siteicons.refresh_many, ctx.db, [x["url"] for x in configured_links["items"] if x.get("site_icon", True)]
        + ([partner_link()["url"]] if partner_link() else []))))
    ctx.server.reload_rooms()
    try:
        ctx.java.write_config()
    except OSError as e:
        log.error("cannot write the FRN server configuration: %s", e)
    if _cluster_get("cluster.guard") or account_conflict():
        await account_guard("startup")                 # Backup mit dem Konto des Masters: FRN-Server bleibt aus
    elif ctx.java.direct:
        await ctx.java.control("start")
    elif _RESTORED.get("ok"):
        await ctx.java.control("restart")             # the FRN server reads the restored configuration
        ctx.auth.audit("backup_restored", "system", (_RESTORED.get("manifest") or {}).get("created_by", ""), "")
    await ctx.server.start()
    ctx.tasks.append(asyncio.ensure_future(background()))
    ctx.tasks.append(asyncio.ensure_future(hourly_update_check()))
    ctx.tasks.append(asyncio.ensure_future(midnight_site_icon_refresh()))
    ctx.tasks.append(asyncio.ensure_future(cluster_hourly()))
    ctx.tasks.append(asyncio.ensure_future(cluster_auto_return()))
    ctx.tasks.append(asyncio.ensure_future(widget_loop()))
    pend = _cluster_get("cluster.return_pending")
    if pend:                                           # dashboard restarted while stations were sent back: start FRN again
        ctx.tasks.append(asyncio.ensure_future(_return_restart(float(pend.get("start_at") or 0))))
    ctx.tasks.append(asyncio.ensure_future(mail_auto_loop()))      # ✉️ new mail domains → certificate → mail server


async def _shutdown() -> None:
    if ctx:
        await ctx.server.stop()
        await ctx.java.stop_child()
        for t in ctx.tasks:
            t.cancel()


CRASH_SERVICES = [   # welcher Teil des Dashboards steckt in einem Stack (Absturz-Befunde, auch für den crash-hook)
    (r"/frnadn/frn/", "FRN-Protokoll"), (r"/frnadn/live\.py$", "Live-Daten"), (r"/frnadn/(sysman|clientsw)\.py$", "System Manager"),
    (r"/frnadn/frn_errorlog\.py$", "FRN-Fehlerprotokoll"), (r"/frnadn/stats\.py$", "Statistik"), (r"/frnadn/db\.py$", "Datenbank"),
    (r"/frnadn/(backup|n8mig)\.py$", "Backup"), (r"/frnadn/updater\.py$", "Update-Prüfung"), (r"/frnadn/tls\.py$", "HTTPS"),
    (r"/frnadn/auth\.py$", "Anmeldung"), (r"/frnadn/(settings|system)\.py$", "Einstellungen & System"), (r"/frnadn/siteicons\.py$", "Site-Icons"),
    (r"/frnadn/app\.py$", "Dashboard"), (r"/(uvicorn|starlette|fastapi|websockets)/", "Webinterface"),
]


@contextlib.asynccontextmanager
async def lifespan(_app):
    if not DEMO:       # Absturz-Melder (N8 Kit): Hänger der Event-Loop, abgestürzte Tasks, harter Absturz → Admin → System → 💥 Abstürze
        try:
            from .n8_crash import CrashWatch
            CrashWatch(str(DATA), app="ADN-FRN-Server", unit="frnadn.service", services=CRASH_SERVICES).install()
        except Exception as e:  # noqa: BLE001
            log.warning("Absturz-Melder nicht aktiv: %s", e)
    await _startup()
    yield
    await _shutdown()


app.router.lifespan_context = lifespan
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


_tls_manager = None


class _Server:
    """Uvicorn server without per-instance signal handlers (HTTP + HTTPS share one process)."""
    @staticmethod
    def make(app_, **kwargs):
        import contextlib
        import uvicorn

        class Server(uvicorn.Server):
            @contextlib.contextmanager
            def capture_signals(self):
                yield

        kwargs.setdefault("log_level", "warning")
        kwargs.setdefault("access_log", False)
        kwargs.setdefault("loop", "asyncio")
        kwargs.setdefault("proxy_headers", True)
        kwargs.setdefault("forwarded_allow_ips", "127.0.0.1")
        for k, v in _sec.UVICORN_KWARGS.items():
            kwargs.setdefault(k, v)          # no "server: uvicorn" header
        return Server(uvicorn.Config(app_, **kwargs))


_SELF = {"host": "127.0.0.1", "port": 8090}


async def _serve(host: str, port: int) -> None:
    """Run the dashboard and (when enabled) the ACME HTTP listener + HTTPS server."""
    _SELF.update(host=host, port=port)
    import signal
    global ctx, _tls_manager, _tls_main
    if ctx is None:
        res = fbackup.apply_pending(DATA, FRN_HOME)      # restore prepared in the web interface: before the DB opens
        if res:
            _RESTORED.update(res)
            log.warning("Backup restored: %s", "ok" if res.get("ok") else res.get("error"))
        ctx = Ctx()
    https_cfg = {
        "enabled": ctx.settings.get("https.enabled"),
        "domain": ctx.settings.get("https.domain"),
        "email": ctx.settings.get("https.email"),
        "staging": ctx.settings.get("https.staging"),
        "http_port": ctx.settings.get("https.http_port"),
        "port": ctx.settings.get("https.port"),
        "letsencrypt": True,
        # the portal page's own domain goes on the same certificate (one more name, SAN)
        "extra": _cert_plan()["extra"],          # further domains (Live, 📰 portal) and ✉️ mail names whose DNS is ready          # ✉️ mail.<domain> (and mta-sts.<domain>) of N8 Mail
    }
    servers, server_tasks, helpers = [], [], []
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()

    def stop_all():
        stopping.set()
        for srv in servers:
            srv.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_all)
        except (NotImplementedError, RuntimeError):
            pass

    async def serve_contained(srv):
        try:
            await srv.serve()
        except SystemExit:
            log.exception("Uvicorn server exited unexpectedly")

    async def start(srv, optional=False):
        servers.append(srv)
        task = asyncio.create_task(serve_contained(srv))
        while not srv.started and not task.done() and not stopping.is_set():
            await asyncio.sleep(0.05)
        if not srv.started and not stopping.is_set():
            servers.remove(srv)
            if optional:
                return None
            raise RuntimeError(f"Dashboard-Port {srv.config.port} ist belegt oder nicht erlaubt.")
        server_tasks.append(task)
        return srv

    if https_cfg["enabled"]:
        from .tls import CertManager, build_http_app
        cm = CertManager(https_cfg, DATA)
        _tls_manager = cm
        http_app = build_http_app(cm, redirect=True)
        await start(_Server.make(http_app, host=host, port=cm.http_port, lifespan="off"), optional=False)

        def tls_server(lifespan):
            return _Server.make(app, host=host, port=cm.https_port, lifespan=lifespan,
                                ssl_certfile=cm.cert_file, ssl_keyfile=cm.key_file)

        async def renew_loop(main_server):
            while not stopping.is_set():
                await asyncio.sleep(12 * 3600)
                if await cm.renew() and main_server.config.ssl is not None:
                    main_server.config.ssl.load_cert_chain(cm.cert_file, cm.key_file)
                    log.info("Let's Encrypt Zertifikat neu geladen.")
                    await _mail_after_cert("certs")

        if cm.have_cert():
            main = await start(tls_server("on"))
            _tls_main = main
            log.info("Dashboard HTTPS aktiv: %s", cm.https_url())
            if port not in (cm.http_port, cm.https_port):
                await start(_Server.make(http_app, host=host, port=port, lifespan="off"), optional=True)
            helpers.append(asyncio.create_task(renew_loop(main)))

            async def expand(main_server):
                """A domain was added (portal): fetch the certificate with all names, then reload it in place."""
                if await cm.obtain() and main_server.config.ssl is not None:
                    main_server.config.ssl.load_cert_chain(cm.cert_file, cm.key_file)
                    log.info("Zertifikat jetzt für %s", ", ".join(cm.names()))
                    await _mail_after_cert("apply")
                elif not stopping.is_set():
                    log.error("Zertifikat für %s konnte nicht erweitert werden – DNS und Port 80 prüfen", ", ".join(cm.names()))

            if cm.needs_expand():
                helpers.append(asyncio.create_task(expand(main)))
        else:
            # Keep the dashboard available while certbot obtains its first certificate.
            fallback_port = port if port not in (cm.http_port, cm.https_port) else 8080
            await start(_Server.make(app, host=host, port=fallback_port, lifespan="on"))
            log.info("Noch kein Zertifikat. Dashboard vorübergehend unter http://%s:%s erreichbar.", host, fallback_port)

            async def obtain_then_serve():
                if await cm.obtain() and not stopping.is_set():
                    main = await start(tls_server("off"), optional=True)
                    if main:
                        global _tls_main
                        _tls_main = main
                        log.info("Let's Encrypt HTTPS ist aktiv: %s", cm.https_url())
                        await renew_loop(main)
                    else:
                        log.error("HTTPS-Port %s konnte nicht geöffnet werden.", cm.https_port)
                elif not stopping.is_set():
                    log.error("Let's Encrypt Zertifikat nicht verfügbar; Dashboard bleibt vorübergehend auf HTTP.")

            helpers.append(asyncio.create_task(obtain_then_serve()))
    else:
        await start(_Server.make(app, host=host, port=port, lifespan="on"))
        log.info("Dashboard HTTP aktiv auf %s:%s", host, port)

    stop_wait = asyncio.create_task(stopping.wait())
    if server_tasks:
        await asyncio.wait([*server_tasks, stop_wait], return_when=asyncio.FIRST_COMPLETED)
    stop_all()
    for task in helpers:
        task.cancel()
    pending = [task for task in server_tasks if not task.done()]
    if pending:
        await asyncio.wait(pending, timeout=8)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(_serve(os.environ.get("FRNADN_BIND", "0.0.0.0"),
                           int(os.environ.get("FRNADN_PORT", "8080"))))
    except KeyboardInterrupt:
        pass
