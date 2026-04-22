from __future__ import annotations

"""
Known-site registry.

PT ecosystem tools (PT-Plugin-Plus / PT-depiler / ptool / MoviePilot) all treat
**site** — not **engine** — as the user-facing unit. A site has a name ("馒头",
"北邮人"), one or more domains, and a pointer to the underlying engine
framework ("schema"). The engine is still the source of truth for parsers, but
the user interacts with concrete sites.

This module is the registry: a curated list of well-known PT sites that the
scanner can recognize by domain. Matching a site gives us:

- The canonical display name (used in the Dashboard site column).
- The correct engine schema, so we don't have to rely on HTML sniffing for
  sites we already know about.
- Site-specific path overrides when the site deviates from its engine's
  defaults (e.g. a NexusPHP fork that renames ``signup.php``).
- Extra aliases so search boxes can find the site via common nicknames.

When a user's domain **doesn't** match any entry here, the scanner falls back
to the engine signature detector — so this list is a convenience layer, not a
hard allowlist. Adding a new site here is a few lines and a commit.
"""

from dataclasses import dataclass
from typing import Optional

from pt_invite_watcher.utils.parse import normalize_domain


@dataclass(frozen=True)
class SiteDefinition:
    """Curated metadata for a well-known PT site."""

    id: str                            # lowercase slug — stable identity for the registry
    name: str                          # display name as it should appear in the UI
    aliases: tuple[str, ...]           # nicknames to match in search boxes
    domains: tuple[str, ...]           # primary domain first; suffix matching applied on all
    schema: str                        # underlying engine: nexusphp / unit3d / gazelle / mteam / discuz / tnode
    tags: tuple[str, ...] = ()         # eg ("中文", "综合"), ("English", "音乐")
    registration_path: str = ""        # override engine default (empty = use engine default)
    invite_path: str = ""              # override engine default
    notes: str = ""                    # one-liner visible in the UI tooltip

    @property
    def primary_domain(self) -> str:
        return self.domains[0] if self.domains else ""

    @property
    def primary_url(self) -> str:
        d = self.primary_domain
        return f"https://{d}/" if d else ""


