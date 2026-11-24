"""
Start:              python -m frnadn
Superadmin:         python -m frnadn set-superadmin USERNAME        (asks for the password)
New password:       python -m frnadn reset-password USERNAME
Current values:     python -m frnadn show-settings                  (JSON, used by setup.sh)
Apply setup:        python -m frnadn apply-setup FILE.json          (JSON from install.sh)
Write config:       python -m frnadn write-config                   (server.properties etc. from SQLite)
FRN account:        python -m frnadn add-account EMAIL CALLSIGN     (stand-alone password list; asks for the password)
Portal token:       python -m frnadn api-token NAME                 (API token for the HobbyRadioPortal, printed once)
Behind the portal:  python -m frnadn behind-proxy                   (own HTTPS off; prints domain/e-mail as JSON)
Backup:             python -m frnadn backup [DIR]                   (encrypted .frnbak; asks for a password, min. 10)
Restore:            python -m frnadn restore FILE.frnbak            (stop frnadn first; asks for the backup password)

Passwords can also come from the environment variable FRNADN_PASSWORD (scripts).
"""
import getpass
import json
import os
import sys

G, R, N = "\033[0;32m", "\033[0;31m", "\033[0m"


def _ctx():
    from . import app as a
    a.ctx = a.Ctx()
    return a.ctx


def _password(prompt: str, min_len: int = 10) -> str:
    pw = os.environ.get("FRNADN_PASSWORD")
    if pw is None:
        pw = getpass.getpass(prompt)
        if getpass.getpass("Repeat: ") != pw:
            raise SystemExit("The passwords differ.")
    if len(pw) < min_len:
        raise SystemExit(f"At least {min_len} characters.")
    return pw


def apply_setup(path: str) -> int:
    """{"settings": {...}, "test_room": "Test", "rooms": [...], "superadmin": {"username", "password"}}"""
    c = _ctx()
    data = json.loads(open(path, encoding="utf-8").read())
    rooms = [r.strip() for r in data.get("rooms") or [] if r.strip()]
    test = (data.get("test_room") or "").strip()
    if (rooms or test) and not c.db.q("SELECT 1 FROM rooms LIMIT 1"):
        c.store.room_create(test or "Test", 0, {"parrot": 1, "tot": 60})
        for i, name in enumerate(r for r in rooms if r.lower() != (test or "test").lower()):
            c.store.room_create(name, i + 1)
        c.store.rooms()                                 # assigns net00 … netNN
        print(f"   {G}✓{N} Räume angelegt: {test or 'Test'} (net00, Parrot), {', '.join(rooms)}")
    else:
        c.store.ensure_rooms()
        have = {r["name"].lower() for r in c.store.rooms()}
        new = [r for r in rooms if r.lower() not in have]
        for name in new:
            c.store.room_create(name)
        if new:
            print(f"   {G}✓{N} Räume dazu: {', '.join(new)}")
    settings = {k: v for k, v in (data.get("settings") or {}).items() if v is not None}
    if not settings.get("frn.default_room") and rooms:
        settings["frn.default_room"] = rooms[0]
    changed = c.settings.update(settings, "setup")
    print(f"   {G}✓{N} Einstellungen in SQLite gespeichert ({len(changed)} geändert)")
    sa = data.get("superadmin") or {}
    if sa.get("username") and sa.get("password"):
        c.auth.set_superadmin(sa["username"], sa["password"])
        print(f"   {G}✓{N} Superadmin {sa['username']} angelegt (Passwort als scrypt-Hash gespeichert)")
    c.java.write_config()
    print(f"   {G}✓{N} {c.java.home / 'server.properties'} geschrieben")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("run", "serve"):
        from .app import main as run
        run()
        return 0
    cmd = args[0]
    if cmd == "set-superadmin" and len(args) > 1:
        c = _ctx()
        c.auth.set_superadmin(args[1], _password(f"Password for {args[1]} (min. 10): "))
        print(f"{G}✓{N} {args[1]} is the superadmin.")
        return 0
    if cmd == "reset-password" and len(args) > 1:
        c = _ctx()
        c.auth.reset(args[1], _password(f"New password for {args[1]} (min. 10): "))
        print(f"{G}✓{N} Password of {args[1]} set. All sessions of {args[1]} ended.")
        return 0
    if cmd == "show-settings":
        c = _ctx()
        s = c.settings.all()
        s.pop("sysman.password", None)
        s["_rooms"] = [r["name"] for r in c.store.rooms()]
        s["_superadmin"] = c.auth.has_superadmin()
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    if cmd == "apply-setup" and len(args) > 1:
        return apply_setup(args[1])
    if cmd == "add-account" and len(args) > 2:
        c = _ctx()
        c.store.account_save(args[1], args[2], " ".join(args[3:]), _password(f"FRN password for {args[1]} (min. 4): ", 4))
        c.java.write_config()
        print(f"{G}✓{N} FRN account {args[1]} saved – restart the FRN server to use it.")
        return 0
    if cmd in ("backup", "restore"):
        from pathlib import Path
        from . import backup as bk
        data = Path(os.environ.get("FRNADN_DATA", Path(__file__).resolve().parent.parent / "data"))
        home = Path(os.environ.get("FRNADN_FRN_HOME", data / "frn"))
        try:
            if cmd == "backup":
                pw = _password("Password for the backup (min. 10): ", bk.MIN_PASSWORD)
                p = bk.create(data, home, pw, "cli", Path(args[1]) if len(args) > 1 else None)
                print(f"{G}✓{N} {p} ({p.stat().st_size // 1024} KB) – keep the password, without it the backup cannot be opened.")
                return 0
            if len(args) < 2:
                print("usage: python -m frnadn restore FILE.frnbak", file=sys.stderr)
                return 2
            pw = os.environ.get("FRNADN_PASSWORD")
            if pw is None:
                pw = getpass.getpass("Password of the backup: ")
            tmp = data / "restore-cli.tar"
            try:
                m = bk.open_backup(Path(args[1]), pw, tmp)
                res = bk.apply(tmp, data, home)
            finally:
                tmp.unlink(missing_ok=True)
            print(f"{G}✓{N} Backup from {m.get('host')} ({m.get('version')}) restored – previous state in {res['kept']}.")
            print("  Start the dashboard again (systemctl start frnadn); it writes the FRN configuration and you log in again.")
            return 0
        except bk.BackupError as e:
            print(f"{R}✗{N} {e}", file=sys.stderr)
            return 2
    if cmd == "api-token" and len(args) > 1:
        c = _ctx()
        try:
            print(c.auth.create_api_token(" ".join(args[1:]), "installer", "")["token"])
        except Exception as e:   # AuthError / ValueError: name or limit
            print(e, file=sys.stderr)
            return 2
        return 0
    if cmd == "behind-proxy":
        # Used by the HobbyRadioPortal installer: nginx of the portal takes ports 80/443 and the domain, the dashboard
        # then listens on 127.0.0.1 (FRNADN_BIND/FRNADN_PORT in a systemd drop-in written by the portal).
        c = _ctx()
        before = {"https_was": bool(c.settings.get("https.enabled")), "domain": c.settings.get("https.domain") or "",
                  "email": c.settings.get("https.email") or "", "title": c.settings.get("dashboard.title") or ""}
        if before["https_was"]:
            c.settings.update({"https.enabled": False}, "hobbyradioportal")
        print(json.dumps(before))
        return 0
    if cmd == "write-config":
        c = _ctx()
        c.store.ensure_rooms()
        c.java.write_config()
        print(f"{G}✓{N} {c.java.home / 'server.properties'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
