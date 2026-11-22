"""Link menu configuration (same options as HBlink4-FreeRadioID)."""
import pytest

from frnadn import links


def test_defaults_and_legacy_list(tmp_path):
    f = tmp_path / "links.json"
    cfg = links.read(f)
    assert cfg["enabled"] and cfg["style"] == "menu" and cfg["items"][0]["label"] == "FreeRadioNetwork"
    f.write_text('[{"label": "A", "url": "https://example.org"}]')           # older format
    cfg = links.read(f)
    # older entries get the defaults of the new options: new tab and site icon on for web links
    assert cfg["items"] == [{"label": "A", "url": "https://example.org", "site_icon": True, "new_tab": True}] and cfg["style"] == "menu"


def test_normalize_keeps_options():
    cfg = links.normalize({"enabled": False, "label": "Mehr", "style": "bar", "items": [
        {"icon": "🌐", "label": "Web", "url": "https://example.org", "new_tab": True},
        {"icon": "✉️", "label": "Mail", "url": "mailto:a@example.org", "new_tab": False},
        {"label": "Setup", "url": "#config"}]})
    assert cfg["enabled"] is False and cfg["style"] == "bar" and cfg["label"] == "Mehr"
    assert cfg["items"][1] == {"icon": "✉️", "label": "Mail", "url": "mailto:a@example.org", "new_tab": False}
    assert cfg["items"][2] == {"label": "Setup", "url": "#config"}


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "//evil.example", "https://", "ftp://x.org", "#", "http://a b"])
def test_rejects_dangerous_or_broken_urls(url):
    with pytest.raises(ValueError):
        links.normalize({"items": [{"label": "x", "url": url}]})


def test_limits_and_style():
    with pytest.raises(ValueError):
        links.normalize({"items": [{"label": "x", "url": "https://e.org"}] * 21})
    with pytest.raises(ValueError):
        links.normalize({"style": "tiles", "items": []})
    with pytest.raises(ValueError):
        links.normalize({"items": [{"label": "", "url": "https://e.org"}]})


def test_write_roundtrip(tmp_path):
    f = tmp_path / "branding" / "links.json"
    cfg = links.normalize({"items": [{"label": "A", "url": "/static/x"}]})
    links.write(f, cfg)
    assert links.read(f) == cfg
