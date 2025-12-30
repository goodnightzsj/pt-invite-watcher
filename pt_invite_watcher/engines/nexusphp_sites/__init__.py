from __future__ import annotations

from typing import Optional

from pt_invite_watcher.models import Site


class NexusPhpSiteAdapter:
    """
    A lightweight per-site hook layer for NexusPHP variations.

    Keep it minimal: adapters are optional and should never break the default flow.
    """

    def match(self, site: Site) -> bool:
        return False

    def extract_uid(self, html: str) -> Optional[str]:
        return None

    def invite_permission_reason(self, text: str, html: str) -> Optional[str]:
        return None


_ADAPTERS: list[NexusPhpSiteAdapter] = []


def register_nexusphp_site_adapter(adapter: NexusPhpSiteAdapter) -> None:
    _ADAPTERS.append(adapter)


def get_nexusphp_site_adapter(site: Site) -> Optional[NexusPhpSiteAdapter]:
    for adapter in _ADAPTERS:
        try:
            if adapter.match(site):
                return adapter
        except Exception:
            continue
    return None

