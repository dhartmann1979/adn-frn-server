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
  FRNADN_PORT      web port, default 80
  FRNADN_DEMO      1 = demo mode (simulated system values)
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import __version__
from .auth import ADMIN_ROLES, Auth, AuthError
from .db import DB
from .frn.javasrv import JavaServer
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
        self.stats = Stats(self.db)
        self.live = Live(self.db, self.notify, self.stats.bump)
        self.java = JavaServer(self.store, self.settings, FRN_HOME, FRN_JAR, demo=DEMO)
        self.server = LogWatch(self.store, self.live, FRN_HOME, self.java)
        self.live.server = self.server
        self.live.chat_mode = self.settings.get("dashboard.chat")
        self.system = System(demo=DEMO)
        self.sockets: Dict[WebSocket, Dict[str, Any]] = {}
        self.restart_needed = False
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
app = FastAPI(title="frn_adn", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=800)


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
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
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


def info_for(u) -> Dict[str, Any]:
    s = ctx.settings.all()
    addr = s["frn.address"]
    if addr:
        addr = f"{addr}:{s['frn.port']}"
    return {"title": s["dashboard.title"], "subtitle": s["dashboard.subtitle"], "address": addr, "public": s["dashboard.public"],
            "version": __version__, "demo": DEMO, "chat": ctx.chat_allowed(u), "owner": s["frn.owner_callsign"],
            "website": s["frn.website"], "setup_needed": not ctx.auth.has_superadmin()}


def refresh_sockets() -> None:
    for ws, meta in list(ctx.sockets.items()):
        u = user_of(ws)
        meta.update(see_hidden=ctx.see_hidden(u), chat=ctx.chat_allowed(u), admin=is_admin(u))


# ---------------------------------------------------------------- pages & public API
@app.get("/")
async def index():
    html = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{V}}", __version__)
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/api/info")
async def api_info(request: Request):
    u = user_of(request)
    i = info_for(u)
    if not u and not i["public"]:
        return {"title": i["title"], "public": False, "user": None, "login_required": True, "setup_needed": i["setup_needed"]}
    return {**i, "user": u}


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
    r = ctx.auth.login(str(b.get("username", "")), str(b.get("password", "")), ip_of(request), request.headers.get("user-agent", ""), hours)
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
    changed = ctx.settings.update(changes, u["username"])
    keys = [f.key for f in changed]
    if keys:
        ctx.auth.audit("settings_changed", u["username"], ", ".join(k for k in keys), ip_of(request))
        ctx.live.chat_mode = ctx.settings.get("dashboard.chat")
        if any(k.startswith(("frn.", "sysman.")) for k in keys):
            config_changed(u, request, "settings " + ", ".join(keys))
        refresh_sockets()
        await push({"type": "info"})
        await push({"type": "rooms"})
    return {"changed": keys, "restart_needed": ctx.restart_needed}


@app.post("/api/admin/server/{action}")
async def server_control(action: str, request: Request):
    u = need_admin(request)
    if action not in ("start", "stop", "restart"):
        raise HTTPError(404, "Unknown action.")
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
GITHUB_REPO = os.environ.get("FRNADN_GITHUB_REPO", "dhartmann1979/adn-frn-server")
_update_state: Dict[str, Any] = {"checked": None, "github": None, "java": None}

async def check_all_updates(force: bool = False) -> Dict[str, Any]:
    import json, urllib.request
    def github_check():
        req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/commits/main",
            headers={"User-Agent": "frn-adn-update", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=12) as r: remote = json.loads(r.read(500000))
        try:
            local = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
            local_sha = local.stdout.strip() if local.returncode == 0 else ""
        except Exception: local_sha = ""
        sha = remote.get("sha", "")
        return {"ok": True, "repo": GITHUB_REPO, "local": local_sha, "latest": sha,
                "update": bool(local_sha and sha and local_sha != sha),
                "message": (remote.get("commit", {}).get("message", "").split("\n")[0])}
    try: gh = await asyncio.to_thread(github_check)
    except Exception as e: gh = {"ok": False, "error": str(e)[:200], "update": False}
    java = await ctx.java.check_update()
    _update_state.update(checked=time.time(), github=gh, java=java)
    return dict(_update_state)

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


@app.get("/branding/logo")
async def branding_logo():
    p = DATA / "branding" / "logo.png"
    return FileResponse(p, media_type="image/png") if p.exists() else FileResponse(STATIC / "adn-icon.svg", media_type="image/svg+xml")

