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
COLS = ("id, title, teaser, body, category, icon, author, author_name, published, pinned, created_at, updated_at, published_at, updated_by, "
        "image_alt, (image != '') AS has_image")
IMAGE_RE = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
IMAGE_MAX = 1_500_000            # bytes after decoding – the browser makes the picture small (max. 1600 px) before uploading
MAGIC = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",), "image/webp": (b"RIFF",)}


class PortalError(Exception):
    """Message is shown to the admin."""


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    d["published"], d["pinned"], d["has_image"] = bool(d["published"]), bool(d["pinned"]), bool(d.get("has_image"))
    d["image_url"] = f"/api/portal/news/{d['id']}/image?v={int(d['updated_at'])}" if d["has_image"] else ""
    return d


def _public(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: d[k] for k in ("id", "title", "teaser", "body", "category", "icon", "author_name", "pinned", "published_at", "updated_at",
                              "image_url", "image_alt")}


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
    out["image_alt"] = re.sub(r"\s+", " ", str(b.get("image_alt") or "")).strip()[:200] if "image_alt" in b else None
    img = b.get("image")
    if img is None or img == "keep":
        out["image"] = None                          # unchanged
    elif img == "":
        out["image"] = ""                            # removed
    else:
        out["image"] = check_image(str(img))
    out["pinned"] = 1 if b.get("pinned") else 0
    out["published"] = 1 if b.get("published") else 0
    return out


def check_image(data_url: str) -> str:
    """Only JPEG, PNG or WebP as data URL, at most 1.5 MB, and the bytes must really be that format."""
    import base64
    m = IMAGE_RE.fullmatch(data_url.strip())
    if not m:
        raise PortalError("Topic image: JPEG, PNG or WebP only.")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except ValueError:
        raise PortalError("Topic image: damaged file.")
    if len(raw) > IMAGE_MAX:
        raise PortalError("Topic image: at most 1.5 MB.")
    if not any(raw.startswith(x) for x in MAGIC[m.group(1)]) or (m.group(1) == "image/webp" and raw[8:12] != b"WEBP"):
        raise PortalError("Topic image: the file is not what it claims to be.")
    return data_url.strip()


def get_image(db, nid: int, public: bool = True):
    """(content type, bytes) of the topic image or None."""
    import base64
    r = db.q("SELECT image FROM news WHERE id = ?" + (" AND published = 1" if public else ""), (int(nid),))
    if not r or not r[0]["image"]:
        return None
    m = IMAGE_RE.fullmatch(r[0]["image"])
    return (m.group(1), base64.b64decode(m.group(2))) if m else None


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
             "updated_by=?, image_alt=COALESCE(?, image_alt) WHERE id=?",
             (c["title"], c["teaser"], c["body"], c["category"], c["icon"], c["published"], c["pinned"], now, pub_at,
              user.get("username", ""), c["image_alt"], int(nid)))
        if c["image"] is not None:
            db.x("UPDATE news SET image=? WHERE id=?", (c["image"], int(nid)))
        return get(db, int(nid))
    cur = db.x("INSERT INTO news (title, teaser, body, category, icon, author, author_name, published, pinned, created_at, updated_at, "
               "published_at, updated_by, image, image_alt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (c["title"], c["teaser"], c["body"], c["category"], c["icon"], user.get("username", ""), name, c["published"],
                c["pinned"], now, now, now if c["published"] else None, user.get("username", ""), c["image"] or "", c["image_alt"] or ""))
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
