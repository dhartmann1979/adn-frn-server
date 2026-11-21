"""SQLite access for the FRN server configuration: rooms and the own FRN password list."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..db import DB
from ..settings import Settings

# columns of a room that the admin portal edits (the rest is internal)
ROOM_COLUMNS = ("name", "enabled", "hidden", "owners", "show_info", "tot", "speechpause", "speechpause_msg", "parrot",
                "parrot_startstop", "unmute_min", "acl_cl", "acl_gw", "acl_info", "bl_regexp", "bl_info", "tg_params")
MAX_ROOMS = 64                      # net00 … net63
PARROT_NAMES = ("test", "parrot", "echo")
DEFAULT_ROOMS = ["Test", "Nachtschicht", "World"]


class Store:
    def __init__(self, db: DB, settings: Settings):
        self.db = db
        self.settings = settings
        self._rooms: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------ rooms
    def rooms(self) -> List[Dict[str, Any]]:
        if self._rooms is None:
            self._fix_indexes()
            self._rooms = [dict(r) for r in self.db.q("SELECT * FROM rooms ORDER BY position, id")]
        return [dict(r) for r in self._rooms]

    def room_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return next((r for r in self.rooms() if r["name"].lower() == (name or "").lower()), None)

    def invalidate(self) -> None:
        self._rooms = None

    def _fix_indexes(self) -> None:
        """Every room keeps its netNN index for ever (the ACL files of the server use it).
        net00 is always the test/parrot room of the Java FRN server."""
        rows = self.db.q("SELECT id, name, idx FROM rooms ORDER BY position, id")
        used = {r["idx"] for r in rows if r["idx"] is not None}
        done = set()
        if 0 not in used:
            cand = next((r for r in rows if r["idx"] is None and r["name"].lower() in PARROT_NAMES), None)
            if cand:
                self.db.x("UPDATE rooms SET idx=0, parrot=1 WHERE id=?", (cand["id"],))
                used.add(0)
                done.add(cand["id"])
        for r in rows:
            if r["idx"] is None and r["id"] not in done:
                i = next((n for n in range(1, MAX_ROOMS) if n not in used), None)
                if i is None:
                    continue
                self.db.x("UPDATE rooms SET idx=? WHERE id=?", (i, r["id"]))
                used.add(i)

    def ensure_rooms(self, names: Optional[List[str]] = None) -> None:
        if self.db.q("SELECT 1 FROM rooms LIMIT 1"):
            return
        names = names or DEFAULT_ROOMS
        if not any(n.lower() in PARROT_NAMES for n in names):
            names = ["Test"] + list(names)
        for i, name in enumerate(names):
            self.room_create(name, i, {"parrot": 1, "tot": 60} if name.lower() in PARROT_NAMES else {})
        if not self.settings.get("frn.default_room"):
            self.settings.update({"frn.default_room": next(n for n in names if n.lower() not in PARROT_NAMES)
                                  if len(names) > 1 else names[0]}, "setup")

    def free_index(self) -> Optional[int]:
        used = {r["idx"] for r in self.rooms()}
        return next((n for n in range(1, MAX_ROOMS) if n not in used), None)

    def room_create(self, name: str, position: Optional[int] = None, extra: Optional[Dict[str, Any]] = None) -> int:
        if position is None:
            position = (self.db.q("SELECT MAX(position) AS m FROM rooms")[0]["m"] or 0) + 1
        extra = {k: v for k, v in (extra or {}).items() if k in ROOM_COLUMNS and k != "name"}
        cols = {"name": name, "position": position, **extra}
        cur = self.db.x(f"INSERT INTO rooms ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
        self.invalidate()
        return cur.lastrowid

    def room_update(self, room_id: int, values: Dict[str, Any]) -> None:
        values = {k: v for k, v in values.items() if k in ROOM_COLUMNS}
        if values:
            self.db.x(f"UPDATE rooms SET {', '.join(k + '=?' for k in values)} WHERE id=?", [*values.values(), room_id])
        self.invalidate()

    def room_delete(self, room_id: int) -> None:
        self.db.x("DELETE FROM rooms WHERE id=?", (room_id,))
        self.invalidate()

    def room_order(self, ids: List[int]) -> None:
        self.db.tx([("UPDATE rooms SET position=? WHERE id=?", (i, rid)) for i, rid in enumerate(ids)])
        self.invalidate()

    # ------------------------------------------------------------ own FRN password list (stand-alone, FRNPasswd.xml)
    def account_get(self, email: str) -> Optional[Dict[str, Any]]:
        rows = self.db.q("SELECT * FROM frn_accounts WHERE email=?", (email.strip().lower(),))
        return dict(rows[0]) if rows else None

    def accounts(self, with_password: bool = False) -> List[Dict[str, Any]]:
        hide = () if with_password else ("password", "password_hash")
        return [{k: r[k] for k in r.keys() if k not in hide} for r in self.db.q("SELECT * FROM frn_accounts ORDER BY callsign, email")]

    def account_save(self, email: str, callsign: str, name: str, password: Optional[str], disabled: bool = False) -> None:
        email = email.strip().lower()
        if self.account_get(email):
            self.db.x("UPDATE frn_accounts SET callsign=?, name=?, disabled=? WHERE email=?",
                      (callsign.upper(), name, 1 if disabled else 0, email))
            if password:
                self.db.x("UPDATE frn_accounts SET password=? WHERE email=?", (password, email))
        else:
            self.db.x("INSERT INTO frn_accounts (email, callsign, name, password_hash, password, disabled, created_at) "
                      "VALUES (?,?,?,?,?,?,?)", (email, callsign.upper(), name, "", password or "", 1 if disabled else 0, time.time()))

    def account_delete(self, email: str) -> None:
        self.db.x("DELETE FROM frn_accounts WHERE email=?", (email.strip().lower(),))

    def account_seen(self, email: str) -> None:
        self.db.x("UPDATE frn_accounts SET last_login=? WHERE email=?", (time.time(), email.strip().lower()))
