from datetime import datetime
import discord
from discord.ext import tasks
from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf, menus
import pytz
from fuzzywuzzy import fuzz, process
from typing import Iterable, TypeVar, Callable, Any, Optional
import itertools
import operator

_T = TypeVar("_T")


def all_min(
    iterable: Iterable[_T],
    key: Callable[[_T], Any] = lambda x: x,
    *,
    sortkey: Optional[Callable[[_T], Any]] = None,
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
    if sortkey:
        iterable = sorted(iterable, key=sortkey)
    return min(
        map(lambda x: (x[0], list(x[1])), itertools.groupby(iterable, key=key)),
        key=lambda x: x[0],
    )[1]


class ChannelTimezone(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_channel(timezone=None, message_id=None)
        self.config.register_user(stats={})

        self.tztask = self.tzloop.start()
        self.next_to_edit: dict[int, dict[str, str | int]] = {}
        """A dict with keys as channel ids where the timezone message is to be update in the next iteration of the task loop."""

    # <=================================
    # <=================================
    # Code Stolen From Aikaterna => https://github.com/MelonBot-Development/aikaterna-cogs/blob/76994e66736818d4e66ffc0149abd1f37ed78177/timezone/timezone.py#L27C5-L67C24
    # <=================================
    # <=================================

    async def cog_unload(self):
        self.tztask.cancel()

    async def get_usertime(self, user: discord.User):
        tz = None
        usertime = await self.config.user(user).usertime()
        if usertime:
            tz = pytz.timezone(usertime)

        return usertime, tz

    def fuzzy_timezone_search(self, tz: str):
        fuzzy_results = process.extract(
            tz.replace(" ", "_"), pytz.common_timezones, limit=500, scorer=fuzz.partial_ratio
        )
        matches = [x for x in fuzzy_results if x[1] > 98]
        return matches

    async def format_results(self, ctx: commands.Context, tz):
        if not tz:
            await ctx.send(
                "Error: Incorrect format or no matching timezones found.\n"
                "Use: **Continent/City** with correct capitals or a partial timezone name to search. "
                "e.g. `America/New_York` or `New York`\nSee the full list of supported timezones here:\n"
                "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>"
            )
            return None
        elif len(tz) == 1:
            # command specific response, so don't do anything here
            return tz
        else:
            msg = ""
            for timezone in tz:
                msg += f"{timezone[0]}\n"

            embed_list = []
            for page in cf.pagify(msg, delims=["\n"], page_length=500):
                e = discord.Embed(
                    title=f"{len(tz)} results, please be more specific.", description=page
                )
                e.set_footer(text="https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
                embed_list.append(e)
            if len(embed_list) == 1:
                close_control = {"\N{CROSS MARK}": menus.close_menu}
                await menus.menu(ctx, embed_list, close_control)
            else:
                await menus.menu(ctx, embed_list, menus.DEFAULT_CONTROLS)
            return None

    # <=================================
    # <=================================
    # End of Code Stolen From Aikaterna
    # <=================================
    # <=================================

    @commands.group(name="timezone", aliases=["tz"], invoke_without_command=True)
    async def tz(self, ctx: commands.Context):
        return await ctx.send_help()

    @tz.command(name="set")
    async def tz_set(
        self,
        ctx: commands.GuildContext,
        channel: discord.TextChannel = commands.parameter(
            converter=Optional[discord.TextChannel],
            default=operator.attrgetter("channel"),
            displayed_default="<this channel>",
        ),
        *,
        timezone: str,
    ):
        """Set the timezone for the channel"""
        if await self.config.channel(channel).timezone():
            return await ctx.send(
                f"Channel already has a timezone set. Use `{ctx.clean_prefix}mcm tz remove` to remove it."
            )
        timezone = timezone.replace(" ", "_")
        res = self.fuzzy_timezone_search(timezone)
        tz = await self.format_results(ctx, res)
        if not tz:
            return
        tz = pytz.timezone(tz[0][0])
        message = await channel.send(
            f"The time in {tz.zone} is {datetime.now(tz).strftime('%H:%M')}. Last update: <t:{int(datetime.now(tz).timestamp())}:R>"
        )
        await message.pin()
        await self.config.channel(channel).set({"timezone": tz.zone, "message_id": message.id})
        await ctx.send(f"Set the timezone for {channel.mention} to {tz}", delete_after=10)

        self.next_to_edit.clear()
        self.tzloop.restart()
        self.tztask = self.tzloop.get_task()

    @tz.command(name="remove")
    async def tz_remove(
        self,
        ctx: commands.GuildContext,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """Remove the timezone for the channel"""
        msg = await self.config.channel(channel).message_id()
        try:
            msg = await commands.MessageConverter().convert(ctx, str(msg))
        except commands.BadArgument:
            pass
        else:
            await msg.delete()
        await self.config.channel(channel).clear()
        await ctx.send(f"Removed the timezone for {channel.mention}")

        self.next_to_edit.clear()
        self.tzloop.restart()
        self.tztask = self.tzloop.get_task()

    @tz.command(name="clear")
    async def tz_clear(self, ctx: commands.GuildContext):
        """Clear all channel timezones"""
        await self.config.clear_all_channels()
        await ctx.send("Cleared all channel timezones")

        self.next_to_edit.clear()
        self.tzloop.restart()
        self.tztask = self.tzloop.get_task()

    @tasks.loop(seconds=1)
    async def tzloop(self):
        # we have to iterate over self.next_to_edit and edit each message one by one, the messages are to be update only when the time in teh timezone raached half or full hour.

        for channel_id, data in self.next_to_edit.items():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                await self.config.channel_from_id(channel_id).clear()
                continue
            message_id = int(data["message_id"])
            tz = pytz.timezone(data["timezone"])
            now = datetime.now(tz)
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                message = await channel.send(
                    f"The time in {tz.zone} is {datetime.now(tz).strftime('%H:%M')}. Last update: <t:{int(now.timestamp())}:R>"
                )
                await message.pin(reason="Timezone message")
                await self.config.channel(channel).message_id.set(message.id)
            else:
                await message.edit(
                    content=f"The time in {tz.zone} is {datetime.now(tz).strftime('%H:%M')}. Last update: <t:{int(now.timestamp())}:R>"
                )

        else:
            self.next_to_edit.clear()

        def distance_to_hour(x):
            dt = datetime.now(pytz.timezone(x[1]["timezone"]))
            res = 30 - dt.minute if dt.minute < 30 else 60 - dt.minute
            return res

        all_chans: dict[int, dict[str, str | int]] = await self.config.all_channels()

        closest = all_min(all_chans.items(), key=distance_to_hour, sortkey=distance_to_hour)

        self.next_to_edit = timestamps = dict(
            map(
                lambda x: (
                    x[0],
                    {**x[1], "datetime": datetime.now(pytz.timezone(x[1]["timezone"]))},
                ),
                all_min(
                    all_chans.items(),
                    key=distance_to_hour,
                ),
            )
        )

        diff = distance_to_hour(next(iter(timestamps.items())))
        self.tzloop.change_interval(minutes=diff)
