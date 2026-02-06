from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from pt_invite_watcher.utils.parse import cfg_str, normalize_domain


MTEAM_DOMAIN_SUFFIX = "m-team.cc"


@dataclass(frozen=True)
class SiteTemplateDefinition:
    name: str
    registration_default_path: str
    invite_default_path: str
    allowed_domain_suffixes: tuple[str, ...] = ()

    def allowed_for_domain(self, domain: str) -> bool:
        if not self.allowed_domain_suffixes:
            return True
        dom = normalize_domain(domain)
        return any(dom.endswith(suffix) for suffix in self.allowed_domain_suffixes)


SITE_TEMPLATES: dict[str, SiteTemplateDefinition] = {
    "nexusphp": SiteTemplateDefinition(
        name="nexusphp",
        registration_default_path="signup.php",
        invite_default_path="invite.php",
    ),
    "custom": SiteTemplateDefinition(
        name="custom",
        registration_default_path="signup.php",
        invite_default_path="invite.php",
    ),
    "mteam": SiteTemplateDefinition(
        name="mteam",
        registration_default_path="signup",
        invite_default_path="invite",
        allowed_domain_suffixes=(MTEAM_DOMAIN_SUFFIX,),
    ),
}


def normalize_template(value: Any) -> str:
    tpl = cfg_str(value).lower()
    return tpl if tpl in SITE_TEMPLATES else ""


def infer_template(domain: str, value: Any, *, default: str = "nexusphp") -> str:
    dom = normalize_domain(domain)
    tpl = normalize_template(value)
    if dom.endswith(MTEAM_DOMAIN_SUFFIX):
        return tpl or "mteam"
    return tpl or default


def infer_template_optional(domain: str, value: Any) -> Optional[str]:
    dom = normalize_domain(domain)
    tpl = normalize_template(value)
    if dom.endswith(MTEAM_DOMAIN_SUFFIX):
        return tpl or "mteam"
    return tpl or None


def default_paths_for_template(template: str) -> tuple[str, str]:
    tpl = normalize_template(template)
    spec = SITE_TEMPLATES.get(tpl) or SITE_TEMPLATES["nexusphp"]
    return spec.registration_default_path, spec.invite_default_path


def validate_template_for_domain(template: str, domain: str) -> bool:
    tpl = normalize_template(template)
    if not tpl:
        return False
    return SITE_TEMPLATES[tpl].allowed_for_domain(domain)

