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
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from . import __version__, branding as brandstore, links as linkstore, siteicons, updater
from .auth import ADMIN_ROLES, Auth, AuthError
from .db import DB
from .frn.acl import ACLStore
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
        self.acls = ACLStore(self.db, self.store, FRN_HOME)
        self.stats = Stats(self.db)
        self.live = Live(self.db, self.notify, self.stats.bump)
        self.java = JavaServer(self.store, self.settings, FRN_HOME, FRN_JAR, demo=DEMO)
        self.server = LogWatch(self.store, self.live, FRN_HOME, self.java)
        self.live.server = self.server
        self.live.chat_mode = self.settings.get("dashboard.chat")
        self.system = System(demo=DEMO)
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
    if any(k.startswith("https.") for k in keys):
        ctx.dashboard_restart_needed = True
    if keys:
        ctx.auth.audit("settings_changed", u["username"], ", ".join(k for k in keys), ip_of(request))
        ctx.live.chat_mode = ctx.settings.get("dashboard.chat")
        if any(k.startswith(("frn.", "sysman.")) for k in keys):
            config_changed(u, request, "settings " + ", ".join(keys))
        refresh_sockets()
        await push({"type": "info"})
        await push({"type": "rooms"})
    return {"changed": keys, "restart_needed": ctx.restart_needed, "dashboard_restart_needed": ctx.dashboard_restart_needed}


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
GITHUB_REPO = os.environ.get("FRNADN_GITHUB_REPO", updater.DEFAULT_REPO)
GITHUB_BRANCH = os.environ.get("FRNADN_GITHUB_BRANCH", "main")
_update_state: Dict[str, Any] = {"checked": None, "github": None, "java": None}

async def check_all_updates(force: bool = False) -> Dict[str, Any]:
    """Dashboard (GitHub) and Java FRN server. Results are cached for ten minutes unless forced."""
    if not force and _update_state["checked"] and time.time() - _update_state["checked"] < 600:
        return dict(_update_state)
    gh = await asyncio.to_thread(updater.check, GITHUB_REPO, GITHUB_BRANCH, True)
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


@app.get("/api/links")
async def public_links():
    return links_payload(linkstore.read(LINKS_FILE))


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
    await asyncio.to_thread(siteicons.refresh_many, ctx.db, [x["url"] for x in cfg["items"]], bool(b.get("refresh_icons")))
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


@app.get("/link-icons/{key}")
async def cached_link_icon(key: str):
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise HTTPError(404, "Site icon not found.")
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
        gh = _update_state.get("github") or {}
        expected = str(b.get("expected") or (gh.get("latest") or {}).get("commit") or "")
        if not expected:
            raise HTTPError(400, "Bitte zuerst nach Updates suchen.")
        try:
            result = await asyncio.to_thread(updater.install, GITHUB_BRANCH, expected)
        except updater.UpdateError as e:
            raise HTTPError(400, str(e))
        if result.get("changed"):
            # Restart FRN as well: the dashboard's site status is derived from the server's live log stream.
            try:
                frn_restart = await ctx.java.control("restart")
                result["frn_restart"] = {"ok": frn_restart.get("rc") == 0, **frn_restart}
            except Exception as e:
                log.exception("FRN restart after dashboard update")
                result["frn_restart"] = {"ok": False, "out": str(e)}
            # systemd (Restart=always) starts the dashboard again on the new code; without systemd the admin must do it.
            result["restart_required"] = True
            result["restarting"] = updater.under_systemd()
            if result["restarting"]:
                asyncio.get_running_loop().call_later(1.5, os._exit, 3)
        _update_state["github"] = await asyncio.to_thread(updater.check, GITHUB_REPO, GITHUB_BRANCH, True)
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
    """One check shortly after start, then at every full hour. Never installs anything by itself."""
    await asyncio.sleep(30)
    while True:
        try: await check_all_updates(True)
        except Exception: log.exception("update check")
        await asyncio.sleep(3600 - (time.time() % 3600) + 5)

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
    for error in ctx.acls.sync_from_files():
        log.warning("ACL import: %s", error)
    configured_links = linkstore.read(LINKS_FILE)
    ctx.tasks.append(asyncio.create_task(asyncio.to_thread(
        siteicons.refresh_many, ctx.db, [x["url"] for x in configured_links["items"]])))
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
        return Server(uvicorn.Config(app_, **kwargs))


async def _serve(host: str, port: int) -> None:
    """Run the dashboard and (when enabled) the ACME HTTP listener + HTTPS server."""
    import signal
    global ctx, _tls_manager
    if ctx is None:
        ctx = Ctx()
    https_cfg = {
        "enabled": ctx.settings.get("https.enabled"),
        "domain": ctx.settings.get("https.domain"),
        "email": ctx.settings.get("https.email"),
        "staging": ctx.settings.get("https.staging"),
        "http_port": ctx.settings.get("https.http_port"),
        "port": ctx.settings.get("https.port"),
        "letsencrypt": True,
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

        if cm.have_cert():
            main = await start(tls_server("on"))
            log.info("Dashboard HTTPS aktiv: %s", cm.https_url())
            if port not in (cm.http_port, cm.https_port):
                await start(_Server.make(http_app, host=host, port=port, lifespan="off"), optional=True)
            helpers.append(asyncio.create_task(renew_loop(main)))
        else:
            # Keep the dashboard available while certbot obtains its first certificate.
            fallback_port = port if port not in (cm.http_port, cm.https_port) else 8080
            await start(_Server.make(app, host=host, port=fallback_port, lifespan="on"))
            log.info("Noch kein Zertifikat. Dashboard vorübergehend unter http://%s:%s erreichbar.", host, fallback_port)

            async def obtain_then_serve():
                if await cm.obtain() and not stopping.is_set():
                    main = await start(tls_server("off"), optional=True)
                    if main:
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
                           int(os.environ.get("FRNADN_PORT", "80"))))
    except KeyboardInterrupt:
        pass
