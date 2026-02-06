from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse


def page_kind_from_url(url: str) -> Optional[str]:
    """
    Normalize common PT page kinds from a URL path.

    Returns None when URL is empty or cannot be parsed.
    """
    if not url:
        return None
    try:
        parsed = urlparse(str(url))
        path = (parsed.path or "/").strip("/").lower()
    except Exception:
        return None

    if not path:
        return "home"
    if path.startswith("usercp"):
        return "usercp"
    if path.startswith("signup"):
        return "signup"
    if path.startswith("userdetails"):
        return "userdetail"
    if path.startswith("invite"):
        return "invite"
    if path.startswith("login"):
        return "login"
    return path.split("/", 1)[0] or "other"


def hosts_related(host_a: str, host_b: str) -> bool:
    a = (host_a or "").lower().strip(".")
    b = (host_b or "").lower().strip(".")
    if not a or not b:
        return True
    return a == b or a.endswith("." + b) or b.endswith("." + a)

