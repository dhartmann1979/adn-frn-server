"""HTTPS support for frn_adn, adapted from HBlink4-FreeRadioID.

HTTP-01 challenges are served from a private webroot on port 80. Certbot runs
as the frnadn service user with isolated config/work/log directories. Renewals
are checked twice daily and the live Uvicorn SSLContext is reloaded in place.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

logger = logging.getLogger("frnadn.tls")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{10,200}$")
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([A-Za-z0-9-]{1,63}\.)+[A-Za-z]{2,63}$")


class CertManager:
    def __init__(self, cfg: Dict[str, Any], data_dir: Path):
        self.cfg = cfg or {}
        self.domain = str(self.cfg.get("domain") or "").strip().lower()
        self.email = str(self.cfg.get("email") or "").strip()
        self.letsencrypt = bool(self.cfg.get("letsencrypt", True))
        self.staging = bool(self.cfg.get("staging", False))
        self.https_port = int(self.cfg.get("port", 443))
        self.http_port = int(self.cfg.get("http_port", 80))
        # further names on the same certificate (SAN), e.g. the domain of the portal page
        self.extra = [d for d in (str(x or "").strip().lower() for x in (self.cfg.get("extra") or []))
                      if d and d != self.domain and _DOMAIN_RE.fullmatch(d)]
        self.base = Path(data_dir) / "letsencrypt"
        self.webroot = self.base / "webroot"
        self.webroot.mkdir(parents=True, exist_ok=True)
        if self.letsencrypt:
            live = self.base / "config" / "live" / self.domain
            self.cert_file, self.key_file = str(live / "fullchain.pem"), str(live / "privkey.pem")
        else:
            self.cert_file = str(self.cfg.get("cert_file") or "")
            self.key_file = str(self.cfg.get("key_file") or "")
        self._mtime = self._cert_mtime()

    def valid_domain(self) -> bool:
        return bool(_DOMAIN_RE.fullmatch(self.domain))

    def have_cert(self) -> bool:
        return bool(self.cert_file and self.key_file and os.path.isfile(self.cert_file) and os.path.isfile(self.key_file))

    def _cert_mtime(self) -> float:
        try:
            return os.stat(self.cert_file).st_mtime
        except OSError:
            return 0.0

    def names(self) -> list[str]:
        return [self.domain, *self.extra]

    def _marker(self) -> Path:
        return self.base / f"names-{self.domain}.txt"

    def needs_expand(self) -> bool:
        """The certificate exists but was issued for other names (a domain was added or removed)."""
        if not self.letsencrypt or not self.have_cert():
            return False
        try:
            have = self._marker().read_text(encoding="utf-8").split()
        except OSError:
            have = [self.domain]
        return sorted(have) != sorted(self.names())

    def https_url(self, path: str = "/", host: str = "") -> str:
        port = "" if self.https_port == 443 else f":{self.https_port}"
        h = (host or "").split(":")[0].strip().lower()
        return f"https://{h if h in self.names() else self.domain}{port}{path}"

    def _certbot_base(self) -> list[str]:
        exe = shutil.which("certbot")
        if not exe:
            raise RuntimeError("certbot fehlt. Bitte certbot installieren (apt install certbot).")
        return [exe, "--config-dir", str(self.base / "config"),
                "--work-dir", str(self.base / "work"), "--logs-dir", str(self.base / "logs"),
                "--non-interactive"]

    async def _run(self, args: list[str]) -> int:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            logger.error("certbot nach 5 Minuten abgebrochen")
            raise
        for line in out.decode(errors="replace").splitlines()[-25:]:
            if line.strip():
                logger.info("certbot: %s", line)
        return proc.returncode

    async def obtain(self) -> bool:
        if not self.letsencrypt:
            return self.have_cert()
        if not self.valid_domain():
            logger.error("Ungültiger öffentlicher Domainname: %r", self.domain)
            return False
        try:
            args = self._certbot_base() + ["certonly", "--webroot", "-w", str(self.webroot),
                "--cert-name", self.domain, "--agree-tos", "--keep-until-expiring", "--expand"]
            for d in self.names():
                args += ["-d", d]
        except RuntimeError as exc:
            logger.error("%s", exc)
            return False
        args += ["--email", self.email] if self.email else ["--register-unsafely-without-email"]
        if self.staging:
            args.append("--staging")
        logger.info("Let's Encrypt Zertifikat für %s wird angefordert …", ", ".join(self.names()))
        try:
            rc = await self._run(args)
        except (asyncio.TimeoutError, RuntimeError):
            return False
        if rc == 0 and self.have_cert():
            self._mtime = self._cert_mtime()
            try:
                self._marker().write_text(" ".join(self.names()), encoding="utf-8")
            except OSError:
                pass
            logger.info("Zertifikat für %s ist bereit", self.domain)
            return True
        logger.error("certbot fehlgeschlagen (Exit %s). DNS, Port 80 und Firewall prüfen.", rc)
        return False

    async def renew(self) -> bool:
        if not self.letsencrypt:
            changed = self._cert_mtime() != self._mtime
            self._mtime = self._cert_mtime()
            return changed
        try:
            rc = await self._run(self._certbot_base() + ["renew", "--cert-name", self.domain])
        except (asyncio.TimeoutError, RuntimeError):
            return False
        mtime = self._cert_mtime()
        changed = rc == 0 and mtime != self._mtime
        self._mtime = mtime
        if changed:
            logger.info("Let's Encrypt Zertifikat für %s erneuert", self.domain)
        return changed


def build_http_app(cm: CertManager, redirect: bool = True) -> Starlette:
    async def challenge(request: Request):
        token = request.path_params["token"]
        path = cm.webroot / ".well-known" / "acme-challenge" / token
        if not _TOKEN_RE.fullmatch(token) or not path.is_file():
            return PlainTextResponse("not found", status_code=404)
        return FileResponse(str(path), media_type="text/plain")

    async def other(request: Request):
        if not redirect:
            return PlainTextResponse("HTTPS only", status_code=404)
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(cm.https_url(request.url.path + query, request.headers.get("host", "")), status_code=301)

    return Starlette(routes=[
        Route("/.well-known/acme-challenge/{token}", challenge),
        Route("/{path:path}", other, methods=["GET", "HEAD", "POST"]),
    ])