# Curated set. Selected for coverage (each major engine family has at least a
# few representatives) and popularity (the PT communities that back each site
# are active as of the publication date). Entries stay minimal — just enough to
# auto-recognize a domain and fill in sensible defaults. Users can still override
# every field in the UI.
_SITES: tuple[SiteDefinition, ...] = (
    # ---------- M-Team (API-only engine) ----------
    SiteDefinition(
        id="mteam",
        name="馒头",
        aliases=("M-Team", "mteam", "mt"),
        domains=("m-team.cc", "kp.m-team.cc", "api.m-team.cc", "m-team.io"),
        schema="mteam",
        tags=("中文", "综合"),
        registration_path="signup",
        invite_path="invite",
        notes="基于 JSON API，需在站点配置中填入 Authorization 与 API Key",
    ),

    # ---------- 国内 NexusPHP 综合站 ----------
    SiteDefinition(
        id="byrbt",
        name="北邮人",
        aliases=("BYRBT", "北邮", "byr.pt"),
        domains=("byr.pt",),
        schema="nexusphp",
        tags=("中文", "综合", "学校"),
        notes="北京邮电大学 PT",
    ),
    SiteDefinition(
        id="tju",
        name="北洋园",
        aliases=("TJUPT", "北洋园PT"),
        domains=("tjupt.org",),
        schema="nexusphp",
        tags=("中文", "综合", "学校"),
        notes="天津大学 PT",
    ),
    SiteDefinition(
        id="hdhome",
        name="家园 (HDHome)",
        aliases=("HDHome", "家园", "hdhome"),
        domains=("hdhome.org",),
        schema="nexusphp",
        tags=("中文", "综合", "高清"),
    ),
    SiteDefinition(
        id="hdsky",
        name="天空 (HDSky)",
        aliases=("HDSky", "天空", "hdsky"),
        domains=("hdsky.me",),
        schema="nexusphp",
        tags=("中文", "综合", "高清"),
    ),
    SiteDefinition(
        id="ourbits",
        name="OurBits (我堡)",
        aliases=("OurBits", "我堡", "ob"),
        domains=("ourbits.club",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="pterclub",
        name="猫站 (PTer)",
        aliases=("PTerClub", "猫站", "pter"),
        domains=("pterclub.com",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="chdbits",
        name="CHDBits (彩虹岛)",
        aliases=("CHDBits", "彩虹岛", "chd"),
        domains=("chdbits.co",),
        schema="nexusphp",
        tags=("中文", "综合", "高清"),
    ),
    SiteDefinition(
        id="ttg",
        name="TTG (吐鲁番)",
        aliases=("TTG", "吐鲁番", "totheglory"),
        domains=("totheglory.im",),
        schema="nexusphp",
        tags=("中文", "综合", "高清"),
        notes="有自定义改造，部分路径与标准 NP 不同",
    ),
    SiteDefinition(
        id="hdchina",
        name="瓷器 (HDChina)",
        aliases=("HDChina", "瓷器", "hdc"),
        domains=("hdchina.org",),
        schema="nexusphp",
        tags=("中文", "综合", "高清"),
    ),
    SiteDefinition(
        id="hdfans",
        name="红豆饭 (HDFans)",
        aliases=("HDFans", "红豆饭"),
        domains=("hdfans.org",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="haidan",
        name="海胆 (HaiDan)",
        aliases=("HaiDan", "海胆"),
        domains=("www.haidan.video",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="beitai",
        name="备胎 (BeiTai)",
        aliases=("BeiTai", "备胎"),
        domains=("pt.keepfrds.com",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="btschool",
        name="BTSchool (校园)",
        aliases=("BTSchool", "校园"),
        domains=("pt.btschool.club", "pt.btschool.net"),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="zmpt",
        name="织梦 (ZmPT)",
        aliases=("ZmPT", "织梦"),
        domains=("zmpt.cc",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="pthome",
        name="铂金家 (PTHome)",
        aliases=("PTHome", "铂金家"),
        domains=("pthome.net",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="ssd",
        name="不可说 (SSD)",
        aliases=("SSD", "不可说", "SpringSunday"),
        domains=("springsunday.net",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="audiences",
        name="观众 (Audiences)",
        aliases=("Audiences", "观众", "aud"),
        domains=("audiences.me",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="hddolby",
        name="杜比 (HDDolby)",
        aliases=("HDDolby", "杜比"),
        domains=("www.hddolby.com",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="u2",
        name="U2 (动漫花园)",
        aliases=("U2", "daydream.dmhy", "u2.dmhy.org"),
        domains=("u2.dmhy.org",),
        schema="nexusphp",
        tags=("中文", "动漫"),
        notes="重度魔改 NP — 部分选择器与标准不同",
    ),
    SiteDefinition(
        id="hdkyl",
        name="麒麟 (HDKyl)",
        aliases=("HDKyl", "麒麟"),
        domains=("hdkyl.in",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="qingwa",
        name="青蛙 (QingWa)",
        aliases=("QingWa", "青蛙"),
        domains=("www.qingwa.pro",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),
    SiteDefinition(
        id="lemonhd",
        name="柠檬 (LemonHD)",
        aliases=("LemonHD", "柠檬"),
        domains=("lemonhd.org",),
        schema="nexusphp",
        tags=("中文", "综合"),
    ),

    # ---------- 国外 Unit3D ----------
    SiteDefinition(
        id="blutopia",
        name="BLU (Blutopia)",
        aliases=("BLU", "blutopia"),
        domains=("blutopia.cc", "blutopia.xyz"),
        schema="unit3d",
        tags=("English", "综合"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="aither",
        name="Aither",
        aliases=("AR", "aither"),
        domains=("aither.cc",),
        schema="unit3d",
        tags=("English", "综合"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="fearnopeer",
        name="FNP (FearNoPeer)",
        aliases=("FNP", "fearnopeer"),
        domains=("fearnopeer.com",),
        schema="unit3d",
        tags=("English", "综合"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="reelflix",
        name="ReelFliX",
        aliases=("RF", "reelflix"),
        domains=("reelflix.xyz",),
        schema="unit3d",
        tags=("English", "综合"),
        registration_path="register",
        invite_path="invites",
    ),

    # ---------- 国外 Gazelle (音乐向) ----------
    SiteDefinition(
        id="redacted",
        name="RED (Redacted)",
        aliases=("RED", "redacted"),
        domains=("redacted.sh", "redacted.ch"),
        schema="gazelle",
        tags=("English", "音乐"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="orpheus",
        name="OPS (Orpheus)",
        aliases=("OPS", "orpheus"),
        domains=("orpheus.network",),
        schema="gazelle",
        tags=("English", "音乐"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
)


# Lookup tables. Primary matching is exact-domain; suffix matching is used so
# www.byr.pt still resolves to the byr.pt entry.
_BY_ID: dict[str, SiteDefinition] = {sd.id: sd for sd in _SITES}
_BY_DOMAIN: dict[str, SiteDefinition] = {}
for _sd in _SITES:
    for _d in _sd.domains:
        _BY_DOMAIN[_d.lower().strip(".")] = _sd


def find_by_domain(domain: str) -> Optional[SiteDefinition]:
    """Look up a site definition by full or parent domain.

    ``m.byr.pt`` and ``www.byr.pt`` both resolve to the ``byr.pt`` entry; this
    covers the common case of users adding the mobile subdomain or getting
    redirected to a marketing subdomain.
    """
    dom = normalize_domain(domain)
    if not dom:
        return None
    sd = _BY_DOMAIN.get(dom)
    if sd is not None:
        return sd
    for known, candidate in _BY_DOMAIN.items():
        # Only match strict subdomain (e.g. www.byr.pt → byr.pt); avoid
        # confusing kp.m-team.cc with api.m-team.cc by matching the *longest*
        # known domain first.
        if dom.endswith("." + known) or known.endswith("." + dom):
            return candidate
    return None


def find_by_id(site_id: str) -> Optional[SiteDefinition]:
    return _BY_ID.get((site_id or "").strip().lower())


def list_all() -> tuple[SiteDefinition, ...]:
    return _SITES


__all__ = [
    "SiteDefinition",
    "find_by_domain",
    "find_by_id",
    "list_all",
]
