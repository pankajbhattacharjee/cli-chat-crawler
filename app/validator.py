"""Validation of everything the LLM (or user) wants to pass to the CLI.

The LLM only proposes *parameters*. They are validated and clamped here;
the command line itself is built from a fixed template in executor.py.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from . import config

ALLOWED_PORTS = {80, 443, 8080, 8443}
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp")
DEFAULT_PAGES, DEFAULT_DEPTH = 15, 2


class ValidationError(ValueError):
    pass


@dataclass
class CrawlArgs:
    url: str
    max_pages: int
    depth: int
    notes: list[str] = field(default_factory=list)


def _clamp(value, lo, hi, default, name, notes):
    try:
        v = int(value) if value is not None else default
    except (TypeError, ValueError):
        notes.append(f"{name} invalid; using {default}")
        return default
    c = max(lo, min(v, hi))
    if c != v:
        notes.append(f"{name} limited from {v} to {c}")
    return c


def _assert_public(host: str, port: int) -> None:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValidationError(f"Could not resolve host '{host}'.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValidationError(
                f"'{host}' resolves to a non-public address ({ip}); crawling it is not allowed.")


def validate_crawl_request(url, max_pages=None, depth=None) -> CrawlArgs:
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("No URL provided.")
    url = url.strip()
    if len(url) > 2048:
        raise ValidationError("URL is too long.")
    if any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValidationError("URL contains whitespace or control characters.")
    if "://" not in url:
        url = "https://" + url
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValidationError(f"Scheme '{p.scheme}' is not allowed; use http or https.")
    host = (p.hostname or "").lower()
    if not host or host.startswith("-"):
        raise ValidationError("URL has no valid host.")
    if p.username or p.password:
        raise ValidationError("URLs with embedded credentials are not allowed.")
    try:
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        raise ValidationError("URL has an invalid port.")
    if port not in ALLOWED_PORTS and not config.DEV_ALLOW_PRIVATE:
        raise ValidationError(f"Port {port} is not allowed (allowed: {sorted(ALLOWED_PORTS)}).")
    if not config.DEV_ALLOW_PRIVATE:
        if host == "localhost" or host.endswith(BLOCKED_SUFFIXES):
            raise ValidationError(f"Host '{host}' is internal and cannot be crawled.")
        _assert_public(host, port)
    notes: list[str] = []
    return CrawlArgs(
        url=urlunparse((p.scheme, p.netloc, p.path or "/", "", p.query, "")),
        max_pages=_clamp(max_pages, 1, config.MAX_PAGES_CAP, DEFAULT_PAGES, "max_pages", notes),
        depth=_clamp(depth, 0, config.MAX_DEPTH_CAP, DEFAULT_DEPTH, "depth", notes),
        notes=notes,
    )
