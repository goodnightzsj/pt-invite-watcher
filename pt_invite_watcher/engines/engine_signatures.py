from __future__ import annotations

"""
Engine signature library for PT site identification.

Inspired by the multi-engine schemas used in community tools:
- PT-Plugin-Plus / PT-depiler (browser extensions, TypeScript schemas)
- ptool (sagan/ptool, Go templates)
- MoviePilot (Python, bundled indexer definitions)

Those projects converged on ~7 engine families. Historically this codebase knew
only two (nexusphp + mteam), which misidentified everything else as nexusphp and
pointed default signup/invite paths at `.php` endpoints that don't exist on
non-PHP engines (Unit3D, Gazelle JSON API, …).

This module declares **signatures** only — URL path conventions, HTML substrings,
cookie names, and header patterns. Full invite/registration parsers for the new
engines can be plugged in incrementally; in the meantime, scanner_site_check
routes unsupported engines to an honest "unknown — engine X not fully supported"
AspectResult so users see the correct engine label in the dashboard instead of a
false "closed" verdict derived from parsing the wrong kind of HTML.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class EngineSignature:
    """Static fingerprint of a PT site engine.

    Each non-empty field contributes a weighted score during detection; the
    engine with the highest score wins. Fields may be empty when a signal is
    not known/reliable for that engine.
    """
    name: str
    # Substrings expected to appear in the HTML of a logged-out landing page.
    # Lowercased at match time. High-precision markers (vendor names, generator
    # meta tags) should be listed first — the selector prefers the earliest hit.
    html_markers: tuple[str, ...] = ()
    # URL paths characteristic of this engine. We don't HEAD them during
    # detection (too noisy), but they feed default-path selection once the
    # engine is decided.
    path_markers: tuple[str, ...] = ()
    # Cookie names that only this engine sets. httpx Response.cookies is keyed
    # by cookie name, so an exact match is enough.
    cookie_markers: tuple[str, ...] = ()
    # Response header values that strongly imply this engine (e.g., Laravel's
    # Set-Cookie: laravel_session, or a Server: header).
    header_markers: tuple[tuple[str, str], ...] = ()  # (header_name_lower, substring_lower)
    # Domain-suffix shortcuts. If the site's domain ends with any of these,
    # detection short-circuits to this engine without scoring.
    domain_suffixes: tuple[str, ...] = ()
    # Default paths used when the user hasn't configured custom ones.
    default_registration_path: str = "signup.php"
    default_invite_path: str = "invite.php"
    # True when we have a full check_registration + check_invites parser wired
    # up for this engine. When False the scanner still reports reachability and
    # the engine label, but returns AspectResult(state="unknown") for the other
    # two dimensions with an explicit reason so the gap is auditable.
    fully_supported: bool = False
    # Human-readable tags for dashboards / debugging.
    description: str = ""


# Ordered from most-specific / highest-priority down to "default catch-all".
# Detection picks the highest-scoring match; ties resolve by this ordering.
ENGINES: tuple[EngineSignature, ...] = (
    EngineSignature(
        name="mteam",
        html_markers=("m-team",),
        path_markers=("api/member/profile", "api/torrent/search", "/login", "/invite"),
        domain_suffixes=("m-team.cc", "m-team.io"),
        default_registration_path="signup",
        default_invite_path="invite",
        fully_supported=True,
        description="馒头（M-Team）— JSON API",
    ),
    EngineSignature(
        name="unit3d",
        # Unit3D is a Laravel app. The bundle path "/js/app.js" and the
        # laravel_session cookie are near-universal; the CSS class prefix
        # `torrent-search--list__results` is a Unit3D 7.x/8.x marker.
        html_markers=(
            "unit3d",
            "torrent-search--list__results",
            "/js/app.js",
            "laravel",
            "data-page=",
        ),
        path_markers=("/torrents", "/register", "/login", "/invites", "/users/"),
        cookie_markers=("laravel_session", "XSRF-TOKEN", "unit3d_session"),
        header_markers=(("set-cookie", "laravel_session"), ("set-cookie", "xsrf-token")),
        default_registration_path="register",
        default_invite_path="invites",
        fully_supported=False,
        description="Unit3D（BLU / BHD / ACGGrand 等现代 Laravel 框架）",
    ),
    EngineSignature(
        name="gazelle",
        # Classic Gazelle (ajax.php + session cookie); GazelleJSONAPI is a
        # superset detected the same way but handled differently once
        # parsers exist.
        html_markers=(
            "torrent_table",
            "gazelle",
            "ajax.php",
            "class=\"username\"",
        ),
        path_markers=("/ajax.php", "/user.php", "/torrents.php", "/top10.php", "/collages.php"),
        cookie_markers=("session",),
        default_registration_path="register.php",
        default_invite_path="user.php?action=invite",
        fully_supported=False,
        description="Gazelle（RED / Orpheus 等音乐向私有 tracker）",
    ),
    EngineSignature(
        name="discuz",
        # Discuz-based trackers are rare but real (a few CN private forums add
        # tracker modules). Classic markers are the "Powered by Discuz" footer
        # and DZ's cookie prefix.
        html_markers=("discuz!", "powered by discuz", "comiis"),
        path_markers=("member.php", "forum.php", "plugin.php?id=", "home.php"),
        cookie_markers=(),  # Discuz prefixes cookies with a site-specific hash
        default_registration_path="member.php?mod=register",
        default_invite_path="plugin.php?id=invite",
        fully_supported=False,
        description="Discuz 论坛型 PT",
    ),
    EngineSignature(
        name="tnode",
        # Seen on a handful of heavily-modified NP forks that advertise themselves
        # as TNode (sometimes includes `tnode` in the HTML comments).
        html_markers=("tnode",),
        path_markers=("/torrents", "/login", "/invite"),
        default_registration_path="auth/register",
        default_invite_path="invite",
        fully_supported=False,
        description="TNode（部分现代 JS 前端魔改站）",
    ),
    # Default bucket last — NexusPHP is the most common engine on Chinese PT
    # sites and several of the above will also have `nexusphp`-like paths, so
    # NexusPHP's markers stay generic and it wins by default when nothing else
    # scores higher.
    EngineSignature(
        name="nexusphp",
        html_markers=(
            "nexusphp",
            "powered by nexusphp",
            "takelogin.php",
            "takesignup.php",
            "torrents.php",
            "userdetails.php",
            "getusertorrentlistajax",
            "info_block",
        ),
        path_markers=(
            "signup.php", "login.php", "takelogin.php", "takesignup.php",
            "torrents.php", "userdetails.php", "usercp.php", "invite.php",
            "mybonus.php",
        ),
        cookie_markers=("c_secure_login", "c_secure_uid", "c_secure_pass", "c_lang_folder"),
        default_registration_path="signup.php",
        default_invite_path="invite.php",
        fully_supported=True,
        description="NexusPHP（国内 PT 主流）",
    ),
)


# Lookup by name for fast access.
ENGINES_BY_NAME: dict[str, EngineSignature] = {sig.name: sig for sig in ENGINES}


def get_signature(engine: Optional[str]) -> Optional[EngineSignature]:
    return ENGINES_BY_NAME.get((engine or "").strip().lower())


def is_fully_supported(engine: Optional[str]) -> bool:
    sig = get_signature(engine)
    return bool(sig and sig.fully_supported)


@dataclass
class ScoredDetection:
    engine: str
    score: int
    signals: list[str] = field(default_factory=list)


def score_html(html: str) -> list[ScoredDetection]:
    """Score every engine against the given HTML body.

    Returns ranked matches (highest score first). An engine scores 3 per unique
    html_marker hit; path markers are not scored here (they're applied once we
    see actual HTTP traffic to those paths, not during passive HTML scoring).

    Empty/None HTML returns an empty list — callers should fall back to domain
    or template hints.
    """
    if not html:
        return []
    h = html.lower()
    results: list[ScoredDetection] = []
    for sig in ENGINES:
        score = 0
        signals: list[str] = []
        for marker in sig.html_markers:
            m = marker.lower()
            if m and m in h:
                score += 3
                signals.append(f"html:{marker}")
        if score > 0:
            results.append(ScoredDetection(engine=sig.name, score=score, signals=signals))
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def score_cookies(cookies: Optional[dict]) -> list[ScoredDetection]:
    """Score every engine against cookie names that the site has set."""
    if not cookies:
        return []
    names = {str(k).lower() for k in cookies.keys()}
    results: list[ScoredDetection] = []
    for sig in ENGINES:
        score = 0
        signals: list[str] = []
        for cookie in sig.cookie_markers:
            if cookie.lower() in names:
                score += 2
                signals.append(f"cookie:{cookie}")
        if score > 0:
            results.append(ScoredDetection(engine=sig.name, score=score, signals=signals))
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def score_headers(headers: Optional[dict]) -> list[ScoredDetection]:
    """Score every engine against response headers (Set-Cookie, Server, etc.)."""
    if not headers:
        return []
    lowered: list[tuple[str, str]] = []
    for k, v in headers.items():
        lowered.append((str(k).lower(), str(v).lower()))
    results: list[ScoredDetection] = []
    for sig in ENGINES:
        score = 0
        signals: list[str] = []
        for name, needle in sig.header_markers:
            for hk, hv in lowered:
                if hk == name and needle in hv:
                    score += 2
                    signals.append(f"header:{name}={needle}")
                    break
        if score > 0:
            results.append(ScoredDetection(engine=sig.name, score=score, signals=signals))
    results.sort(key=lambda r: r.score, reverse=True)
    return results


def detect_engine(
    *,
    html: str = "",
    cookies: Optional[dict] = None,
    headers: Optional[dict] = None,
    domain: str = "",
) -> Optional[ScoredDetection]:
    """Combine all signals and return the most likely engine, or None if no hit.

    Callers should still honor an explicit user-provided `template` over this
    auto-detection; this function is the "I have HTML/cookies/headers, please
    make an educated guess" fallback.
    """
    dom = (domain or "").lower().strip()
    if dom:
        for sig in ENGINES:
            for suffix in sig.domain_suffixes:
                if dom.endswith(suffix):
                    return ScoredDetection(engine=sig.name, score=100, signals=[f"domain:{suffix}"])

    aggregate: dict[str, ScoredDetection] = {}
    for bucket in (score_html(html), score_cookies(cookies), score_headers(headers)):
        for det in bucket:
            existing = aggregate.get(det.engine)
            if existing is None:
                aggregate[det.engine] = ScoredDetection(
                    engine=det.engine,
                    score=det.score,
                    signals=list(det.signals),
                )
            else:
                existing.score += det.score
                existing.signals.extend(det.signals)

    if not aggregate:
        return None
    winner = max(aggregate.values(), key=lambda d: d.score)
    return winner


__all__ = [
    "ENGINES",
    "ENGINES_BY_NAME",
    "EngineSignature",
    "ScoredDetection",
    "detect_engine",
    "get_signature",
    "is_fully_supported",
    "score_cookies",
    "score_headers",
    "score_html",
]
