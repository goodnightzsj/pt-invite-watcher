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

Coverage tracks three upstream sources, in this order of authority:

- ``sagan/ptool/site/tpl/tpl.go`` — definitive schema + URL for each site.
- ``pt-plugins/PT-Plugin-Plus/resource/sites/`` — cross-check on domains.
- ``jxxghp/MoviePilot-Wiki/site.md`` — cross-check on supported sites.

Whenever a domain value moves (sites routinely shuffle between .cc / .club /
.net TLDs) we keep the historical ones as secondary entries in ``domains`` so
users running older MoviePilot snapshots still match.

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
# domain overrides come from ptool + PT-Plugin-Plus + MoviePilot-Wiki.
_SITES: tuple[SiteDefinition, ...] = (
    # ======================================================================
    #                       M-Team (API-only engine)
    # ======================================================================
    SiteDefinition(
        id="mteam",
        name="馒头",
        aliases=("M-Team", "mteam", "mt"),
        domains=("api.m-team.cc", "kp.m-team.cc", "m-team.cc", "m-team.io"),
        schema="mteam",
        tags=("中文", "综合"),
        registration_path="signup",
        invite_path="invite",
        notes="JSON API — 需在站点配置中填入 Authorization 与 API Key",
    ),

    # ======================================================================
    #                     国内 NexusPHP 主流站（按拼音 slug 排序）
    # ======================================================================
    _np("ptzeroff", "0ff (自由农场)", aliases=("0ff", "pt0ffcc", "自由农场"),
        domains=("pt.0ff.cc",)),
    _np("13city", "13City", aliases=("13city",),
        domains=("13city.org",)),
    _np("1ptba", "1PTA (壹PT吧)", aliases=("1PTBA", "壹PT吧"),
        domains=("1ptba.com",)),
    _np("2xfree", "2xFree", aliases=("2xfree", "pt2xfree"),
        domains=("pt.2xfree.org",)),
    _np("3wmg", "芒果 (3WMG)", aliases=("3wmg", "芒果"),
        domains=("www.3wmg.com",)),
    _np("pt52", "52PT", aliases=("52pt",),
        domains=("52pt.site",)),
    _np("audiences", "观众 (Audiences)", aliases=("Audiences", "ad", "观众"),
        domains=("audiences.me", "cinefiles.info")),
    _np("azusa", "梓喵 (Azusa)", aliases=("Azusa", "梓喵"),
        domains=("azusa.wiki", "zimiao.icu")),
    _np("baozi", "包子PT", aliases=("baozi", "包子"),
        domains=("p.t-baozi.cc",)),
    _np("beitai", "备胎 (BeiTai)", aliases=("BeiTai", "备胎"),
        domains=("www.beitai.pt",)),
    _np("biho", "必火pt (BiHo)", aliases=("biho", "必火"),
        domains=("www.biho.xyz",)),
    _np("btschool", "BTSchool (学校)", aliases=("BTSchool", "学校"),
        domains=("pt.btschool.club", "pt.btschool.net")),
    _np("byrbt", "北邮人 (BYRBT)", aliases=("BYRBT", "byr", "北邮", "北邮人"),
        domains=("byr.pt",), tags=("中文", "综合", "学校"),
        notes="北京邮电大学 PT"),
    _np("cangbaoge", "藏宝阁 (CangBaoGe)", aliases=("CangBaoGe", "cbg", "藏宝阁"),
        domains=("cangbao.ge",)),
    _np("carpt", "CarPT (小车站)", aliases=("CarPT", "小车站"),
        domains=("carpt.net",)),
    _np("ccfbits", "CCFBits", aliases=("CCFBits",),
        domains=("ccfbits.org",)),
    _np("chdbits", "CHDBits (彩虹岛)", aliases=("CHDBits", "彩虹岛", "chd", "rainbowisland"),
        domains=("ptchdbits.co", "chdbits.co", "chdbits.xyz", "rainbowisland.co"),
        tags=("中文", "综合", "高清")),
    _np("crabpt", "蟹黄堡 (CrabPT)", aliases=("CrabPT", "蟹黄堡"),
        domains=("crabpt.vip",)),
    _np("cspt", "财神 (CSPT)", aliases=("CSPT", "财神"),
        domains=("cspt.top",)),
    _np("cyanbug", "大青虫 (CyanBug)", aliases=("CyanBug", "大青虫"),
        domains=("cyanbug.net",)),
    _np("dajiao", "打胶 (DaJiao)", aliases=("dajiao", "打胶"),
        domains=("dajiao.cyou",)),
    _np("dhtclub", "DHTCLUB", aliases=("DHTClub",),
        domains=("pt.dhtclub.com",)),
    _np("discfan", "蝶粉 (DiscFan)", aliases=("DiscFan", "蝶粉"),
        domains=("discfan.net",)),
    _np("dragonhd", "龍之家 (DragonHD)", aliases=("DragonHD", "龙之家"),
        domains=("www.dragonhd.xyz",)),
    _np("dubhe", "天枢 (DuBhe)", aliases=("DuBhe", "天枢"),
        domains=("dubhe.site",)),
    _np("ecust", "ECUST PT (华东理工)", aliases=("ECUST", "ecustpt"),
        domains=("pt.ecust.pp.ua", "ecustpt.eu.org"), tags=("中文", "综合", "学校"),
        notes="华东理工大学 PT"),
    _np("gainbound", "丐帮 (GainBound)", aliases=("GainBound", "丐帮"),
        domains=("gainbound.net",)),
    _np("gamegamept", "GGPT", aliases=("ggpt", "GameGamePT"),
        domains=("www.gamegamept.com",)),
    _np("gamerapt", "駕瞑羅 (GamerAPT)", aliases=("GamerAPT",),
        domains=("gamerapt.link",)),
    _np("gtk", "PT GTK", aliases=("PTGTK", "gtkpw"),
        domains=("pt.gtk.pw", "pt.gtkpw.xyz")),
    _np("haidan", "海胆 (HaiDan)", aliases=("HaiDan", "海胆"),
        domains=("www.haidan.video",)),
    _np("hares", "白兔 (Hares Club)", aliases=("Hares", "HaresClub", "白兔"),
        domains=("club.hares.top",)),
    _np("hdarea", "高清地带 (HDArea)", aliases=("HDArea", "高清地带"),
        domains=("hdarea.club",)),
    _np("hdatmos", "阿童木 (HDAtmos)", aliases=("HDAtmos", "阿童木"),
        domains=("hdatmos.club",)),
    _np("hdclone", "HDClone", aliases=("HDClone",),
        domains=("pt.hdclone.org",)),
    _np("hdchina", "瓷器 (HDChina)", aliases=("HDChina", "瓷器", "hdc"),
        domains=("hdchina.org",), tags=("中文", "综合", "高清")),
    _np("hdcity", "城市 (HDCity)", aliases=("HDCity", "城市"),
        domains=("hdcity.city", "leniter.org")),
    _np("hddolby", "杜比 (HDDolby)", aliases=("HDDolby", "杜比"),
        domains=("www.hddolby.com", "hddolby.com")),
    _np("hdfans", "红豆饭 (HDFans)", aliases=("HDFans", "红豆饭"),
        domains=("hdfans.org", "pt.hd4fans.org")),
    _np("hdhome", "家园 (HDHome)", aliases=("HDHome", "家园"),
        domains=("hdhome.org",), tags=("中文", "综合", "高清")),
    _np("hdkyl", "麒麟 (HDKyl)", aliases=("HDKyl", "HDKylin", "麒麟"),
        domains=("www.hdkyl.in", "hdkyl.in")),
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
        domains=("hdvideo.top", "hdvideo.one")),
    _np("hdzone", "高清地带 (HDZone)", aliases=("HDZone", "HDFun"),
        domains=("hdzone.me", "hdfun.me")),
    _np("hhanclub", "憨憨 (HHanClub)", aliases=("HHanClub", "hh", "hhan", "憨憨"),
        domains=("hhanclub.top", "hhan.club")),
    _np("htpt", "海棠 (HTPT)", aliases=("HTPT", "海棠"),
        domains=("www.htpt.cc", "htpt.cc")),
    _np("hudbt", "蝴蝶 (HUDBT)", aliases=("HUDBT", "蝴蝶"),
        domains=("hudbt.hust.edu.cn",), tags=("中文", "综合", "学校"),
        notes="华中科技大学 PT"),
    _np("hxpt", "好学 (HXPT)", aliases=("HXPT", "好学"),
        domains=("www.hxpt.org",)),
    _np("icc2022", "冰淇淋 (ICC2022)", aliases=("ICC", "ICC2022", "冰淇淋"),
        domains=("www.icc2022.com",)),
    _np("ihdbits", "iHDBits", aliases=("iHDBits",),
        domains=("ihdbits.me",)),
    _np("ilolicon", "ilolicon PT", aliases=("ilolicon",),
        domains=("mua.xloli.cc",)),
    _np("itzmx", "PT分享站 (ITZMX)", aliases=("ITZMX",),
        domains=("pt.itzmx.com",)),
    _np("joyhd", "JoyHD", aliases=("JoyHD",),
        domains=("www.joyhd.net", "joyhd.net")),
    _np("kamept", "KamePT", aliases=("KamePT", "kame"),
        domains=("kamept.com",)),
    _np("keepfrds", "朋友 (KeepFRDS)", aliases=("KeepFRDS", "frds", "朋友", "月月"),
        domains=("pt.keepfrds.com",)),
    _np("kufei", "库非 (KuFei)", aliases=("KuFei", "库非"),
        domains=("kufei.org",)),
    _np("lajidui", "垃圾堆 (LaJiDui)", aliases=("LaJiDui", "垃圾堆"),
        domains=("pt.lajidui.top",)),
    _np("leaves", "红叶 (RedLeaves)", aliases=("RedLeaves", "红叶"),
        domains=("leaves.red",)),
    _np("lemonhd", "柠檬 (LemonHD)", aliases=("LemonHD", "leaguehd", "lemon", "柠檬"),
        domains=("lemonhd.club", "leaguehd.com", "lemonhd.org")),
    _np("longpt", "LongPT", aliases=("LongPT",),
        domains=("longpt.org",)),
    _np("luckpt", "LuckPT", aliases=("LuckPT",),
        domains=("pt.luckpt.de",)),
    _np("march", "March", aliases=("duckboobee",),
        domains=("duckboobee.org",)),
    _np("nicept", "老师 (NicePT)", aliases=("NicePT", "老师"),
        domains=("www.nicept.net", "nicept.net")),
    _np("novahd", "NovaHD", aliases=("NovaHD",),
        domains=("pt.novahd.top",)),
    _np("okpt", "OKPT", aliases=("OKPT",),
        domains=("www.okpt.net",)),
    _np("opencd", "皇后 (OpenCD)", aliases=("OpenCD", "皇后", "开心"),
        domains=("open.cd",)),
    _np("oshen", "奥申 (Oshen)", aliases=("Oshen", "奥申", "欧神"),
        domains=("www.oshen.win",)),
    _np("ourbits", "OurBits (我堡)", aliases=("OurBits", "OB", "我堡"),
        domains=("ourbits.club",)),
    _np("pandapt", "熊猫高清 (PandaPT)", aliases=("PandaPT", "panda", "熊猫"),
        domains=("pandapt.net",)),
    _np("piggo", "猪猪 (PigGo)", aliases=("PigGo", "猪猪"),
        domains=("piggo.me",)),
    _np("playletpt", "PlayletPT", aliases=("PlayletPT",),
        domains=("playletpt.xyz",)),
    _np("ptcafe", "咖啡 (PTCafe)", aliases=("PTCafe", "咖啡"),
        domains=("ptcafe.club",)),
    _np("ptchina", "铂金学院 (PTChina)", aliases=("PTChina", "铂金学院"),
        domains=("ptchina.org",)),
    _np("pterclub", "猫站 (PTer)", aliases=("PTerClub", "PTer", "猫站"),
        domains=("pterclub.net", "pterclub.com")),
    _np("pthome", "铂金家 (PTHome)", aliases=("PTHome", "铂金家"),
        domains=("pthome.net",)),
    _np("ptlsp", "PTLSP", aliases=("PTLSP",),
        domains=("www.ptlsp.com",)),
    _np("ptsbao", "烧包 (PTSBao)", aliases=("PTSBao", "烧包"),
        domains=("ptsbao.club",)),
    _np("ptskit", "PTSKIT", aliases=("PTSKIT",),
        domains=("www.ptskit.org",)),
    _np("pttime", "PTTime (PTT)", aliases=("PTT", "PTTime"),
        domains=("www.pttime.org",)),
    _np("ptvicomo", "象站 (PTVicomo)", aliases=("PTVicomo", "象站"),
        domains=("ptvicomo.net",)),
    _np("ptzone", "PTzone", aliases=("PTzone",),
        domains=("ptzone.xyz",)),
    _np("pwtorrents", "PWTorrents", aliases=("PWT", "ProWrestlingTorrents"),
        domains=("pwtorrents.net",), tags=("English", "综合")),
    _np("qingwa", "青蛙 (QingWa)", aliases=("QingWa", "青蛙"),
        domains=("www.qingwapt.com", "qingwapt.com", "www.qingwa.pro")),
    _np("railgunpt", "RailgunPT", aliases=("RailgunPT", "bilibili"),
        domains=("bilibili.download",)),
    _np("raingfh", "雨 (Raingfh)", aliases=("Raingfh", "雨"),
        domains=("raingfh.top",)),
    _np("rousi", "Rousi", aliases=("Rousi",),
        domains=("rousi.zip",)),
    _np("sharkpt", "鲨鱼 (SharkPT)", aliases=("SharkPT", "鲨鱼"),
        domains=("sharkpt.net",)),
    _np("siqi", "思齐 (SiQi)", aliases=("SiQi", "思齐"),
        domains=("si-qi.xyz",)),
    _np("soulvoice", "聆音 (SoulVoice)", aliases=("SoulVoice", "聆音"),
        domains=("pt.soulvoice.club",)),
    _np("ssd", "不可说 (SSD)", aliases=("SSD", "SpringSunday", "春天"),
        domains=("springsunday.net",)),
    _np("tccf", "精品论坛 (TCCF)", aliases=("TCCF", "ET8", "TorrentCCF", "他吹吹风"),
        domains=("et8.org",)),
    _np("tjupt", "北洋园 (TJUPT)", aliases=("TJUPT", "北洋", "北洋园PT"),
        domains=("tjupt.org",), tags=("中文", "综合", "学校"),
        notes="天津大学 PT"),
    _np("tlfbits", "TLF (吐鲁番)", aliases=("TLF", "TLFBits", "EastGame", "吐鲁番"),
        domains=("pt.eastgame.org",)),
    _np("tmpt", "唐门 (TMPT)", aliases=("TMPT", "唐门"),
        domains=("tmpt.top",)),
    _np("tosky", "ToSky", aliases=("ToSky",),
        domains=("t.tosky.club",)),
    _np("ttg", "TTG (听听歌)", aliases=("TTG", "ToTheGlory", "听听歌"),
        domains=("totheglory.im",), tags=("中文", "综合", "高清"),
        notes="重度魔改 NP — 部分路径与标准不同"),
    _np("tu88", "TU88", aliases=("TU88",),
        domains=("pt.tu88.men",)),
    _np("u2", "U2 (动漫花园)", aliases=("U2", "DMHY", "动漫花园"),
        domains=("u2.dmhy.org", "dmhy.best"), tags=("中文", "动漫"),
        notes="重度魔改 NP — 部分选择器与标准不同"),
    _np("ubits", "你堡 (UBits)", aliases=("UBits", "ub", "你堡"),
        domains=("ubits.club",)),
    _np("ultrahd", "UltraHD", aliases=("UltraHD",),
        domains=("ultrahd.net",)),
    _np("uploads", "Uploads (LTD)", aliases=("Uploads", "LTD"),
        domains=("uploads.ltd",)),
    _np("wintersakura", "冬樱 (WinterSakura)", aliases=("WinterSakura", "wtsakura", "冬樱"),
        domains=("wintersakura.net",)),
    _np("wukongwendao", "悟空问道 (WuKong)", aliases=("WuKong", "悟空问道"),
        domains=("wukongwendao.top",)),
    _np("xingyunge", "星陨阁 (XingYunGe)", aliases=("XingYunGe", "星陨阁"),
        domains=("pt.xingyungept.org",)),
    _np("xingtan", "杏坛 (XingTan)", aliases=("XingTan", "Xinglin", "杏林"),
        domains=("xingtan.one", "xinglin.one")),
    _np("zmpt", "织梦 (ZmPT)", aliases=("ZmPT", "织梦"),
        domains=("zmpt.cc",)),
    _np("zrpt", "自然 (ZRPT)", aliases=("ZRPT", "自然"),
        domains=("zrpt.cc",)),

    # ---- 学校/机构 NP (PTPP 目录补充) ----
    _np("bitpt", "BitPT", aliases=("BitPT",),
        domains=("bitpt.cn",)),
    _np("nanyangpt", "南洋 (NanyangPT)", aliases=("NanyangPT", "南洋"),
        domains=("nanyangpt.com",), tags=("中文", "综合", "学校"),
        notes="上海交通大学闵行校区"),
    _np("neubt", "NEUBT", aliases=("NEUBT",),
        domains=("bt.neu6.edu.cn",), tags=("中文", "综合", "学校"),
        notes="东北大学 PT"),
    _np("npupt", "浦园 (NPUPT)", aliases=("NPUPT", "浦园"),
        domains=("npupt.com",), tags=("中文", "综合", "学校"),
        notes="南京邮电大学"),
    _np("pthdbd", "BD之家 (HDBD)", aliases=("HDBD",),
        domains=("pt.hdbd.us",)),
    _np("sjtupt", "PT @ SJTU", aliases=("SJTUPT",),
        domains=("pt.sjtu.edu.cn",), tags=("中文", "综合", "学校"),
        notes="上海交通大学 PT"),
    _np("xidian", "PT @ 西电", aliases=("XiDian", "XDPT"),
        domains=("resource.xidian.edu.cn",), tags=("中文", "综合", "学校"),
        notes="西安电子科技大学 PT"),
    _np("xauat", "PT @ 西安建大", aliases=("XAUAT", "xauatpt"),
        domains=("pt.xauat6.edu.cn",), tags=("中文", "综合", "学校"),
        notes="西安建筑科技大学 PT"),
    _np("bjtupt", "PT @ 北交大", aliases=("BJTUPT", "智行"),
        domains=("pt.zhixing.bjtu.edu.cn",), tags=("中文", "综合", "学校"),
        notes="北京交通大学 PT"),
    _np("newworld", "新世界 (NewWorld)", aliases=("NewWorld", "新世界"),
        domains=("pt.newworld.plus",)),

    # ======================================================================
    #                       Discuz 论坛型 PT
    # ======================================================================
    SiteDefinition(
        id="skyeysnow",
        name="天雪 (SkyeySnow)",
        aliases=("SkyeySnow", "天雪"),
        domains=("skyeysnow.com", "skyey.win", "skyey2.com"),
        schema="discuz",
        tags=("中文", "综合"),
        notes="Discuz 论坛型",
    ),

    # ======================================================================
    #                       TNode
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
        aliases=("Monika", "莫妮卡"),
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
    SiteDefinition(
        id="beyondhd",
        name="BHD (Beyond-HD)",
        aliases=("BHD", "Beyond-HD", "beyondhd"),
        domains=("beyond-hd.me",),
        schema="unit3d",
        tags=("English", "综合", "高清"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="jptvts",
        name="JPTV.ts",
        aliases=("JPTVTS",),
        domains=("jptvts.us",),
        schema="unit3d",
        tags=("English", "日剧"),
        registration_path="register",
        invite_path="invites",
        notes="JPTV 镜像",
    ),
    SiteDefinition(
        id="asiancinema",
        name="AsianCinema",
        aliases=("AC", "asiancinema"),
        domains=("asiancinema.me",),
        schema="unit3d",
        tags=("English", "亚洲影视"),
        registration_path="register",
        invite_path="invites",
    ),
    SiteDefinition(
        id="hawke",
        name="Hawke.uno",
        aliases=("Hawke",),
        domains=("hawke.uno",),
        schema="unit3d",
        tags=("English", "亚洲影视"),
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
        domains=("dicmusic.com", "dicmusic.club", "52dic.vip"),
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

    # ---- 国外主流 Gazelle 生态 (PT-Plugin-Plus 收录) ----
    SiteDefinition(
        id="ptp",
        name="PTP (PassThePopcorn)",
        aliases=("PTP", "PassThePopcorn"),
        domains=("passthepopcorn.me",),
        schema="gazelle",
        tags=("English", "电影"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
        notes="国际权威电影站 (Gazelle 变种)",
    ),
    SiteDefinition(
        id="btn",
        name="BTN (BroadcastTheNet)",
        aliases=("BTN", "BroadcastTheNet"),
        domains=("broadcasthe.net",),
        schema="gazelle",
        tags=("English", "电视剧"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
        notes="国际权威电视剧站 (Gazelle 变种)",
    ),
    SiteDefinition(
        id="ggn",
        name="GGn (GazelleGames)",
        aliases=("GGn", "GazelleGames"),
        domains=("gazellegames.net",),
        schema="gazelle",
        tags=("English", "游戏"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="bib",
        name="BiB (BaconBits)",
        aliases=("BiB", "BaconBits"),
        domains=("baconbits.org",),
        schema="gazelle",
        tags=("English", "综合"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="bibliotik",
        name="Bibliotik",
        aliases=("Bibliotik",),
        domains=("bibliotik.me",),
        schema="gazelle",
        tags=("English", "电子书"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="brokenstones",
        name="BS (BrokenStones)",
        aliases=("BS", "BrokenStones"),
        domains=("brokenstones.is",),
        schema="gazelle",
        tags=("English", "Mac/软件"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="anthelion",
        name="ANT (Anthelion)",
        aliases=("ANT", "Anthelion"),
        domains=("anthelion.me",),
        schema="gazelle",
        tags=("English", "电影"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="nebulance",
        name="NBL (Nebulance)",
        aliases=("NBL", "Nebulance"),
        domains=("nebulance.io",),
        schema="gazelle",
        tags=("English", "电视剧"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="alpharatio",
        name="AR (AlphaRatio)",
        aliases=("AR", "AlphaRatio"),
        domains=("alpharatio.cc",),
        schema="gazelle",
        tags=("English", "综合"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="animebytes",
        name="AB (AnimeBytes)",
        aliases=("AB", "AnimeBytes"),
        domains=("animebytes.tv",),
        schema="gazelle",
        tags=("English", "动漫"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
        notes="动漫/J-音乐权威站",
    ),
    SiteDefinition(
        id="sugoimusic",
        name="SM (SugoiMusic)",
        aliases=("SM", "SugoiMusic"),
        domains=("sugoimusic.me",),
        schema="gazelle",
        tags=("English", "音乐", "日系"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="thegeeks",
        name="TG (TheGeeks)",
        aliases=("TG", "TheGeeks"),
        domains=("thegeeks.click",),
        schema="gazelle",
        tags=("English", "纪录片"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="concertos",
        name="Concertos",
        aliases=("Concertos",),
        domains=("concertos.live",),
        schema="gazelle",
        tags=("English", "现场音乐"),
        registration_path="register.php",
        invite_path="user.php?action=invite",
    ),
    SiteDefinition(
        id="karagarga",
        name="KG (Karagarga)",
        aliases=("KG", "Karagarga"),
        domains=("karagarga.in",),
        schema="gazelle",
        tags=("English", "纪录片"),
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
