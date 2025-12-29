from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pt_invite_watcher.models import Site


SITE_LIST_SUMMARY_KEY = "effective_sites_summary"
SITE_LIST_SUMMARY_VERSION = 1


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_domain(domain: str) -> str:
    return (domain or "").strip().lower()


def _normalize_template(site: Site) -> str:
    tpl = _safe_str(getattr(site, "template", None)).lower()
    if tpl in {"nexusphp", "custom", "mteam"}:
        return tpl
    if _normalize_domain(site.domain).endswith("m-team.cc"):
        return "mteam"
    return "nexusphp"


def _default_paths(template: str) -> tuple[str, str]:
    if template == "mteam":
        return "signup", "invite"
    return "signup.php", "invite.php"


def _effective_paths(site: Site, template: str) -> tuple[str, str]:
    reg_default, inv_default = _default_paths(template)
    reg_path = _safe_str(getattr(site, "registration_path", None)) or reg_default
    inv_path = _safe_str(getattr(site, "invite_path", None)) or inv_default
    return reg_path, inv_path


@dataclass(frozen=True)
class SiteListDiff:
    added: list[str]
    removed: list[str]
    updated: dict[str, dict[str, tuple[str, str]]]

    @property
    def empty(self) -> bool:
        return not self.added and not self.removed and not self.updated


def build_summary(sites: list[Site], *, now: datetime) -> dict[str, Any]:
    items: dict[str, dict[str, Any]] = {}
    for site in sites:
        domain = _normalize_domain(site.domain)
        if not domain:
            continue
        template = _normalize_template(site)
        reg_path, inv_path = _effective_paths(site, template)
        items[domain] = {
            "domain": domain,
            "name": _safe_str(site.name) or domain,
            "url": _safe_str(site.url),
            "template": template,
            "registration_path": reg_path,
            "invite_path": inv_path,
            "source": "moviepilot" if site.id is not None else "manual",
        }
    return {"version": SITE_LIST_SUMMARY_VERSION, "updated_at": now.isoformat(), "items": items}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def diff_summary(prev: Any, cur: Any) -> SiteListDiff:
    prev_obj = _safe_dict(prev)
    cur_obj = _safe_dict(cur)
    prev_items = _safe_dict(prev_obj.get("items"))
    cur_items = _safe_dict(cur_obj.get("items"))

    prev_domains = set(_normalize_domain(x) for x in prev_items.keys())
    cur_domains = set(_normalize_domain(x) for x in cur_items.keys())

    added = sorted([d for d in cur_domains if d and d not in prev_domains])
    removed = sorted([d for d in prev_domains if d and d not in cur_domains])

    updated: dict[str, dict[str, tuple[str, str]]] = {}
    for domain in sorted([d for d in cur_domains if d and d in prev_domains]):
        before = _safe_dict(prev_items.get(domain))
        after = _safe_dict(cur_items.get(domain))
        changes: dict[str, tuple[str, str]] = {}
        for field in ("name", "url", "template", "registration_path", "invite_path"):
            a = _safe_str(before.get(field))
            b = _safe_str(after.get(field))
            if a != b:
                changes[field] = (a, b)
        if changes:
            updated[domain] = changes

    return SiteListDiff(added=added, removed=removed, updated=updated)


def format_diff_lines(diff: SiteListDiff, cur_summary: dict[str, Any], *, max_lines: int = 12) -> list[str]:
    items = _safe_dict(cur_summary.get("items"))
    lines: list[str] = []

    def _site_label(domain: str) -> str:
        item = _safe_dict(items.get(domain))
        name = _safe_str(item.get("name")) or domain
        url = _safe_str(item.get("url"))
        if url:
            return f"{name} ({domain}) {url}"
        return f"{name} ({domain})"

    for d in diff.added:
        lines.append(f"新增：{_site_label(d)}")
    for d in diff.removed:
        lines.append(f"删除：{d}")
    for d, changes in diff.updated.items():
        fields = ", ".join([f"{k}:{v[0] or '-'}→{v[1] or '-'}" for k, v in list(changes.items())[:3]])
        more = "…" if len(changes) > 3 else ""
        lines.append(f"修改：{d} ({fields}{more})")

    if len(lines) <= max_lines:
        return lines
    head = lines[:max_lines]
    head.append(f"…以及其它 {len(lines) - max_lines} 项变更")
    return head

