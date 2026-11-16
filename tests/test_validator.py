import socket

import pytest

from app import config
from app.validator import ValidationError, validate_crawl_request


@pytest.fixture(autouse=True)
def fake_public_dns(monkeypatch):
    real = socket.getaddrinfo

    def fake(host, port, *a, **k):
        if host in ("example.com", "www.example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]
        return real(host, port, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    monkeypatch.setattr(config, "DEV_ALLOW_PRIVATE", False)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://[::1]/", "http://0.0.0.0/",
    "file:///etc/passwd", "ftp://example.com/", "javascript:alert(1)",
    "https://user:pass@example.com/", "https://example.com:22/", "https://example.com/a b",
    "http://printer.local/", "",
])
def test_rejects_unsafe(url):
    with pytest.raises(ValidationError):
        validate_crawl_request(url)


def test_accepts_public_and_adds_scheme():
    a = validate_crawl_request("example.com")
    assert a.url == "https://example.com/"


def test_clamps_limits():
    a = validate_crawl_request("https://example.com", max_pages=9999, depth=50)
    assert a.max_pages == config.MAX_PAGES_CAP and a.depth == config.MAX_DEPTH_CAP
    assert a.notes


def test_defaults_when_invalid_numbers():
    a = validate_crawl_request("https://example.com", max_pages="lots", depth=None)
    assert a.max_pages == 15 and a.depth == 2
