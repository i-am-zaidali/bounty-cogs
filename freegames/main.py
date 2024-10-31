import asyncio
import datetime
import itertools
import json
import logging
import typing as t

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import (
    DB,
    FreeStuffGameInfo,
    FreeStuffResponse,
    GamerPowerGiveaway,
    GamerPowerResponse,
    StoreLogos,
)

log = logging.getLogger("red.craycogs.freegames")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]

T = t.TypeVar("T")


def chunks(iterable: t.Iterable[T], n: int):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        yield batch


class FreeGames(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """
    Sources updates on freely available games on popular stores such as epic and steam.

    Uses two APIs: [GamerPower](https://www.gamerpower.com/) (FREE) and [FreeStuffBot](https://docs.freestuffbot.xyz/) (PAID, requires API key).

    To set the API key for FreeStuffBot API, use `[p]set api freestuff api_key,<your_key>`."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False

        self.session = aiohttp.ClientSession()
        self.post_task = self.check_for_freegames.start()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(
            self.__version__, self.__author__
        )
        return f"{helpcmd}\n\n{txt}"

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            dump = await asyncio.to_thread(self.db.model_dump, mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    async def cog_unload(self) -> None:
        await self.save()
        self.post_task.cancel()
        await self.session.close()

    async def fetch_gamerpower_games(self, platforms=[], exclude_ids=[]):
        if platforms:
            url = "https://www.gamerpower.com/api/filter"
            params = {"platform": ".".join(platforms), "type": "game.beta"}
        else:
            url = "https://www.gamerpower.com/api/filter"
            params = {"type": "game.beta"}

        async with self.session.get(url, params=params) as resp:
            if resp.status not in [200, 201]:
                log.error(
                    "Failed to fetch gamerpower games: %s", await resp.json()
                )
                return
            data = await resp.json()
            return GamerPowerResponse(
                giveaways=filter(lambda x: x["id"] not in exclude_ids, data)
            )

    async def fetch_freestuff_games(self, platforms=[], exclude_ids=[]):
        baseurl = "https://api.freestuffbot.xyz/v1"
        headers = {
            "Authorization": f"Basic {(await self.bot.get_shared_api_tokens('freestuff')).get('api_key')}"
        }
        while True:
            async with self.session.get(
                baseurl + "/games/free", headers=headers
            ) as resp:
                rl_keys = [
                    "x-ratelimit-remaining",
                    "x-ratelimit-reset",
                    "x-ratelimit-limit",
                    "retry-after",
                ]
                ratelimit: dict[str, int] = {
                    k: resp.headers.get(k, 0) for k in rl_keys
                }
                if resp.status == 429:
                    log.warning("Ratelimited: %s", ratelimit)
                    await asyncio.sleep(int(ratelimit["retry-after"]))
                    continue
                elif resp.status not in [200, 201]:
                    log.error(
                        "Failed to fetch freestuff games: %s", await resp.json()
                    )
                    return
                data: dict[str, list[int]] = await resp.json()

                results = []
                for chunk in chunks(
                    filter(lambda x: x not in exclude_ids, data["data"]), 5
                ):
                    ids = "+".join(map(str, chunk))
                    async with self.session.get(
                        baseurl + f"/game/{ids}/info", headers=headers
                    ) as resp2:
                        if resp2.status not in [200, 201]:
                            log.error(
                                "Failed to fetch freestuff game: %s",
                                await resp2.json(),
                            )
                            continue

                        json = await resp2.json()
                        results.extend(json["data"].values())
                try:
                    return FreeStuffResponse(
                    games=filter(
                        lambda x: x
                        and (x["store"] in platforms if platforms else True),
                        results,
                    )
                )
                except Exception as e:
                    log.exception("Malformed data recieved frkm the FreeStuffBot API", exc_info=e)
                    log.exception("%s", json.dumps(indent =4))
                    return None

    @tasks.loop(
        time=[
            datetime.time(
                hour=i, minute=0, second=0, tzinfo=datetime.timezone.utc
            )
            for i in range(0, 24, 4)
        ]
    )
    async def check_for_freegames(self, save_after=True):
        for guildid, conf in self.db.configs.items():
            guild = self.bot.get_guild(guildid)
            fs = conf.freestuff
            gp = conf.gamerpower
            pings = " ".join(
                itertools.chain(
                    (f"<@&{x}>" for x in conf.pingroles),
                    (f"<@{x}>" for x in conf.pingusers),
                )
            )
            if fs.toggle:
                channel = guild.get_channel(fs.channel)
                if not channel:
                    fs.toggle = False
                    log.info(
                        "Channel not found, disabling freestuff for guild %s",
                        guild,
                    )
                    continue

                exclude_ids = fs.posted_ids
                platforms = fs.stores_to_check
                data = await self.fetch_freestuff_games(platforms, exclude_ids)
                if not data:
                    continue

                for game in data.games:
                    embed, view = self.generate_freestuff_embed_view(game)
                    await channel.send(
                        pings,
                        embed=embed,
                        view=view,
                        allowed_mentions=discord.AllowedMentions.all(),
                    )

                fs.posted_ids.update((x.id for x in data.games))

            if gp.toggle:
                channel = guild.get_channel(gp.channel)
                if not channel:
                    gp.toggle = False
                    log.info(
                        "Channel not found, disabling gamerpower for guild %s",
                        guild,
                    )
                    continue

                exclude_ids = gp.posted_ids
                platforms = gp.stores_to_check
                data = await self.fetch_gamerpower_games(platforms, exclude_ids)
                if not data:
                    continue

                for game in data.giveaways:
                    embed, view = self.generate_gamerpower_embed_view(game)
                    await channel.send(
                        pings,
                        embed=embed,
                        view=view,
                        allowed_mentions=discord.AllowedMentions.all(),
                    )

                gp.posted_ids.update((x.id for x in data.giveaways))

        if save_after:
            await self.save()

    @check_for_freegames.before_loop
    async def before_check_for_freegames(self):
        await self.bot.wait_until_red_ready()

    @check_for_freegames.error
    async def error_handler(self, exc: BaseException):
        log.error("Error in check_for_freegames", exc_info=exc)

    def generate_freestuff_embed_view(self, data: FreeStuffGameInfo):
        embed = (
            discord.Embed(
                title=data.title,
                description=(
                    cf.quote(data.description)
                    + f"\n{cf.strikethrough(f'{data.org_price.usd} USD')} "
                    f"Free {f'until <t:{data.until}:F>' if data.until else '**FOREVER** :tada:'}\n"
                    f"{f'Rating: {data.rating:.0%}' if data.rating else ''}"
                ),
                color=discord.Color.random(),
            )
            .set_footer(text=f"via freestuffbot.xyz\n©️ {data.copyright}")
            .set_image(url=data.thumbnail.full)
            .set_thumbnail(url=StoreLogos._member_map_[data.store])
        )
        view = (
            discord.ui.View()
            .add_item(
                discord.ui.Button(
                    label="Open in browser", url=data.urls.browser
                )
            )
            .add_item(
                discord.ui.Button(
                    label=f"Open in {data.store.title()}", url=data.urls.client
                )
            )
        )
        return embed, view

    def generate_gamerpower_embed_view(self, data: GamerPowerGiveaway):
        embed = (
            discord.Embed(
                title=data.title,
                description=(
                    cf.quote(data.description)
                    + f"\n{cf.strikethrough(f'{data.worth_currency}{data.worth}') if data.worth else '-# Price not available'}\n"
                    f"Free {f'until <t:{int(data.end_date.timestamp())}:F>' if data.end_date else '**FOREVER** :tada:'}\n"
                    f"Current users: {data.users} users\n\n"
                    f"Published on: <t:{int(data.published_date.timestamp())}:F>\n"
                ),
                color=discord.Color.random(),
            )
            .set_footer(text="via gamerpower.com")
            .set_image(url=data.image)
            .set_thumbnail(
                url=StoreLogos._member_map_.get(
                    next(iter(data.platforms), "").replace("-", "_"),
                    data.thumbnail,
                )
            )
            .add_field(
                name="Instructions:",
                value=cf.quote(data.instructions),
                inline=False,
            )
            .add_field(
                name="Platforms",
                value=cf.humanize_list(
                    [x.replace("-", " ").capitalize() for x in data.platforms]
                ),
            )
        )

        view = (
            discord.ui.View()
            .add_item(
                discord.ui.Button(
                    label="GamerPower Link", url=data.gamerpower_url
                )
            )
            .add_item(
                discord.ui.Button(
                    label="Direct URL", url=data.open_giveaway_url
                )
            )
        )

        return embed, view
