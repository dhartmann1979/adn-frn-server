"""📰 Portal page: only admins write and publish news; visitors see published news only; own domain shows the portal."""
import pytest
from fastapi.testclient import TestClient

H = {"X-N8": "1"}


@pytest.fixture
def client(app_mod):
    app_mod.ctx.auth.set_superadmin("chef", "chef-passwort-1")
    with TestClient(app_mod.app) as c:
        c.A = app_mod
        yield c


def login(c, user="chef", pw="chef-passwort-1"):
    r = c.post("/api/auth/login", json={"username": user, "password": pw}, headers=H)
    assert r.status_code == 200, r.text


def test_only_admins_write_and_visitors_see_published(client):
    assert client.post("/api/admin/news", json={"title": "x"}, headers=H).status_code in (401, 403)
    login(client)
    r = client.post("/api/admin/news", json={"title": "Neuer Raum", "body": "**Hallo** <script>x</script>", "category": "net",
                                             "published": False}, headers=H)
    assert r.status_code == 200, r.text
    nid = r.json()["item"]["id"]
    assert client.post("/api/admin/news", json={"title": "  "}, headers=H).status_code == 400
    assert client.post("/api/admin/news", json={"title": "a", "category": "spam"}, headers=H).status_code == 400
    pub = client.get("/api/portal").json()
    assert pub["total"] == 0                                         # draft is not public
    assert client.get(f"/api/portal/news/{nid}").status_code == 404
    r = client.post(f"/api/admin/news/{nid}/publish", json={"published": True}, headers=H).json()
    assert r["item"]["published"] and r["item"]["published_at"]
    client.post("/api/auth/logout", json={}, headers=H)
    pub = client.get("/api/portal").json()
    assert pub["total"] == 1 and pub["news"][0]["title"] == "Neuer Raum" and "author" not in pub["news"][0]
    assert client.get(f"/api/portal/news/{nid}").json()["item"]["body"].startswith("**Hallo**")   # stored as written, rendered escaped
    rss = client.get("/portal/rss.xml")
    assert rss.status_code == 200 and "Neuer Raum" in rss.text and "<script>" not in rss.text
    assert client.delete(f"/api/admin/news/{nid}", headers=H).status_code in (401, 403)


def test_plain_user_is_no_author(client):
    chef = [u for u in client.A.ctx.auth.users() if u["username"] == "chef"][0]
    client.A.ctx.auth.create(chef, "leser", "leser-passwort-1", "user")
    login(client, "leser", "leser-passwort-1")
    assert client.post("/api/admin/news", json={"title": "x"}, headers=H).status_code == 403


def test_pinned_first_and_settings(client):
    login(client)
    a = client.post("/api/admin/news", json={"title": "A", "published": True}, headers=H).json()["item"]
    b = client.post("/api/admin/news", json={"title": "B", "published": True, "pinned": True}, headers=H).json()["item"]
    assert [n["id"] for n in client.get("/api/portal").json()["news"]] == [b["id"], a["id"]]
    assert client.post("/api/admin/portal/settings", json={"changes": {"portal.domain": "x.example.org"}}, headers=H).status_code == 400
    assert client.post("/api/admin/portal/settings", json={"changes": {"portal.title": "N8 News"}}, headers=H).json()["ok"]
    assert client.get("/api/portal").json()["title"] == "N8 News"
    client.post("/api/admin/portal/settings", json={"changes": {"portal.enabled": False}}, headers=H)
    assert client.get("/api/portal").status_code == 404
    assert client.get("/portal", follow_redirects=False).status_code == 302


def test_portal_domain_shows_portal(client):
    login(client)
    client.A.ctx.settings.update({"https.domain": "frn.example.org"}, "test")
    r = client.post("/api/admin/domains", json={"domain": "news.example.org", "email": "a@example.org", "target": "portal"}, headers=H)
    assert r.status_code == 200 and "Portal" in r.json()["message"]
    assert client.A.ctx.settings.get("portal.domain") == "news.example.org"
    d = client.get("/api/admin/domains").json()
    assert [(s["domain"], s["target"]) for s in d["sites"]] == [("frn.example.org", "live"), ("news.example.org", "portal")]
    assert d["add"]["allowed"] and [t["id"] for t in d["add"]["targets"]] == ["live", "portal"]
    assert 'portal.js' in client.get("/", headers={"host": "news.example.org"}).text
    assert 'portal.js' not in client.get("/", headers={"host": "frn.example.org"}).text
    assert client.get("/api/info").json()["portal"]["url"] == "http://news.example.org/"
    assert client.delete("/api/admin/domains/news.example.org", headers=H).json()["ok"]
    assert client.A.ctx.settings.get("portal.domain") == ""


