from __future__ import annotations

from typing import Any, Optional

from pt_invite_watcher.engines.engine_signatures import (
    ENGINES_BY_NAME,
    detect_engine,
    get_signature,
    is_fully_supported,
)
from pt_invite_watcher.engines.site_registry import find_by_domain as _site_find_by_domain
from pt_invite_watcher.site_templates import MTEAM_DOMAIN_SUFFIX, normalize_template
from pt_invite_watcher.utils.parse import normalize_domain


def engine_for_site(
    site: Any,
    *,
    hint: Optional[str] = None,
    html: Optional[str] = None,
    cookies: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> str:
    """Pick the canonical engine label for a site.

    Resolution order (highest-priority first):
    1. Explicit user-set ``site.template`` — never second-guess the operator.
    2. Domain-suffix shortcuts from the engine signature table (e.g. m-team.cc).
    3. Composite signal detection via ``detect_engine`` (HTML + cookies +
       headers). Only kicks in when the caller actually has a response to
       analyse; passive calls still fall through to the default.
    4. A single lowercase ``hint`` string (retained for compatibility with the
       old ``engine_hint_from_html`` contract).
    5. Default to ``nexusphp`` — it's still the dominant engine on Chinese PT
       sites so this is the safest fallback.

    The returned label always exists as a key in ``site_templates.SITE_TEMPLATES``
    *or* in the engine signature table so downstream code can always look up a
    default path for it.
    """
    domain = normalize_domain(getattr(site, "domain", "") or "")

    # 0. Hard domain override for API-locked engines. m-team.cc speaks a JSON
    #    API only — using the NexusPHP parser on it would fail outright, so
    #    even if the user set a different template we stick with mteam here.
    if domain.endswith(MTEAM_DOMAIN_SUFFIX):
        return "mteam"

    # 1. User-provided template wins for every other engine. Picking unit3d /
    #    gazelle / discuz / tnode in the UI must be honored even if HTML
    #    signals disagree (users sometimes configure alternate mirrors where
    #    the landing page is a placeholder).
    template = normalize_template(getattr(site, "template", None))
    if template:
        return template

    # 2. Known-site registry lookup. Most users are adding mainstream PT sites
    #    we already know about; when a domain matches the curated registry we
    #    get both the engine and the correct path conventions in one step,
    #    skipping any guesswork.
    if domain:
        site_def = _site_find_by_domain(domain)
        if site_def is not None:
            return site_def.schema

    # 3. Additional domain-suffix shortcuts declared by engine signatures.
    #    Kept after the template/registry checks so only "hard" overrides
    #    (mteam above) ignore user intent; engines added to the signature
    #    table with a domain_suffix are treated as strong hints, not absolute
    #    rules.
    for sig in ENGINES_BY_NAME.values():
        if sig.name == "mteam":
            continue  # already handled above
        if sig.domain_suffixes and domain:
            for suffix in sig.domain_suffixes:
                if domain.endswith(suffix):
                    return sig.name

    # 3. Composite detection across HTML / cookies / headers.
    detection = detect_engine(
        html=html or "",
        cookies=cookies,
        headers=headers,
        domain=domain,
    )
    if detection and detection.score >= 3:
        # Score >= 3 means at least one solid signal (html_marker is worth 3).
        return detection.engine

    # 4. Single-string legacy hint.
    hint_value = str(hint or "").strip().lower()
    if hint_value:
        return hint_value

    return "nexusphp"


def default_paths_for_engine(engine: Optional[str]) -> tuple[str, str]:
    """Return (registration_path, invite_path) appropriate for the engine.

    Falls back to NexusPHP-style paths when the engine is unknown.
    """
    sig = get_signature(engine)
    if sig is not None:
        return sig.default_registration_path, sig.default_invite_path
    return "signup.php", "invite.php"


def default_paths_for_site(site: Any, *, engine: Optional[str] = None) -> tuple[str, str]:
    """Return (registration_path, invite_path) with site-registry overrides applied.

    Priority:
    1. Site's domain matches the curated registry AND that entry overrides the
       relevant path — use the override. Keeps per-site quirks (like a
       NexusPHP fork that renames ``signup.php``) out of the generic engine
       defaults.
    2. Engine defaults (``default_paths_for_engine``).

    The caller is still responsible for honoring the per-Site explicit
    ``site.registration_path`` / ``site.invite_path`` fields — those are
    user-owned and beat everything here.
    """
    domain = normalize_domain(getattr(site, "domain", "") or "")
    eng = engine or engine_for_site(site)
    reg_default, inv_default = default_paths_for_engine(eng)
    if not domain:
        return reg_default, inv_default
    sd = _site_find_by_domain(domain)
    if sd is None:
        return reg_default, inv_default
    reg = sd.registration_path or reg_default
    inv = sd.invite_path or inv_default
    return reg, inv


def engine_fully_supported(engine: Optional[str]) -> bool:
    """Expose the signature-table ``fully_supported`` flag to pipeline code."""
    return is_fully_supported(engine)


__all__ = [
    "default_paths_for_engine",
    "default_paths_for_site",
    "engine_for_site",
    "engine_fully_supported",
]
