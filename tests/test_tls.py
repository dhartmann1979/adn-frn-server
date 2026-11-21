from starlette.testclient import TestClient

from frnadn.tls import CertManager, build_http_app


def test_cert_manager_validates_domain_and_uses_isolated_data_dir(tmp_path):
    manager = CertManager({"domain": "dashboard.example.org", "port": 443}, tmp_path)
    assert manager.valid_domain()
    assert manager.base == tmp_path / "letsencrypt"
    assert manager.webroot.is_dir()
    invalid = CertManager({"domain": "localhost"}, tmp_path)
    assert not invalid.valid_domain()


def test_http_app_serves_acme_challenge_and_redirects_other_paths(tmp_path):
    manager = CertManager({"domain": "dashboard.example.org", "port": 443}, tmp_path)
    challenge = manager.webroot / ".well-known" / "acme-challenge"
    challenge.mkdir(parents=True)
    (challenge / "AbCdEf0123456789").write_text("challenge-response", encoding="utf-8")
    with TestClient(build_http_app(manager)) as client:
        response = client.get("/.well-known/acme-challenge/AbCdEf0123456789", follow_redirects=False)
        assert response.status_code == 200
        assert response.text == "challenge-response"
        redirect = client.get("/admin?from=http", follow_redirects=False)
        assert redirect.status_code == 301
        assert redirect.headers["location"] == "https://dashboard.example.org/admin?from=http"
