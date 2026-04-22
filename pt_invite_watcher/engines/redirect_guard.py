from __future__ import annotations

"""
Redirect-hijack defense for site probes.

Some PT sites, when dead or hidden, redirect visitors to decoy hosts (baidu, google,
weibo, URL shorteners, the operator's personal blog, …). With httpx `follow_redirects=True`
we'd silently end up at baidu.com and a 200 HTML would read as "site is up".

This module provides:

- `guarded_get`: GET a URL while following 3xx hops **manually**, so each hop's target host
  is checked against a known-good registrable domain before we proceed. HTML-level
  redirects (`<meta http-equiv="refresh">`, `window.location = "…"`) are also detected
  from the final response body.
- `registrable_domain` / `same_registrable_domain`: lightweight second-level-domain
  matching without an external dependency. Strict enough that `www.x.com` ≡ `m.x.com`
  but `x.com` ≢ `baidu.com`.
- `is_blacklisted_host`: common decoy hosts that should never be a legitimate PT target.

All predicates err on the side of *detection*: a false positive surfaces as a "可能被
劫持" warning in the Logs page, which is far cheaper than a false negative that silently
reports a hijacked site as healthy.
"""

import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from pt_invite_watcher.net import (
    DEFAULT_REQUEST_RETRY_ATTEMPTS,
    DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    request_with_retry,
)


logger = logging.getLogger("pt_invite_watcher.redirect_guard")


# Two-label public suffixes. Without this, `foo.example.co.uk` would be bucketed as
# `example.co.uk` → `co.uk`, which is wrong. Not a complete PSL — just the platforms our
# users actually target. A missing entry only makes us *stricter* (more likely to warn on
# legitimate cross-subdomain navigation), which fails safely toward detection.
_MULTI_PART_TLDS: frozenset[str] = frozenset({
    "co.uk", "org.uk", "ac.uk", "gov.uk",
    "com.cn", "net.cn", "org.cn", "edu.cn", "gov.cn",
    "co.jp", "or.jp", "ne.jp",
    "com.hk", "com.tw", "com.au", "com.sg", "co.kr", "com.my",
    "com.br", "com.mx", "com.ar", "co.in",
    "github.io", "gitlab.io",
})


# Hosts that almost never indicate a legitimate PT site — redirecting here is a strong
# signal of hijack / takedown / decoy parking.
_REDIRECT_BLACKLIST: frozenset[str] = frozenset({
    "baidu.com", "google.com", "bing.com", "yahoo.com", "sogou.com", "duckduckgo.com",
    "qq.com", "weibo.com", "sina.com.cn", "sohu.com", "163.com", "126.com",
    "taobao.com", "tmall.com", "jd.com", "alipay.com",
    "github.com", "gitee.com",
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "lnkd.in", "ow.ly",
})


def registrable_domain(host: str) -> str:
    """Best-effort second-level domain extraction.

    Examples:
        registrable_domain("www.example.com") -> "example.com"
        registrable_domain("m.example.co.uk") -> "example.co.uk"
        registrable_domain("example") -> "example"
    """
    h = (host or "").lower().strip(".").strip()
    if not h:
        return ""
    parts = h.split(".")
    if len(parts) < 2:
        return h
    if len(parts) >= 3 and ".".join(parts[-2:]) in _MULTI_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_registrable_domain(a: str, b: str) -> bool:
    ra = registrable_domain(a)
    rb = registrable_domain(b)
    return bool(ra) and ra == rb


def is_blacklisted_host(host: str) -> bool:
    rd = registrable_domain(host)
    if not rd:
        return False
    return rd in _REDIRECT_BLACKLIST


