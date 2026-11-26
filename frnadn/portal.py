"""Portal page: news of the server operators, public, optionally on its own domain.

Only admins (role ``admin`` or ``superadmin``) write, edit, publish and delete news – there are no other authors.
Visitors see published news only. The text is stored as written (a small Markdown subset) and rendered in the browser
with everything escaped first, so no HTML or script of an author ever reaches a visitor.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

CATEGORIES = [("info", "ℹ️ Info"), ("important", "⚠️ Important"), ("tech", "🛠️ Technology"), ("event", "📅 Event"),
              ("net", "📻 Net & rooms")]
CAT_IDS = {c for c, _ in CATEGORIES}
LIMITS = {"title": 140, "teaser": 400, "body": 20000, "icon": 8}
COLS = "id, title, teaser, body, category, icon, author, author_name, published, pinned, created_at, updated_at, published_at, updated_by"


class PortalError(Exception):
    """Message is shown to the admin."""


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    d["published"], d["pinned"] = bool(d["published"]), bool(d["pinned"])
    return d


def _public(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: d[k] for k in ("id", "title", "teaser", "body", "category", "icon", "author_name", "pinned", "published_at", "updated_at")}


def list_all(db) -> List[Dict[str, Any]]:
    return [_row(r) for r in db.q(f"SELECT {COLS} FROM news ORDER BY pinned DESC, COALESCE(published_at, created_at) DESC, id DESC")]


def list_public(db, offset: int = 0, limit: int = 10, category: str = "") -> Dict[str, Any]:
    where, args = "published = 1", []
    if category in CAT_IDS:
        where += " AND category = ?"
        args.append(category)
    total = db.q(f"SELECT COUNT(*) AS n FROM news WHERE {where}", args)[0]["n"]
    rows = db.q(f"SELECT {COLS} FROM news WHERE {where} ORDER BY pinned DESC, published_at DESC, id DESC LIMIT ? OFFSET ?",
                [*args, max(1, min(int(limit), 50)), max(0, int(offset))])
    return {"total": total, "news": [_public(_row(r)) for r in rows]}


def get(db, nid: int, public: bool = False) -> Optional[Dict[str, Any]]:
    r = db.q(f"SELECT {COLS} FROM news WHERE id = ?" + (" AND published = 1" if public else ""), (int(nid),))
    if not r:
        return None
    d = _row(r[0])
    return _public(d) if public else d


def _clean(b: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k in ("title", "teaser", "body", "icon"):
        v = str(b.get(k) or "")
        v = v.replace("\r\n", "\n").replace("\r", "\n")
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", v)
        v = v.strip() if k != "body" else v.strip("\n ")
        if k in ("title", "teaser", "icon"):
            v = re.sub(r"\s+", " ", v)
        if len(v) > LIMITS[k]:
            raise PortalError(f"{ {'title': 'Title', 'teaser': 'Teaser', 'body': 'Text', 'icon': 'Icon'}[k] }: at most {LIMITS[k]} characters.")
        out[k] = v
    if not out["title"]:
        raise PortalError("Please enter a title.")
    cat = str(b.get("category") or "info")
    if cat not in CAT_IDS:
        raise PortalError("Unknown category.")
    out["category"] = cat
    out["pinned"] = 1 if b.get("pinned") else 0
    out["published"] = 1 if b.get("published") else 0
    return out


def save(db, b: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    """Create (no id) or update a news item. Returns the stored item."""
    c = _clean(b)
    now = time.time()
    name = str(user.get("display_name") or user.get("username") or "")
    nid = b.get("id")
    if nid:
        old = get(db, int(nid))
        if not old:
            raise PortalError("This news item does not exist (any more).")
        pub_at = old["published_at"] if old["published"] and c["published"] else (now if c["published"] else old["published_at"])
        db.x("UPDATE news SET title=?, teaser=?, body=?, category=?, icon=?, published=?, pinned=?, updated_at=?, published_at=?, "
             "updated_by=? WHERE id=?", (c["title"], c["teaser"], c["body"], c["category"], c["icon"], c["published"], c["pinned"],
                                         now, pub_at, user.get("username", ""), int(nid)))
        return get(db, int(nid))
    cur = db.x("INSERT INTO news (title, teaser, body, category, icon, author, author_name, published, pinned, created_at, updated_at, "
               "published_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (c["title"], c["teaser"], c["body"], c["category"], c["icon"], user.get("username", ""), name, c["published"],
                c["pinned"], now, now, now if c["published"] else None, user.get("username", "")))
    return get(db, cur.lastrowid)


def set_published(db, nid: int, published: bool, user: Dict[str, Any]) -> Dict[str, Any]:
    old = get(db, nid)
    if not old:
        raise PortalError("This news item does not exist (any more).")
    now = time.time()
    db.x("UPDATE news SET published=?, published_at=?, updated_at=?, updated_by=? WHERE id=?",
         (1 if published else 0, (old["published_at"] if old["published"] else now) if published else old["published_at"], now,
          user.get("username", ""), int(nid)))
    return get(db, nid)


def delete(db, nid: int) -> bool:
    return db.x("DELETE FROM news WHERE id = ?", (int(nid),)).rowcount > 0


def host_is_portal(host: str, portal_domain: str) -> bool:
    h = (host or "").split(":")[0].strip().lower().rstrip(".")
    d = (portal_domain or "").strip().lower().rstrip(".")
    return bool(d) and h == d
