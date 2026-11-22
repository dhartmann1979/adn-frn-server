"""Fetch, validate and cache public website favicons in SQLite."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import urlsplit

from .db import DB

MAX_BYTES = 256 * 1024
CACHE_SECONDS = 30 * 86400
MISS_CACHE_SECONDS = 3600
TIMEOUT = 3.5


def origin_for(url: str) -> Optional[str]:
    try:
        p = urlsplit(str(url))
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
            return None
        default_port = 80 if p.scheme == "http" else 443
        if p.port not in (None, default_port):
            return None
        try:
            host = ipaddress.ip_address(p.hostname).compressed.lower()
        except ValueError:
            if "%" in p.hostname:
                return None
            host = p.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        if not host or len(host) > 253:
            return None
        return f"{p.scheme.lower()}://{f'[{host}]' if ':' in host else host}"
    except (ValueError, UnicodeError):
        return None


def key_for(url: str) -> Optional[str]:
    origin = origin_for(url)
    return hashlib.sha256(origin.encode("utf-8")).hexdigest() if origin else None


def _public_target(url: str) -> bool:
    origin = origin_for(url)
    if not origin:
        return False
    p = urlsplit(origin)
    host = p.hostname or ""
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            port = 443 if p.scheme == "https" else 80
            addresses = {ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(ip.is_global for ip in addresses)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > 4 or not _public_target(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url: str, accept: str) -> Tuple[Optional[bytes], str]:
    if not _public_target(url):
        return None, "not a public HTTP(S) address"
    opener = urllib.request.build_opener(_SafeRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "frn-adn-site-icon/1.0", "Accept": accept})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                return None, "icon exceeds size limit"
            return data, ""
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        return None, str(exc)[:180]


def _image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")):
        return "image/x-icon"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _fetch_icon(origin: str) -> Tuple[Optional[bytes], str, str]:
    failures = []
    for path in ("/favicon.ico", "/favicon.png", "/apple-touch-icon.png"):
        data, error = _get(origin + path, "image/avif,image/webp,image/png,image/*,*/*;q=0.5")
        if data:
            content_type = _image_type(data)
            if content_type:
                return data, content_type, ""
            failures.append("server returned an unsupported image format")
        elif error:
            failures.append(error)
    return None, "", failures[-1] if failures else "no site icon found"


def refresh_one(db: DB, url: str, force: bool = False) -> bool:
    origin = origin_for(url)
    if not origin:
        return False
    key = hashlib.sha256(origin.encode("utf-8")).hexdigest()
    current = db.q("SELECT fetched_at,data FROM link_icons WHERE url_hash=?", (key,))
    interval = CACHE_SECONDS if current and current[0]["data"] is not None else MISS_CACHE_SECONDS
    if current and not force and time.time() - float(current[0]["fetched_at"]) < interval:
        return current[0]["data"] is not None
    data, content_type, error = _fetch_icon(origin)
    db.x("""INSERT INTO link_icons(url_hash,origin,content_type,data,fetched_at,error) VALUES(?,?,?,?,?,?)
           ON CONFLICT(url_hash) DO UPDATE SET origin=excluded.origin,content_type=excluded.content_type,
           data=excluded.data,fetched_at=excluded.fetched_at,error=excluded.error""",
          (key, origin, content_type, data, time.time(), error))
    return data is not None


def refresh_many(db: DB, urls: Iterable[str], force: bool = False) -> None:
    unique: Dict[str, str] = {}
    for url in urls:
        origin = origin_for(url)
        if origin:
            unique[origin] = url
    if not unique:
        return
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda url: refresh_one(db, url, force), unique.values()))
    db.x("DELETE FROM link_icons WHERE fetched_at < ?", (time.time() - CACHE_SECONDS,))


def cached_icon(db: DB, key: str) -> Optional[Dict[str, Any]]:
    row = db.q("SELECT content_type,data,fetched_at FROM link_icons WHERE url_hash=?", (key,))
    if not row or row[0]["data"] is None:
        return None
    return {"content_type": row[0]["content_type"], "data": bytes(row[0]["data"]), "fetched_at": row[0]["fetched_at"]}
