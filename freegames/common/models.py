import contextlib
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
        normalized_list = [
            (
                x.lower()
                .strip()
                .replace("playstation ", "ps")
                .replace("|", "")
                .replace(".", "")
                .replace("nintendo ", "")
                .replace(" ", "-")
            )
            for x in v.split(",")
        ]
        with contextlib.suppress(ValueError):
            normalized_list.remove("pc")
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
    client: typing.Optional[str]
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
    epic_games_store = epic = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Epic_Games_logo.svg/120px-Epic_Games_logo.svg.png"
    )
    ubisoft = uplay = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Ubisoft_logo.svg/250px-Ubisoft_logo.svg.png"
    )
    gog = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2e/GOG.com_logo.svg/75px-GOG.com_logo.svg.png"
    itchio = itch = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Itch.io_logo.svg/250px-Itch.io_logo.svg.png"
    )
    ps4 = ps5 = ps = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5c/PlayStation_logo_and_wordmark.svg/250px-PlayStation_logo_and_wordmark.svg.png"
    )
    switch = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f0/Nintendo_Switch_logo.svg/250px-Nintendo_Switch_logo.svg.png"
    android = google = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a4/Android_2023_3D_logo_and_wordmark.svg/330px-Android_2023_3D_logo_and_wordmark.svg.png"
    )
    ios = apple = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/Apple_logo_black.svg/120px-Apple_logo_black.svg.png"
    )
    vr = "https://i.fbcd.co/products/resized/resized-750-500/bdd43339451c69679f9199209f394e9b1273d6cdd0ebb7488715918781ac5b32.webp"
    battlenet = "https://upload.wikimedia.org/wikipedia/en/thumb/a/a8/Battlenet-logo.png/250px-Battlenet-logo.png"
    origin = "https://cdn.worldvectorlogo.com/logos/origin-4.svg"
    drm_free = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/DRM-free.svg/600px-DRM-free.svg.png"
    xbox_360 = xbox = xbox_one = xbox_series_xs = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/Xbox_logo_%282019%29.svg/250px-Xbox_logo_%282019%29.svg.png"
    )

    humble = "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0c/Humble_Bundle_logo.svg/250px-Humble_Bundle_logo.svg.png"
    twitch = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ce/Twitch_logo_2019.svg/330px-Twitch_logo_2019.svg.png"
    discord = "https://upload.wikimedia.org/wikipedia/en/thumb/9/98/Discord_logo.svg/330px-Discord_logo.svg.png"
    other = ""

    def __str__(self):
        return self.value