@app.post("/api/admin/branding")
async def save_branding(request: Request):
    u = need_admin(request)
    import base64
    b = await body(request)
    encoded = str(b.get("logo", ""))
    if encoded:
        try: data = base64.b64decode(encoded.split(",", 1)[-1], validate=True)
        except Exception: raise HTTPError(400, "Invalid logo upload.")
        if len(data) > 2_000_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPError(400, "Please upload a PNG image up to 2 MB.")
        folder = DATA / "branding"; folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "logo.png.tmp"; tmp.write_bytes(data); os.replace(tmp, folder / "logo.png")
    ctx.auth.audit("branding_changed", u["username"], "logo updated" if encoded else "theme changed", ip_of(request))
    return {"ok": True}
\n@app.get("/api/admin/updates")
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
        result = await ctx.java.install_update()
    elif target == "github":
        if not _update_state.get("github", {}).get("update"):
            raise HTTPError(400, "No checked GitHub update is available.")
        def fast_forward():
            dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True, timeout=8)
            if dirty.returncode or dirty.stdout.strip(): raise RuntimeError("Working tree is not clean; refusing to overwrite local changes.")
            fetch = subprocess.run(["git", "-C", str(ROOT), "fetch", "--no-tags", "origin", "main"], capture_output=True, text=True, timeout=120)
            if fetch.returncode: raise RuntimeError(fetch.stderr[-500:])
            pull = subprocess.run(["git", "-C", str(ROOT), "merge", "--ff-only", "FETCH_HEAD"], capture_output=True, text=True, timeout=60)
            if pull.returncode: raise RuntimeError(pull.stderr[-500:])
            return {"ok": True, "output": pull.stdout[-1000:]}
        result = await asyncio.to_thread(fast_forward)
        result["restart_required"] = True
    else: raise HTTPError(400, "Unknown update target.")
    ctx.auth.audit("upgrade_" + target, u["username"], str(result), ip_of(request))
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
               "client_txtimeout":"frn.tx_timeout", "default_net":"frn.default_room",\n               "standalone":"frn.standalone", "allowLANAddr":"frn.allow_lan",\n               "backup_server_addr":"frn.backup_host", "backup_server_port":"frn.backup_port",\n               "voip_skip_muted_crosslink_clients":"frn.skip_muted_crosslink",\n               "voip_skip_muted_gateway_clients":"frn.skip_muted_gateway",\n               "voip_skip_muted_pconly_clients":"frn.skip_muted_pconly"}
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
    if not changes: raise HTTPError(400, "No supported FRN settings were found in this file.")
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
    return {"ok": True, "imported": list(changes), "rooms": imported_rooms, "ignored": [k for k in parsed if k not in mapping], "backup": str(backup) if backup.exists() else None,
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
    return {"files": ctx.java.acl_files()}


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


@app.post("/api/admin/restart")
async def restart_app(request: Request):
    """Restart the whole program; systemd starts it again (Restart=always)."""
    u = need_admin(request)
    ctx.auth.audit("app_restart", u["username"], "", ip_of(request))
    asyncio.get_running_loop().call_later(0.5, os._exit, 3)
    return {"ok": True}


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
    # Run at each full local hour; never install automatically.
    while True:
        now = time.time()
        wait = 3600 - (now % 3600)
        await asyncio.sleep(wait)
        try: await check_all_updates(True)
        except Exception: log.exception("hourly update check")

async def background() -> None:
    n = 0
    while True:
        try:
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
    ctx.store.ensure_rooms()
    ctx.server.reload_rooms()
    try:
        ctx.java.write_config()
    except OSError as e:
        log.error("cannot write the FRN server configuration: %s", e)
    if ctx.java.direct:
        await ctx.java.control("start")
    await ctx.server.start()
    ctx.tasks.append(asyncio.ensure_future(background()))
    ctx.tasks.append(asyncio.ensure_future(hourly_update_check()))


async def _shutdown() -> None:
    if ctx:
        await ctx.server.stop()
        await ctx.java.stop_child()
        for t in ctx.tasks:
            t.cancel()


@contextlib.asynccontextmanager
async def lifespan(_app):
    await _startup()
    yield
    await _shutdown()


app.router.lifespan_context = lifespan
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def main() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(app, host=os.environ.get("FRNADN_BIND", "0.0.0.0"), port=int(os.environ.get("FRNADN_PORT", "80")),
                log_level="warning", proxy_headers=True, forwarded_allow_ips="127.0.0.1")
