"""Full backup and restore of adn-frn-server.

A backup (``*.frnbak``) is a tar.gz, encrypted with a password of your choice (format ``n8mig``: scrypt + SHAKE-256 +
HMAC-SHA-256, standard library only – see n8mig.py; HBlink4-FreeRadioID uses the same format):

    manifest.json            app, format, version, time, host, title, counts
    data/frnadn.db           the whole SQLite database (consistent copy via the SQLite backup API): settings, users,
                             rooms, access lists, FRN accounts, statistics, chat, client logos …
    data/branding/…          logo, site icon, link menu
    frn/…                    configuration of the Java FRN server: server.properties, log4j.xml, acl/ (no logs)

Not included: Let's Encrypt certificates (fetched again), logs, update state, older backups.

Restore
    • web:     Admin → System → Backup & restore – the upload is checked, then the dashboard restarts and applies it
               before it opens the database (``restore.pending.tar``), writes the FRN configuration and restarts the FRN server
    • console: ``frnadn restore FILE`` (service stopped) – also used by ``scripts/install.sh`` (FRNADN_RESTORE=…)
The current state is kept in ``<data>/before-restore-<time>/`` first.
"""
import io
import json
import os
import shutil
import socket
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__, n8mig

FORMAT = "adn-frn-server-backup"
SCHEMA = 1
PENDING = "restore.pending.tar"
DONE = "restore.done.json"
MIN_PASSWORD = 10
MAX_FILES = 20000
MAX_BYTES = 4 * 1024 ** 3
KEEP = 5
SKIP_DATA = {"backups", "letsencrypt", "frn", "update.pending", "update.pending.tmp", "update.result", PENDING, DONE,
             "frnadn.db", "frnadn.db-wal", "frnadn.db-shm", "restore-upload.frnbak"}


class BackupError(Exception):
    pass


def _name() -> str:
    return time.strftime(f"frn-backup-{socket.gethostname()}-%Y%m%d-%H%M%S.frnbak")


def _counts(db_path: Path) -> Dict[str, int]:
    out = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for key, table in (("rooms", "rooms"), ("users", "users"), ("accounts", "frn_accounts"), ("stations", "stations"),
                           ("talks", "talks"), ("lists", "frn_lists")):
            try:
                out[key] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                out[key] = 0
        try:
            row = con.execute("SELECT value FROM settings WHERE key='dashboard.title'").fetchone()
            out["_title"] = json.loads(row[0]) if row else ""
        except (sqlite3.Error, ValueError):
            out["_title"] = ""
    finally:
        con.close()
    return out


def create(data: Path, frn_home: Path, password: str, actor: str, out_dir: Optional[Path] = None) -> Path:
    """Creates an encrypted backup in out_dir (default <data>/backups) and returns its path."""
    if len(password or "") < MIN_PASSWORD:
        raise BackupError(f"The backup password needs at least {MIN_PASSWORD} characters.")
    data, frn_home = Path(data), Path(frn_home)
    out_dir = Path(out_dir or data / "backups")
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    with tempfile.TemporaryDirectory(prefix="frnadn-backup-", dir=out_dir) as tmp:
        snap = Path(tmp) / "frnadn.db"
        src = sqlite3.connect(str(data / "frnadn.db"))
        dst = sqlite3.connect(str(snap))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        counts = _counts(snap)
        title = counts.pop("_title", "")
        manifest = {"app": "adn-frn-server", "format": FORMAT, "schema": SCHEMA, "version": __version__, "created": time.time(),
                    "created_by": actor, "host": socket.gethostname(), "title": title, "counts": counts,
                    "contents": ["Settings", "Users", "Rooms", "Access lists", "FRN accounts", "Statistics", "Chat",
                                 "Client logos", "Branding", "server.properties"]}
        plain = Path(tmp) / "backup.tar.gz"
        with tarfile.open(plain, "w:gz") as tar:
            m = json.dumps(manifest, indent=1, ensure_ascii=False).encode()
            ti = tarfile.TarInfo("manifest.json")
            ti.size, ti.mtime, ti.mode = len(m), int(time.time()), 0o600
            tar.addfile(ti, io.BytesIO(m))
            tar.add(snap, arcname="data/frnadn.db")
            for item in sorted(data.iterdir()):
                if item.name in SKIP_DATA or item.name.startswith(("before-restore-", ".")) or item.is_symlink():
                    continue
                tar.add(item, arcname="data/" + item.name, filter=_clean)
            if frn_home.is_dir():
                for item in sorted(frn_home.iterdir()):
                    if item.name in ("logs", "backups") or item.is_symlink():
                        continue
                    tar.add(item, arcname="frn/" + item.name, filter=_clean)
        out = out_dir / _name()
        n8mig.encrypt_file(plain, out, password)
    prune(out_dir)
    return out


def _clean(ti: tarfile.TarInfo) -> Optional[tarfile.TarInfo]:
    if not (ti.isfile() or ti.isdir()) or ti.name.endswith(("-wal", "-shm")) or "/logs/" in ti.name + "/":
        return None
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    return ti


