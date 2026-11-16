#!/usr/bin/env python3
"""sitecrawl - a small, polite, same-domain website crawler.

Usage:
  python cli/sitecrawl.py --url https://example.com --max-pages 15 --depth 2 --out result.json

Behaviour
  * Respects robots.txt and stays on the start URL's domain.
  * Refuses non-public IP targets (SSRF protection), re-checked on every redirect.
  * Writes structured JSON to --out; progress goes to stdout, problems to stderr.

Exit codes
  0  finished (JSON status is "success" or "partial")
  1  failed (nothing could be crawled)
  2  refused (invalid arguments or blocked target)
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import sys
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UA = "SiteCrawlBot/1.0 (educational demo; respects robots.txt)"
MAX_BODY = 2_000_000          # bytes read per page
MAX_REDIRECTS = 3
REQ_TIMEOUT = 10              # seconds per request
POLITE_DELAY = 0.3            # seconds between requests
MAX_LIST = {"internal": 200, "external": 100}
MAX_BOOKS = 500
SKIP_EXT = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".pdf", ".zip", ".gz", ".mp3",
    ".mp4", ".avi", ".mov", ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".ttf", ".exe",
}
SOCIAL_HOSTS = ("twitter.com", "x.com", "facebook.com", "linkedin.com", "github.com",
                "instagram.com", "youtube.com", "tiktok.com")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class Blocked(Exception):
    """Target refused for safety reasons."""


class FetchError(Exception):
    """Network-level failure."""


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hostkey(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def canon(url: str) -> str:
    return urldefrag(url)[0]


def check_host(host: str, allow_private: bool) -> None:
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchError(f"DNS lookup failed for {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise Blocked(f"{host} resolves to non-public address {ip}")


def fetch(session: requests.Session, url: str, allow_private: bool):
    """GET with manual redirect handling so every hop is re-validated."""
    for _ in range(MAX_REDIRECTS + 1):
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            raise Blocked(f"unsupported URL: {url}")
        check_host(p.hostname, allow_private)
        try:
            r = session.get(url, timeout=REQ_TIMEOUT, allow_redirects=False, stream=True)
        except requests.exceptions.RequestException as e:
            raise FetchError(f"{type(e).__name__}: {str(e)[:150]}") from e
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            r.close()
            continue
        try:
            header = r.headers.get("Content-Type", "")
            ctype = header.split(";")[0].strip().lower()
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BODY:
                    break
            is_text = ctype.startswith("text/") or ctype in ("application/xhtml+xml", "")
            enc = r.encoding if "charset" in header.lower() else "utf-8"
            text = body.decode(enc or "utf-8", errors="replace") if is_text else ""
        finally:
            r.close()
        return r.status_code, url, ctype, text
    raise FetchError("too many redirects")


def load_robots(session, start: str, allow_private: bool):
    p = urlparse(start)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    rp = RobotFileParser()
    info = {"url": robots_url, "found": False, "note": ""}
    try:
        status, _, _, text = fetch(session, robots_url, allow_private)
    except FetchError as e:
        rp.allow_all = True
        info["note"] = f"robots.txt unreachable ({e}); proceeding with limits"
        return rp, info
    if status == 200:
        rp.parse(text.splitlines())
        rp.modified()
        info["found"] = True
    elif status in (401, 403):
        rp.disallow_all = True
        info["note"] = f"robots.txt returned {status}; treated as disallow-all"
    else:
        rp.allow_all = True
        info["note"] = f"no robots.txt (HTTP {status})"
    return rp, info


def parse_page(url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")

    def meta(**attrs):
        tag = soup.find("meta", attrs=attrs)
        return (tag.get("content") or "").strip() if tag else ""

    links, emails = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            emails.add(href[7:].split("?")[0].strip().lower())
        elif not href.lower().startswith(("tel:", "javascript:", "data:", "#")):
            links.append(urljoin(url, href))
    books = []
    for item in soup.select("article.product_pod"):          # Books to Scrape listing cards
        a = item.select_one("h3 a")
        if not a:
            continue
        price, avail = item.select_one(".price_color"), item.select_one(".availability")
        rating = item.select_one("p.star-rating")
        cls = [c for c in (rating.get("class") or []) if c != "star-rating"] if rating else []
        books.append({
            "title": (a.get("title") or a.get_text(strip=True)).strip(),
            "price": price.get_text(strip=True) if price else "",
            "availability": " ".join(avail.get_text(" ", strip=True).split()) if avail else "",
            "rating": cls[0] if cls else "",
            "product_url": urljoin(url, a.get("href", "")),
        })
    h1 = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:5]
    h2 = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:10]
    html_tag = soup.find("html")
    for t in soup(["script", "style", "noscript", "template"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    emails.update(e.lower() for e in EMAIL_RE.findall(text))
    page = {
        "title": soup.title.get_text(strip=True) if soup.title else "",
        "meta_description": meta(name="description") or meta(property="og:description"),
        "language": (html_tag.get("lang") if html_tag else "") or "",
        "h1": h1,
        "h2": h2,
        "word_count": len(text.split()),
        "text_snippet": text[:300],
    }
    return page, links, emails, books


def crawl(args) -> int:
    t0 = time.time()
    deadline = t0 + args.timeout
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    start = canon(args.url)
    base = hostkey(start)

    result = {
        "task": "website_crawl", "target": start, "started_at": now(), "finished_at": None,
        "status": "failed", "limits": {"max_pages": args.max_pages, "max_depth": args.depth,
                                       "time_budget_sec": args.timeout},
        "robots": {}, "site": {}, "stats": {}, "pages": [], "books": [], "internal_links": [],
        "external_links": [], "errors": [], "truncated": [],
    }

    def finish(code: int) -> int:
        result["finished_at"] = now()
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, args.out)
        log(f"RESULT status={result['status']} pages={len(result['pages'])} "
            f"errors={len(result['errors'])}")
        return code

    log(f"[crawl] target={start} max_pages={args.max_pages} depth={args.depth}")
    try:
        rp, result["robots"] = load_robots(session, start, args.allow_private)
    except Blocked as e:
        result["errors"].append({"url": start, "code": "blocked", "message": str(e)})
        warn(f"BLOCKED: {e}")
        return finish(2)
    log(f"[robots] found={result['robots']['found']} {result['robots']['note']}".strip())
    delay = max(POLITE_DELAY, min(rp.crawl_delay(UA) or 0, 2.0))

    queue = deque([(start, 0)])
    seen = {start}
    internal, external, emails, social = {}, {}, set(), set()
    books_by_url = {}
    attempts = 0
    while queue:
        if attempts >= args.max_pages:
            result["truncated"].append("max_pages")
            break
        if time.time() > deadline:
            result["truncated"].append("time_budget")
            result["errors"].append({"url": None, "code": "time_budget",
                                     "message": f"{args.timeout}s budget exhausted"})
            break
        url, depth = queue.popleft()
        if not rp.can_fetch(UA, url):
            result["errors"].append({"url": url, "code": "robots_disallowed",
                                     "message": "disallowed by robots.txt"})
            log(f"[skip] robots.txt disallows {url}")
            continue
        if attempts:
            time.sleep(delay)
        attempts += 1
        log(f"[fetch] ({attempts}/{args.max_pages}) depth={depth} {url}")
        try:
            status, final, ctype, html = fetch(session, url, args.allow_private)
        except Blocked as e:
            result["errors"].append({"url": url, "code": "blocked", "message": str(e)})
            warn(f"BLOCKED: {e}")
            if url == start:
                return finish(2)
            continue
        except FetchError as e:
            result["errors"].append({"url": url, "code": "fetch_error", "message": str(e)})
            warn(f"ERROR {url}: {e}")
            continue
        if depth == 0:
            base = hostkey(final)
        if status >= 400:
            result["errors"].append({"url": url, "code": f"http_{status}",
                                     "message": f"HTTP {status}"})
            warn(f"HTTP {status} {url}")
            continue
        if not html:
            log(f"[skip] non-HTML content ({ctype or 'unknown'}) {url}")
            continue
        page, links, found_emails, found_books = parse_page(final, html)
        page.update({"url": final, "status_code": status, "depth": depth})
        emails |= found_emails
        for book in found_books:
            if book["product_url"] and len(books_by_url) < MAX_BOOKS:
                books_by_url.setdefault(book["product_url"], book)
        n_int = n_ext = 0
        for link in links:
            link = canon(link)
            lp = urlparse(link)
            if lp.scheme not in ("http", "https") or not lp.hostname:
                continue
            if hostkey(link) == base:
                n_int += 1
                internal.setdefault(link, None)
                ext = os.path.splitext(lp.path)[1].lower()
                if depth < args.depth and link not in seen and ext not in SKIP_EXT:
                    seen.add(link)
                    queue.append((link, depth + 1))
            else:
                n_ext += 1
                external.setdefault(link, None)
                if any(hostkey(link).endswith(s) for s in SOCIAL_HOSTS):
                    social.add(link)
        page["internal_links_count"], page["external_links_count"] = n_int, n_ext
        result["pages"].append(page)
        log(f"[ok] {status} \"{page['title'][:60]}\" words={page['word_count']} "
            f"links={n_int}+{n_ext}")

    pages = result["pages"]
    home = pages[0] if pages else {}
    result["books"] = list(books_by_url.values())
    result["site"] = {
        "title": home.get("title", ""), "description": home.get("meta_description", ""),
        "language": home.get("language", ""), "emails": sorted(emails)[:20],
        "social_links": sorted(social)[:20],
    }
    for key, store in (("internal", internal), ("external", external)):
        urls = list(store)
        if len(urls) > MAX_LIST[key]:
            result["truncated"].append(f"{key}_links_list")
        result[f"{key}_links"] = urls[: MAX_LIST[key]]
    result["stats"] = {
        "pages_crawled": len(pages),
        "errors": len(result["errors"]),
        "unique_internal_links": len(internal),
        "unique_external_links": len(external),
        "total_words": sum(p["word_count"] for p in pages),
        "total_books_extracted": len(result["books"]),
        "duration_sec": round(time.time() - t0, 2),
    }
    soft = [e for e in result["errors"] if e["code"] != "robots_disallowed"]
    if not pages:
        result["status"] = "failed"
        return finish(1)
    result["status"] = "partial" if (soft or "time_budget" in result["truncated"]) else "success"
    return finish(0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Polite same-domain website crawler -> JSON")
    ap.add_argument("--url", required=True)
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=45, help="overall time budget (seconds)")
    ap.add_argument("--out", required=True, help="path of the JSON result file")
    ap.add_argument("--allow-private", action="store_true",
                    help="DEV/TEST ONLY: permit private/loopback targets")
    args = ap.parse_args()
    p = urlparse(args.url)
    if p.scheme not in ("http", "https") or not p.hostname:
        warn("invalid --url: must be http(s)")
        return 2
    args.max_pages = max(1, min(args.max_pages, 100))
    args.depth = max(0, min(args.depth, 5))
    args.timeout = max(5, min(args.timeout, 300))
    return crawl(args)


if __name__ == "__main__":
    sys.exit(main())
