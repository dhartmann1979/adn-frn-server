"""
N8 update guard 1.0 – shared by the N8schicht services (HBlink4-FreeRadioID, adn-frn-server, N8-HotSpot;
N8 Crosslink does the same in update.sh). Same file in every repository.

An update from the web interface works like this:

1. before the restart the updater calls ``mark_pending(state_dir, old, new)``,
2. the service restarts with the new code,
3. ``ExecStartPre=-/bin/sh scripts/n8-update-guard.sh <repo> <state_dir>`` counts the starts; after three failed
   starts it resets the checkout to the old commit (rollback),
4. the new code calls ``await startup_check(state_dir, url)`` once it serves: if the web interface answers,
   the update counts as successful; if it does not answer within ``timeout`` s, the process exits with
   code 1 so systemd starts it again (→ step 3).

The outcome is kept in ``update.result`` (JSON) and shown in Admin → Updates.
"""
import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("n8.update")
PENDING = "update.pending"
RESULT = "update.result"


def _p(state_dir, name: str) -> Path:
    return Path(state_dir) / name


def mark_pending(state_dir, old: str, new: str, old_version: str = "", new_version: str = "") -> None:
    """Remember what was installed, before the service restarts."""
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    txt = f"old={old}\nnew={new}\ntries=0\ntime={int(time.time())}\nold_version={old_version}\nnew_version={new_version}\n"
    tmp = _p(state_dir, PENDING + ".tmp")
    tmp.write_text(txt)
    os.replace(tmp, _p(state_dir, PENDING))


def _read_pending(state_dir) -> Optional[Dict[str, str]]:
    try:
        lines = _p(state_dir, PENDING).read_text().splitlines()
    except OSError:
        return None
    return dict(line.split("=", 1) for line in lines if "=" in line)


def _write_result(state_dir, ok: bool, info: Dict[str, str], message: str = "") -> Dict[str, Any]:
    res = {"ok": ok, "from": info.get("old_version") or info.get("old", "")[:7],
           "to": info.get("new_version") or info.get("new", "")[:7],
           "old": info.get("old", ""), "new": info.get("new", ""), "time": int(time.time()), "message": message}
    try:
        _p(state_dir, RESULT).write_text(json.dumps(res))
    except OSError as e:
        log.warning(f"update result not saved: {e}")
    return res


def last_result(state_dir) -> Optional[Dict[str, Any]]:
    """Outcome of the last update from the web interface (None if there was none)."""
    try:
        return json.loads(_p(state_dir, RESULT).read_text())
    except (OSError, ValueError):
        return None


def local_url(host: str, port: int, path: str = "/", https: bool = False) -> str:
    """Address of the own web interface for the check (listening on all addresses → 127.0.0.1)."""
    h = (host or "").strip("[]")
    if h in ("", "0.0.0.0", "::", "*"):
        h = "127.0.0.1"
    if ":" in h:
        h = f"[{h}]"
    return f"{'https' if https else 'http'}://{h}:{int(port)}{path}"


def pending(state_dir) -> bool:
    return _p(state_dir, PENDING).exists()


def _get(url: str, timeout: float) -> int:
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):   # a redirect (e.g. to HTTPS) is an answer, too
            return None
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, headers={"User-Agent": "n8-update-guard"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


async def startup_check(state_dir, url: str, timeout: float = 90, delay: float = 3) -> Optional[Dict[str, Any]]:
    """Run as a background task after the start. Only does something after an update."""
    info = _read_pending(state_dir)
    if info is None:
        return None
    await asyncio.sleep(delay)
    t0 = time.monotonic()
    err = ""
    while time.monotonic() - t0 < timeout:
        try:
            code = await asyncio.to_thread(_get, url, 5)
            if code < 500:
                try:
                    _p(state_dir, PENDING).unlink()
                except OSError:
                    pass
                res = _write_result(state_dir, True, info)
                log.info(f"⬆️ Update checked: web interface answers ({res['from']} → {res['to']})")
                return res
            err = f"HTTP {code}"
        except Exception as e:  # noqa: BLE001 – any failure counts as "not answering"
            err = str(e)
        await asyncio.sleep(3)
    log.error(f"⬆️ Web interface does not answer after the update ({err}) – restarting so the guard can roll back")
    os._exit(1)
