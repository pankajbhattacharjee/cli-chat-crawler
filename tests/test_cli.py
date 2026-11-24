"""Runs the real CLI against a local fixture website."""
import functools
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

CLI = Path(__file__).resolve().parent.parent / "cli" / "sitecrawl.py"


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    (root / "private").mkdir(parents=True)
    (root / "index.html").write_text(
        '<html lang="en"><head><title>Home</title><meta name="description" content="A test site">'
        '</head><body><h1>Welcome</h1><a href="/about.html">About</a> '
        '<a href="/private/secret.html">Secret</a> <a href="https://other.example/x">Ext</a> '
        '<a href="mailto:hi@test.dev">mail</a> <a href="/books.html">Books</a><script>ignore()</script></body></html>')
    (root / "about.html").write_text("<html><head><title>About</title></head><body><h2>Team</h2>"
                                      "<a href='/missing.html'>broken</a></body></html>")
    (root / "books.html").write_text(
        '<html><head><title>Books</title></head><body>'
        '<article class="product_pod"><p class="star-rating Three"></p>'
        '<h3><a href="cat/a_1/index.html" title="A Light in the Attic">A Light in the ...</a></h3>'
        '<p class="price_color">\u00a351.77</p><p class="instock availability"> In stock </p></article>'
        '<article class="product_pod"><p class="star-rating One"></p>'
        '<h3><a href="cat/b_2/index.html" title="Tipping the Velvet">Tipping the ...</a></h3>'
        '<p class="price_color">\u00a353.74</p><p class="instock availability">In stock</p></article>'
        '</body></html>', encoding="utf-8")
    (root / "private" / "secret.html").write_text("<title>Secret</title>")
    (root / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()


def run(url, out, *extra):
    return subprocess.run([sys.executable, str(CLI), "--url", url, "--out", str(out), *extra],
                          capture_output=True, text=True, timeout=60)


def test_real_crawl_respects_robots_and_reports_partial(site, tmp_path):
    out = tmp_path / "r.json"
    p = run(site, out, "--allow-private", "--max-pages", "10")
    assert p.returncode == 0, p.stderr
    d = json.loads(out.read_text())
    urls = [pg["url"] for pg in d["pages"]]
    assert site in urls and site + "about.html" in urls
    assert not any("private" in u for u in urls)               # robots respected
    assert d["site"]["title"] == "Home" and d["site"]["emails"] == ["hi@test.dev"]
    assert d["pages"][0]["h1"] == ["Welcome"] and "ignore()" not in d["pages"][0]["text_snippet"]
    codes = {e["code"] for e in d["errors"]}
    assert {"robots_disallowed", "http_404"} <= codes
    assert d["status"] == "partial"                            # a 404 happened -> honest status


def test_private_target_blocked_without_flag(site, tmp_path):
    out = tmp_path / "r.json"
    p = run(site, out)
    assert p.returncode == 2
    assert json.loads(out.read_text())["errors"][0]["code"] == "blocked"


def test_unreachable_site_fails_honestly(tmp_path):
    out = tmp_path / "r.json"
    p = run("http://127.0.0.1:9/", out, "--allow-private", "--max-pages", "1")
    assert p.returncode == 1
    assert json.loads(out.read_text())["status"] == "failed"


def test_extracts_book_fields(site, tmp_path):
    out = tmp_path / "b.json"
    assert run(site, out, "--allow-private", "--max-pages", "10").returncode == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["stats"]["total_books_extracted"] == len(d["books"]) == 2
    first = d["books"][0]
    assert first == {"title": "A Light in the Attic", "price": "\u00a351.77", "availability": "In stock",
                     "rating": "Three", "product_url": site + "cat/a_1/index.html"}
    assert d["books"][1]["rating"] == "One"


def test_off_domain_redirect_is_not_followed(tmp_path):
    root = tmp_path / "s"
    root.mkdir()
    (root / "index.html").write_text(
        '<html><title>Home</title><body><a href="/go">go</a></body></html>')

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/go":
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{self.server.server_port}/index.html")
                self.end_headers()
            else:
                super().do_GET()

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        out = tmp_path / "r.json"
        p = run(f"http://127.0.0.1:{srv.server_port}/", out, "--allow-private", "--max-pages", "5")
        assert p.returncode == 0
        d = json.loads(out.read_text())
        assert "off_domain_redirect" in {e["code"] for e in d["errors"]}
        assert not any("localhost" in pg["url"] for pg in d["pages"])
    finally:
        srv.shutdown()
