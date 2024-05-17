import asyncio
import itertools
import logging
import math
from typing import Any, Callable, Dict, Iterable, List, Optional, TypeVar

import discord
from discord.ext import tasks
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .models import GiveawayObj, GiveawaySettings, GiveawayView
from .utils import EmojiConverter, TimeConverter

guild_defaults = {
    "giveaways": [],
    "giveaway_settings": {"notify_users": True, "emoji": "\U0001f389"},
}
log = logging.getLogger("red.craycogs.Giveaway.giveaways")

_T = TypeVar("_T")

Missing = object()


def all_min(
    iterable: Iterable[_T],
    key: Callable[[_T], Any] = lambda x: x,
    *,
    sortkey: Optional[Callable[[_T], Any]] = Missing,
):
    """A simple one liner function that returns all the least elements of an iterable instead of just one like the builtin `min()`.

    !!!!!! SORT THE DATA PRIOR TO USING THIS FUNCTION !!!!!!
    or pass the `sortkey` argument to this function which will be passed to the `sorted()` builtin to sort the iterable

    A small explanation of what it does from bard:
    - itertools.groupby() groups the elements in the iterable by their key value.
    - map() applies the function lambda x: (x[0], list(x[1])) to each group.
      This function returns a tuple containing the key of the group and a list of all of the elements in the group.
    - min() returns the tuple with the minimum key value.
    - [1] gets the second element of the tuple, which is the list of all of the minimum elements in the iterable.
    """
    if sortkey is not Missing:
        iterable = sorted(iterable, key=sortkey)
    try:
        return min(
            map(lambda x: (x[0], list(x[1])), itertools.groupby(iterable, key=key)),
            key=lambda x: x[0],
        )[1]

    except ValueError:
        return []


