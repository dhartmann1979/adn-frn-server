"""
Users, logins and sessions.

* Three roles, as on the DMR Die N8schicht server:
  ``superadmin`` – one account, created by the guided installation (or the CLI);
  manages admins and users. ``admin`` – everything except other admins.
  ``user`` – sees the dashboard also when it is not public, and hidden rooms.
* There is no factory login. Passwords are stored as scrypt hashes;
  sessions as SHA-256 of a random token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Any, Dict, List, Optional

from .db import DB

ROLES = ("superadmin", "admin", "user")
ADMIN_ROLES = ("superadmin", "admin")
_N, _R, _P = 2 ** 14, 8, 1


class AuthError(Exception):
    """Message is shown to the user."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, want = stored.split("$")
        if algo != "scrypt":
            return False
        want_b = base64.b64decode(want)
        dk = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                            dklen=len(want_b), maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(dk, want_b)
    except Exception:
        return False


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, db: DB):
        self.db = db
        self._fails: Dict[str, List[float]] = {}
        self.db.x("UPDATE users SET role='user' WHERE role='viewer'")

    def has_superadmin(self) -> bool:
        return bool(self.db.q("SELECT 1 FROM users WHERE role='superadmin' AND disabled=0 LIMIT 1"))

    def set_superadmin(self, username: str, password: str, display_name: str = "") -> None:
        """Create or replace the superadmin (installation / CLI). Any other superadmin becomes admin."""
        username = (username or "").strip()
        self._check(username, password)
        rows = self.db.q("SELECT id FROM users WHERE username = ?", (username,))
        if rows:
            self.db.x("UPDATE users SET password_hash=?, role='superadmin', disabled=0, default_pw=0 WHERE id=?",
                      (hash_password(password), rows[0]["id"]))
            uid = rows[0]["id"]
        else:
            uid = self.db.x("INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?,?,?,?,?)",
                            (username, hash_password(password), "superadmin", display_name[:64], time.time())).lastrowid
        self.db.x("UPDATE users SET role='admin' WHERE role='superadmin' AND id<>?", (uid,))
        self.db.x("DELETE FROM sessions WHERE user_id=?", (uid,))
        self.audit("superadmin_set", username, "installation / command line")

    # ------------------------------------------------------------ helpers
    @staticmethod
    def public(row) -> Dict[str, Any]:
        return {"id": row["id"], "username": row["username"], "role": row["role"],
                "display_name": row["display_name"], "disabled": bool(row["disabled"]),
                "default_pw": bool(row["default_pw"]), "created_at": row["created_at"],
                "last_login": row["last_login"]}

    def audit(self, action: str, username: str = "", detail: str = "", ip: str = "") -> None:
        self.db.x("INSERT INTO audit (ts, action, username, detail, ip) VALUES (?,?,?,?,?)",
                  (time.time(), action, username, detail[:500], ip))
        self.db.x("DELETE FROM audit WHERE id <= (SELECT MAX(id) - 2000 FROM audit)")

    def audit_log(self, limit: int = 300) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.db.q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    # ------------------------------------------------------------ login
    def _throttled(self, key: str) -> bool:
        now = time.time()
        recent = [t for t in self._fails.get(key, []) if now - t < 900]
        self._fails[key] = recent
        return len(recent) >= 5

    def login(self, username: str, password: str, ip: str = "", ua: str = "",
              hours: float = 12) -> Dict[str, Any]:
        key = f"{ip}|{(username or '').lower()}"
        if self._throttled(key):
            raise AuthError("Too many failed attempts. Please wait 15 minutes.")
        rows = self.db.q("SELECT * FROM users WHERE username = ?", ((username or "").strip(),))
        row = rows[0] if rows else None
        if not row or row["disabled"] or not verify_password(password or "", row["password_hash"]):
            self._fails.setdefault(key, []).append(time.time())
            self.audit("login_failed", (username or "")[:64], "", ip)
            raise AuthError("Wrong username or password.")
        self._fails.pop(key, None)
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.db.x("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, ip, user_agent) VALUES (?,?,?,?,?,?)",
                  (_th(token), row["id"], now, now + hours * 3600, ip, ua[:200]))
        self.db.x("UPDATE users SET last_login = ? WHERE id = ?", (now, row["id"]))
        self.db.x("DELETE FROM sessions WHERE expires_at < ?", (now,))
        self.audit("login", row["username"], "", ip)
        return {"token": token, "user": self.public(row), "max_age": int(hours * 3600)}

    def session_user(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        rows = self.db.q("SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                         "WHERE s.token_hash = ? AND s.expires_at > ? AND u.disabled = 0", (_th(token), time.time()))
        return self.public(rows[0]) if rows else None

    def logout(self, token: Optional[str]) -> None:
        if token:
            self.db.x("DELETE FROM sessions WHERE token_hash = ?", (_th(token),))

    def sessions(self) -> List[Dict[str, Any]]:
        rows = self.db.q("SELECT s.*, u.username, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
                         "WHERE s.expires_at > ? ORDER BY s.created_at DESC", (time.time(),))
        return [{"id": r["token_hash"][:12], "username": r["username"], "created_at": r["created_at"],
                 "expires_at": r["expires_at"], "ip": r["ip"], "user_agent": r["user_agent"], "role": r["role"]} for r in rows]

    def revoke(self, short_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{12}", short_id or ""):
            raise AuthError("Unknown session.")
        self.db.x("DELETE FROM sessions WHERE substr(token_hash, 1, 12) = ?", (short_id,))

    # ------------------------------------------------------------ users
    def users(self) -> List[Dict[str, Any]]:
        return [self.public(r) for r in self.db.q("SELECT * FROM users ORDER BY CASE role WHEN 'superadmin' THEN 0 "
                                                  "WHEN 'admin' THEN 1 ELSE 2 END, username COLLATE NOCASE")]

    def _get(self, uid: int):
        rows = self.db.q("SELECT * FROM users WHERE id = ?", (uid,))
        if not rows:
            raise AuthError("Unknown user.")
        return rows[0]

    @staticmethod
    def _check(username: Optional[str] = None, password: Optional[str] = None, role: Optional[str] = None):
        if username is not None and not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", username):
            raise AuthError("Username: 3–32 characters, letters, digits, . _ -")
        if password is not None and len(password) < 10:
            raise AuthError("The password needs at least 10 characters.")
        if role is not None and role not in ROLES:
            raise AuthError("Unknown role.")

    def _admins_left(self, excluding: int) -> int:
        return len(self.db.q("SELECT id FROM users WHERE role='admin' AND disabled=0 AND id != ?", (excluding,)))

    @staticmethod
    def _may_manage(actor: Dict[str, Any], role: str) -> None:
        if actor["role"] not in ADMIN_ROLES:
            raise AuthError("Admins only.")
        if role == "superadmin":
            raise AuthError("The superadmin is set by the installation (python -m frnadn set-superadmin).")
        if role == "admin" and actor["role"] != "superadmin":
            raise AuthError("Only the superadmin manages admins.")

    def create(self, actor: Dict[str, Any], username: str, password: str, role: str = "user",
               display_name: str = "", ip: str = "") -> Dict[str, Any]:
        username = (username or "").strip()
        self._check(username, password, role)
        self._may_manage(actor, role)
        if self.db.q("SELECT 1 FROM users WHERE username = ?", (username,)):
            raise AuthError("This username already exists.")
        self.db.x("INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?,?,?,?,?)",
                  (username, hash_password(password), role, (display_name or "")[:64], time.time()))
        self.audit("user_created", actor["username"], f"{username} ({role})", ip)
        return self.public(self.db.q("SELECT * FROM users WHERE username = ?", (username,))[0])

    def update(self, actor: Dict[str, Any], uid: int, changes: Dict[str, Any], ip: str = "") -> Dict[str, Any]:
        row = self._get(uid)
        if uid != actor["id"]:
            self._may_manage(actor, row["role"])
            if "role" in changes:
                self._may_manage(actor, changes["role"])
        elif "role" in changes and changes["role"] != row["role"]:
            raise AuthError("You cannot change your own role.")
        sets, args, notes = [], [], []
        if "username" in changes and changes["username"] != row["username"]:
            name = (changes["username"] or "").strip()
            self._check(username=name)
            if self.db.q("SELECT 1 FROM users WHERE username = ? AND id != ?", (name, uid)):
                raise AuthError("This username already exists.")
            sets.append("username = ?"); args.append(name); notes.append(f"renamed to {name}")
        if "display_name" in changes:
            sets.append("display_name = ?"); args.append((changes["display_name"] or "")[:64])
        if "role" in changes and changes["role"] != row["role"]:
            self._check(role=changes["role"])
            sets.append("role = ?"); args.append(changes["role"]); notes.append(f"role {changes['role']}")
        if "disabled" in changes:
            dis = bool(changes["disabled"])
            if dis and row["role"] == "superadmin":
                raise AuthError("The superadmin cannot be locked.")
            if dis and uid == actor["id"]:
                raise AuthError("You cannot lock yourself out.")
            sets.append("disabled = ?"); args.append(1 if dis else 0); notes.append("locked" if dis else "unlocked")
        if changes.get("password"):
            self._check(password=changes["password"])
            sets.append("password_hash = ?"); args.append(hash_password(changes["password"]))
            sets.append("default_pw = 0"); notes.append("new password")
        if sets:
            self.db.x(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*args, uid))
            if changes.get("password") or changes.get("disabled"):
                self.db.x("DELETE FROM sessions WHERE user_id = ?", (uid,))
            self.audit("user_changed", actor["username"], f"{row['username']}: {', '.join(notes) or 'details'}", ip)
        return self.public(self._get(uid))

    def delete(self, actor: Dict[str, Any], uid: int, ip: str = "") -> None:
        row = self._get(uid)
        if uid == actor["id"]:
            raise AuthError("You cannot delete yourself.")
        self._may_manage(actor, row["role"])
        self.db.x("DELETE FROM users WHERE id = ?", (uid,))
        self.audit("user_deleted", actor["username"], row["username"], ip)

    def change_own(self, user: Dict[str, Any], old: str, new: str, new_username: str = "", ip: str = "") -> Dict[str, Any]:
        row = self._get(user["id"])
        if not verify_password(old or "", row["password_hash"]):
            raise AuthError("The current password is wrong.")
        changes: Dict[str, Any] = {"password": new}
        if new_username and new_username != row["username"]:
            changes["username"] = new_username
        self._check(password=new)
        out = self.update(user, user["id"], changes, ip)
        self.audit("password_changed", out["username"], "", ip)
        return out

    def reset(self, username: str, password: str) -> None:
        """CLI: set a password (and unlock) without the old one."""
        self._check(password=password)
        rows = self.db.q("SELECT id FROM users WHERE username = ?", (username,))
        if rows:
            self.db.x("UPDATE users SET password_hash=?, disabled=0, default_pw=0 WHERE id=?",
                      (hash_password(password), rows[0]["id"]))
        else:
            raise AuthError(f"Unknown user {username}. The superadmin is created with set-superadmin.")
        self.db.x("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username = ?)", (username,))
        self.audit("password_reset_cli", username)
