from app.core.session import safe_next_url, webui_role


def test_safe_next_url_allows_relative_paths():
    assert safe_next_url("/admin/") == "/admin/"
    assert safe_next_url("/?x=1") == "/?x=1"


def test_safe_next_url_blocks_open_redirects():
    assert safe_next_url("https://evil.example") == "/"
    assert safe_next_url("//evil.example") == "/"
    assert safe_next_url("") == "/"
    assert safe_next_url(None) == "/"


def test_webui_role_mapping():
    assert webui_role("admin") == "admin"
    assert webui_role("user") == "user"
    assert webui_role("other") == "user"