class Giveaway(commands.Cog):
    """Start rigged giveaways that anyone can join!"""

    __author__ = ["crayyy_zee"]
    __version__ = "1.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, 1, True)
        self.config.register_guild(**guild_defaults)
        self.config.register_global(
            max_duration=3600 * 12
        )  # a day long duration by default

        self.cache: Dict[int, List[GiveawayObj]] = {}

        self.task = self.end_giveaway.start()
        self.to_end: List[GiveawayObj] = []
        self.view = GiveawayView(self)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        for giveaways in self.cache.values():
            for giveaway in giveaways:
                if giveaway._host == user_id:
                    await giveaway.end()
                    await self.remove_giveaway(giveaway)

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    async def cog_load(self):
        guilds = await self.config.all_guilds()

        for guild_data in guilds.values():
            for x in guild_data.get("giveaways", []):
                x.update({"bot": self.bot})
                giveaway = GiveawayObj.from_json(x)
                await self.add_giveaway(giveaway)

        self.max_duration: int = await self.config.max_duration()
        self.bot.add_view(self.view)
        if self.bot.get_cog("Dev"):
            self.bot.add_dev_env_value("giveaway", lambda x: self)

    async def get_giveaway(self, guild_id: int, giveaway_id: int):
        if not (guild := self.cache.get(guild_id)):
            return None

        for giveaway in guild:
            if giveaway.message_id == giveaway_id:
                return giveaway

    async def add_giveaway(self, giveaway: GiveawayObj):
        if await self.get_giveaway(giveaway.guild_id, giveaway.message_id):
            return
        self.cache.setdefault(giveaway.guild_id, []).append(giveaway)

    async def remove_giveaway(self, giveaway: GiveawayObj):
        if not (guild := self.cache.get(giveaway.guild_id)):
            return
        self.cache[giveaway.guild_id].remove(giveaway)

    async def get_guild_settings(self, guild_id: int):
        return GiveawaySettings(
            **await self.config.guild_from_id(guild_id).giveaway_settings()
        )

    async def _back_to_config(self):
        for guild_id, giveaways in self.cache.items():
            await self.config.guild_from_id(guild_id).giveaways.set(
                [x.json for x in giveaways]
            )

    async def cog_unload(self):
        self.task.cancel()
        self.view.stop()
        self.bot.remove_dev_env_value("giveaway")
        await self._back_to_config()

    @tasks.loop(seconds=1)
    async def end_giveaway(self):
        if (
            self.end_giveaway._current_loop
            and self.end_giveaway._current_loop % 100 == 0
        ):
            await self._back_to_config()

        results = await asyncio.gather(
            *[giveaway.end() for giveaway in self.to_end], return_exceptions=True
        )

        for result in results:
            if isinstance(result, Exception):
                log.error(f"A giveaway ended with an error:", exc_info=result)

        self.to_end = all_min(
            itertools.chain.from_iterable(self.cache.values()),
            key=lambda x: math.ceil(x.remaining_time),
            sortkey=lambda x: math.ceil(x.remaining_time),
        )
        if not self.to_end:
            log.debug("No giveaways to end, stopping task.")
            return self.end_giveaway.stop()

        interval = max(
            math.ceil(getattr(next(iter(self.to_end), None), "remaining_time", 1)), 1
        )
        self.end_giveaway.change_interval(seconds=interval)
        log.debug(f"Changed interval to {interval} seconds")

    @commands.group(name="giveaway")
    @commands.mod_or_permissions(manage_messages=True)
    async def giveaway(self, ctx: commands.Context):
        """
        Manage Giveaways."""

    @giveaway.command(name="start", usage="<time> [name]")
    @commands.bot_has_permissions(embed_links=True)
    async def giveaway_start(
        self,
        ctx: commands.Context,
        time: TimeConverter,
        winner: Optional[discord.User] = None,
        *,
        name: str = "New Giveaway!",
    ):
        """
        Start a giveaway.

        `time`: The duration to start the giveaway. The duration uses basic time units
                `s` (seconds), `m` (minutes), `h` (hours), `d` (days), `w` (weeks)
                The maximum duration is 12 hours. change that with `giveawayset maxduration`.

        `name`: The name of the giveaway.
        """

        giveaway = GiveawayObj(
            **{
                "message_id": None,
                "channel_id": ctx.channel.id,
                "guild_id": ctx.guild.id,
                "bot": ctx.bot,
                "name": name,
                "emoji": (await self.get_guild_settings(ctx.guild.id)).emoji,
                "host": ctx.author.id,
                "ends_at": time,
                "winner": getattr(winner, "id", None),
            }
        )

        await giveaway.start()
        await ctx.tick(message="Giveaway for `{}` started!".format(name))

        self.to_end.clear()
        if self.end_giveaway.is_running():
            self.end_giveaway.restart()
        else:
            self.end_giveaway.start()
        self.task = self.end_giveaway.get_task()

    @giveaway.command(name="end")
    async def giveaway_end(self, ctx: commands.Context, giveaway_id: int):
        """
        End a giveaway.

        `giveaway_id`: The `msg-ID` of the giveaway to end.
        """

        giveaway = await self.get_giveaway(ctx.guild.id, giveaway_id)

        if giveaway is None:
            await ctx.send("Giveaway not found.")
            return

        await giveaway.end()
        await ctx.tick(message="Giveaway ended!")

        self.to_end.clear()
        if self.end_giveaway.is_running():
            self.end_giveaway.restart()
        else:
            self.end_giveaway.start()
        self.task = self.end_giveaway.get_task()

    @giveaway.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def giveaway_list(self, ctx: commands.Context):
        """
        Get a list of all the active giveaways in this server."""
        if not self.cache.get(ctx.guild.id):
            await ctx.send("No giveaways found.")
            return

        embed = discord.Embed(
            title="Giveaways in **{}**".format(ctx.guild.name),
            description="\n".join(
                "{} - {}".format(
                    f"[{x.name}]({x.jump_url})",
                    cf.humanize_timedelta(timedelta=x.remaining_seconds),
                )
                for x in self.cache[ctx.guild.id]
            ),
            color=await ctx.embed_color(),
        )
        await ctx.send(embed=embed)

    @commands.group(name="giveawayset", aliases=["gset", "giveawaysettings"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def gset(self, ctx: commands.Context):
        """
        Customize settings for giveaways."""

    @gset.command(name="emoji")
    async def gset_emoji(self, ctx: commands.Context, emoji: EmojiConverter):
        """
        Change the emoji used for giveaways.

        `emoji`: The emoji to use.
        """

        await self.config.guild_from_id(ctx.guild.id).giveaway_settings.emoji.set(emoji)
        await ctx.tick()

    @gset.command(name="maxduration", aliases=["duration", "md"])
    @commands.is_owner()
    async def gset_duration(self, ctx: commands.Context, duration: TimeConverter[True]):
        """
        Change the max duration for giveaways.

        `duration`: The duration to set.
        """

        await self.config.max_duration.set(duration.total_seconds())
        await ctx.tick()

    @gset.command(name="notifyusers", aliases=["notify"])
    async def gset_notify(self, ctx: commands.Context, notify: bool):
        """
        Toggle whether or not to notify users when a giveaway ends.

        `notify`: Whether or not to notify users. (`True`/`False`)
        """

        await self.config.guild_from_id(
            ctx.guild.id
        ).giveaway_settings.notify_users.set(notify)
        await ctx.tick()

    @gset.command(name="showsettings", aliases=["ss", "showsetting", "show"])
    async def gset_showsettings(self, ctx: commands.Context):
        """
        See the configured settings for giveaways in your server."""
        settings = await self.get_guild_settings(ctx.guild.id)
        embed = discord.Embed(
            title=f"Giveaway Settings for **{ctx.guild.name}**",
            description=f"Emoji: `{settings.emoji}`\n"
            f"Notify users: `{settings.notify_users}`"
            + (
                f"\nMax duration: `{cf.humanize_timedelta(seconds=await self.config.max_duration())}`"
                if await ctx.bot.is_owner(ctx.author)
                else ""
            ),
        )

        await ctx.send(embed=embed)
