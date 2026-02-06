from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urljoin, urlparse

from fastapi import HTTPException

from pt_invite_watcher.site_templates import default_paths_for_template, normalize_template
from pt_invite_watcher.utils.parse import cfg_str, normalize_domain
from pt_invite_watcher.utils.url import hosts_related


def derive_site_page_urls(
    *,
    base_url: str,
    template: Any,
    registration_path: Any = None,
    invite_path: Any = None,
    invite_uid: Any = None,
) -> dict[str, str]:
    """
    Derive registration/invite URLs for a site.

    Keep this logic centralized so routes (sites/dashboard) don't drift:
    - default_paths are only applied for: "", "nexusphp", "mteam"
    - invite_uid overrides invite_path only for: "", "nexusphp"
    """
    tpl = cfg_str(template).lower()
    reg_path = cfg_str(registration_path)
    inv_path = cfg_str(invite_path)

    if tpl in {"", "nexusphp", "mteam"}:
        reg_default, inv_default = default_paths_for_template(tpl)
        reg_path = reg_path or reg_default
        inv_path = inv_path or inv_default

    uid = cfg_str(invite_uid)
    if uid and tpl in {"", "nexusphp"}:
        inv_path = f"invite.php?id={uid}"

    return {
        "registration_url": urljoin(base_url.rstrip("/") + "/", reg_path) if base_url and reg_path else "",
        "invite_url": urljoin(base_url.rstrip("/") + "/", inv_path) if base_url and inv_path else "",
    }


def site_entry_view(entry: Dict[str, Any], base_url: str) -> Dict[str, Any]:
    template = normalize_template(entry.get("template")) or "nexusphp"
    return {
        "mode": cfg_str(entry.get("mode")) or "manual",
        "template": template,
        "cookie_configured": bool(cfg_str(entry.get("cookie"))),
        "authorization_configured": bool(cfg_str(entry.get("authorization"))),
        "did_configured": bool(cfg_str(entry.get("did"))),
    }


def domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname
        return normalize_domain(host or "")
    except Exception:
        return ""


def relative_path_from_page_url(page_url: str, site_url: str, *, label: str) -> str:
    try:
        p = urlparse(page_url)
        site_host = urlparse(site_url).hostname or ""
        page_host = p.hostname or ""
        if site_host and page_host and not hosts_related(site_host, page_host):
            raise ValueError(f"{label} host mismatch: {page_host} (site={site_host})")
        rel = (p.path or "").strip()
        if rel in {"", "/"}:
            raise ValueError(f"{label} path missing")
        rel = rel.lstrip("/")
        if p.query:
            rel = f"{rel}?{p.query}"
        return rel
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


__all__ = ["derive_site_page_urls", "domain_from_url", "relative_path_from_page_url", "site_entry_view"]