def test_choose_what_each_domain_shows(client, monkeypatch):
    monkeypatch.setattr(client.A, "_restart_soon", lambda why: None)
    login(client)
    client.A.ctx.settings.update({"https.domain": "frn.example.org"}, "test")
    for dom, t in (("www.example.org", "portal"), ("live.example.org", "live"), ("news.example.org", "portal")):
        assert client.post("/api/admin/domains", json={"domain": dom, "target": t}, headers=H).json()["ok"]
    assert client.post("/api/admin/domains", json={"domain": "www.example.org"}, headers=H).status_code == 400
    assert client.post("/api/admin/domains", json={"domain": "x.example.org", "target": "evil"}, headers=H).status_code == 400
    page = lambda h: "portal.js" in client.get("/", headers={"host": h}).text
    assert page("www.example.org") and page("news.example.org") and not page("live.example.org") and not page("frn.example.org")
    # switch: the main domain shows the portal, www the live dashboard – at once, no restart
    assert client.post("/api/admin/domains/frn.example.org/target", json={"target": "portal"}, headers=H).json()["ok"]
    assert client.post("/api/admin/domains/www.example.org/target", json={"target": "live"}, headers=H).json()["ok"]
    assert page("frn.example.org") and not page("www.example.org")
    assert client.post("/api/admin/domains/nope.example.org/target", json={"target": "live"}, headers=H).status_code == 404
    assert client.A.ctx.settings.get("portal.domain") == "frn.example.org"
    assert client.get("/api/info").json()["portal"]["url"] == "http://frn.example.org/"
    # the portal links back to the first live domain
    assert client.get("/api/portal", headers={"host": "frn.example.org"}).json()["dashboard_url"] == "http://www.example.org/"
    # removing the certificate's main name promotes the next one
    assert client.delete("/api/admin/domains/frn.example.org", headers=H).json()["ok"]
    assert client.A.ctx.settings.get("https.domain") == "www.example.org"
    assert [s["domain"] for s in client.get("/api/admin/domains").json()["sites"]][0] == "www.example.org"
    # turning the portal page off: portal domains show the dashboard
    client.post("/api/admin/portal/settings", json={"changes": {"portal.enabled": False}}, headers=H)
    assert not page("news.example.org")


def test_cert_names_and_redirect_host(tmp_path):
    from frnadn.tls import CertManager, build_http_app
    cm = CertManager({"domain": "frn.example.org", "extra": ["news.example.org", "bad name"], "letsencrypt": True}, tmp_path)
    assert cm.names() == ["frn.example.org", "news.example.org"]
    assert cm.https_url("/x", "news.example.org:80") == "https://news.example.org/x"
    assert cm.https_url("/x", "evil.example.com") == "https://frn.example.org/x"
    c = TestClient(build_http_app(cm))
    assert c.get("/a", headers={"host": "news.example.org"}, follow_redirects=False).headers["location"] == "https://news.example.org/a"


def test_topic_image(client):
    import base64
    login(client)
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 64).decode()
    r = client.post("/api/admin/news", json={"title": "Mit Bild", "image": f"data:image/png;base64,{png}", "image_alt": "Antenne"}, headers=H)
    assert r.status_code == 200, r.text
    n = r.json()["item"]
    assert n["has_image"] and n["image_url"].startswith(f"/api/portal/news/{n['id']}/image") and "image" not in n
    assert client.get(n["image_url"]).headers["content-type"] == "image/png"          # admin sees the draft image
    # fake image, wrong type, too big
    for bad in ("data:image/png;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode(), "data:image/svg+xml;base64,PHN2Zz4=",
                "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff" + b"0" * 1_600_000).decode()):
        assert client.post("/api/admin/news", json={"id": n["id"], "title": "x", "image": bad}, headers=H).status_code == 400
    # keep the image when editing without a new one
    client.post("/api/admin/news", json={"id": n["id"], "title": "Mit Bild 2", "published": True}, headers=H)
    client.post("/api/auth/logout", json={}, headers=H)
    pub = client.get("/api/portal").json()["news"][0]
    assert pub["image_url"] and pub["image_alt"] == "Antenne"
    assert client.get(pub["image_url"]).content.startswith(b"\x89PNG")
    assert "<enclosure" in client.get("/portal/rss.xml").text
    login(client)
    client.post("/api/admin/news", json={"id": n["id"], "title": "Ohne Bild", "published": True, "image": ""}, headers=H)
    assert client.get(f"/api/portal/news/{n['id']}/image").status_code == 404
