import datetime
import enum
import typing

import discord
import pydantic

from . import Base

GuildMessageable = typing.Union[
    discord.TextChannel, discord.VoiceChannel, discord.Thread
]


GamerPowerStores = typing.Literal[
    "steam",
    "epic-games-store",
    "ubisoft",
    "gog",
    "itchio",
    "ps4",
    "ps5",
    "xbox-one",
    "xbox-series-xs",
    "switch",
    "android",
    "ios",
    "vr",
    "battlenet",
    "origin",
    "drm-free",
    "xbox-360",
]
FreeStuffStores = typing.Literal[
    "steam",
    "epic",
    "humble",
    "gog",
    "origin",
    "uplay",
    "twitch",
    "itch",
    "discord",
    "apple",
    "google",
    "switch",
    "ps",
    "xbox",
    "other",
]


class ServiceConfig(Base):
    toggle: bool = False
    channel: int | None = None
    stores_to_check: typing.Set[str]
    posted_ids: typing.Set[int] = pydantic.Field(default_factory=set)


class GamerPowerConfig(ServiceConfig):
    stores_to_check: typing.Set[GamerPowerStores] = pydantic.Field(default_factory=set)


class FreeStuffConfig(ServiceConfig):
    stores_to_check: typing.Set[FreeStuffStores] = pydantic.Field(default_factory=set)


class GuildSettings(Base):
    gamerpower: GamerPowerConfig = pydantic.Field(default_factory=GamerPowerConfig)
    freestuff: FreeStuffConfig = pydantic.Field(default_factory=FreeStuffConfig)
    pingroles: typing.Set[int] = pydantic.Field(default_factory=set)
    pingusers: typing.Set[int] = pydantic.Field(default_factory=set)


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())


Status = typing.Literal["Active", "Expired"]
GiveawayType = typing.Literal["DLC", "Game", "Other", "Early Access"]


class GamerPowerGiveaway(Base):
    description: str
    end_date: typing.Optional[datetime.datetime] = None
    gamerpower_url: str
    id: int
    image: str
    instructions: str
    open_giveaway_url: str
    platforms: list[GamerPowerStores]
    published_date: datetime.datetime
    status: Status
    thumbnail: str
    title: str
    type: GiveawayType
    users: int
    worth: typing.Optional[float] = None
    worth_currency: typing.Optional[str] = None

    @pydantic.field_validator("platforms", mode="before")
    @classmethod
    def str_to_list(cls, v: str):
        normalized_list = list(
            map(
                lambda x: x.lower()
                .strip()
                .replace("playstation ", "ps")
                .replace("|", "")
                .replace(".", "")
                .replace("ninetendo ", "")
                .replace(" ", "-"),
                v.split(","),
            )
        )
        try:
            normalized_list.remove("pc")
        except ValueError:
            pass
        return normalized_list

    @pydantic.model_validator(mode="before")
    @classmethod
    def worth_to_int(cls, data: dict[str, typing.Any]):
        v = data.get("worth")
        if v == "N/A":
            data["worth"] = None
            return data
        currency = v[0]
        data["worth"] = float(v[1:])
        data["worth_currency"] = currency
        return data

    @pydantic.field_validator("end_date", mode="before")
    @classmethod
    def end_date_to_datetime(cls, v: str):
        if v == "N/A":
            return None
        return datetime.datetime.fromisoformat(v)


class Urls(Base):
    default: str
    browser: str
    client: str
    org: str


class Price(Base):
    usd: float
    eur: float
    gbp: float
    brl: float
    bgn: float
    pln: float
    huf: float
    btc: float
    euro: float
    dollar: float


class Thumbnail(Base):
    org: str
    blank: str
    full: str
    tags: str


class GameFlags(enum.IntEnum):
    NONE = 0
    TRASH = 1 << 0
    THIRDPARTY = 1 << 1


ProductKind = typing.Literal["game", "dlc", "software", "art", "ost", "book", "other"]
AnnouncementType = typing.Literal["free", "weekend", "discount", "ad", "unknown"]


class FreeStuffGameInfo(Base):
    id: int
    urls: Urls
    title: str
    org_price: Price
    price: Price
    thumbnail: Thumbnail
    kind: ProductKind
    tags: list[str]
    store: FreeStuffStores
    flags: GameFlags
    type: AnnouncementType
    description: str = ""
    rating: float | None = None
    notice: str = ""
    until: int | None = None
    localized: dict[str, dict] = pydantic.Field(default_factory=dict)
    copyright: str | None
    notice: str | None
    platforms: list[str] | None


class GamerPowerResponse(Base):
    giveaways: list[GamerPowerGiveaway]


class FreeStuffResponse(Base):
    games: list[FreeStuffGameInfo]


class StoreLogos(enum.Enum):
    steam = "https://store.steampowered.com/favicon.ico"
    epic_games_store = epic = "https://cdn.brandfetch.io/epicgames.com/w/441/h/512/logo"
    ubisoft = uplay = (
        "https://cdn.brandfetch.io/ubisoft.com/w/493/h/512/theme/light/symbol"
    )
    gog = "https://cdn.brandfetch.io/gogalaxy.com/w/400/h/400"
    itchio = itch = "https://cdn.brandfetch.io/itch.io/w/316/h/316"
    ps4 = ps5 = ps = (
        "https://cdn.brandfetch.io/sonyentertainmentnetwork.com/w/400/h/400"
    )
    switch = "https://cdn.brandfetch.io/nintendo.com/w/400/h/400"
    android = google = "https://cdn.brandfetch.io/android.com/w/512/h/289/symbol"
    ios = apple = "https://cdn.brandfetch.io/apple.com/w/419/h/512/logo"
    vr = "https://designbundles.net/xfankystore/1181849-vr-glasses-icon-logo-virtual-reality-concept-glass"
    battlenet = "https://www.pngegg.com/en/search?q=Battle.net"
    origin = "https://worldvectorlogo.com/logo/origin-4"
    drm_free = "https://en.m.wikipedia.org/wiki/File:DRM-free.svg"
    xbox_360 = xbox = xbox_one = xbox_series_xs = (
        "https://cdn.brandfetch.io/xbox.com/w/512/h/512/symbol"
    )

    humble = "https://cdn.brandfetch.io/humblebundle.com/w/256/h/256"
    twitch = "https://cdn.brandfetch.io/twitch.tv/w/439/h/512/symbol"
    discord = "https://cdn.brandfetch.io/discord.com/w/512/h/397/symbol"
    other = ""

    def __str__(self):
        return self.value
