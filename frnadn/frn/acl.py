"""SQLite mirror and FRN XML bridge for the server's per-room ACL files."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..db import DB
from .store import Store

log = logging.getLogger("frnadn.frn.acl")

FILE_KIND = {"AdminList": "admin", "MuteList": "mute", "BlockList": "block", "AccessList": "access"}
KIND_FILE = {v: k for k, v in FILE_KIND.items()}
ENTRY_ORDER = {
    "admin": ("ID", "EMailAddressEncrypted", "OperatorName", "ClientType", "BandChannel", "Country", "CityCityPart", "Admin", "ModificationDate", "Comment"),
    "mute": ("ID", "EMailAddressEncrypted", "OperatorName", "ClientType", "BandChannel", "Country", "CityCityPart", "Admin", "ModificationDate", "Comment"),
    "block": ("ID", "EMailAddressEncrypted", "OperatorName", "ClientType", "BandChannel", "Country", "CityCityPart", "Admin", "ModificationDate", "Comment"),
    "access": ("ID", "EMailAddress", "OperatorName", "ClientType", "BandChannel", "Country", "CityCityPart", "RXOnly"),
}


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _entry_fields(node: ET.Element) -> Dict[str, str]:
    return {child.tag: child.text or "" for child in list(node)}


def _operator(fields: Dict[str, Any]) -> tuple[str, str]:
    value = str(fields.get("OperatorName") or "")
    call, _, name = value.partition(",")
    return call.strip(), name.strip()


def _stamp(value: str) -> float:
    if value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError):
            pass
    return time.time()


class ACLStore:
    """Keep SQLite in sync with FRN's XStream XML while preserving imported fields."""

    def __init__(self, db: DB, store: Store, home: Path):
        self.db, self.store, self.home = db, store, Path(home)
        self.acl_dir = self.home / "acl"

    def _rooms(self) -> Dict[int, Dict[str, Any]]:
        return {int(r["idx"]): dict(r) for r in self.store.rooms() if r.get("idx") is not None}

    def sync_from_files(self) -> List[str]:
        """Import only changed, valid files; missing or malformed files never clear SQLite."""
        errors: List[str] = []
        rooms = self._rooms()
        for path in sorted(self.acl_dir.glob("*.xml")):
            match = re.fullmatch(r"(AdminList|MuteList|BlockList|AccessList)(\d{1,2})\.xml", path.name)
            if not match:
                continue
            file_kind, raw_idx = match.groups()
            kind, idx = FILE_KIND[file_kind], int(raw_idx)
            room = rooms.get(idx)
            if room is None:
                errors.append(f"{path.name}: room index {idx:02d} does not exist")
                continue
            try:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                if self.db.kv_get(f"acl-file-sha:{path.name}") == digest:
                    continue
                root = ET.fromstring(raw)
                expected_root = {"admin": "Admin", "mute": "Mute", "block": "Block", "access": "Access"}[kind]
                if root.tag != expected_root:
                    raise ValueError(f"expected <{expected_root}> root, found <{root.tag}>")
                entries = [n for n in root.iter("Client") if n is not root]
                meta = {n.tag: n.text or "" for n in list(root) if n.tag != "Client"}
                self._replace_from_xml(kind, room, entries, meta, digest, path.name)
            except (OSError, ET.ParseError, ValueError) as exc:
                log.warning("Could not import ACL file %s: %s", path, exc)
                errors.append(f"{path.name}: {exc}")
        return errors

    def _replace_from_xml(self, kind: str, room: Dict[str, Any], entries: List[ET.Element], meta: Dict[str, str], digest: str, file_name: str) -> None:
        rid = int(room["id"])
        statements = []
        if kind == "access":
            statements.append(("DELETE FROM room_access WHERE room_id=?", (rid,)))
            for i, node in enumerate(entries):
                fields = _entry_fields(node)
                call, _ = _operator(fields)
                email = fields.get("EMailAddress", "").strip() or f"id:{fields.get('ID') or i}"
                statements.append(("INSERT OR REPLACE INTO room_access(room_id,email,can_tx,note) VALUES(?,?,?,?)",
                                   (rid, email, 0 if _bool(fields.get("RXOnly")) else 1, json.dumps(fields, ensure_ascii=False))))
            statements.extend([
                ("UPDATE rooms SET access_on=?, txright_on=?, notice=? WHERE id=?",
                 (int(_bool(meta.get("Enabled"))), int(_bool(meta.get("TRXControl"))), meta.get("InfoMessage", ""), rid)),
            ])
        else:
            statements.append(("DELETE FROM frn_lists WHERE kind=? AND room_id=?", (kind, rid)))
            for i, node in enumerate(entries):
                fields = _entry_fields(node)
                call, _ = _operator(fields)
                email = fields.get("EMailAddressEncrypted", "").strip() or f"id:{fields.get('ID') or i}"
                statements.append(("INSERT OR REPLACE INTO frn_lists(kind,room_id,email,callsign,info,added_by,ts) VALUES(?,?,?,?,?,?,?)",
                                   (kind, rid, email, call, json.dumps(fields, ensure_ascii=False), "FRN XML import",
                                    _stamp(fields.get("ModificationDate", "")))))
        statements.extend([
            ("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (f"acl-file-meta:{file_name}", json.dumps(meta, ensure_ascii=False))),
            ("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
             (f"acl-file-sha:{file_name}", digest)),
        ])
        self.db.tx(statements)
        self.store.invalidate()

    def payload(self) -> Dict[str, Any]:
        errors = self.sync_from_files()
        rooms = []
        files = []
        for room in self.store.rooms():
            rid, idx = int(room["id"]), int(room["idx"])
            rooms.append({"id": rid, "idx": idx, "name": room["name"], "access_on": bool(room["access_on"]),
                          "txright_on": bool(room["txright_on"]), "notice": room.get("notice", "")})
            for kind, fname in KIND_FILE.items():
                file_name = f"{fname}{idx:02d}.xml"
                path = self.acl_dir / file_name
                rows = self._entries(kind, rid)
                if path.exists() or rows:
                    files.append({"file": file_name, "kind": fname, "room": room["name"], "room_id": rid, "idx": idx,
                                  "mtime": path.stat().st_mtime if path.exists() else None, "entries": rows})
        return {"rooms": rooms, "files": files, "errors": errors}

    def _entries(self, kind: str, rid: int) -> List[Dict[str, Any]]:
        if kind == "access":
            rows = self.db.q("SELECT email,can_tx,note FROM room_access WHERE room_id=? ORDER BY email COLLATE NOCASE", (rid,))
            out = []
            for n, row in enumerate(rows):
                fields = json.loads(row["note"] or "{}")
                call, name = _operator(fields)
                out.append({"row_id": row["email"] or str(n), "id": fields.get("ID", ""),
                            "email": fields.get("EMailAddress") or row["email"], "callsign": call, "name": name,
                            "client_type": fields.get("ClientType", "2"), "band_channel": fields.get("BandChannel", "PC Only"),
                            "country": fields.get("Country", ""), "city": fields.get("CityCityPart", ""),
                            "can_tx": bool(row["can_tx"]), "fields": fields})
            return out
        rows = self.db.q("SELECT id,email,callsign,info FROM frn_lists WHERE kind=? AND room_id=? ORDER BY callsign COLLATE NOCASE,email COLLATE NOCASE",
                         (kind, rid))
        out = []
        for row in rows:
            fields = json.loads(row["info"] or "{}")
            call, name = _operator(fields)
            out.append({"row_id": row["id"], "id": fields.get("ID", ""),
                        "email": fields.get("EMailAddressEncrypted") or row["email"], "callsign": row["callsign"] or call,
                        "name": name, "client_type": fields.get("ClientType", "2"), "band_channel": fields.get("BandChannel", ""),
                        "country": fields.get("Country", ""), "city": fields.get("CityCityPart", ""), "fields": fields})
        return out

    def save(self, user: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one add/edit/delete/config action and export a safety-backed FRN XML file."""
        self.sync_from_files()
        action, kind = str(data.get("action", "")), str(data.get("kind", ""))
        if kind not in KIND_FILE.values():
            raise ValueError("Unknown ACL list.")
        try:
            rid = int(data.get("room_id"))
        except (TypeError, ValueError):
            raise ValueError("Choose a room.")
        room = next((r for r in self.store.rooms() if int(r["id"]) == rid), None)
        if room is None:
            raise ValueError("The room no longer exists.")
        idx = int(room["idx"])
        if kind == "access" and action == "config":
            self.db.x("UPDATE rooms SET access_on=?,txright_on=?,notice=? WHERE id=?",
                       (int(bool(data.get("access_on"))), int(bool(data.get("txright_on"))),
                        str(data.get("notice", ""))[:1000], rid))
        elif action in ("add", "edit"):
            entry = data.get("entry") or {}
            entry_id = str(entry.get("id", "")).strip()[:120]
            email_key = str(entry.get("email", "")).strip()[:250]
            callsign = str(entry.get("callsign", "")).strip().upper()[:30]
            name = str(entry.get("name", "")).strip()[:80]
            if not entry_id or not email_key:
                raise ValueError("Enter the FRN client ID and e-mail address.")
            if action == "add" and ("@" not in email_key or any(c.isspace() for c in email_key)):
                raise ValueError("Enter a valid e-mail address.")
            client_type = str(entry.get("client_type", "2"))
            if client_type not in ("0", "1", "2"):
                raise ValueError("Client type must be Crosslink (0), Gateway (1), or PC Only (2).")
            base = {"ID": entry_id, "OperatorName": callsign + (", " + name if name else ""), "ClientType": client_type,
                    "BandChannel": str(entry.get("band_channel", "PC Only" if client_type == "2" else ""))[:100],
                    "Country": str(entry.get("country", ""))[:80], "CityCityPart": str(entry.get("city", ""))[:100]}
            if kind == "access":
                fields = {**base, "EMailAddress": email_key, "RXOnly": "false" if bool(entry.get("can_tx", True)) else "true"}
                stored_email = email_key
                if action == "edit":
                    old_email = str(data.get("old_email", ""))
                    old = self.db.q("SELECT note FROM room_access WHERE room_id=? AND email=?", (rid, old_email))
                    if not old:
                        raise ValueError("This ACL entry no longer exists.")
                    if email_key != old_email and self.db.q("SELECT 1 FROM room_access WHERE room_id=? AND email=?", (rid, email_key)):
                        raise ValueError("That e-mail is already on the access list.")
                    preserved = json.loads(old[0]["note"] or "{}")
                    preserved.update(fields)
                    fields = preserved
                    self.db.x("DELETE FROM room_access WHERE room_id=? AND email=?", (rid, old_email))
                elif self.db.q("SELECT 1 FROM room_access WHERE room_id=? AND email=?", (rid, stored_email)):
                    raise ValueError("That e-mail is already on the access list.")
                self.db.x("INSERT INTO room_access(room_id,email,can_tx,note) VALUES(?,?,?,?)",
                          (rid, stored_email, int(bool(entry.get("can_tx", True))), json.dumps(fields, ensure_ascii=False)))
            else:
                fields = {**base, "EMailAddressEncrypted": email_key}
                if kind == "admin":
                    # The FRN client/server checks this flag in AdminList entries.
                    fields["Admin"] = "true"
                old_id = data.get("row_id")
                if action == "edit":
                    row = self.db.q("SELECT info FROM frn_lists WHERE id=? AND kind=? AND room_id=?", (old_id, kind, rid))
                    if not row:
                        raise ValueError("This ACL entry no longer exists.")
                    old_fields = json.loads(row[0]["info"] or "{}")
                    old_fields.update(fields)
                    fields = old_fields
                    self.db.x("UPDATE frn_lists SET email=?,callsign=?,info=? WHERE id=? AND kind=? AND room_id=?",
                              (email_key, callsign, json.dumps(fields, ensure_ascii=False), old_id, kind, rid))
                else:
                    if self.db.q("SELECT 1 FROM frn_lists WHERE kind=? AND room_id=? AND email=?", (kind, rid, email_key)):
                        raise ValueError("That e-mail is already on this list.")
                    self.db.x("INSERT INTO frn_lists(kind,room_id,email,callsign,info,added_by,ts) VALUES(?,?,?,?,?,?,?)",
                              (kind, rid, email_key, callsign, json.dumps(fields, ensure_ascii=False), user, time.time()))
        elif action == "delete":
            row_id = data.get("row_id")
            if kind == "access":
                email = str(row_id or "")
                self.db.x("DELETE FROM room_access WHERE room_id=? AND email=?", (rid, email))
            else:
                self.db.x("DELETE FROM frn_lists WHERE id=? AND kind=? AND room_id=?", (row_id, kind, rid))
        else:
            raise ValueError("Unknown ACL action.")
        self.store.invalidate()
        room = next(r for r in self.store.rooms() if int(r["id"]) == rid)
        self._write_file(kind, room)
        return {"ok": True, "restart_needed": True}

    def _write_file(self, kind: str, room: Dict[str, Any]) -> None:
        idx, rid = int(room["idx"]), int(room["id"])
        file_name = f"{KIND_FILE[kind]}{idx:02d}.xml"
        path = self.acl_dir / file_name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_dir = self.acl_dir / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(backup_dir, 0o700)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = backup_dir / f"{file_name}.{stamp}.bak"
            shutil.copy2(path, backup)
            os.chmod(backup, 0o600)
        root_name = {"admin": "Admin", "mute": "Mute", "block": "Block", "access": "Access"}[kind]
        file_meta = self.db.kv_get(f"acl-file-meta:{file_name}")
        try:
            meta = json.loads(file_meta) if file_meta else {}
        except (TypeError, json.JSONDecodeError):
            meta = {}
        root = ET.Element(root_name)
        meta["Net"] = str(room["name"])
        if kind == "access":
            meta.update({"Enabled": "true" if room["access_on"] else "false",
                         "TRXControl": "true" if room["txright_on"] else "false", "InfoMessage": room.get("notice", "")})
        for tag in ("Net", "Enabled", "TRXControl", "InfoMessage"):
            if tag in meta:
                ET.SubElement(root, tag).text = str(meta.pop(tag) or "")
        query = self._entries(kind, rid)
        for item in query:
            fields = dict(item["fields"])
            if kind == "access":
                fields["RXOnly"] = "false" if item["can_tx"] else "true"
            ordered = list(ENTRY_ORDER[kind])
            ordered.extend(sorted(k for k in fields if k not in ordered))
            node = ET.SubElement(root, "Client")
            for key in ordered:
                if key in fields:
                    ET.SubElement(node, key).text = str(fields[key] or "")
        for key, value in meta.items():
            ET.SubElement(root, key).text = str(value or "")
        ET.indent(root, space="  ")
        content = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(content)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        digest = hashlib.sha256(content).hexdigest()
        self.db.kv_set(f"acl-file-sha:{file_name}", digest)
        self.db.kv_set(f"acl-file-meta:{file_name}", json.dumps(meta, ensure_ascii=False))
