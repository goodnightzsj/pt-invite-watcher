from __future__ import annotations

from typing import Any, Optional

from pt_invite_watcher.site_templates import MTEAM_DOMAIN_SUFFIX, normalize_template
from pt_invite_watcher.utils.parse import normalize_domain


def engine_for_site(site: Any, *, hint: Optional[str] = None) -> str:
    """
    Decide the scanning "engine" label for a site.

    Priority:
    1) Domain fallback: m-team.cc -> mteam (strong signal; avoids hint misclassification).
    2) Explicit template on the Site object (nexusphp/custom).
    3) Lightweight HTML engine hint (best-effort).
    4) Default: nexusphp.

    Note: this does not change the wire protocol; it is used for consistent
    labeling between scan pipeline and dashboard rendering.
    """
    domain = normalize_domain(getattr(site, "domain", "") or "")

    if domain.endswith(MTEAM_DOMAIN_SUFFIX):
        return "mteam"

    template = normalize_template(getattr(site, "template", None))
    if template:
        return template

    hint_value = str(hint or "").strip().lower()
    if hint_value:
        return hint_value

    return "nexusphp"


__all__ = ["engine_for_site"]
