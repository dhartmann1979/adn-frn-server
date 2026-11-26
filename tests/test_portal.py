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
    r = client.post("/api/admin/domains", json={"domain": "news.example.org", "email": "a@example.org"}, headers=H)
    assert r.status_code == 200 and "Portal" in r.json()["message"]
    assert client.A.ctx.settings.get("portal.domain") == "news.example.org"
    d = client.get("/api/admin/domains").json()
    assert [s["domain"] for s in d["sites"]] == ["frn.example.org", "news.example.org"] and d["add"]["allowed"] is False
    assert 'portal.js' in client.get("/", headers={"host": "news.example.org"}).text
    assert 'portal.js' not in client.get("/", headers={"host": "frn.example.org"}).text
    assert client.get("/api/info").json()["portal"]["url"] == "http://news.example.org/"
    assert client.delete("/api/admin/domains/news.example.org", headers=H).json()["ok"]
    assert client.A.ctx.settings.get("portal.domain") == ""


def test_cert_names_and_redirect_host(tmp_path):
    from frnadn.tls import CertManager, build_http_app
    cm = CertManager({"domain": "frn.example.org", "extra": ["news.example.org", "bad name"], "letsencrypt": True}, tmp_path)
    assert cm.names() == ["frn.example.org", "news.example.org"]
    assert cm.https_url("/x", "news.example.org:80") == "https://news.example.org/x"
    assert cm.https_url("/x", "evil.example.com") == "https://frn.example.org/x"
    c = TestClient(build_http_app(cm))
    assert c.get("/a", headers={"host": "news.example.org"}, follow_redirects=False).headers["location"] == "https://news.example.org/a"