# Keep these patterns deliberately lenient — hijacked pages use a wide variety of
# markup styles. False positives surface as warnings, not hard failures.
_HTML_META_REFRESH_RE = re.compile(
    r"""<meta\s[^>]*http-equiv\s*=\s*["']?refresh["']?[^>]*content\s*=\s*["'][^"']*?url\s*=\s*([^"'>\s]+)""",
    re.IGNORECASE,
)
_HTML_JS_LOCATION_RE = re.compile(
    r"""(?:window\.|document\.|top\.|parent\.|self\.)?location(?:\.href)?\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_HTML_JS_REPLACE_RE = re.compile(
    r"""(?:window\.|document\.)?location\.(?:replace|assign)\s*\(\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


def detect_html_offsite_redirect(html: str, *, expected_host: str) -> Optional[str]:
    """Scan HTML (first 16KB) for meta-refresh / JS-level redirects leaving the expected domain.

    Returns the offending host on hit, or None otherwise (relative URLs always return None).
    """
    if not html:
        return None
    snippet = html[:16_384]
    candidates: list[str] = []
    m = _HTML_META_REFRESH_RE.search(snippet)
    if m:
        candidates.append(m.group(1))
    for pat in (_HTML_JS_LOCATION_RE, _HTML_JS_REPLACE_RE):
        for jm in pat.finditer(snippet):
            candidates.append(jm.group(1))
    for raw in candidates:
        target = (raw or "").strip().strip("\"'")
        if not target or target.startswith("#") or target[:11].lower().startswith("javascript:"):
            continue
        th = (urlparse(target).hostname or "").lower()
        if not th:
            # Relative URL — same host by definition.
            continue
        if is_blacklisted_host(th):
            return th
        if expected_host and not same_registrable_domain(th, expected_host):
            return th
    return None


class RedirectedAwayError(httpx.RequestError):
    """A redirect chain left the expected registrable domain.

    Subclasses httpx.RequestError so upstream code that treats RequestError as a transient
    network failure (counts toward scan_task_error, circuit-breaker failure, etc.) keeps
    working without modification. The ``reason`` / ``host`` / ``chain`` attributes give
    callers everything they need to build a human-readable detail string.
    """

    def __init__(self, *, reason: str, host: Optional[str], chain: list[dict[str, Any]]):
        msg = f"redirected_away:{host}" if host else f"redirect_{reason}"
        super().__init__(msg)
        self.reason = reason
        self.host = host or ""
        self.chain = chain


@dataclass
class GuardedResponse:
    response: Optional[httpx.Response]
    error: Optional[Exception]
    retries: int
    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    off_site_reason: Optional[str] = None  # "blacklisted" | "off_site" | "html_redirect" | "too_many_redirects" | ...
    off_site_host: Optional[str] = None


async def guarded_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    expected_host: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    attempts: int = DEFAULT_REQUEST_RETRY_ATTEMPTS,
    delay_seconds: int = DEFAULT_REQUEST_RETRY_DELAY_SECONDS,
    max_redirects: int = 8,
) -> GuardedResponse:
    """GET `url`, following 3xx hops **manually**.

    Each hop's `Location` target is checked against `expected_host` (or the original URL's
    host if None). On the final response, the HTML body is scanned for meta-refresh / JS
    redirects that point off-site. Retry, backoff, and Retry-After handling are delegated
    to `request_with_retry` so we get the same robust per-hop behavior we already trust.

    The returned GuardedResponse is never raised — callers decide whether an off_site_reason
    translates to `reachability=down`, `registration=unknown`, etc.
    """
    target = url
    exp = (expected_host or urlparse(url).hostname or "").lower()
    chain: list[dict[str, Any]] = []
    total_retries = 0
    for _hop in range(max_redirects + 1):
        current_url = target  # bind explicitly so the lambda below captures the right value
        resp, err, used = await request_with_retry(
            lambda: client.get(current_url, headers=headers or None, follow_redirects=False),
            attempts=attempts,
            delay_seconds=delay_seconds,
        )
        total_retries = used
        if err is not None or resp is None:
            return GuardedResponse(None, err, total_retries, chain, None, None)

        status = resp.status_code
        if 300 <= status < 400 and status != 304:
            location = (resp.headers.get("Location") or resp.headers.get("location") or "").strip()
            chain.append({"from_url": current_url, "status": int(status), "location": location[:500]})
            with suppress(Exception):
                await resp.aclose()
            if not location:
                return GuardedResponse(None, None, total_retries, chain, "missing_location", None)
            next_url = urljoin(current_url, location)
            next_host = (urlparse(next_url).hostname or "").lower()
            if not next_host:
                return GuardedResponse(None, None, total_retries, chain, "bad_location", None)
            if is_blacklisted_host(next_host):
                return GuardedResponse(None, None, total_retries, chain, "blacklisted", next_host)
            if exp and not same_registrable_domain(next_host, exp):
                return GuardedResponse(None, None, total_retries, chain, "off_site", next_host)
            target = next_url
            continue

        # Non-3xx (or 304): we've reached the final response. Look for in-body redirects only
        # when the body is HTML and we have an expected host to compare against.
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if exp and ("html" in content_type or content_type == "" and resp.content[:1] in (b"<", b" ")):
            try:
                body = resp.text
            except Exception:
                body = ""
            if body:
                off = detect_html_offsite_redirect(body, expected_host=exp)
                if off:
                    # Preserve the final response so the caller can log a snippet if useful.
                    return GuardedResponse(resp, None, total_retries, chain, "html_redirect", off)
        return GuardedResponse(resp, None, total_retries, chain, None, None)

    return GuardedResponse(None, None, total_retries, chain, "too_many_redirects", None)


def off_site_detail(gr: GuardedResponse) -> Optional[str]:
    """Build a short human-readable description from a guarded response's off-site state."""
    if not gr.off_site_reason:
        return None
    host = gr.off_site_host or "?"
    hops = len(gr.redirect_chain)
    tag = {
        "blacklisted": "命中黑名单",
        "off_site": "跳出预期域",
        "html_redirect": "页面内跳转",
        "missing_location": "3xx 缺少 Location",
        "bad_location": "Location 无法解析",
        "too_many_redirects": "跳转次数超限",
    }.get(gr.off_site_reason, gr.off_site_reason)
    return f"redirect_{gr.off_site_reason}:{host} ({tag}, hops={hops})"


__all__ = [
    "GuardedResponse",
    "RedirectedAwayError",
    "detect_html_offsite_redirect",
    "guarded_get",
    "is_blacklisted_host",
    "off_site_detail",
    "registrable_domain",
    "same_registrable_domain",
]
