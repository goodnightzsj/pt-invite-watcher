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

Coverage is drawn from the public templates in these upstream projects — most
of the Chinese NexusPHP universe, M-Team, major Unit3D and Gazelle sites, and
a handful of Discuz-based trackers. Adding a new site here is a few lines and
a commit; the dataset is expected to grow over time as the PT ecosystem
evolves.

When a user's domain doesn't match any entry here, the scanner falls back
to the engine signature detector — so this list is a convenience layer, not a
hard allowlist.
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


def _np(
    id: str,
    name: str,
    *,
    aliases: tuple[str, ...] = (),
    domains: tuple[str, ...],
    tags: tuple[str, ...] = ("中文", "综合"),
    notes: str = "",
    registration_path: str = "",
    invite_path: str = "",
) -> SiteDefinition:
    """Terse NexusPHP factory — registry entries vastly outnumber the others so
    a one-line helper cuts a lot of noise."""
    return SiteDefinition(
        id=id,
        name=name,
        aliases=aliases,
        domains=domains,
        schema="nexusphp",
        tags=tags,
        notes=notes,
        registration_path=registration_path,
        invite_path=invite_path,
    )


# Curated set. Each entry carries at least one known domain; aliases and
# domain overrides come from the upstream ptool / PT-Plugin-Plus tables.
_SITES: tuple[SiteDefinition, ...] = (
    # ======================================================================
    #                       M-Team (API-only engine)
    # ======================================================================
    SiteDefinition(
        id="mteam",
        name="馒头",
        aliases=("M-Team", "mteam", "mt"),
        domains=("m-team.cc", "kp.m-team.cc", "api.m-team.cc", "m-team.io"),
        schema="mteam",
        tags=("中文", "综合"),
        registration_path="signup",
        invite_path="invite",
        notes="JSON API — 需在站点配置中填入 Authorization 与 API Key",
    ),

    # ======================================================================
    #                       国内 NexusPHP 主流站
    # ======================================================================
    _np("ptzeroff", "0ff (自由农场)", aliases=("0ff", "pt0ffcc", "自由农场"),
        domains=("pt.0ff.cc",)),
    _np("1ptba", "1PTA (壹PT吧)", aliases=("1PTBA", "1ptba", "壹PT吧"),
        domains=("1ptba.com",)),
    _np("2xfree", "2xFree", aliases=("2xfree", "pt2xfree"),
        domains=("pt.2xfree.org",)),
    _np("pt52", "52PT", aliases=("52pt",),
        domains=("52pt.site",)),
    _np("audiences", "观众 (Audiences)", aliases=("Audiences", "ad", "观众"),
        domains=("audiences.me", "cinefiles.info"), tags=("中文", "综合")),
    _np("azusa", "梓喵 (Azusa)", aliases=("Azusa", "梓喵"),
        domains=("azusa.wiki", "zimiao.icu")),
    _np("btschool", "BTSchool (学校)", aliases=("BTSchool", "学校"),
        domains=("pt.btschool.club", "pt.btschool.net")),
    _np("byrbt", "北邮人 (BYRBT)", aliases=("BYRBT", "byr.pt", "北邮", "北邮人"),
        domains=("byr.pt",), tags=("中文", "综合", "学校"),
        notes="北京邮电大学 PT"),
    _np("carpt", "CarPT (小车站)", aliases=("CarPT", "小车站"),
        domains=("carpt.net",)),
    _np("chdbits", "CHDBits (彩虹岛)", aliases=("CHDBits", "彩虹岛", "chd", "rainbowisland"),
        domains=("chdbits.co", "chdbits.xyz", "rainbowisland.co"),
        tags=("中文", "综合", "高清")),
    _np("cyanbug", "大青虫 (CyanBug)", aliases=("CyanBug", "大青虫"),
        domains=("cyanbug.net",)),
    _np("dajiao", "打胶 (DaJiao)", aliases=("dajiao", "打胶"),
        domains=("dajiao.cyou",)),
    _np("discfan", "蝶粉 (DiscFan)", aliases=("DiscFan", "蝶粉"),
        domains=("discfan.net",)),
    _np("ecust", "ECUST PT (华东理工)", aliases=("ECUST", "ecustpt"),
        domains=("ecustpt.eu.org",), tags=("中文", "综合", "学校"),
        notes="华东理工大学 PT"),
    _np("gainbound", "丐帮 (GainBound)", aliases=("GainBound", "丐帮"),
        domains=("gainbound.net",)),
    _np("gtk", "PT GTK", aliases=("PTGTK", "gtkpw", "gtk"),
        domains=("pt.gtkpw.xyz",)),
    _np("haidan", "海胆 (HaiDan)", aliases=("HaiDan", "海胆"),
        domains=("www.haidan.video",)),
    _np("hares", "白兔 (Hares Club)", aliases=("Hares", "HaresClub", "白兔"),
        domains=("club.hares.top",)),
    _np("hdatmos", "阿童木 (HDAtmos)", aliases=("HDAtmos", "阿童木"),
        domains=("hdatmos.club",)),
    _np("hdchina", "瓷器 (HDChina)", aliases=("HDChina", "瓷器", "hdc"),
        domains=("hdchina.org",), tags=("中文", "综合", "高清")),
    _np("hdcity", "城市 (HDCity)", aliases=("HDCity", "城市"),
        domains=("hdcity.city", "leniter.org")),
    _np("hddolby", "杜比 (HDDolby)", aliases=("HDDolby", "杜比"),
        domains=("www.hddolby.com", "hddolby.com")),
    _np("hdfans", "红豆饭 (HDFans)", aliases=("HDFans", "红豆饭"),
        domains=("hdfans.org",)),
    _np("hdhome", "家园 (HDHome)", aliases=("HDHome", "家园"),
        domains=("hdhome.org",), tags=("中文", "综合", "高清")),
    _np("hdkyl", "麒麟 (HDKyl)", aliases=("HDKyl", "HDKylin", "麒麟"),
        domains=("hdkyl.in",)),
    _np("hdmayi", "蚂蚁 (HDMayi)", aliases=("HDMayi", "蚂蚁"),
        domains=("hdmayi.com",)),
    _np("hdpt", "明教 (HDPT)", aliases=("HDPT", "明教"),
        domains=("hdpt.xyz",)),
    _np("hdsky", "天空 (HDSky)", aliases=("HDSky", "天空"),
        domains=("hdsky.me",), tags=("中文", "综合", "高清")),
    _np("hdtime", "高清时光 (HDTime)", aliases=("HDTime", "高清时光"),
        domains=("hdtime.org",)),
    _np("hdupt", "好多油 (HDUPT)", aliases=("HDUPT", "upxin", "hdu", "好多油"),
        domains=("pt.hdupt.com",)),
    _np("hdvideo", "高清视频 (HDVideo)", aliases=("HDVideo", "高清视频"),
        domains=("hdvideo.one",)),
    _np("hdzone", "高清地带 (HDZone)", aliases=("HDArea", "HDZone", "高清地带"),
        domains=("hdzone.me", "hdfun.me")),
    _np("hhanclub", "憨憨 (HHanClub)", aliases=("HHanClub", "hh", "hhan", "憨憨"),
        domains=("hhanclub.top", "hhan.club")),
    _np("htpt", "海棠 (HTPT)", aliases=("HTPT", "海棠"),
        domains=("htpt.cc",)),
    _np("hudbt", "蝴蝶 (HUDBT)", aliases=("HUDBT", "蝴蝶"),
        domains=("hudbt.hust.edu.cn",), tags=("中文", "综合", "学校"),
        notes="华中科技大学 PT"),
    _np("ihdbits", "iHDBits", aliases=("iHDBits",),
        domains=("ihdbits.me",)),
    _np("joyhd", "JoyHD", aliases=("JoyHD",),
        domains=("joyhd.net",)),
    _np("kamept", "KamePT", aliases=("KamePT", "kame"),
        domains=("kamept.com",)),
    _np("keepfrds", "朋友 (KeepFRDS)", aliases=("KeepFRDS", "frds", "朋友", "月月"),
        domains=("pt.keepfrds.com",)),
    _np("leaves", "红叶 (RedLeaves)", aliases=("RedLeaves", "红叶"),
        domains=("leaves.red",)),
    _np("lemonhd", "柠檬 (LemonHD)", aliases=("LemonHD", "leaguehd", "lemon", "柠檬"),
        domains=("leaguehd.com", "lemonhd.org")),
    _np("nicept", "老师 (NicePT)", aliases=("NicePT", "老师"),
        domains=("nicept.net",)),
    _np("opencd", "皇后 (OpenCD)", aliases=("OpenCD", "皇后", "开心"),
        domains=("open.cd",)),
    _np("ourbits", "OurBits (我堡)", aliases=("OurBits", "OB", "我堡"),
        domains=("ourbits.club",)),
    _np("piggo", "猪猪 (PigGo)", aliases=("PigGo", "猪猪"),
        domains=("piggo.me",)),
    _np("pterclub", "猫站 (PTer)", aliases=("PTerClub", "PTer", "猫站"),
        domains=("pterclub.com",)),
    _np("pthome", "铂金家 (PTHome)", aliases=("PTHome", "铂金家"),
        domains=("pthome.net",)),
    _np("qingwa", "青蛙 (QingWa)", aliases=("QingWa", "qingwa", "青蛙"),
        domains=("www.qingwa.pro", "qingwapt.com")),
    _np("skyeysnow", "天雪 (SkyeySnow)", aliases=("SkyeySnow", "天雪"),
        domains=("skyey.win", "skyey2.com")),  # Note: schema overridden below
    _np("soulvoice", "聆音 (SoulVoice)", aliases=("SoulVoice", "聆音"),
        domains=("pt.soulvoice.club",)),
    _np("ssd", "不可说 (SSD)", aliases=("SSD", "SpringSunday", "春天", "不可说"),
        domains=("springsunday.net",)),
    _np("tccf", "精品论坛 (TCCF)", aliases=("TCCF", "ET8", "TorrentCCF", "精品论坛", "他吹吹风"),
        domains=("et8.org",)),
    _np("tjupt", "北洋园 (TJUPT)", aliases=("TJUPT", "北洋", "北洋园PT"),
        domains=("tjupt.org",), tags=("中文", "综合", "学校"),
        notes="天津大学 PT"),
    _np("tlfbits", "TLF (吐鲁番)", aliases=("TLF", "TLFBits", "EastGame", "吐鲁番"),
        domains=("pt.eastgame.org",)),
    _np("ttg", "TTG (听听歌)", aliases=("TTG", "ToTheGlory", "听听歌"),
        domains=("totheglory.im",), tags=("中文", "综合", "高清"),
        notes="重度魔改 NP — 部分路径与标准不同"),
    _np("u2", "U2 (动漫花园)", aliases=("U2", "DMHY", "动漫花园"),
        domains=("u2.dmhy.org", "dmhy.best"), tags=("中文", "动漫"),
        notes="重度魔改 NP — 部分选择器与标准不同"),
    _np("xingtan", "杏坛 (XingTan)", aliases=("XingTan", "Xinglin", "杏坛", "杏林"),
        domains=("xinglin.one",)),
    _np("zmpt", "织梦 (ZmPT)", aliases=("ZmPT", "织梦"),
        domains=("zmpt.cc",)),

    # ---- 国内 NexusPHP 其他（domain 清单来自 PTPP resource/sites）----
    _np("nanyangpt", "南洋 (NanyangPT)", aliases=("NanyangPT", "南洋"),
        domains=("nanyangpt.com",), tags=("中文", "综合", "学校"),
        notes="上海交通大学闵行校区"),
    _np("npupt", "浦园 (NPUPT)", aliases=("NPUPT", "浦园"),
        domains=("npupt.com",), tags=("中文", "综合", "学校"),
        notes="南京邮电大学"),
    _np("pthdbd", "BD之家 (HDBD)", aliases=("HDBD", "pt.hdbd.us"),
        domains=("pt.hdbd.us",)),
    _np("ccfbits", "CCFBits", aliases=("CCFBits",),
        domains=("ccfbits.org",)),
    _np("bitpt", "BitPT", aliases=("BitPT",),
        domains=("bitpt.cn",)),
    _np("neubt", "NEUBT", aliases=("NEUBT",),
        domains=("bt.neu6.edu.cn",), tags=("中文", "综合", "学校"),
        notes="东北大学 PT"),
    _np("sjtupt", "PT @ SJTU", aliases=("SJTUPT",),
        domains=("pt.sjtu.edu.cn",), tags=("中文", "综合", "学校"),
        notes="上海交通大学 PT"),

    # ======================================================================
    #                       Discuz 论坛型 PT
    # ======================================================================
    # skyeysnow 其实是 discuz —— _np 错标为 nexusphp，手动覆盖：
    SiteDefinition(
        id="skyeysnow-dz",
        name="天雪 (SkyeySnow · Discuz)",
        aliases=("SkyeySnow-DZ",),
        domains=("skyey.win", "skyey2.com"),
        schema="discuz",
        tags=("中文", "综合"),
        notes="Discuz 论坛型",
    ),

    # ======================================================================
    #                       TNode（朱雀系列等）
    # ======================================================================
    SiteDefinition(
        id="zhuque",
        name="朱雀 (ZhuQue)",
        aliases=("ZhuQue", "朱雀"),
        domains=("zhuque.in",),
        schema="tnode",
        tags=("中文", "综合"),
        notes="TNode 现代前端魔改",
    ),

    # ======================================================================
    #                       Unit3D (Laravel 框架 — 多为国外站)
    # ======================================================================
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
    SiteDefinition(
        id="hdpost",
        name="HDPost (普斯特)",
        aliases=("HDPost", "普斯特"),
        domains=("pt.hdpost.top",),
        schema="unit3d",
        tags=("中文", "综合"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="jptvclub",
        name="JPTV.club",
        aliases=("JPTV", "jptv.club"),
        domains=("jptv.club",),
        schema="unit3d",
        tags=("English", "日剧"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="monikadesign",
        name="MonikaDesign (莫妮卡)",
        aliases=("Monika", "MonikaDesign", "莫妮卡"),
        domains=("monikadesign.uk",),
        schema="unit3d",
        tags=("English", "综合"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="oldtoons",
        name="Old Toons World",
        aliases=("OTW", "OldToons", "oldtoonsworld"),
        domains=("oldtoons.world",),
        schema="unit3d",
        tags=("English", "动漫"),
        registration_path="register",
        invite_path="invites",
    ),

    # ======================================================================
    #                       Gazelle (音乐向 + 少数视频向)
    # ======================================================================
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
    SiteDefinition(
        id="jpopsuki",
        name="JPopsuki",
        aliases=("JPop", "jpopsuki"),
        domains=("jpopsuki.eu",),
        schema="gazelle",
        tags=("English", "音乐", "日系"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="dicmusic",
        name="海豚 (DICMusic)",
        aliases=("DIC", "DICMusic", "海豚"),
        domains=("dicmusic.club", "52dic.vip", "dicmusic.com"),
        schema="gazelle",
        tags=("中文", "音乐"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="gpw",
        name="GPW (海豹 / GreatPosterWall)",
        aliases=("GPW", "GreatPosterWall", "海豹"),
        domains=("greatposterwall.com",),
        schema="gazelle",
        tags=("中文", "电影"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
        notes="基于 GazellePW 变种",
    ),
)


# Filter out the accidental nexusphp-tagged skyeysnow entry produced by the
# `_np` factory earlier — we keep the `discuz`-typed one as the canonical
# registration. The factory call is useful for readability but we have to
# prune the duplicate since _SITES is a flat tuple.
def _dedupe_skyeysnow(entries: tuple[SiteDefinition, ...]) -> tuple[SiteDefinition, ...]:
    seen_domains: set[str] = set()
    out: list[SiteDefinition] = []
    # Iterate reversed so the Discuz definition (declared later) wins; that's
    # the one we actually want when a user types "skyey.win".
    for sd in reversed(entries):
        overlapping = {d for d in sd.domains if d in seen_domains}
        if overlapping:
            continue
        for d in sd.domains:
            seen_domains.add(d)
        out.append(sd)
    return tuple(reversed(out))


_SITES = _dedupe_skyeysnow(_SITES)


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