def prune(out_dir: Path) -> None:
    files = sorted(Path(out_dir).glob("frn-backup-*.frnbak"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP:]:
        old.unlink(missing_ok=True)


def listing(out_dir: Path) -> List[Dict[str, Any]]:
    d = Path(out_dir)
    if not d.is_dir():
        return []
    return [{"name": p.name, "size": p.stat().st_size, "created": p.stat().st_mtime}
            for p in sorted(d.glob("frn-backup-*.frnbak"), key=lambda p: p.stat().st_mtime, reverse=True)]


def check_tar(tar_path: Path) -> Dict[str, Any]:
    """Every member is checked before anything is changed: only data/… and frn/…, no links, no .., size limits."""
    total, n, manifest = 0, 0, None
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for m in tar:
                n += 1
                total += m.size
                name = m.name
                if n > MAX_FILES or total > MAX_BYTES:
                    raise BackupError("The backup is too large.")
                if name.startswith("/") or ".." in Path(name).parts or not (m.isfile() or m.isdir()):
                    raise BackupError(f"Unsafe entry in the backup: {name}")
                if name == "manifest.json":
                    manifest = json.loads(tar.extractfile(m).read(1_000_000))
                elif not (name.startswith(("data/", "frn/")) or name in ("data", "frn")):
                    raise BackupError(f"Unexpected entry in the backup: {name}")
            names = tar.getnames()
    except (tarfile.TarError, OSError, ValueError) as e:
        raise BackupError(f"The backup is damaged: {e}") from None
    if not manifest or manifest.get("format") != FORMAT:
        raise BackupError("This is not a backup of adn-frn-server.")
    if "data/frnadn.db" not in names:
        raise BackupError("The backup has no database.")
    return manifest


def open_backup(path: Path, password: str, dest_tar: Path) -> Dict[str, Any]:
    """Decrypts a .frnbak into dest_tar (600) and checks it. Returns the manifest."""
    try:
        n8mig.decrypt_file(path, dest_tar, password)
    except n8mig.MigrationError as e:
        msg = str(e)
        if "passt nicht" in msg:
            msg = "Wrong password or damaged file."
        elif "Kein N8" in msg:
            msg = "This is not a backup of adn-frn-server (.frnbak)."
        raise BackupError(msg) from None
    try:
        return check_tar(dest_tar)
    except BackupError:
        Path(dest_tar).unlink(missing_ok=True)
        raise


def apply(tar_path: Path, data: Path, frn_home: Path) -> Dict[str, Any]:
    """Replaces database, branding and FRN configuration with the backup. The old state goes to before-restore-<time>/."""
    data, frn_home = Path(data), Path(frn_home)
    manifest = check_tar(tar_path)
    keep = data / time.strftime("before-restore-%Y%m%d-%H%M%S")
    keep.mkdir(mode=0o700)
    for name in ("frnadn.db", "frnadn.db-wal", "frnadn.db-shm", "branding"):
        if (data / name).exists():
            shutil.move(str(data / name), str(keep / name))
    if frn_home.is_dir():
        (keep / "frn").mkdir()
        for item in frn_home.iterdir():
            if item.name not in ("logs",):
                shutil.move(str(item), str(keep / "frn" / item.name))
    frn_home.mkdir(parents=True, exist_ok=True)
    try:
        _extract(tar_path, data, frn_home)
    except Exception:
        _rollback(keep, data, frn_home)
        raise
    return {"manifest": manifest, "kept": str(keep)}


def _rollback(keep: Path, data: Path, frn_home: Path) -> None:
    for name in ("frnadn.db", "frnadn.db-wal", "frnadn.db-shm", "branding"):
        t = data / name
        if t.is_dir():
            shutil.rmtree(t, ignore_errors=True)
        else:
            t.unlink(missing_ok=True)
        if (keep / name).exists():
            shutil.move(str(keep / name), str(t))
    if (keep / "frn").is_dir():
        for item in list(frn_home.iterdir()):
            if item.name != "logs":
                shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
        for item in (keep / "frn").iterdir():
            shutil.move(str(item), str(frn_home / item.name))


def _extract(tar_path: Path, data: Path, frn_home: Path) -> None:
    with tarfile.open(tar_path, "r:gz") as tar:
        for m in tar:
            if m.name == "manifest.json" or m.name in ("data", "frn"):
                continue
            base, rel = (data, m.name[5:]) if m.name.startswith("data/") else (frn_home, m.name[4:])
            target = (base / rel).resolve()
            if not str(target).startswith(str(base.resolve())):
                raise BackupError(f"Unsafe entry in the backup: {m.name}")
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, 0o640 if target.suffix != ".db" else 0o600)
    (frn_home / "logs").mkdir(exist_ok=True)
    con = sqlite3.connect(str(data / "frnadn.db"))
    try:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.execute("DELETE FROM sessions")          # everybody logs in again
        con.commit()
    finally:
        con.close()
    if ok != "ok":
        raise BackupError(f"Database in the backup is damaged: {ok}")


def apply_pending(data: Path, frn_home: Path) -> Optional[Dict[str, Any]]:
    """At start, before the database is opened: apply a restore that the web interface has prepared."""
    p = Path(data) / PENDING
    if not p.is_file():
        return None
    try:
        res = apply(p, data, frn_home)
        res.update(ok=True, applied=time.time())
    except Exception as e:   # never block the start – the old state stays (or is in before-restore-*)
        res = {"ok": False, "error": str(e), "applied": time.time()}
    p.unlink(missing_ok=True)
    tmp = Path(data) / (DONE + ".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False))
    tmp.replace(Path(data) / DONE)
    return res
